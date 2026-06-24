"""Run the social distribution for a given calendar day.

# Spec: docs/architecture/social.md

Cron entry-point. Idempotent per (platform, tipus, territori,
setmana) via the SocialPost row. Modes:

  --data YYYY-MM-DD   process a specific date (default: today UTC)
  --tipus T           run only the matching slot (handy for backfills)
  --dry-run           render PNGs but never call the IG API
  --force             ignore existing publicat row + re-publish

The command:
  1. Reads ConfiguracioGlobal.instagram_actiu.
  2. Walks the calendari for the target weekday.
  3. For each slot (gated by the distribution matrix), builds payload,
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

from music.audit import log_staff_action
from ranking.models import ConfiguracioGlobal, MatriuPublicacio
from social import calendari, captions, instagram_client, payload, renderer
from social.calendari import tq_week_start
from social.captions import instagram_username
from social.models import SocialPost

logger = logging.getLogger(__name__)


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
        # Master + per-channel gate (2026-06-07): `distribucio_activa`
        # AND `instagram_actiu`. The per-slot matrix gate (canal × tipus
        # × dia_setmana) is applied below (an off slot is 'omès').
        if not cfg.pot_publicar("instagram") and not opts["dry_run"]:
            if not cfg.distribucio_activa:
                self.stdout.write("Distribució pausada (mestre). Surt.")
            else:
                self.stdout.write("Kill switch actiu (instagram_actiu=False). Surt.")
            return

        # Sprint Distribució v2 lot B: configurable per-channel delay.
        # Cron fires this command at the slot's base time; sleeping
        # here stretches the schedule wider without editing crontab.
        # Skipped under --dry-run (used by staff preview + tests).
        delay_min = max(0, min(180, int(cfg.delay_instagram_min or 0)))
        if delay_min and not opts.get("dry_run") and not opts.get("force"):
            import time as _time

            self.stdout.write(
                f"Sleep {delay_min} min (ConfiguracioGlobal.delay_instagram_min)…"
            )
            _time.sleep(delay_min * 60)

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

        # Distribution-matrix gate (the per-(canal × tipus) toggle, on top
        # of the master + per-channel switches checked at command entry).
        # The legacy Instagram-only "phase" rollout gate was removed
        # 2026-06 (prod was at fase 5 = everything on, so removal is
        # neutral). The per-slot day is fixed by the calendar (calendari.py),
        # not the matrix — the matrix only gates on/off per (canal × tipus).
        # An off cell is recorded 'omès' so the slot shows inactive instead
        # of vanishing.
        if not MatriuPublicacio.actiu_per("instagram", slot.tipus):
            self.stdout.write("  · matriu de distribució desactivada → omès")
            self._record_omes(slot, territori, setmana, motiu="matriu desactivada")
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
        # `phrase_ids` is the list of narrative phrases the engine
        # actually emitted (empty for novetats / engine fallback).
        # We stash it on `post.metadata` after a successful publish
        # via `registry.mark_used` so future weeks pick fresh copy.
        phrase_ids: list[str] = []
        if slot.tipus == SocialPost.TIPUS_TOP_PPCC:
            paths = renderer.render_feed_top(
                "top_ppcc", territori, setmana, data["entries"]
            )
            result = captions.compose_for_channel(
                "instagram_feed", "top_ppcc", territori, setmana, data["entries"]
            )
            caption = result["text"]
            phrase_ids = result.get("phrase_ids") or []
        elif slot.tipus == SocialPost.TIPUS_TOP_TERRITORIAL:
            paths = renderer.render_feed_top(
                "top_territorial", territori, setmana, data["entries"]
            )
            result = captions.compose_for_channel(
                "instagram_feed",
                "top_territorial",
                territori,
                setmana,
                data["entries"],
            )
            caption = result["text"]
            phrase_ids = result.get("phrase_ids") or []
        else:  # nous_*
            paths = renderer.render_feed_novetats(slot.tipus, setmana, data["items"])
            # Novetats now run through the narrative engine (audit #5).
            result = captions.compose_for_channel(
                "instagram_feed", slot.tipus, "", setmana, data["items"]
            )
            caption = result["text"]
            phrase_ids = result.get("phrase_ids") or []

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
        # Coordinates are spread across the canvas so the bubbles
        # don't all clump at the centre — see `_slide_tags` docstring.
        tags_per_slide = self._slide_tags(slot.tipus, len(paths), data)
        # Per-slide alt text — same chunking as _slide_tags so each
        # alt describes the slide the screen-reader user is on.
        entries_for_alts = data.get("entries") or data.get("items") or []
        alts_per_slide = captions.slide_alts(
            slot.tipus, territori, setmana, entries_for_alts, len(paths)
        )

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
                alt_text=alts_per_slide[0] or None,
            )
        else:
            child_ids = []
            for i, u in enumerate(urls):
                cid = instagram_client.upload_carousel_item(
                    u,
                    user_tags=tags_per_slide[i] or None,
                    alt_text=alts_per_slide[i] or None,
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
        # K1 analytics: aggregate counter for IG feed publications.
        from analytics.events import register as _register_event

        _register_event("social_publicat", dim1=slot.platform, dim2=slot.tipus)
        # Narrative-engine ledger: record the phrase ids that
        # actually shipped so the next picks for the same
        # (channel, territori) avoid them within the rolling window.
        # Best-effort: a registry write hiccup must not turn a
        # successful publish into a logged failure.
        for pid in phrase_ids:
            try:
                from social.narrative.registry import mark_used

                mark_used(pid, territori, setmana, "instagram_feed")
            except Exception:
                logger.exception(
                    "registry.mark_used failed for pid=%s (continuing)", pid
                )
        self.stdout.write(f"  · publicat → media_id={media_id}")

    # ── story flow ───────────────────────────────────────────────

    def _publish_story(self, post, slot, territori, setmana, data, cfg, opts):
        if territori == "PPCC":
            # Step 3b: the PPCC story set is a fixed 7-slide editorial
            # sequence (intro → 11-40 → 4-10 → podi → #1 hero → novetats
            # → outro).
            novetats_items = self._story_novetats_items(setmana, opts)
            hero_headline = self._story_hero_headline(setmana)
            paths = renderer.render_stories_ppcc(
                setmana,
                data["entries"],
                novetats_items=novetats_items,
                hero_headline=hero_headline,
            )
            max_cancons = None
        else:
            # Step 3c: editorial territorial story set (same grammar as
            # PPCC, recoloured + degraded by omission). Only CAT/VAL/BAL
            # host a territorial story (calendari rotation). Any other
            # code in a story slot is a misconfiguration: fail loud (the
            # slot is marked ERROR by _handle_slot), never derive a silent
            # story. Coherent with ALT/CAR not being public tops.
            if territori not in calendari.TERRITORIS_ROTATORI:
                raise ValueError(
                    f"no editorial story for territori={territori!r}; "
                    f"expected one of {calendari.TERRITORIS_ROTATORI}"
                )
            hero_headline = self._story_hero_headline(setmana, territori)
            paths = renderer.render_stories_territorial(
                territori,
                setmana,
                data["entries"],
                hero_headline=hero_headline,
            )
            max_cancons = None
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
                "n_slides": len(paths),
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
        # K1 analytics: counter for IG stories. dim1 is the platform
        # (instagram_story) and dim2 is the slot tipus (top_ppcc, …).
        # A story-set is ONE publication conceptually, regardless of
        # how many slides it carries — same treatment as an IG feed
        # carousel (1 publication with N images). The previous
        # `n=len(story_ids)` over-counted by 42× for a top story-set,
        # inflating the StaffAnalytics social tab (Bug 2 of Fase 3
        # audit, 2026-05-18).
        from analytics.events import register as _register_event

        _register_event("social_publicat", dim1=slot.platform, dim2=slot.tipus, n=1)
        self.stdout.write(f"  · {len(story_ids)} stories publicades.")

    # ── PPCC story-set extras (Step 3b) ──────────────────────────

    def _story_hero_headline(self, setmana, territori: str = "PPCC") -> str:
        """Short uppercase Playfair headline for the #1 hero slide,
        derived from the strongest scenario of the week (post-dedup).
        Falls back to a generic line on any error so the render never
        crashes. `territori` defaults to PPCC so the current PPCC call is
        unchanged; the territorial wire (final slice) passes its code."""
        try:
            from social.narrative.scenarios import detect_all, fallback_scenario
            from social.narrative.story_synth import synthesize_hero

            scenarios = detect_all(territori, setmana)
            scenario = scenarios[0] if scenarios else fallback_scenario(territori)
            return synthesize_hero(scenario)
        except Exception:  # noqa: BLE001 — never block a publication
            logger.exception("hero headline synthesis failed; using generic")
            return ""

    def _story_novetats_items(self, setmana, opts, *, limit: int = 3) -> list[dict]:
        """The 2-3 most recent releases (albums + singles merged) for the
        novetats story slide. Reuses `payload.build_novetats`; returns an
        empty list when there's nothing recent (the slide is then
        skipped)."""
        publish_date = opts.get("_target_date") or datetime.date.today()
        merged: list[dict] = []
        for tipus in ("nous_albums", "nous_singles"):
            try:
                d = payload.build_novetats(tipus, setmana, publish_date=publish_date)
            except Exception:  # noqa: BLE001 — best-effort
                logger.exception("build_novetats(%s) failed for story set", tipus)
                d = None
            if d and d.get("items"):
                merged.extend(d["items"])
        # Most recent first (lower `dies` = newer; None sinks to the end),
        # de-duplicated by slug.
        merged.sort(key=lambda it: (it.get("dies") is None, it.get("dies") or 0))
        seen: set = set()
        out: list[dict] = []
        for it in merged:
            slug = it.get("slug")
            if slug in seen:
                continue
            seen.add(slug)
            out.append(it)
            if len(out) >= limit:
                break
        return out

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _slide_tags(tipus: str, n_slides: int, data: dict) -> list[list[dict]]:
        """Per-slide `user_tags` payloads, one entry per slide.

        Slide 0 is always the cover (no tags). The rest mirror the
        renderer's chunking AND ordering so every artist appears on the
        same slide — and the same row — where their entry was drawn:

          • top_*       → `render_feed_top`'s countdown blocks
                          [(30,40),(20,30),(10,20),(0,10)], each block
                          REVERSED within the slide (40→31 … 10→1)
          • nous_albums → 1 album per slide
          • nous_singles → bin-packed (≤10 per slide, even split)

        The reversal matters: pre-2026-06 the tags were built 1→40
        while the slides render 40→1, so every tag pointed at the
        wrong artist. We now build the per-slide chunk in the exact
        order the renderer drew it.

        For top + nous_singles every artist on the entry is tagged
        (principal + collaborators); nous_albums tags the album artist
        plus each track collaborator. Tag coordinates are spread across
        the canvas so Instagram's tappable bubbles don't all clump at
        the centre. We anchor each tag to the approximate row Y of the
        corresponding entry and zigzag the X between three columns.
        """
        out: list[list[dict]] = [[]]  # cover slide → no tags

        def _tag(handle_url: str | None, *, x: float, y: float) -> dict | None:
            u = instagram_username(handle_url)
            if not u:
                return None
            # Clamp to (0.05, 0.95) — Meta rejects tags outside that
            # range silently. Bubbles render with an offset so we keep
            # them well inside the canvas.
            x = max(0.05, min(0.95, x))
            y = max(0.05, min(0.95, y))
            return {"username": u, "x": x, "y": y}

        # Y range for list rows: leaves headroom (top pill area) and
        # footer (page indicator + brand pill).
        Y_TOP, Y_BOTTOM = 0.18, 0.88
        # Three-column zigzag — keeps consecutive bubbles apart.
        XS = (0.30, 0.50, 0.70)

        def _row_xy(row_idx: int, n_rows: int) -> tuple[float, float]:
            """Y-center for row `row_idx` of `n_rows` evenly-spaced
            rows; X cycles through XS so adjacent bubbles don't
            overlap vertically."""
            if n_rows <= 0:
                return 0.5, 0.5
            step = (Y_BOTTOM - Y_TOP) / max(1, n_rows)
            y = Y_TOP + step * (row_idx + 0.5)
            return XS[row_idx % len(XS)], y

        CAP = 20  # Meta's per-image user_tags limit.

        def _entry_urls(entry: dict) -> list[str]:
            """Resolve the per-entry handle list, accepting both the
            new payload (`artistes_instagram_urls`) and the legacy
            single-URL fallback."""
            urls = entry.get("artistes_instagram_urls")
            if not urls:
                single = entry.get("artista_instagram_url")
                urls = [single] if single else []
            return [u for u in urls if u]

        def _tags_for_chunk(chunk: list[dict]) -> list[dict]:
            """Tags for one slide's entries, IN THE ORDER GIVEN (the
            caller passes the chunk in the same order the renderer drew
            it). Principal-first, then round-robin over collabs so a
            single very-collaborative entry can never monopolise the
            CAP and starve other entries of their principal tag:

              Pass 1: principal of every entry.
              Pass 2: 1st collab of every entry that has one.
              Pass 3: 2nd collab of every entry that has one.  …

            Caught at the 2026-05-23 audit on a real worst-case
            ("La Gent de la Mediterrània", 23 collaborators); without
            round-robin that one entry would have eaten all 20 slots."""
            chunk_urls = [_entry_urls(e) for e in chunk]
            tags: list[dict] = []
            for i, urls in enumerate(chunk_urls):
                if len(tags) >= CAP:
                    break
                if not urls:
                    continue
                bx, by = _row_xy(i, len(chunk))
                t = _tag(urls[0], x=bx, y=by)
                if t and t not in tags:
                    tags.append(t)
            max_extra = max((len(u) - 1 for u in chunk_urls), default=0)
            for collab_idx in range(1, max_extra + 1):
                if len(tags) >= CAP:
                    break
                for i, urls in enumerate(chunk_urls):
                    if len(tags) >= CAP:
                        break
                    if collab_idx >= len(urls):
                        continue
                    bx, by = _row_xy(i, len(chunk))
                    # Horizontal nudge keyed on collab_idx so adjacent
                    # collab bubbles don't overlap the principal at bx.
                    nudge_dx = (collab_idx % 3) * 0.10 - 0.10
                    t = _tag(urls[collab_idx], x=bx + nudge_dx, y=by)
                    if t and t not in tags:
                        tags.append(t)
            return tags[:CAP]

        TOP_TIPUS = (SocialPost.TIPUS_TOP_PPCC, SocialPost.TIPUS_TOP_TERRITORIAL)
        if tipus in TOP_TIPUS:
            entries = data.get("entries") or []
            # Mirror render_feed_top EXACTLY: same countdown blocks,
            # same present-filtering, same per-slide reversal — so each
            # tag lands on the slide AND row where the renderer drew it.
            for lo, hi in ((30, 40), (20, 30), (10, 20), (0, 10)):
                block = entries[lo:hi]
                if not block:
                    continue
                out.append(_tags_for_chunk(list(reversed(block))))
        elif tipus == SocialPost.TIPUS_NOUS_ALBUMS:
            items = data.get("items") or []
            # 1 slide per album (renderer caps at 9; n_slides may be
            # smaller if there are fewer items). Tag the album artist +
            # every track collaborator that has a handle.
            for item in items[: n_slides - 1]:
                out.append(_tags_for_chunk([item]))
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
                out.append(_tags_for_chunk(items[offset : offset + per_slide]))
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
