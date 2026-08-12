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
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from music.audit import log_staff_action
from ranking.models import ConfiguracioGlobal, MatriuPublicacio
from social import calendari, captions, instagram_client, payload, renderer
from social.calendari import tq_week_start
from social.captions import instagram_username
from social.models import SocialPost

logger = logging.getLogger(__name__)


def _marca_handles_rebutjats(handles: list[str]) -> None:
    """Stamp `instagram_rebutjat_at` on the artists Meta refused.

    Best-effort: flagging is bookkeeping, and it must never turn a
    successful publication into a failed one.
    """
    from django.db.models import Q
    from django.utils import timezone as _tz

    from music.models import Artista

    try:
        cond = Q()
        for h in set(handles):
            cond |= Q(instagram_url__iregex=rf"/{re.escape(h)}/?$")
        if not cond:
            return
        ara = _tz.now()
        n = 0
        for a in Artista.objects.filter(cond):
            # Empty the URL and put the artist BACK in the staff queue.
            # A refused handle is worthless to us and, since the field is
            # public (artist page + JSON-LD `sameAs`), a renamed account
            # leaves a dead link on the site and in Google's structured
            # data. The old value is kept so a merely-private account can
            # be restored by hand.
            a.instagram_rebutjat_url = a.instagram_url
            a.instagram_url = ""
            a.instagram_rebutjat_at = ara
            a.instagram_revisat = False
            a.save(
                update_fields=[
                    "instagram_url",
                    "instagram_rebutjat_url",
                    "instagram_rebutjat_at",
                    "instagram_revisat",
                ]
            )
            n += 1
        logger.warning(
            "Handles d'Instagram rebutjats per Meta: %s (%s artistes buidats "
            "i tornats a la cua)",
            ", ".join(sorted(set(handles))),
            n,
        )
    except Exception:  # pragma: no cover - bookkeeping must not break publish
        logger.exception("no s'han pogut marcar els handles rebutjats")


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


# ── Instagram user_tags helpers ──────────────────────────────────────
# Shared by the feed carousel tagger (`_slide_tags`) and the story
# tagger (`_story_tags`).

USER_TAGS_CAP = 20  # Meta's per-image user_tags limit.


def _norm_tag(handle_url: str | None, *, x: float, y: float) -> dict | None:
    """Meta `user_tags` payload for one handle URL, or None when the
    entry has no usable handle. Coordinates clamp to (0.05, 0.95) —
    Meta rejects tags outside that range silently; bubbles render with
    an offset so we keep them well inside the canvas."""
    u = instagram_username(handle_url)
    if not u:
        return None
    return {
        "username": u,
        "x": max(0.05, min(0.95, x)),
        "y": max(0.05, min(0.95, y)),
    }


def _entry_urls(entry: dict) -> list[str]:
    """Resolve the per-entry handle list, accepting both the new
    payload (`artistes_instagram_urls`) and the legacy single-URL
    fallback."""
    urls = entry.get("artistes_instagram_urls")
    if not urls:
        single = entry.get("artista_instagram_url")
        urls = [single] if single else []
    return [u for u in urls if u]


def _tags_for_entries(chunk: list[dict], pos_fn) -> list[dict]:
    """Tags for one image's entries, IN THE ORDER GIVEN (the caller
    passes the chunk in the same order the renderer drew it);
    `pos_fn(i, n) -> (x, y)` anchors entry `i` of `n` on the canvas.

    Principal-first, then round-robin over collabs so a single
    very-collaborative entry can never monopolise the cap and starve
    other entries of their principal tag:

      Pass 1: principal of every entry.
      Pass 2: 1st collab of every entry that has one.
      Pass 3: 2nd collab of every entry that has one.  …

    Caught at the 2026-05-23 audit on a real worst-case
    ("La Gent de la Mediterrània", 23 collaborators); without
    round-robin that one entry would have eaten all 20 slots."""
    chunk_urls = [_entry_urls(e) for e in chunk]
    tags: list[dict] = []
    for i, urls in enumerate(chunk_urls):
        if len(tags) >= USER_TAGS_CAP:
            break
        if not urls:
            continue
        bx, by = pos_fn(i, len(chunk))
        t = _norm_tag(urls[0], x=bx, y=by)
        if t and t not in tags:
            tags.append(t)
    max_extra = max((len(u) - 1 for u in chunk_urls), default=0)
    for collab_idx in range(1, max_extra + 1):
        if len(tags) >= USER_TAGS_CAP:
            break
        for i, urls in enumerate(chunk_urls):
            if len(tags) >= USER_TAGS_CAP:
                break
            if collab_idx >= len(urls):
                continue
            bx, by = pos_fn(i, len(chunk))
            # Horizontal nudge keyed on collab_idx so adjacent collab
            # bubbles don't overlap the principal at bx.
            nudge_dx = (collab_idx % 3) * 0.10 - 0.10
            t = _norm_tag(urls[collab_idx], x=bx + nudge_dx, y=by)
            if t and t not in tags:
                tags.append(t)
    return tags[:USER_TAGS_CAP]


# ── Story-slide anchor functions ─────────────────────────────────────
# Tappable-bubble anchors mirroring each story slide's grammar
# (`renderer.render_stories_ppcc` / `_territorial`): approximate
# normalized centres of the drawn item, NOT pixel-exact — same
# discipline as the feed tagger's evenly-spaced row anchors. Chunks
# arrive in DRAW order (the tagger mirrors the renderer's reversal),
# so index `i` is the i-th drawn item.


def _pos_story_mosaic(i: int, n: int) -> tuple[float, float]:
    """Slide «top 40→21»: 4×5 cover mosaic — column/row centres."""
    r, c = divmod(i, 4)
    return 0.16 + c * 0.213, 0.22 + r * 0.135


def _pos_story_pairs(i: int, n: int) -> tuple[float, float]:
    """Slide «top 20→11»: 5 centred 2-column pair rows."""
    return (0.35, 0.65)[i % 2], 0.21 + (i // 2) * 0.148


def _pos_story_grid(i: int, n: int) -> tuple[float, float]:
    """Slide «top 10→4»: 2-column pairs (#10/#9, #8/#7, #6/#5), then
    #4 centred below."""
    if i == 6:
        return 0.5, 0.84
    return (0.35, 0.65)[i % 2], 0.30 + (i // 2) * 0.185


def _pos_story_podi(i: int, n: int) -> tuple[float, float]:
    """Slide «podi»: #3 on top, #2 below — both centred."""
    return 0.5, 0.38 + i * 0.30


def _pos_story_hero(i: int, n: int) -> tuple[float, float]:
    """Slide «#1 hero»: single centred entry."""
    return 0.5, 0.60


def _pos_story_novetats(i: int, n: int) -> tuple[float, float]:
    """Slide «novetats»: ≤3 stacked release rows."""
    return 0.5, 0.40 + i * 0.17


def _pos_moviment(i: int, n: int) -> tuple[float, float]:
    """Feed «moviment»: single artwork cover, one protagonist entry.
    Anchor low-centre, near the credit line where the artist reads —
    unlike the tops, whose cover carries no tag (this IS the cover)."""
    return 0.5, 0.80


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
        self._n_errors = 0
        for slot, territori in slots:
            self._handle_slot(slot, territori, setmana, cfg, opts)
        # A per-slot failure marks the SocialPost ERROR but must NOT be
        # swallowed: exit non-zero so tq-run records status=FAIL and the
        # watchdog alerts (the 2026-07 invisible-IG-outage bug). Slots
        # that already published stay publicat — partial failure is
        # reported, not rolled back.
        if self._n_errors:
            raise CommandError(
                f"{self._n_errors} slot(s) van fallar; SocialPost en estat ERROR."
            )

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

        # Moviment master gate: with `moviment_actiu` off (the default) the
        # Thursday slot is a full no-op — NO SocialPost row, no attempt —
        # so the merge is inert until staff enable it (unlike the matrix
        # gate below, which records an 'omès' row).
        if slot.tipus == SocialPost.TIPUS_MOVIMENT and not getattr(
            cfg, "moviment_actiu", False
        ):
            self.stdout.write("  · moviment desactivat (dorment) → cap fila")
            return

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
        elif slot.tipus == SocialPost.TIPUS_MOVIMENT:
            data = payload.build_moviment(
                setmana, getattr(cfg, "moviment_pujada_minima", 5)
            )
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
            self._n_errors += 1
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
        artwork = getattr(cfg, "feed_artwork_actiu", False)
        if slot.tipus == SocialPost.TIPUS_TOP_PPCC:
            paths = renderer.render_feed_top(
                "top_ppcc", territori, setmana, data["entries"], artwork=artwork
            )
            result = captions.compose_for_channel(
                "instagram_feed", "top_ppcc", territori, setmana, data["entries"]
            )
            caption = result["text"]
            phrase_ids = result.get("phrase_ids") or []
        elif slot.tipus == SocialPost.TIPUS_TOP_TERRITORIAL:
            paths = renderer.render_feed_top(
                "top_territorial", territori, setmana, data["entries"], artwork=artwork
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
        elif slot.tipus == SocialPost.TIPUS_MOVIMENT:
            paths = renderer.render_feed_moviment(setmana, data)
            caption = captions.caption_moviment(setmana, data)
            phrase_ids = []
        else:  # nous_*
            paths = renderer.render_feed_novetats(
                slot.tipus,
                setmana,
                data["items"],
                artwork=artwork,
                mosaic_max=getattr(cfg, "feed_artwork_mosaic_max", 6),
            )
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
        # Moviment is a single artwork cover carrying its ONE protagonist
        # entry. Unlike the tops (cover untagged, tags on the list slides),
        # the tag + invitation belong ON this cover — so we reuse the SAME
        # primitives at the entry level rather than `_slide_tags`
        # (multi-slide-coupled): `_tags_for_entries` tags the protagonist
        # (+ any track collaborators with a handle; no handle → no tag, no
        # error), and `_collaborator_plan` runs the ADR-0015 policy over the
        # entry's `artistes_pool`. The collaborator behaviour is gated by
        # `ig_collaboradors_actiu` (inside `_collaborator_plan`), exactly
        # like the tops — `moviment_actiu` only gates the post existing.
        if slot.tipus == SocialPost.TIPUS_MOVIMENT:
            tags_per_slide = [_tags_for_entries([data], _pos_moviment)]
            alts_per_slide = [captions.alt_moviment(data)]
            collab_pool, collab_slots, collab_id_by_user = self._collaborator_plan(
                slot.tipus, {"entries": [data]}, cfg
            )
        else:
            tags_per_slide = self._slide_tags(slot.tipus, len(paths), data)
            # Per-slide alt text — same chunking as _slide_tags so each
            # alt describes the slide the screen-reader user is on.
            entries_for_alts = data.get("entries") or data.get("items") or []
            alts_per_slide = captions.slide_alts(
                slot.tipus, territori, setmana, entries_for_alts, len(paths)
            )

            # Collaborator plan (ADR-0015). GATED: with `ig_collaboradors_actiu`
            # False (the default) this returns an empty plan and every branch
            # below is byte-identical to the pre-collaborator flow (no
            # `collaborators` key ever reaches the container). With it on, the
            # parent container is created inside a non-blocking substitution
            # guard.
            collab_pool, collab_slots, collab_id_by_user = self._collaborator_plan(
                slot.tipus, data, cfg
            )

        # Real publish: upload each as carousel item, then carousel
        # parent + publish. Single-image fallback when only one
        # slide. Meta processes uploads asynchronously, so each
        # container must reach status_code=FINISHED *before* we hit
        # /media_publish — otherwise the API replies with code 9007
        # / subcode 2207027 ("Media ID is not available").
        urls = [_public_url_for(p) for p in paths]
        if len(urls) == 1:

            def _make_parent(collaborators):
                cid = instagram_client.upload_image(
                    urls[0],
                    caption,
                    user_tags=tags_per_slide[0] or None,
                    alt_text=alts_per_slide[0] or None,
                    collaborators=collaborators or None,
                )
                # Wait INSIDE the attempt so a collaborator error that
                # surfaces during async processing (not just at create)
                # also triggers substitution.
                instagram_client.wait_until_finished(cid)
                return cid

        else:
            child_ids = []
            # Handles Meta refused mid-upload. The post still goes out
            # without those tags; the artists get flagged afterwards so a
            # human can fix the account, because a publish rejection is
            # the only evidence we ever get that a handle went stale.
            handles_dolents: list[str] = []
            for i, u in enumerate(urls):
                cid = instagram_client.upload_carousel_item(
                    u,
                    user_tags=tags_per_slide[i] or None,
                    alt_text=alts_per_slide[i] or None,
                    dropped=handles_dolents,
                )
                instagram_client.wait_until_finished(cid)
                child_ids.append(cid)
            if handles_dolents:
                _marca_handles_rebutjats(handles_dolents)

            def _make_parent(collaborators):
                cid = instagram_client.create_carousel(
                    child_ids, caption, collaborators=collaborators or None
                )
                instagram_client.wait_until_finished(cid)
                return cid

        container, used_collabs = self._create_parent_with_guard(
            _make_parent, collab_pool, collab_slots
        )
        media_id = instagram_client.publish_container(container)
        # Registry: one InvitacioColaboracioIG per effectively-sent
        # collaborator, ONLY now that the post is published (no orphan
        # rows if the publish above raised).
        self._record_invitacions(used_collabs, collab_id_by_user, media_id, slot.tipus)
        self._mark(
            post,
            SocialPost.STATUS_PUBLICAT,
            instagram_media_id=media_id,
            metadata={
                "slides": [p.name for p in paths],
                "caption_len": len(caption),
                **({"collaborators": used_collabs} if used_collabs else {}),
            },
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

    # ── collaborator invitations (ADR-0015 §5.2/§5.3, gated) ─────────

    def _collaborator_plan(self, tipus: str, data: dict, cfg):
        """Ordered pool + slot count for a feed post. GATED: returns an
        empty plan (no-op) unless `ig_collaboradors_actiu` is on.

        Returns `(ordered_usernames, slots, id_by_username)`:
          - `ordered_usernames` = the policy-selected usernames first,
            then the remaining pool in order (the substitution reserve).
          - `slots` = len(selected) (already ≤ the module's clamp of 3).
          - `id_by_username` maps each username back to its artista_id so
            we can write the registry row after publish."""
        if not getattr(cfg, "ig_collaboradors_actiu", False):
            return [], 0, {}
        from social import collaboradors as C

        entries = data.get("entries") or data.get("items") or []
        pool: list[tuple[int, str]] = []
        seen: set[int] = set()
        for entry in entries:
            for pa in entry.get("artistes_pool") or []:
                aid, uname = pa.get("id"), pa.get("username")
                if aid is None or not uname or aid in seen:
                    continue
                seen.add(aid)
                pool.append((aid, uname))
        if not pool:
            return [], 0, {}

        pool_objs = [C.PoolArtist(artista_id=aid, username=u) for aid, u in pool]
        historic = self._load_historic([aid for aid, _ in pool])
        config = C.PolicyConfig.from_config(cfg)
        selected = C.select_collaborators(
            pool_objs, historic, config, now=timezone.now()
        )
        selected_ids = {s.artista_id for s in selected}
        selected_usernames = [s.username for s in selected]
        reserve = [u for aid, u in pool if aid not in selected_ids]
        id_by_username = {u: aid for aid, u in pool}
        return selected_usernames + reserve, len(selected_usernames), id_by_username

    @staticmethod
    def _load_historic(artista_ids):
        """`{artista_id: [InviteRecord, ...]}` from the invite registry."""
        from collections import defaultdict

        from social.collaboradors import InviteRecord
        from social.models import InvitacioColaboracioIG

        hist = defaultdict(list)
        for r in InvitacioColaboracioIG.objects.filter(artista_id__in=artista_ids):
            hist[r.artista_id].append(
                InviteRecord(
                    estat=r.estat,
                    data_invitacio=r.data_invitacio,
                    data_resolucio=r.data_resolucio,
                )
            )
        return hist

    @staticmethod
    def _offending_username(err_text: str, collaborators):
        """The collaborator handle named in a container error, or None
        (then the guard leave-one-out identifies it)."""
        low = (err_text or "").lower()
        for u in collaborators or []:
            if u.lower() in low:
                return u
        return None

    def _create_parent_with_guard(self, make_parent, pool_usernames, slots):
        """Create (and FINISH) the parent container, applying the
        non-blocking substitution guard (§5.3) when there are
        collaborators to try. Returns `(container_id, used_usernames)`.

        With an empty plan (`slots == 0`) this is exactly
        `make_parent(None)` — the byte-identical no-collaborator path."""
        if not pool_usernames or slots <= 0:
            return make_parent(None), []

        from social import collaboradors as C

        holder: dict = {}

        def _try(collaborators):
            try:
                holder["cid"] = make_parent(collaborators)
                return True, None
            except Exception as exc:  # noqa: BLE001 — treated as a handle failure
                logger.warning(
                    "collaborator container attempt failed (%s): %s",
                    collaborators,
                    str(exc)[:200],
                )
                return False, self._offending_username(str(exc), collaborators)

        result = C.publish_with_collaborator_guard(pool_usernames, slots, _try)
        for d in result.dropped:
            self.stdout.write(
                f"  · col·laborador descartat: {d['username']} ({d['reason']})"
            )
        return holder["cid"], result.used

    @staticmethod
    def _record_invitacions(used_usernames, id_by_username, media_id, tipus):
        """One InvitacioColaboracioIG per sent collaborator. Idempotent
        (UNIQUE(artista, ig_media_id)); called ONLY after the post
        publishes so a failed publish leaves no orphan rows."""
        if not used_usernames:
            return
        from social.models import InvitacioColaboracioIG

        now = timezone.now()
        for u in used_usernames:
            aid = id_by_username.get(u)
            if aid is None:
                continue
            InvitacioColaboracioIG.objects.get_or_create(
                artista_id=aid,
                ig_media_id=media_id,
                defaults={
                    "username_snapshot": u,
                    "tipus_publicacio": tipus,
                    "data_invitacio": now,
                    "estat": InvitacioColaboracioIG.ESTAT_PENDENT,
                },
            )

    # ── story flow ───────────────────────────────────────────────

    @staticmethod
    def _story_tags(
        territori: str,
        entries: list[dict],
        novetats_items: list[dict] | None,
    ) -> list[list[dict]]:
        """Per-story `user_tags`, one list per rendered story, mirroring
        `render_stories_ppcc` / `render_stories_territorial` slide
        emission EXACTLY — same slices, same conditional tiers, same
        draw-order reversal — so every mention lands on the story where
        the song is visible, anchored near its drawn item. Intro and
        outro carry no entries → no tags. PPCC emits every tier
        unconditionally; territorial degrades by omission (mosaic n>20,
        pairs n>10, grid n>3, podi n>1, hero if entries)."""
        novetats_items = [it for it in (novetats_items or []) if it]
        out: list[list[dict]] = [[]]  # intro
        n = len(entries)
        ppcc = territori == "PPCC"
        if ppcc or n > 20:
            out.append(
                _tags_for_entries(list(reversed(entries[20:40])), _pos_story_mosaic)
            )
        if ppcc or n > 10:
            out.append(
                _tags_for_entries(list(reversed(entries[10:20])), _pos_story_pairs)
            )
        if ppcc or n > 3:
            out.append(
                _tags_for_entries(list(reversed(entries[3:10])), _pos_story_grid)
            )
        if ppcc or n > 1:
            out.append(_tags_for_entries(list(reversed(entries[1:3])), _pos_story_podi))
        if ppcc or entries:
            out.append(_tags_for_entries(entries[:1], _pos_story_hero))
        if novetats_items:
            out.append(_tags_for_entries(novetats_items[:3], _pos_story_novetats))
        out.append([])  # outro
        return out

    def _create_story_with_guard(self, image_url: str, tags: list[dict]) -> str:
        """Create (and FINISH) one STORIES container, applying the same
        non-blocking substitution guard as the feed collaborators
        (§5.3 semantics, reused via `max_slots`): a username Meta
        rejects is dropped and the story retried, last resort created
        with no mentions. Only a non-tag failure propagates."""
        if not tags:
            container = instagram_client.upload_story(image_url)
            instagram_client.wait_until_finished(container)
            return container

        from social import collaboradors as C

        by_user = {t["username"]: t for t in tags}
        holder: dict = {}

        def _try(usernames):
            subset = [by_user[u] for u in usernames if u in by_user]
            try:
                cid = instagram_client.upload_story(image_url, user_tags=subset or None)
                instagram_client.wait_until_finished(cid)
                holder["cid"] = cid
                return True, None
            except Exception as exc:  # noqa: BLE001 — treated as a tag failure
                logger.warning(
                    "story container attempt failed (%s): %s",
                    usernames,
                    str(exc)[:200],
                )
                return False, self._offending_username(str(exc), usernames)

        result = C.publish_with_collaborator_guard(
            list(by_user), len(by_user), _try, max_slots=USER_TAGS_CAP
        )
        for d in result.dropped:
            self.stdout.write(f"  · menció descartada: {d['username']} ({d['reason']})")
        return holder["cid"]

    def _publish_story(self, post, slot, territori, setmana, data, cfg, opts):
        if territori == "PPCC":
            # Step 3b: the PPCC story set is a fixed 8-slide editorial
            # sequence (intro → 21-40 → 11-20 → 4-10 → podi → #1 hero →
            # novetats → outro).
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
            novetats_items = None  # the cron passes none to territorial sets
        self.stdout.write(f"  · renderitzades {len(paths)} stories")

        if opts["dry_run"]:
            self._mark(
                post,
                SocialPost.STATUS_PENDENT,
                metadata={"dry_run": True, "stories": [p.name for p in paths]},
            )
            self.stdout.write("  · --dry-run, no es publica.")
            return

        # Per-story mentions (user_tags) — API payload only, images
        # untouched. Built to mirror the renderer's emission; on any
        # count mismatch we publish untagged rather than mis-anchor
        # (defensive: a renderer change without tagger sync must never
        # put a mention on the wrong story).
        tags_per_story = self._story_tags(territori, data["entries"], novetats_items)
        if len(tags_per_story) != len(paths):
            logger.warning(
                "story tags/slides mismatch (%d tag sets vs %d slides) for "
                "%s %s; publishing without mentions",
                len(tags_per_story),
                len(paths),
                slot.tipus,
                territori,
            )
            tags_per_story = [[] for _ in paths]

        # Resumable story sets (2026-07-20 story-3 post-mortem). A prior
        # partial run left the row in ERROR with `metadata.published_slides`
        # (idx+name+sid per slide that went out); we skip those and publish
        # only the gap. `--force` starts fresh (ignores prior slides) so it
        # re-publishes the whole set — it never reads the resume state, so
        # it can't half-skip.
        done_by_idx: dict[int, dict] = {}
        if not opts.get("force"):
            for d in (post.metadata or {}).get("published_slides") or []:
                if isinstance(d, dict) and "idx" in d:
                    done_by_idx[d["idx"]] = d

        story_ids: list[str] = []
        published_slides: list[dict] = []
        fallides: list[dict] = []
        for idx, p in enumerate(paths):
            if idx in done_by_idx:
                d = done_by_idx[idx]
                story_ids.append(d["sid"])
                published_slides.append(d)
                self.stdout.write(
                    f"  · story {idx + 1}/{len(paths)} ja publicada, salta"
                )
                continue
            url = _public_url_for(p)
            try:
                # Same async-readiness gate as the feed flow above,
                # inside the guard (a tag can also fail at FINISH).
                container = self._create_story_with_guard(url, tags_per_story[idx])
                sid = instagram_client.publish_container(container)
                story_ids.append(sid)
                published_slides.append({"idx": idx, "name": p.name, "sid": sid})
                # Per-story mention audit trail: makes a mention
                # verification a `grep "story .* tags="` instead of a
                # reconstruction (the built list is the ground truth; a
                # guard drop still surfaces on its own `menció descartada`
                # line). Usernames only — no coordinates, no payload.
                logger.info(
                    "story %d/%d %s %s media=%s tags=[%s]",
                    idx + 1,
                    len(paths),
                    slot.tipus,
                    territori,
                    sid,
                    ",".join(t["username"] for t in tags_per_story[idx]),
                )
            except Exception as exc:  # noqa: BLE001 — one bad story must not
                # block the rest of the set (non-blocking, §5.6).
                logger.exception(
                    "story %d/%d failed for %s %s",
                    idx + 1,
                    len(paths),
                    slot.tipus,
                    territori,
                )
                fallides.append({"story": p.name, "error": str(exc)[:200]})

        meta = {
            "stories": [p.name for p in paths],
            "story_ids": story_ids,
            "max_cancons": max_cancons,
            "n_slides": len(paths),
            "n_mencions": sum(len(t) for t in tags_per_story),
            "published_slides": published_slides,
        }
        if fallides:
            meta["stories_fallides"] = fallides
            if not story_ids:
                # Nothing went out — plain slot failure (the caller
                # marks ERROR and counts it; metadata persisted here).
                self._mark(post, SocialPost.STATUS_ERROR, metadata=meta)
                raise RuntimeError(
                    f"cap story publicada ({len(fallides)} pàgines han fallat)"
                )
            # Incomplete set: keep it ERROR (not PUBLICAT) with the
            # published slides persisted, so tq-run's retry re-enters
            # `_publish_story` and backfills only the gap. Counted so
            # handle() raises CommandError → non-zero exit (honours the
            # PR #319 discipline until the set is truly complete).
            self._mark(
                post,
                SocialPost.STATUS_ERROR,
                metadata=meta,
                error_msg=(
                    f"{len(fallides)} de {len(paths)} stories pendents " "(resumible)"
                ),
            )
            self._n_errors += 1
            self.stdout.write(
                f"  · ⚠ {len(fallides)} de {len(paths)} stories pendents; "
                "re-intent al proper run"
            )
            return

        self._mark(
            post,
            SocialPost.STATUS_PUBLICAT,
            instagram_media_id=story_ids[-1] if story_ids else "",
            metadata=meta,
            error_msg=(f"{len(fallides)} stories han fallat" if fallides else ""),
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

        def _tags_for_chunk(chunk: list[dict]) -> list[dict]:
            return _tags_for_entries(chunk, _row_xy)

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
