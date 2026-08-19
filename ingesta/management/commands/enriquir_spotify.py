"""Spotify enrichment cron (Process B).

Per ADR-0012 and docs/architecture/playlists.md "Spotify enrichment
(Process B)". One-shot per Canço: /v1/search by ISRC, then
/v1/tracks/{id} and /v1/artists/{principal_id}; persist the result on
SpotifyMetadata. Process A (actualitzar_playlists_spotify, FASE 5)
reads spotify_id from that table; this command is the only place
that calls /search.

Ordering (FASE 0 "opció C compost") with a pending equity floor:
  1. Pending Cançons (verificada=False, activa=True) ordered by
     ml_confianca desc, NULLs last — these get a RESERVED floor of the
     run's slots (`--pending-floor-frac`, default 0.5) so they don't
     starve behind the verified backlog. The classifier thinks these
     are likely to be approved soon.
  2. Public Cançons (verificada=True, activa=True) ordered by the most
     recent SenyalDiari.lastfm_playcount desc (proxy for "in the
     ranking right now"), NULLs last — fill the remaining slots.
If either pool underfills, the leftover spills to the other (pending
first) so no API call is wasted; the batch is processed pending-first
so the reserved floor survives a mid-run abort. Same total load.

Candidate visibility is a LEFT JOIN on SpotifyMetadata: a Canço with NO
row has never been attempted, so it counts exactly like
enrichment_status="not_attempted" (the row is created lazily on
enrichment). `isrc` must be non-NULL and non-empty. Cançons already
enriched (found OR not_found) are skipped unless --retry-not-found is
set, in which case the not_found subset is appended (oldest enriched_at
first so we cycle through evenly).

--target-playlists narrows the source pool to Cançons currently
appearing in any active SpotifyPlaylist (top + no_verificades
windows). Used for the first run after a long cold-cache period to
fill the playlists quickly before walking the broader backlog.

Resilience (updated 2026-05-23): RateLimitedError writes a cooldown
file and exits cleanly (exit 0) so the watchdog does NOT see a FAIL.
Subsequent cron ticks check the cooldown file and skip silently until
the Retry-After window has passed. Per-Canço commits mean a mid-run
abort never wastes the work already done.

# Spec: docs/architecture/ingesta.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_tz
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Max, OuterRef, Q, Subquery
from django.utils import timezone

from ingesta.caducitat import exclude_caducats
from ingesta.clients.spotify import RateLimitedError, UserSpotifyClient
from music.models import Canco, SpotifyAuth, SpotifyMetadata, SpotifyPlaylist
from music.spotify_dispersio import recalcular_dispersio
from ranking.models import SenyalDiari

logger = logging.getLogger(__name__)

# Legacy per-command cooldown path. Reads still happen via
# `spotify_metadata_cooldown.LEGACY_PATHS` for the transition
# window so a live ban from the old binary keeps being honoured.
# New writes go to the shared `spotify_metadata.cooldown`.
LEGACY_COOLDOWN_FILE = Path("/var/log/topquaranta/status/enriquir_spotify.cooldown")

# Maximum cooldown we will honour from Spotify's Retry-After header.
# Empirically Spotify's rate-limit windows are persistent (the ban
# survives the per-minute bucket reset), and probing /search during
# an active cooldown extends it. Clamping to 24h means: respect any
# value Spotify gives us up to one day, and treat anything beyond
# that as an absurd outlier we still cap. We deliberately do NOT
# clamp aggressively (e.g. 1h) because reintenting earlier than
# Spotify asks tends to re-trigger or worsen the abuse-pattern flag.
MAX_COOLDOWN_S = 86400


class Command(BaseCommand):
    help = "Enrich Cançons with Spotify metadata (Process B)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Max cançons to process this run.",
        )
        parser.add_argument(
            "--throttle",
            type=float,
            default=0.5,
            help=(
                "Seconds between Spotify API calls. Default 0.5 is "
                "conservative enough for /search; raise to 1.0 for the "
                "first cold-cache run after a Spotify cooldown."
            ),
        )
        parser.add_argument(
            "--retry-not-found",
            action="store_true",
            help=(
                "Also re-process Cançons previously flagged not_found, "
                "oldest enriched_at first."
            ),
        )
        parser.add_argument(
            "--target-playlists",
            action="store_true",
            help=(
                "Restrict to Cançons currently in any active "
                "SpotifyPlaylist. Used for the first run after a long "
                "cold-cache period."
            ),
        )
        parser.add_argument(
            "--pending-floor-frac",
            type=float,
            default=0.5,
            help=(
                "Fraction of `--limit` reserved for PENDING (verificada="
                "False) cançons each run, so they don't starve behind the "
                "verified backlog. Default 0.5. Unused floor slots spill to "
                "the verified pool and vice-versa, so no API call is wasted."
            ),
        )
        parser.add_argument(
            "--hydrate-limit",
            type=int,
            default=50,
            help=(
                "Max manual Spotify links to hydrate per run (phase 2, "
                "AFTER the /search pass). Manual links already carry a "
                "staff-pasted id, so hydration is get_track + get_artist "
                "only — NO /search. Conservative default 50: those two "
                "GETs share the rate-limit bucket with /search, so a big "
                "hydration burst could indirectly pressure the /search "
                "window. Manual links are few, so 50 is ample; tune up "
                "for a one-off backlog drain."
            ),
        )

    def handle(self, *args, **opts):
        # Cooldown gate. The metadata-read bucket (`/v1/search`,
        # `/v1/tracks`, `/v1/artists`) is shared with the backfill
        # command (`enriquir_spotify_rebuigs`), so both honour the
        # same shared cooldown file plus the legacy per-command
        # files (transition). Skip silently when any ban is still
        # active; an active ban is documented to be extended by
        # probing during its window.
        from ingesta.clients import spotify_metadata_cooldown as cd

        resume_at = cd.active_resume_at()
        if resume_at is not None:
            self.stdout.write(
                self.style.WARNING(
                    f"[enriquir_spotify] Spotify metadata cooldown "
                    f"active until {resume_at.isoformat()}. Skipping."
                )
            )
            return
        cd.clear_expired()

        auth = SpotifyAuth.load()
        if not auth:
            raise CommandError("No SpotifyAuth row. Run the staff OAuth flow first.")

        throttle = opts["throttle"]
        limit = opts["limit"]
        retry_not_found = opts["retry_not_found"]
        target_playlists = opts["target_playlists"]
        pending_floor_frac = opts["pending_floor_frac"]
        if not 0.0 <= pending_floor_frac <= 1.0:
            raise CommandError("--pending-floor-frac must be in [0.0, 1.0].")
        hydrate_limit = opts["hydrate_limit"]

        client = UserSpotifyClient(auth, throttle_s=throttle)

        candidates = self._select_candidates(
            limit=limit,
            retry_not_found=retry_not_found,
            target_playlists=target_playlists,
            pending_floor_frac=pending_floor_frac,
        )
        self.stdout.write(
            f"[enriquir_spotify] {len(candidates)} candidates "
            f"(limit={limit}, throttle={throttle}, "
            f"retry_not_found={retry_not_found}, "
            f"target_playlists={target_playlists})"
        )

        processed = 0
        found = 0
        not_found = 0
        hydrated = 0
        hydrate_failed = 0
        affected_artist_ids: set[int] = set()
        aborted = False

        try:
            # Phase 1: the /search pass over not_attempted / no-row
            # cançons (manual links are excluded from this queue).
            for canco in candidates:
                outcome = self._enrich_one(client, canco)
                processed += 1
                if outcome == "found":
                    found += 1
                    affected_artist_ids.add(canco.artista_id)
                elif outcome == "not_found":
                    not_found += 1

            # Phase 2: hydrate pending manual links from their known id —
            # NO /search. Inside the same try so a RateLimitedError here
            # also writes the shared cooldown (these GETs share the
            # bucket). Cooldown-gated at the top of handle(), so during a
            # ban this whole run (incl. hydration) is skipped.
            hydrate_candidates = self._select_hydration_candidates(limit=hydrate_limit)
            for canco in hydrate_candidates:
                outcome = self._hydrate_manual_one(client, canco)
                if outcome == "found":
                    hydrated += 1
                    affected_artist_ids.add(canco.artista_id)
                else:
                    # 404 on a staff-pasted id — kept as manual, stamped,
                    # not retried. Surfaces as "failed" in the editor.
                    hydrate_failed += 1
        except RateLimitedError as exc:
            # Spotify asked us to back off for hours. Write the
            # shared metadata cooldown so the backfill command and
            # this command both skip subsequent runs. Exit 0 so the
            # watchdog does NOT flip status=FAIL. Cap at
            # MAX_COOLDOWN_S to ignore absurd values without
            # under-cutting Spotify's own back-off signal.
            from ingesta.clients import spotify_metadata_cooldown as cd

            aborted = True
            effective_cooldown_s = min(exc.retry_after_s, MAX_COOLDOWN_S)
            resume_at = datetime.now(tz=dt_tz.utc).replace(tzinfo=None) + timedelta(
                seconds=effective_cooldown_s
            )
            try:
                cd.write(resume_at)
            except OSError:
                logger.warning("Could not write cooldown file %s", cd.SHARED_PATH)
            self.stdout.write(
                self.style.WARNING(
                    f"[enriquir_spotify] Spotify rate limited; "
                    f"cooldown until {resume_at.isoformat()}. "
                    f"Partial progress saved."
                )
            )

        # Recompute dispersion only for the artists we touched. The
        # full-DB recalc lives in `recalcular_dispersio_spotify` for
        # explicit operator use.
        if affected_artist_ids:
            recalcular_dispersio(artista_ids=affected_artist_ids)

        self.stdout.write(
            f"[enriquir_spotify] done: processed={processed} "
            f"found={found} not_found={not_found} "
            f"hydrated_manual={hydrated} hydrate_failed={hydrate_failed} "
            f"artists_recomputed={len(affected_artist_ids)} "
            f"aborted={aborted}"
        )

    # ── candidate selection ─────────────────────────────────────────────
    def _select_candidates(
        self,
        *,
        limit: int,
        retry_not_found: bool,
        target_playlists: bool,
        pending_floor_frac: float = 0.5,
    ) -> list[Canco]:
        """Build the ordered candidate list by PRIORITY TIERS (2026-06).

        Tiers, always processed in this order so a charting song never
        waits behind the backlog:
          1. Cançons in the current public top (latest TopSetmanal, any
             territori).
          2. Cançons in the provisional top (TopProvisional, any territori).
          3. Pending (verificada=False, activa=True) WITH an ml_confianca,
             most confident first.
          4. Pending WITHOUT an ml_confianca, oldest first.
          5. The rest (verified backlog etc.), by Last.fm playcount desc.

        Every tier draws from the same not_attempted + non-empty-ISRC
        `base` (a Canço with no SpotifyMetadata row counts as
        `not_attempted`; the row is created lazily by `_enrich_one`). The
        two pending tiers keep the caducitat guard (the 04:00 purge only
        sweeps `verificada=False`); the top tiers are current-chart so are
        never caducades, and tier 5 is verified so the purge never touches
        it. `pending_floor_frac` is accepted for back-compat but unused
        (the tiers subsume the old equity floor). Truncated at `limit`.
        """
        from ranking.models import TopProvisional, TopSetmanal

        latest_pc = (
            SenyalDiari.objects.filter(canco=OuterRef("pk"))
            .order_by("-data")
            .values("lastfm_playcount")[:1]
        )

        base = (
            Canco.objects.filter(
                Q(spotify__isnull=True)
                | Q(spotify__enrichment_status=SpotifyMetadata.STATUS_NOT_ATTEMPTED)
            )
            .filter(isrc__isnull=False)
            .exclude(isrc="")
        )
        if target_playlists:
            base = base.filter(pk__in=self._target_playlist_pks())

        # Tier-membership id sets (current charts, any territori).
        latest_setmana = TopSetmanal.objects.aggregate(m=Max("setmana"))["m"]
        top_pks = (
            set(
                TopSetmanal.objects.filter(setmana=latest_setmana).values_list(
                    "canco_id", flat=True
                )
            )
            if latest_setmana is not None
            else set()
        )
        prov_pks = set(TopProvisional.objects.values_list("canco_id", flat=True))

        pending_base = exclude_caducats(base.filter(verificada=False, activa=True))
        tiers = [
            base.filter(pk__in=top_pks),  # 1: public top
            base.filter(pk__in=prov_pks),  # 2: provisional top
            pending_base.filter(ml_confianca__isnull=False).order_by(  # 3: ML
                F("ml_confianca").desc()
            ),
            pending_base.filter(ml_confianca__isnull=True).order_by(  # 4: by date
                "created_at"
            ),
            base.filter(verificada=True)  # 5: verified backlog
            .annotate(_pc=Subquery(latest_pc))
            .order_by(F("_pc").desc(nulls_last=True)),
        ]
        # NOTE tier 5 is verified-only: every non-caducat pending is
        # already in tiers 3/4, and caducat pending must NEVER be selected
        # (the 04:00 purge deletes it), so it is excluded from every tier.

        result: list[Canco] = []
        seen: set[int] = set()
        for tier in tiers:
            if len(result) >= limit:
                break
            for c in tier[:limit]:
                if c.pk in seen:
                    continue
                result.append(c)
                seen.add(c.pk)
                if len(result) >= limit:
                    break

        if retry_not_found and len(result) < limit:
            # Append not_found Cançons oldest first so each retry cycle
            # walks the whole pool evenly.
            retry_qs = (
                Canco.objects.filter(
                    spotify__enrichment_status=SpotifyMetadata.STATUS_NOT_FOUND,
                    activa=True,
                )
                .exclude(isrc="")
                .order_by("spotify__enriched_at")
            )
            seen_pks = {c.pk for c in result}
            for c in retry_qs[: limit - len(result) + len(seen_pks)]:
                if c.pk in seen_pks:
                    continue
                result.append(c)
                if len(result) >= limit:
                    break

        return result[:limit]

    def _target_playlist_pks(self) -> list[int]:
        """The Canco pks that Process A is currently expected to push.

        Mirrors Process A's queries: top playlists pull from
        TopProvisional (top 40 per territori); no_verificades pulls
        from Canco.objects.pendents() top 700 by ml_confianca.
        """
        from ranking.models import TopProvisional

        pks: set[int] = set()
        for pl in SpotifyPlaylist.objects.exclude(spotify_playlist_id=""):
            if pl.kind == SpotifyPlaylist.KIND_TOP:
                rows = TopProvisional.objects.filter(territori=pl.territori).order_by(
                    "posicio"
                )[:40]
                pks.update(rows.values_list("canco_id", flat=True))
            elif pl.kind == SpotifyPlaylist.KIND_NO_VERIFICADES:
                # The 7 chunks together cover the 700 most-likely
                # pending Cançons; we don't need per-chunk granularity
                # here because we just want the union.
                window_pks = (
                    Canco.objects.pendents()
                    .exclude(isrc="")
                    .order_by(F("ml_confianca").desc(nulls_last=True), "-created_at")[
                        :700
                    ]
                    .values_list("pk", flat=True)
                )
                pks.update(window_pks)
        return list(pks)

    # ── per-Canço enrichment ────────────────────────────────────────────
    def _resolve_spotify_id(
        self, client: UserSpotifyClient, canco: Canco
    ) -> str | None:
        """Step 1 ONLY: resolve a Spotify track id from the Canço's ISRC
        via `/v1/search`. Returns the bare 22-char id, or None when
        Spotify has no match for the ISRC. This is the rate-limited,
        ban-prone call — split out so a caller that already knows the id
        can skip it entirely.
        """
        uri = client.search_isrc(canco.isrc)
        return uri.rsplit(":", 1)[-1] if uri else None

    def _mark_not_found(
        self, sm: SpotifyMetadata, status: str = SpotifyMetadata.STATUS_NOT_FOUND
    ) -> str:
        """Stamp a SpotifyMetadata row as attempted-but-unresolved and
        return "not_found". `status` is the status written: NOT_FOUND for
        an automatic search-miss; MANUAL for a manual id whose get_track
        404'd, so the row keeps its staff-pasted id and surfaces as a
        failed hydration (enriched_at stamped, spotify_artist_id empty)
        rather than vanishing. Single-statement transaction so a
        mid-batch abort never leaves a partial update."""
        with transaction.atomic():
            sm.enrichment_status = status
            sm.enriched_at = timezone.now()
            sm.save(update_fields=["enrichment_status", "enriched_at"])
        return "not_found"

    def _hydrate_from_id(
        self,
        client: UserSpotifyClient,
        canco: Canco,
        sm: SpotifyMetadata,
        spotify_id: str,
        *,
        final_status: str = SpotifyMetadata.STATUS_FOUND,
        not_found_status: str = SpotifyMetadata.STATUS_NOT_FOUND,
    ) -> str:
        """Steps 2-3: fetch the full track + artist JSON for a KNOWN
        `spotify_id` and write the complete SpotifyMetadata row. Does
        NOT call `/v1/search`. Returns "found" / "not_found" (the latter
        when `get_track` 404s — a takedown / stale id). Writes inside a
        transaction so a mid-batch abort never leaves a partial update.

        `final_status` is written on success — FOUND for the automatic
        path, MANUAL to preserve a staff link's provenance.
        `not_found_status` is written when get_track 404s — NOT_FOUND
        automatically, MANUAL for a manual id so it keeps the id and
        lands in the "failed hydration" state instead of disappearing.
        """
        # Step 2: full track JSON.
        track = client.get_track(spotify_id)
        if not track:
            # id resolved but get_track 404'd: treat as not_found.
            return self._mark_not_found(sm, status=not_found_status)

        artists = track.get("artists") or []
        principal = artists[0] if artists else {}
        principal_id = principal.get("id", "")

        # Step 3: artist JSON (best-effort: if it 404s we still keep
        # the track data).
        artist_payload = None
        if principal_id:
            artist_payload = client.get_artist(principal_id)

        album = track.get("album") or {}

        with transaction.atomic():
            sm.spotify_id = spotify_id
            sm.spotify_artist_id = principal_id
            sm.spotify_artist_ids = [a.get("id", "") for a in artists if a.get("id")]
            sm.spotify_artist_name = (artist_payload or {}).get(
                "name"
            ) or principal.get("name", "")
            sm.album_type = album.get("album_type", "")
            sm.release_date = album.get("release_date", "") or ""
            sm.duration_ms = track.get("duration_ms")
            sm.explicit = track.get("explicit")
            sm.is_playable = track.get("is_playable")
            sm.images = album.get("images") or []
            sm.genres = (artist_payload or {}).get("genres") or []
            sm.enrichment_status = final_status
            sm.enriched_at = timezone.now()
            sm.save()
            # Keep the legacy Canco.spotify_id in sync so any legacy
            # consumer reading from there sees the same value. New
            # code should read sm.spotify_id directly.
            if canco.spotify_id != spotify_id:
                Canco.objects.filter(pk=canco.pk).update(spotify_id=spotify_id)
        return "found"

    def _enrich_one(self, client: UserSpotifyClient, canco: Canco) -> str:
        """Automatic path: resolve one Canco via search, then hydrate.

        Behaviour-preserving wrapper over `_resolve_spotify_id` +
        `_hydrate_from_id`. Returns "found" / "not_found".
        """
        # Lazy row creation (Option A): a candidate may have no
        # SpotifyMetadata row yet (LEFT-JOIN visibility). get_or_create
        # gives it one in its default `not_attempted` state before we
        # write the outcome below.
        sm, _ = SpotifyMetadata.objects.get_or_create(canco=canco)

        # Step 1: search by ISRC.
        spotify_id = self._resolve_spotify_id(client, canco)
        if not spotify_id:
            return self._mark_not_found(sm)

        # Steps 2-3: hydrate from the resolved id.
        return self._hydrate_from_id(client, canco, sm, spotify_id)

    # ── manual-link hydration (NO /search) ──────────────────────────────
    def _select_hydration_candidates(self, *, limit: int) -> list[Canco]:
        """Manual Spotify links awaiting hydration: `status=manual` with
        `enriched_at IS NULL` (never hydrated). They already carry a
        staff-pasted `spotify_id`, so they skip `/v1/search` entirely —
        Process B hydrates them with get_track + get_artist only. Oldest
        manual edit first (`spotify.updated_at`). A 404 or a successful
        hydration stamps `enriched_at`, dropping the row from this query
        so nothing is retried forever.
        """
        return list(
            Canco.objects.filter(
                spotify__enrichment_status=SpotifyMetadata.STATUS_MANUAL,
                spotify__enriched_at__isnull=True,
            )
            .select_related("spotify")
            .order_by("spotify__updated_at", "pk")[:limit]
        )

    def _hydrate_manual_one(self, client: UserSpotifyClient, canco: Canco) -> str:
        """Hydrate one manual link from its known `spotify_id` — NO
        `/v1/search`. Preserves `status=manual` both on success and on a
        404 (the latter being the "failed hydration" state: id kept,
        enriched_at stamped, spotify_artist_id still empty). Returns
        "found" / "not_found".
        """
        sm = canco.spotify
        return self._hydrate_from_id(
            client,
            canco,
            sm,
            sm.spotify_id,
            final_status=SpotifyMetadata.STATUS_MANUAL,
            not_found_status=SpotifyMetadata.STATUS_MANUAL,
        )
