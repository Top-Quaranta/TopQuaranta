"""Backfill Spotify enrichment for cançons that exist only as HR
rejection rows.

The per-pair rejection-ratio feature in `music.ml` keys on
(artista_deezer_id, artista_spotify_id). The Deezer id is already
stored on every HR row; the Spotify artist id sits on
`SpotifyMetadata.spotify_artist_id` and is therefore only
available for cançons that Process B has enriched. As of 2026-05-25
only 1 of 12 027 rebuigs has the join populated, so the per-pair
feature would fall back to per-deezer (or by-name) on the entire
rebuig universe.

This command enriches the rebuig universe one batch per day,
separately from the maintenance cron at `enriquir_spotify`. Two
reasons for keeping them apart:

  1. The rebuig universe is bounded and finite (~9 400 cançons).
     A dedicated drain command makes the operator's budget
     explicit: `--limit 50` per run, ~6 months to clear at the
     safe 150-API-calls/day rate Spotify's Dev-Mode quota
     tolerates.
  2. Priority order. The cançons that matter most for the
     feature are those whose `artista_deezer_id` has at least one
     `desvincular_album` rejection: those are the deezer-collapsed
     homonyms the feature is designed to disambiguate. Deezer
     profiles without that signal don't change the ratio (their
     rebuigs are either pure language drops or whole-artist
     rejections that already get desvincular_artista).

Selection algorithm:

  a) Collect `artista_deezer_id` values flagged by at least one
     `desvincular_album` HR rebuig (the homonym shortlist).
  b) From rebuigs in the shortlist whose `canco_deezer_id` has no
     enriched SpotifyMetadata yet, pull up to `--limit` candidates.
     Older HR rows first (oldest `created_at`) so the long tail
     drains first.
  c) If the shortlist is exhausted, fall through to any rebuig
     without enrichment, same ordering. Set `--shortlist-only` to
     refuse the fallback.

Each candidate goes through the same enrichment helper Process B
uses, then `HistorialRevisio.artista_spotify_id` is filled in
place via the new column added in migration 0085.

Same cooldown contract as `enriquir_spotify`: a RateLimitedError
from Spotify writes a cooldown file at
`/var/log/topquaranta/status/enriquir_spotify_rebuigs.cooldown`
and the next run skips until the resume timestamp passes.

# Spec: docs/architecture/pipeline.md (Track verification ML)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_tz
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from ingesta.clients.spotify import RateLimitedError, UserSpotifyClient
from ingesta.clients.spotify_backfill_controller import (
    adjust_for_run,
    load_state,
    save_state,
)
from music.models import Canco, HistorialRevisio, SpotifyAuth, SpotifyMetadata

logger = logging.getLogger(__name__)

# Legacy per-command cooldown path. Reads still happen via
# `spotify_metadata_cooldown.LEGACY_PATHS` for the transition
# window so a live ban from the old binary keeps being honoured.
# New writes go to the shared `spotify_metadata.cooldown`.
LEGACY_COOLDOWN_FILE = Path(
    "/var/log/topquaranta/status/enriquir_spotify_rebuigs.cooldown"
)
# Same 24h cap as enriquir_spotify. Spotify's long Retry-After
# windows tend to land between 18h and 24h on Dev-Mode quotas; we
# honour the value when it falls under this cap and refuse to wait
# longer (the cron will retry the next day).
MAX_COOLDOWN_S = 86400


class Command(BaseCommand):
    help = (
        "Backfill Spotify enrichment for rebuig cançons so the per-pair "
        "rejection-ratio feature has full coverage."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Manual override of the daily limit (cançons). When "
                "omitted, the AIMD controller in "
                "`ingesta.clients.spotify_backfill_controller` "
                "picks the limit based on observed bans (starts at "
                "200, ramps +200 every 3 ban-free days up to a hard "
                "ceiling of 800, drops on any ban). Pass --limit to "
                "force a value for THIS run only; the controller "
                "state is left untouched in that case."
            ),
        )
        parser.add_argument(
            "--throttle",
            type=float,
            default=1.0,
            help="Seconds between Spotify API calls. Default 1.0.",
        )
        parser.add_argument(
            "--shortlist-only",
            action="store_true",
            help=(
                "Only enrich cançons whose artista_deezer_id has at "
                "least one desvincular_album rejection. Skips the "
                "fall-through to the wider rebuig universe."
            ),
        )
        parser.add_argument(
            "--include-orfes",
            action="store_true",
            help=(
                "Enable the orphan flow: HR rows whose Canco was "
                "deleted by rebutjar_album/rebutjar_artista but still "
                "carry an ISRC. Runs one /v1/search per distinct "
                "ISRC and writes the resolved spotify_artist_id back "
                "to every HR row with that ISRC. Behind a flag while "
                "we validate it; the production cron does NOT pass "
                "this until the operator says so."
            ),
        )
        parser.add_argument(
            "--include-pendents",
            action="store_true",
            help=(
                "Enable the pendents tail: Cançons with "
                "verificada=False, activa=True that carry an ISRC "
                "and have no SpotifyMetadata yet. Last tier of the "
                "cascade. Behind a flag while we validate it; the "
                "production cron does NOT pass this until the "
                "operator says so."
            ),
        )

    def handle(self, *args, **opts):
        from ingesta.clients import spotify_metadata_cooldown as cd

        # AIMD controller runs FIRST — BEFORE the cooldown gate and
        # BEFORE `clear_expired()`. Ordering is load-bearing: a ban's
        # Retry-After runs 18–24h, longer than the gap to the next
        # daily tick, so the cooldown sentinel has typically just
        # EXPIRED by the time this cron fires again. If we pruned it
        # first (the old order), `detect_recent_ban` would find no
        # file, `last_ban_at` would stay null, no multiplicative
        # decrease would happen, and `dies_sense_ban` would keep
        # climbing — bumping the limit back up the day after a ban.
        # By adjusting before any cleanup, a just-expired sentinel is
        # still on disk and its mtime is seen. We `save_state` here so
        # the decrease persists even if this run then aborts on an
        # active cooldown below. A manual `--limit` override skips the
        # controller and leaves the persisted state untouched.
        manual_limit = opts["limit"]
        if manual_limit is None:
            state = adjust_for_run(load_state())
            save_state(state)
            limit = state.limit_actual
            self.stdout.write(
                f"[enriquir_spotify_rebuigs] AIMD controller -> "
                f"limit={limit} (dies_sense_ban={state.dies_sense_ban}, "
                f"last_safe={state.last_safe_limit}, "
                f"last_ban_at={state.last_ban_at})"
            )
        else:
            limit = manual_limit
            self.stdout.write(
                f"[enriquir_spotify_rebuigs] manual override "
                f"--limit={limit}; controller state unchanged"
            )

        # Cooldown gate. Reads the SHARED metadata cooldown (plus the
        # legacy per-command files during the transition). If the
        # maintenance enrichment was banned, we must skip too: both
        # commands hit `/v1/search`, `/v1/tracks` and `/v1/artists`,
        # which share a single Spotify quota bucket, and probing
        # during an active ban is documented to extend the window.
        # The controller has already recorded + persisted the decrease
        # above, so skipping here loses nothing.
        resume_at = cd.active_resume_at()
        if resume_at is not None:
            self.stdout.write(
                self.style.WARNING(
                    f"[enriquir_spotify_rebuigs] Spotify metadata "
                    f"cooldown active until {resume_at.isoformat()}. "
                    f"Skipping."
                )
            )
            return
        # Prune expired sentinels only AFTER the controller has had a
        # chance to observe them.
        cd.clear_expired()

        auth = SpotifyAuth.load()
        if not auth:
            raise CommandError("No SpotifyAuth row. Run the staff OAuth flow first.")

        throttle = opts["throttle"]
        shortlist_only = opts["shortlist_only"]
        include_orfes = opts["include_orfes"]
        include_pendents = opts["include_pendents"]
        client = UserSpotifyClient(auth, throttle_s=throttle)

        # Cascade: live shortlist alive -> orphans shortlist ->
        # rest of rebuigs (alive + orphans) -> pendents. Each tier
        # only fills what the previous one left in the budget. The
        # AIMD limit caps total items processed regardless of
        # cascade tier; orphan items cost ~1 API call each vs ~3
        # for live items, so a tier shift toward orphans is
        # automatically more conservative on the quota.
        remaining = limit
        live_alive_cancons = self._select_candidates_alive(
            limit=remaining, shortlist_only=shortlist_only
        )
        remaining = max(0, remaining - len(live_alive_cancons))

        orfe_shortlist_isrcs: list[str] = []
        orfe_rest_isrcs: list[str] = []
        if include_orfes and remaining > 0:
            orfe_shortlist_isrcs = self._select_orfe_isrcs(
                limit=remaining, shortlist_only=True
            )
            remaining = max(0, remaining - len(orfe_shortlist_isrcs))
            if not shortlist_only and remaining > 0:
                # Skip the ISRCs we already queued from the shortlist.
                seen = set(orfe_shortlist_isrcs)
                orfe_rest_isrcs = [
                    isrc
                    for isrc in self._select_orfe_isrcs(
                        limit=remaining + len(seen),
                        shortlist_only=False,
                    )
                    if isrc not in seen
                ][:remaining]
                remaining = max(0, remaining - len(orfe_rest_isrcs))

        pendent_cancons: list[Canco] = []
        if include_pendents and remaining > 0:
            pendent_cancons = self._select_pendents(limit=remaining)

        self.stdout.write(
            f"[enriquir_spotify_rebuigs] cascade "
            f"(limit={limit}, throttle={throttle}, "
            f"shortlist_only={shortlist_only}, "
            f"include_orfes={include_orfes}, "
            f"include_pendents={include_pendents}): "
            f"live_alive={len(live_alive_cancons)} "
            f"orfe_shortlist={len(orfe_shortlist_isrcs)} "
            f"orfe_rest={len(orfe_rest_isrcs)} "
            f"pendents={len(pendent_cancons)}"
        )

        live_done = orfe_done_found = pendent_done = 0
        live_found = pendent_found = 0
        aborted = False
        try:
            for canco in live_alive_cancons:
                outcome = self._enrich_one(client, canco)
                live_done += 1
                if outcome == "found":
                    live_found += 1
            for isrc in orfe_shortlist_isrcs + orfe_rest_isrcs:
                outcome = self._enrich_orfe_isrc(client, isrc)
                if outcome == "found":
                    orfe_done_found += 1
            for canco in pendent_cancons:
                outcome = self._enrich_one(client, canco)
                pendent_done += 1
                if outcome == "found":
                    pendent_found += 1
        except RateLimitedError as exc:
            from ingesta.clients import spotify_metadata_cooldown as cd

            aborted = True
            effective = min(exc.retry_after_s, MAX_COOLDOWN_S)
            resume_at = datetime.now(tz=dt_tz.utc).replace(tzinfo=None) + timedelta(
                seconds=effective
            )
            try:
                cd.write(resume_at)
            except OSError:
                logger.warning("Could not write cooldown file %s", cd.SHARED_PATH)
            self.stdout.write(
                self.style.WARNING(
                    f"[enriquir_spotify_rebuigs] rate limited; cooldown "
                    f"until {resume_at.isoformat()}."
                )
            )

        n_orfe = len(orfe_shortlist_isrcs) + len(orfe_rest_isrcs)
        self.stdout.write(
            f"[enriquir_spotify_rebuigs] done: "
            f"live(processed={live_done} found={live_found}) "
            f"orfe(processed={n_orfe} found={orfe_done_found}) "
            f"pendent(processed={pendent_done} found={pendent_found}) "
            f"aborted={aborted}"
        )

    # ── candidate selection ────────────────────────────────────────
    def _select_candidates_alive(
        self, *, limit: int, shortlist_only: bool
    ) -> list[Canco]:
        """Pull up to `limit` rebuig cançons missing SpotifyMetadata.

        Priority:
          1. cançons whose artista_deezer_id has >=1
             desvincular_album HR row (the homonym shortlist).
          2. (optional) any rebuig cançó without enrichment.

        Ordering: oldest HR `created_at` first within each tier so
        the historical tail drains first.
        """
        shortlist = set(
            HistorialRevisio.objects.filter(
                decisio="rebutjada", motiu="desvincular_album"
            )
            .exclude(artista_deezer_id__isnull=True)
            .values_list("artista_deezer_id", flat=True)
            .distinct()
        )

        # HR rows in scope: rebuig + has canco_deezer_id + no
        # SpotifyMetadata yet (the corresponding Canco may have
        # been deleted by `rebutjar_album`/`rebutjar_artista`, in
        # which case we cannot enrich it; only the surviving
        # Canço rows count).
        enriched_dz = set(
            Canco.objects.filter(
                spotify__enrichment_status=SpotifyMetadata.STATUS_FOUND
            )
            .exclude(spotify__spotify_artist_id__isnull=True)
            .exclude(spotify__spotify_artist_id="")
            .values_list("deezer_id", flat=True)
        )

        # Pre-filter set of deezer_ids that still have a *surviving*
        # non-FOUND Canço. This must be applied to the HR scan BEFORE
        # the `limit` cap, otherwise the tier starves: ~95 % of the
        # shortlist HR rows point to cançons already deleted by
        # `rebutjar_album`/`rebutjar_artista`, so iterating oldest-
        # first and capping at `limit` fills the budget entirely with
        # dead deezer_ids and the surviving candidates (which sit far
        # down the created_at order) are never reached. Filtering on
        # this set up front guarantees the cap is spent on enrichable
        # rows only. (Bug: 2026-05-28 the cron logged live_alive=0
        # while 192 live candidates existed beyond the cap.)
        alive_song_dzids = set(
            Canco.objects.exclude(
                spotify__enrichment_status=SpotifyMetadata.STATUS_FOUND
            ).values_list("deezer_id", flat=True)
        )

        hr_priority = (
            HistorialRevisio.objects.filter(
                decisio="rebutjada",
                artista_deezer_id__in=shortlist,
            )
            .exclude(canco_isrc="")
            .exclude(canco_deezer_id__isnull=True)
            .exclude(canco_deezer_id__in=enriched_dz)
            .filter(canco_deezer_id__in=alive_song_dzids)
            # Secondary sort on pk to make the selection deterministic
            # across runs: created_at has large same-timestamp batches
            # (staff bulk actions), and without a tiebreak which rows
            # land inside the cap varied run-to-run.
            .order_by("created_at", "pk")
        )
        priority_dzids: list[int] = []
        for dz in hr_priority.values_list("canco_deezer_id", flat=True):
            if dz not in priority_dzids:
                priority_dzids.append(dz)
            if len(priority_dzids) >= limit:
                break

        result = list(
            Canco.objects.filter(deezer_id__in=priority_dzids).exclude(
                spotify__enrichment_status=SpotifyMetadata.STATUS_FOUND
            )
        )

        if not shortlist_only and len(result) < limit:
            seen = {c.deezer_id for c in result}
            hr_fallback = (
                HistorialRevisio.objects.filter(decisio="rebutjada")
                .exclude(canco_isrc="")
                .exclude(canco_deezer_id__isnull=True)
                .exclude(canco_deezer_id__in=enriched_dz)
                # Same surviving-Canço pre-filter and pk tiebreak as
                # the priority scan above, for the same starvation and
                # determinism reasons.
                .filter(canco_deezer_id__in=alive_song_dzids)
                .order_by("created_at", "pk")
            )
            for dz in hr_fallback.values_list("canco_deezer_id", flat=True):
                if dz in seen:
                    continue
                seen.add(dz)
                canco = (
                    Canco.objects.filter(deezer_id=dz)
                    .exclude(spotify__enrichment_status=SpotifyMetadata.STATUS_FOUND)
                    .first()
                )
                if canco is not None:
                    result.append(canco)
                if len(result) >= limit:
                    break

        return result[:limit]

    def _select_orfe_isrcs(self, *, limit: int, shortlist_only: bool) -> list[str]:
        """Return up to `limit` distinct ISRCs for the orphan flow.

        An "orphan" HR row has a non-empty `canco_isrc`, an empty
        `artista_spotify_id`, no `Canco` row matching its
        `canco_deezer_id` (the cançó was deleted by
        `rebutjar_album` / `rebutjar_artista`), and either
        `spotify_lookup_at IS NULL` or older than 30 days.

        Returns ISRCs deduplicated (one search per ISRC, not one
        per HR row), oldest HR `created_at` first so the long
        historical tail drains first.
        """
        from datetime import timedelta

        from django.db.models import Exists, OuterRef
        from django.utils import timezone

        cutoff = timezone.now() - timedelta(days=30)
        qs = (
            HistorialRevisio.objects.filter(
                decisio="rebutjada",
                artista_spotify_id="",
            )
            .exclude(canco_isrc="")
            .exclude(canco_deezer_id__isnull=True)
            .filter(
                models.Q(spotify_lookup_at__isnull=True)
                | models.Q(spotify_lookup_at__lt=cutoff)
            )
            .annotate(
                has_canco=Exists(
                    Canco.objects.filter(deezer_id=OuterRef("canco_deezer_id"))
                )
            )
            .filter(has_canco=False)
        )
        if shortlist_only:
            shortlist = set(
                HistorialRevisio.objects.filter(
                    decisio="rebutjada", motiu="desvincular_album"
                )
                .exclude(artista_deezer_id__isnull=True)
                .values_list("artista_deezer_id", flat=True)
                .distinct()
            )
            qs = qs.filter(artista_deezer_id__in=shortlist)

        seen: list[str] = []
        for isrc in qs.order_by("created_at").values_list("canco_isrc", flat=True):
            if isrc not in seen:
                seen.append(isrc)
            if len(seen) >= limit:
                break
        return seen

    def _select_pendents(self, *, limit: int) -> list[Canco]:
        """Cançons with `verificada=False, activa=True` carrying an
        ISRC and no SpotifyMetadata yet. Last tier of the cascade.

        Ordered by most-recent `created_at` first so we enrich
        what is freshest in the queue and likely to surface in
        ranking soon, rather than backfilling the deepest
        historical tail (the rebuig flows already drain that).
        """
        return list(
            Canco.objects.filter(verificada=False, activa=True)
            .exclude(isrc="")
            .exclude(isrc__isnull=True)
            .exclude(spotify__enrichment_status=SpotifyMetadata.STATUS_FOUND)
            .order_by("-created_at")[:limit]
        )

    # ── per-orphan-ISRC ────────────────────────────────────────────
    def _enrich_orfe_isrc(self, client: UserSpotifyClient, isrc: str) -> str:
        """Single-call enrichment for an orphan ISRC: one
        `/v1/search?q=isrc:<X>`, extract the principal
        spotify_artist_id from the response, write it back to
        every matching HR row.

        No `Canco` or `SpotifyMetadata` rows are created here;
        the only persistent effect is the HR update plus the
        `spotify_lookup_at` stamp (regardless of found / not
        found, so the candidate query does not re-issue this
        search for the next 30 days).

        Returns `found` or `not_found`.
        """
        from django.utils import timezone

        sp_artist_id = client.search_isrc_principal_artist(isrc)
        now = timezone.now()
        with transaction.atomic():
            qs = HistorialRevisio.objects.filter(canco_isrc=isrc)
            if sp_artist_id:
                qs.filter(artista_spotify_id="").update(
                    artista_spotify_id=sp_artist_id,
                    spotify_lookup_at=now,
                )
                # Rows that already had artista_spotify_id keep it;
                # only the stamp moves so we do not re-try them.
                qs.exclude(artista_spotify_id="").update(spotify_lookup_at=now)
            else:
                qs.update(spotify_lookup_at=now)
        return "found" if sp_artist_id else "not_found"

    # ── per-candidate ───────────────────────────────────────────────
    def _enrich_one(self, client: UserSpotifyClient, canco: Canco) -> str:
        """Run search + track + artist for one cançó, persist the
        result, then copy the resolved spotify_artist_id onto every
        matching HistorialRevisio row.

        Returns the outcome string of the SpotifyMetadata write
        (`found` / `not_found` / `error`)."""
        sm, _ = SpotifyMetadata.objects.get_or_create(canco=canco)
        # `search_isrc` returns a Spotify URI (`spotify:track:<id>`),
        # while `get_track` and the rest of the persistence layer
        # expect the bare ID. Mirrors the strip the maintenance
        # command does at `enriquir_spotify.py::_enrich_one`. Without
        # this strip the next call returns 400 Bad Request and the
        # backfill cannot enrich a single cançó (caught on the first
        # wet run on 2026-05-26).
        uri = client.search_isrc(canco.isrc)
        if not uri:
            sm.enrichment_status = SpotifyMetadata.STATUS_NOT_FOUND
            sm.save(update_fields=["enrichment_status", "updated_at"])
            return "not_found"
        spotify_id = uri.rsplit(":", 1)[-1]

        track = client.get_track(spotify_id)
        if not track:
            sm.enrichment_status = SpotifyMetadata.STATUS_NOT_FOUND
            sm.save(update_fields=["enrichment_status", "updated_at"])
            return "not_found"

        principal_id = ""
        all_ids: list[str] = []
        for a in track.get("artists") or []:
            aid = (a or {}).get("id") or ""
            if not aid:
                continue
            if not principal_id:
                principal_id = aid
            all_ids.append(aid)
        artist_payload = (
            client.get_artist(principal_id) if principal_id else None
        ) or {}

        with transaction.atomic():
            sm.spotify_id = spotify_id
            sm.spotify_artist_id = principal_id
            sm.spotify_artist_ids = all_ids
            sm.spotify_artist_name = artist_payload.get("name") or ""
            sm.genres = artist_payload.get("genres") or []
            sm.images = artist_payload.get("images") or []
            sm.duration_ms = track.get("duration_ms") or None
            sm.explicit = track.get("explicit") or False
            sm.is_playable = track.get("is_playable") or False
            sm.enrichment_status = SpotifyMetadata.STATUS_FOUND
            sm.save()
            if principal_id and canco.deezer_id is not None:
                # Copy the freshly-resolved spotify_artist_id onto
                # every historical decision that referenced this
                # canco_deezer_id (typically the rejection rows we
                # are draining).
                HistorialRevisio.objects.filter(
                    canco_deezer_id=canco.deezer_id,
                    artista_spotify_id="",
                ).update(artista_spotify_id=principal_id)
        return "found"
