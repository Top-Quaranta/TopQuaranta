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

        # `setmana` reference for SocialPost rows = monday of the
        # current ISO week — same convention as TopSetmanal.
        setmana = target - datetime.timedelta(days=target.weekday())

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
            data = payload.build_novetats(slot.tipus, setmana)

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

        # Real publish: upload each as carousel item, then carousel
        # parent + publish. Single-image fallback when only one slide.
        urls = [_public_url_for(p) for p in paths]
        if len(urls) == 1:
            container = instagram_client.upload_image(urls[0], caption)
        else:
            child_ids = [instagram_client.upload_carousel_item(u) for u in urls]
            container = instagram_client.create_carousel(child_ids, caption)
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
