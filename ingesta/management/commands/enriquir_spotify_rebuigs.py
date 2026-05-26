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
from django.db import transaction

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

    def handle(self, *args, **opts):
        # Cooldown gate. Reads the SHARED metadata cooldown (plus
        # the legacy per-command files during the transition). If
        # the maintenance enrichment was banned, we must skip too:
        # both commands hit `/v1/search`, `/v1/tracks` and
        # `/v1/artists`, which share a single Spotify quota
        # bucket, and probing during an active ban is documented
        # to extend the window.
        from ingesta.clients import spotify_metadata_cooldown as cd

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
        cd.clear_expired()

        auth = SpotifyAuth.load()
        if not auth:
            raise CommandError("No SpotifyAuth row. Run the staff OAuth flow first.")

        # AIMD controller decides the daily limit. The controller
        # inspects both cooldown files (this command's and
        # `enriquir_spotify`'s) so a ban observed by the maintenance
        # enrichment converges the backfill's limit too. A manual
        # `--limit` override skips the controller for this run and
        # leaves the persisted state untouched.
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

        throttle = opts["throttle"]
        shortlist_only = opts["shortlist_only"]
        client = UserSpotifyClient(auth, throttle_s=throttle)

        candidates = self._select_candidates(limit=limit, shortlist_only=shortlist_only)
        self.stdout.write(
            f"[enriquir_spotify_rebuigs] {len(candidates)} candidates "
            f"(limit={limit}, throttle={throttle}, "
            f"shortlist_only={shortlist_only})"
        )

        processed = 0
        found = 0
        aborted = False
        try:
            for canco in candidates:
                outcome = self._enrich_one(client, canco)
                processed += 1
                if outcome == "found":
                    found += 1
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

        self.stdout.write(
            f"[enriquir_spotify_rebuigs] done: processed={processed} "
            f"found={found} aborted={aborted}"
        )

    # ── candidate selection ────────────────────────────────────────
    def _select_candidates(self, *, limit: int, shortlist_only: bool) -> list[Canco]:
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

        hr_priority = (
            HistorialRevisio.objects.filter(
                decisio="rebutjada",
                artista_deezer_id__in=shortlist,
            )
            .exclude(canco_isrc="")
            .exclude(canco_deezer_id__isnull=True)
            .exclude(canco_deezer_id__in=enriched_dz)
            .order_by("created_at")
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
                .order_by("created_at")
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
