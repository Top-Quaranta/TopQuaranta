"""Run the social distribution for a given calendar day.

Cron entry-point. Idempotent per (platform, tipus, territori,
setmana) via the SocialPost row. Modes:

  --data YYYY-MM-DD   process a specific date (default: today UTC)
  --tipus T           run only the matching slot (handy for backfills)
  --dry-run           render PNGs but never call the IG API
  --force             ignore existing publicat row + re-publish

The command:
  1. Reads ConfiguracioGlobal.{instagram_actiu, fase_distribucio,
     story_max_cancons_ppcc}.
  2. Walks the calendari for the target weekday.
  3. For each slot whose `min_fase` ≤ current fase, builds payload,
     renders PNGs, uploads + publishes via the IG client.
  4. Updates the SocialPost row + writes a StaffAuditLog entry.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from ingesta.social import calendari, captions, instagram_client, payload, renderer
from ingesta.social.calendari import tq_week_start
from ingesta.social.captions import instagram_username
from music.audit import log_staff_action
from ranking.models import ConfiguracioGlobal
from social.models import SocialPost

logger = logging.getLogger(__name__)

# Stories cap for territorial slots (PPCC is configurable).
STORY_TOP_TERRITORIAL = 5


def _public_url_for(local_path: Path) -> str:
    """Public URL Meta can GET to fetch the rendered PNG.

    Default: a Django endpoint at /api/v1/social/render/<filename>/
    (see web/api/social_public.py). The day we wire a Caddy
    `handle_path /static/social/*` block, flip
    `SOCIAL_PUBLIC_BASE = "https://www.topquaranta.cat/static/social"`
    in settings and the public URL changes without code edits."""
    base = getattr(
        settings,
        "SOCIAL_PUBLIC_BASE",
        "https://www.topquaranta.cat/api/v1/social/render",
    )
    return f"{base.rstrip('/')}/{local_path.name}"


class Command(BaseCommand):
    help = "Publica el contingut social del calendari per al dia indicat."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data",
            type=str,
            default=None,
            help="ISO date (YYYY-MM-DD). Defaults to today.",
        )
        parser.add_argument(
            "--tipus",
            type=str,
            default=None,
            help="Restrict to a single tipus (top_ppcc, "
            "top_territorial, nous_albums, nous_singles).",
        )
        parser.add_argument(
            "--platform",
            type=str,
            default=None,
            help="Restrict to a single platform " "(instagram_feed | instagram_story).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Render the PNGs but never call the IG API.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-render and re-publish even when a " "publicat row already exists.",
        )

    def handle(self, *args, **opts):
        data = opts.get("data")
        target = datetime.date.fromisoformat(data) if data else datetime.date.today()
        cfg = ConfiguracioGlobal.load()
        if not cfg.instagram_actiu and not opts["dry_run"]:
            self.stdout.write("Kill switch actiu (instagram_actiu=False). Surt.")
            return

        slots = calendari.slots_for(target)
        if opts.get("tipus"):
            slots = [(s, t) for (s, t) in slots if s.tipus == opts["tipus"]]
        if opts.get("platform"):
            slots = [(s, t) for (s, t) in slots if s.platform == opts["platform"]]
        if not slots:
            self.stdout.write(f"Cap slot per a {target} (tipus/platform).")
            return

        # `setmana` reference for SocialPost rows = ISO Monday of the
        # *Saturday that opens this TQ-week* (Sat → Fri). Anchoring to
        # the Saturday means Mon/Tue/…/Fri publications all resolve to
        # the same setmana — the same one TopSetmanal computed when
        # the chart was generated on that Saturday. Computing it as
        # `target - target.weekday()` instead would jump to the *next*
        # Monday's ISO week and miss the TopSetmanal row entirely
        # (caught 2026-04-27: territorial slots returned "sense
        # contingut" because they queried the future setmana).
        saturday = tq_week_start(target)
        setmana = saturday - datetime.timedelta(days=saturday.weekday())

        # Stash the resolved publication date so per-slot novetats
        # can compute their window without recomputing from scratch.
        opts["_target_date"] = target
        for slot, territori in slots:
            self._handle_slot(slot, territori, setmana, cfg, opts)

    # ── per-slot dispatch ─────────────────────────────────────────

    # Same map the staff API uses; duplicated here to avoid importing
    # web.api.staff from a management command (cyclic risk).
    _TERRITORI_LABEL = {
        "PPCC": "Global",
        "CAT": "Catalunya",
        "VAL": "País Valencià",
        "BAL": "Illes Balears",
        "AND": "Andorra",
        "CNO": "Catalunya del Nord",
        "FRA": "Franja de Ponent",
        "ALG": "L'Alguer",
        "ALT": "Altres",
        "": "—",
    }

    def _handle_slot(self, slot, territori, setmana, cfg, opts):
        ter_label = self._TERRITORI_LABEL.get(territori, territori or "—")
        label = f"{slot.platform} · {slot.tipus} · {ter_label}"
        # Show the Saturday-of-the-TQ-week (= ISO Monday + 5d), which
        # is what the operator thinks of as "the week of …".
        setmana_dissabte = setmana + datetime.timedelta(days=5)
        self.stdout.write(f"\n[setmana del {setmana_dissabte}] {label}")

        # Phase gate.
        if cfg.fase_distribucio < slot.min_fase:
            self.stdout.write(
                f"  · fase actual {cfg.fase_distribucio} < "
                f"min_fase {slot.min_fase} → omès"
            )
            self._record_omes(slot, territori, setmana, motiu=f"fase < {slot.min_fase}")
            return

        post, _ = SocialPost.objects.get_or_create(
            platform=slot.platform,
            tipus=slot.tipus,
            territori=territori or "",
            setmana=setmana,
            defaults={
                "status": SocialPost.STATUS_PENDENT,
                "scheduled_at": timezone.now(),
            },
        )
        if post.status == SocialPost.STATUS_PUBLICAT and not opts["force"]:
            self.stdout.write("  · ja publicat (--force per re-publicar). Salta.")
            return

        # Build the payload.
        if slot.tipus in (SocialPost.TIPUS_TOP_PPCC, SocialPost.TIPUS_TOP_TERRITORIAL):
            data = payload.build_top(territori, setmana)
        else:
            # Novetats use a publication-date-anchored window so two
            # consecutive runs can't double-count a boundary release.
            publish_date = opts.get("_target_date") or datetime.date.today()
            data = payload.build_novetats(
                slot.tipus, setmana, publish_date=publish_date
            )

        if not data:
            self._mark(
                post,
                SocialPost.STATUS_OMES,
                error_msg="cap contingut per a aquesta setmana",
            )
            self.stdout.write("  · sense contingut → omès")
            return

        try:
            if slot.platform == SocialPost.PLATFORM_INSTAGRAM_FEED:
                self._publish_feed(post, slot, territori, setmana, data, cfg, opts)
            else:
                self._publish_story(post, slot, territori, setmana, data, cfg, opts)
        except Exception as exc:  # noqa: BLE001 — never crash the cron
            logger.exception("publicar_social failed for %s", label)
            self._mark(post, SocialPost.STATUS_ERROR, error_msg=str(exc)[:500])
            # Surface the error in stdout too so the staff cockpit
            # can show it (the panel proxies the captured stdout
            # back to the operator).
            self.stdout.write(f"  · ERROR: {type(exc).__name__}: {exc}")

    # ── feed flow ────────────────────────────────────────────────

    def _publish_feed(self, post, slot, territori, setmana, data, cfg, opts):
        if slot.tipus == SocialPost.TIPUS_TOP_PPCC:
            paths = renderer.render_feed_top(
                "top_ppcc", territori, setmana, data["entries"]
            )
            caption = captions.caption_top(
                "top_ppcc", territori, setmana, data["entries"]
            )
        elif slot.tipus == SocialPost.TIPUS_TOP_TERRITORIAL:
            paths = renderer.render_feed_top(
                "top_territorial", territori, setmana, data["entries"]
            )
            caption = captions.caption_top(
                "top_territorial", territori, setmana, data["entries"]
            )
        else:  # nous_*
            paths = renderer.render_feed_novetats(slot.tipus, setmana, data["items"])
            caption = captions.caption_novetats(slot.tipus, setmana, data["items"])

        self.stdout.write(f"  · renderitzades {len(paths)} slides")

        if opts["dry_run"]:
            self._mark(
                post,
                SocialPost.STATUS_PENDENT,
                metadata={
                    "dry_run": True,
                    "slides": [p.name for p in paths],
                    "caption": caption,
                },
            )
            self.stdout.write("  · --dry-run, no es publica.")
            return

        # Per-slide auto-tags: the cover slide carries no tag; the
        # rest carry the artists whose entries appear on that slide.
        # All tags are placed at (0.5, 0.5) — Meta clusters multiple
        # tags at the same point into a tappable list, so we don't
        # need to spread them across the canvas.
        tags_per_slide = self._slide_tags(slot.tipus, len(paths), data)

        # Real publish: upload each as carousel item, then carousel
        # parent + publish. Single-image fallback when only one
        # slide. Meta processes uploads asynchronously, so each
        # container must reach status_code=FINISHED *before* we hit
        # /media_publish — otherwise the API replies with code 9007
        # / subcode 2207027 ("Media ID is not available").
        urls = [_public_url_for(p) for p in paths]
        if len(urls) == 1:
            container = instagram_client.upload_image(
                urls[0],
                caption,
                user_tags=tags_per_slide[0] or None,
            )
        else:
            child_ids = []
            for i, u in enumerate(urls):
                cid = instagram_client.upload_carousel_item(
                    u,
                    user_tags=tags_per_slide[i] or None,
                )
                instagram_client.wait_until_finished(cid)
                child_ids.append(cid)
            container = instagram_client.create_carousel(child_ids, caption)
        instagram_client.wait_until_finished(container)
        media_id = instagram_client.publish_container(container)
        self._mark(
            post,
            SocialPost.STATUS_PUBLICAT,
            instagram_media_id=media_id,
            metadata={"slides": [p.name for p in paths], "caption_len": len(caption)},
            published_at=timezone.now(),
        )
        log_staff_action(
            None,
            "social_publicat",
            target=post,
            platform=slot.platform,
            tipus=slot.tipus,
        )
        self.stdout.write(f"  · publicat → media_id={media_id}")

    # ── story flow ───────────────────────────────────────────────

    def _publish_story(self, post, slot, territori, setmana, data, cfg, opts):
        if territori == "PPCC":
            max_cancons = max(1, int(cfg.story_max_cancons_ppcc or 40))
        else:
            max_cancons = STORY_TOP_TERRITORIAL

        paths = renderer.render_stories_top(
            slot.tipus,
            territori,
            setmana,
            data["entries"],
            max_cancons=max_cancons,
        )
        self.stdout.write(f"  · renderitzades {len(paths)} stories")

        if opts["dry_run"]:
            self._mark(
                post,
                SocialPost.STATUS_PENDENT,
                metadata={"dry_run": True, "stories": [p.name for p in paths]},
            )
            self.stdout.write("  · --dry-run, no es publica.")
            return

        story_ids: list[str] = []
        for p in paths:
            url = _public_url_for(p)
            container = instagram_client.upload_story(url)
            # Same async-readiness gate as the feed flow above.
            instagram_client.wait_until_finished(container)
            sid = instagram_client.publish_container(container)
            story_ids.append(sid)

        self._mark(
            post,
            SocialPost.STATUS_PUBLICAT,
            instagram_media_id=story_ids[-1] if story_ids else "",
            metadata={
                "stories": [p.name for p in paths],
                "story_ids": story_ids,
                "max_cancons": max_cancons,
            },
            published_at=timezone.now(),
        )
        log_staff_action(
            None,
            "social_publicat",
            target=post,
            platform=slot.platform,
            tipus=slot.tipus,
            n_stories=len(story_ids),
        )
        self.stdout.write(f"  · {len(story_ids)} stories publicades.")

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _slide_tags(tipus: str, n_slides: int, data: dict) -> list[list[dict]]:
        """Per-slide `user_tags` payloads, one entry per slide.

        Slide 0 is always the cover (no tags). The rest mirror the
        renderer's chunking logic so every artist appears on the same
        slide where their entry was drawn:

          • top_*       → 10 entries per slide (uniform)
          • nous_albums → 1 album per slide
          • nous_singles → bin-packed (≤10 per slide, even split)

        All tags are placed at (0.5, 0.5) — Meta clusters multiple
        same-coordinate tags into a single tappable list bubble. We
        don't try to spread them across the canvas because there's
        no meaningful visual position for an artist on a list slide.
        """
        out: list[list[dict]] = [[]]  # cover slide → no tags

        def _tag(handle_url: str | None) -> dict | None:
            u = instagram_username(handle_url)
            return {"username": u, "x": 0.5, "y": 0.5} if u else None

        TOP_TIPUS = (SocialPost.TIPUS_TOP_PPCC, SocialPost.TIPUS_TOP_TERRITORIAL)
        if tipus in TOP_TIPUS:
            entries = data.get("entries") or []
            for page in range(1, n_slides):
                chunk = entries[(page - 1) * 10 : page * 10]
                tags = [t for e in chunk if (t := _tag(e.get("artista_instagram_url")))]
                out.append(tags[:20])  # respect per-image cap
        elif tipus == SocialPost.TIPUS_NOUS_ALBUMS:
            items = data.get("items") or []
            # 1 slide per album (renderer caps at 9; n_slides may be
            # smaller if there are fewer items).
            for item in items[: n_slides - 1]:
                t = _tag(item.get("artista_instagram_url"))
                out.append([t] if t else [])
        elif tipus == SocialPost.TIPUS_NOUS_SINGLES:
            # Mirror the bin-packing in `render_feed_novetats`:
            # `per_slide = ceil(n / n_slides)`. Trailing slide may
            # carry fewer items.
            items = data.get("items") or []
            n = len(items)
            slides = max(1, n_slides - 1)  # exclude cover
            per_slide = -(-n // slides) if n else 0
            offset = 0
            for _ in range(slides):
                chunk = items[offset : offset + per_slide]
                if not chunk:
                    out.append([])
                else:
                    tags = [
                        t for e in chunk if (t := _tag(e.get("artista_instagram_url")))
                    ]
                    out.append(tags[:20])
                offset += per_slide
        # Pad to exactly n_slides in case of any mismatch — the
        # publisher indexes by slide position and would otherwise
        # IndexError.
        while len(out) < n_slides:
            out.append([])
        return out[:n_slides]

    def _record_omes(self, slot, territori, setmana, *, motiu: str):
        post, _ = SocialPost.objects.get_or_create(
            platform=slot.platform,
            tipus=slot.tipus,
            territori=territori or "",
            setmana=setmana,
            defaults={
                "status": SocialPost.STATUS_OMES,
                "error_msg": motiu,
                "scheduled_at": timezone.now(),
            },
        )
        if post.status not in (SocialPost.STATUS_PUBLICAT,):
            post.status = SocialPost.STATUS_OMES
            post.error_msg = motiu
            post.save(update_fields=["status", "error_msg", "updated_at"])

    def _mark(
        self,
        post: SocialPost,
        status: str,
        *,
        instagram_media_id: str | None = None,
        metadata: dict | None = None,
        error_msg: str = "",
        published_at=None,
    ):
        post.status = status
        if instagram_media_id is not None:
            post.instagram_media_id = instagram_media_id
        if metadata is not None:
            post.metadata = metadata
        if error_msg:
            post.error_msg = error_msg
        if published_at is not None:
            post.published_at = published_at
        post.save()
