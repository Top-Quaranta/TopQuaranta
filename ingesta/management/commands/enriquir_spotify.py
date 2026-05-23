"""Spotify enrichment cron (Process B).

Per ADR-0012 and docs/architecture/playlists.md "Spotify enrichment
(Process B)". One-shot per Canço: /v1/search by ISRC, then
/v1/tracks/{id} and /v1/artists/{principal_id}; persist the result on
SpotifyMetadata. Process A (actualitzar_playlists_spotify, FASE 5)
reads spotify_id from that table; this command is the only place
that calls /search.

Ordering (FASE 0 "opció C compost"):
  1. Public Cançons (verificada=True, activa=True) ordered by the
     most recent SenyalDiari.lastfm_playcount desc (proxy for "in
     the ranking right now"), NULLs last.
  2. Pending Cançons (verificada=False, activa=True) ordered by
     ml_confianca desc, NULLs last. These are the tracks the
     classifier thinks are likely to be approved soon.

Both subsets restrict to enrichment_status="not_attempted". Cançons
already enriched (found OR not_found) are skipped unless --retry-not-
found is set, in which case the not_found subset is appended (oldest
enriched_at first so we cycle through evenly).

--target-playlists narrows the source pool to Cançons currently
appearing in any active SpotifyPlaylist (top + no_verificades
windows). Used for the first run after a long cold-cache period to
fill the playlists quickly before walking the broader backlog.

Resilience (updated 2026-05-23): RateLimitedError writes a cooldown
file and exits cleanly (exit 0) so the watchdog does NOT see a FAIL.
Subsequent cron ticks check the cooldown file and skip silently until
the Retry-After window has passed. Per-Canço commits mean a mid-run
abort never wastes the work already done.

# Spec: docs/architecture/playlists.md (Process B section)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_tz
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, OuterRef, Subquery
from django.utils import timezone

from ingesta.clients.spotify import RateLimitedError, UserSpotifyClient
from music.models import Canco, SpotifyAuth, SpotifyMetadata, SpotifyPlaylist
from music.spotify_dispersio import recalcular_dispersio
from ranking.models import SenyalDiari

logger = logging.getLogger(__name__)

COOLDOWN_FILE = Path("/var/log/topquaranta/status/enriquir_spotify.cooldown")

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

    def handle(self, *args, **opts):
        # ── Cooldown gate: skip silently if a previous run set a
        # cooldown (Retry-After was too long). The cron fires every
        # 30 min; we don't want 4+ wasted runs per cooldown window.
        cooldown_file = COOLDOWN_FILE
        if cooldown_file.exists():
            try:
                resume_at = datetime.fromisoformat(cooldown_file.read_text().strip())
                if datetime.now(tz=dt_tz.utc).replace(tzinfo=None) < resume_at:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[enriquir_spotify] Spotify cooldown active "
                            f"until {resume_at.isoformat()}. Skipping."
                        )
                    )
                    return
            except (ValueError, OSError):
                pass  # corrupt file — fall through and delete it
            cooldown_file.unlink(missing_ok=True)

        auth = SpotifyAuth.load()
        if not auth:
            raise CommandError("No SpotifyAuth row. Run the staff OAuth flow first.")

        throttle = opts["throttle"]
        limit = opts["limit"]
        retry_not_found = opts["retry_not_found"]
        target_playlists = opts["target_playlists"]

        client = UserSpotifyClient(auth, throttle_s=throttle)

        candidates = self._select_candidates(
            limit=limit,
            retry_not_found=retry_not_found,
            target_playlists=target_playlists,
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
        affected_artist_ids: set[int] = set()
        aborted = False

        try:
            for canco in candidates:
                outcome = self._enrich_one(client, canco)
                processed += 1
                if outcome == "found":
                    found += 1
                    affected_artist_ids.add(canco.artista_id)
                elif outcome == "not_found":
                    not_found += 1
        except RateLimitedError as exc:
            # Spotify asked us to back off for hours. Write a cooldown
            # file so subsequent cron ticks skip silently, and exit 0
            # so the watchdog does NOT flip status=FAIL. Cap at
            # MAX_COOLDOWN_S to ignore absurd values without
            # under-cutting Spotify's own back-off signal.
            aborted = True
            effective_cooldown_s = min(exc.retry_after_s, MAX_COOLDOWN_S)
            resume_at = datetime.now(tz=dt_tz.utc).replace(tzinfo=None) + timedelta(
                seconds=effective_cooldown_s
            )
            try:
                COOLDOWN_FILE.write_text(resume_at.isoformat())
            except OSError:
                logger.warning("Could not write cooldown file %s", COOLDOWN_FILE)
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
    ) -> list[Canco]:
        """Build the ordered candidate list per FASE 0 "opció C" rules.

        Returns a Python list (not a queryset) because we splice from
        two differently-ordered subsets (public by Last.fm playcount,
        pending by ml_confianca). The list is truncated at `limit`.
        """
        # Latest SenyalDiari.lastfm_playcount per Canço, used as the
        # ordering signal for public cançons. NULLs last keeps cançons
        # that never got a signal at the tail.
        latest_pc = (
            SenyalDiari.objects.filter(canco=OuterRef("pk"))
            .order_by("-data")
            .values("lastfm_playcount")[:1]
        )

        base = Canco.objects.filter(
            spotify__enrichment_status=SpotifyMetadata.STATUS_NOT_ATTEMPTED
        ).exclude(isrc="")
        if target_playlists:
            # Restrict to the Cançons currently selected by Process A
            # for any active playlist. We compute the union of:
            # - the top-N TopProvisional cançons per playlist territori
            # - the no_verificades window (verificada=False, activa=True,
            #   ordered by ml_confianca desc, capped at the 7*100 window).
            base = base.filter(pk__in=self._target_playlist_pks())

        public_qs = (
            base.filter(verificada=True, activa=True)
            .annotate(_pc=Subquery(latest_pc))
            .order_by(F("_pc").desc(nulls_last=True))
        )
        pending_qs = base.filter(verificada=False, activa=True).order_by(
            F("ml_confianca").desc(nulls_last=True), "-created_at"
        )

        # Materialise both head segments up to `limit` so we don't
        # over-fetch.
        public = list(public_qs[:limit])
        result = list(public)
        remaining = limit - len(public)
        if remaining > 0:
            seen_pks = {c.pk for c in public}
            for c in pending_qs[: remaining + len(seen_pks)]:
                # The intersection guard handles the rare case where a
                # Canço changes verificada flag mid-run; cheap O(1) hit.
                if c.pk in seen_pks:
                    continue
                result.append(c)
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
    def _enrich_one(self, client: UserSpotifyClient, canco: Canco) -> str:
        """Resolve one Canco via search + get_track + get_artist.

        Returns "found" / "not_found". Writes the SpotifyMetadata row
        in a transaction so a mid-batch abort never leaves a partial
        update.
        """
        sm = canco.spotify  # OneToOne reverse accessor
        now = timezone.now()

        # Step 1: search by ISRC.
        uri = client.search_isrc(canco.isrc)
        if not uri:
            with transaction.atomic():
                sm.enrichment_status = SpotifyMetadata.STATUS_NOT_FOUND
                sm.enriched_at = now
                sm.save(update_fields=["enrichment_status", "enriched_at"])
            return "not_found"

        spotify_id = uri.rsplit(":", 1)[-1]

        # Step 2: full track JSON.
        track = client.get_track(spotify_id)
        if not track:
            # search said yes but get_track 404'd: treat as not_found.
            with transaction.atomic():
                sm.enrichment_status = SpotifyMetadata.STATUS_NOT_FOUND
                sm.enriched_at = now
                sm.save(update_fields=["enrichment_status", "enriched_at"])
            return "not_found"

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
            sm.enrichment_status = SpotifyMetadata.STATUS_FOUND
            sm.enriched_at = now
            sm.save()
            # Keep the legacy Canco.spotify_id in sync so any legacy
            # consumer reading from there sees the same value. New
            # code should read sm.spotify_id directly.
            if canco.spotify_id != spotify_id:
                Canco.objects.filter(pk=canco.pk).update(spotify_id=spotify_id)
        return "found"
