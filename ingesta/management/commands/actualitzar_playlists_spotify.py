"""Spotify playlist sync (Process A). CACHE-ONLY since 2026-05-22.

For each configured `SpotifyPlaylist`:
  * kind=top: TopProvisional.filter(territori=X) ordered by posicio,
    capped at 40. One row per ranking territori (PPCC + 4 territories).
  * kind=novetats: Canco with data_llancament = yesterday, activa=True,
    capped at 100. Currently parked (no row in prod since FASE C).
  * kind=no_verificades: Canco.objects.pendents() (verificada=False AND
    activa=True), ordered by ml_confianca desc, sliced into 7 non-
    overlapping chunks of 100. Mirrors the /staff/cancons workbench
    exactly (single source of truth via Canco.objects.pendents()).

DESIGN: This command is the DISTRIBUTION half of the Process A / B
split. It NEVER calls /v1/search. It reads spotify_id from
SpotifyMetadata.spotify_id and turns it into a URI for the playlist
write. Cançons whose SpotifyMetadata is in status="found" go in;
status="not_attempted" and status="not_found" are skipped silently.

Why this separation: /v1/search has the tightest Spotify rate-limit
bucket and the previous "search-on-demand" approach made every cron
run hit /search hundreds of times against a cold cache, which on
2026-05-22 triggered a 24h Retry-After ban. Splitting search into a
separate, throttled, idempotent Process B (`enriquir_spotify`) makes
this command deterministic and safe to run on any cadence.

The Spotify playlist is rewritten in place via PUT /playlists/<id>/
items so the public URL + follower count survive every run.

# Spec: docs/architecture/playlists.md (Process A)
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ingesta.clients.spotify import RateLimitedError, UserSpotifyClient
from music.models import Canco, SpotifyAuth, SpotifyMetadata, SpotifyPlaylist
from ranking.models import TopProvisional, TopSetmanal

# Total window pulled from the unverified backlog. 7 chunks * 100 = 700
# slots across 7 Spotify playlists; the rest of the backlog (anything
# older) is not surfaced for triage.
NO_VERIF_WINDOW = 700
NO_VERIF_CHUNK_SIZE = 100


class Command(BaseCommand):
    help = (
        "Spotify playlist sync (Process A). Cache-only since 2026-05-22; "
        "never calls /search. Run enriquir_spotify (Process B) to fill cache."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute the URI lists but don't write to Spotify.",
        )
        parser.add_argument(
            "--only",
            default="",
            help="Sync only the playlist with this codi (else: all).",
        )
        parser.add_argument(
            "--throttle",
            type=float,
            default=None,
            help=(
                "Seconds to wait between Spotify API calls. Defaults to "
                "UserSpotifyClient.DEFAULT_THROTTLE_S (0.2). Used only "
                "for the playlist write endpoint; cache-only sync has "
                "no search calls."
            ),
        )
        parser.add_argument(
            "--freq",
            default="",
            choices=("", "daily", "weekly"),
            help=(
                "Filter playlists by SpotifyPlaylist.freq. 'daily' "
                "covers the rolling top playlists + no_verificades "
                "triage; 'weekly' covers the published weekly chart "
                "mirror playlists (TopSetmanal-based, FASE D). "
                "Empty (default) syncs every configured playlist "
                "regardless of cadence."
            ),
        )

    def handle(self, *args, **opts):
        auth = SpotifyAuth.load()
        if not auth:
            raise CommandError(
                "No hi ha autorització Spotify. Executa "
                "`manage.py autoritzar_spotify` primer."
            )

        throttle = opts.get("throttle")
        client = UserSpotifyClient(auth, throttle_s=throttle)

        qs = SpotifyPlaylist.objects.exclude(spotify_playlist_id="")
        only = (opts.get("only") or "").strip()
        if only:
            # --only wins over --freq: if the operator names a specific
            # playlist, that is the one row to sync regardless of freq.
            qs = qs.filter(codi=only)
        else:
            freq = (opts.get("freq") or "").strip()
            if freq:
                qs = qs.filter(freq=freq)
        playlists = list(qs)
        if not playlists:
            self.stdout.write(
                self.style.WARNING(
                    "Cap SpotifyPlaylist amb spotify_playlist_id configurat. "
                    "Executa `configurar_spotify_playlists` primer."
                )
            )
            return

        # Materialise the no_verificades window ONCE per run, not once per
        # playlist: 7 separate queries would all hit the same scan + sort.
        # We slice from the cached list per chunk_index inside
        # `_select_cancons`. Same ordering rationale as before
        # (ml_confianca desc, created_at desc tiebreak, nulls_last).
        self._no_verif_window: list[Canco] | None = None
        if any(pl.kind == SpotifyPlaylist.KIND_NO_VERIFICADES for pl in playlists):
            self._no_verif_window = list(
                Canco.objects.pendents()
                .exclude(isrc="")
                .order_by(F("ml_confianca").desc(nulls_last=True), "-created_at")[
                    :NO_VERIF_WINDOW
                ]
            )
            self.stdout.write(
                f"[no_verificades] window carregada: "
                f"{len(self._no_verif_window)} cançons "
                f"(top {NO_VERIF_WINDOW} per ml_confianca desc)"
            )

        dry = opts.get("dry_run", False)
        sync_aborted = False
        for pl in playlists:
            try:
                self._sync_one(client, pl, dry)
            except RateLimitedError as exc:
                # Spotify can rate-limit the playlist-write endpoint too
                # (different bucket from /search, but still possible
                # under sustained load). Same fail-fast contract: mark
                # the affected row FAIL and stop the loop.
                self.stderr.write(self.style.ERROR(f"[{pl.codi}] {exc}"))
                self._mark_failed(pl, str(exc))
                sync_aborted = True
                break

        if sync_aborted:
            raise CommandError(
                "Spotify rate limit exceeded the client tolerance; sync "
                "aborted. Watchdog will see status=FAIL on the affected "
                "row. Retry after the Retry-After window."
            )

    # ── per-playlist sync ────────────────────────────────────────────────
    def _sync_one(
        self, client: UserSpotifyClient, pl: SpotifyPlaylist, dry: bool
    ) -> None:
        extra = ""
        if pl.kind == SpotifyPlaylist.KIND_NO_VERIFICADES:
            extra = f" chunk={pl.chunk_index}"
        self.stdout.write(
            f"\n[{pl.codi}] {pl.kind} territori={pl.territori or '-'}{extra}"
        )

        cancons = self._select_cancons(pl)
        # Cache-only resolution: for each Canco, look at SpotifyMetadata
        # and use the cached spotify_id when present. Cançons in
        # status="not_attempted" or "not_found" are silently skipped;
        # Process B (enriquir_spotify) is responsible for filling them.
        uris: list[str] = []
        matched = 0
        for canco in cancons:
            uri = self._resolve_uri_cache_only(canco)
            if uri:
                uris.append(uri)
                matched += 1

        self.stdout.write(
            f"  candidates={len(cancons)} cache_hits={matched} "
            f"(gap={len(cancons) - matched} pending enrichment)"
        )

        if dry:
            self.stdout.write("  (dry-run no s'escriu a Spotify)")
            return

        error_msg = ""
        ok = True
        try:
            client.replace_playlist_tracks(pl.spotify_playlist_id, uris)
        except RateLimitedError:
            # Propagate so the outer handle() loop can stop cleanly.
            raise
        except Exception as exc:  # noqa: BLE001 we log and carry on
            ok = False
            error_msg = f"{type(exc).__name__}: {exc}"
            self.stderr.write(self.style.ERROR(f"  sync falla: {error_msg}"))

        with transaction.atomic():
            pl.last_sync_at = timezone.now()
            pl.last_sync_ok = ok
            pl.last_sync_msg = error_msg
            pl.last_n_tracks = len(cancons)
            pl.last_n_matched = matched
            pl.save(
                update_fields=[
                    "last_sync_at",
                    "last_sync_ok",
                    "last_sync_msg",
                    "last_n_tracks",
                    "last_n_matched",
                ]
            )

        if ok:
            self.stdout.write(self.style.SUCCESS(f"  OK {matched} tracks a Spotify"))

    # ── selection ────────────────────────────────────────────────────────
    def _select_cancons(self, pl: SpotifyPlaylist) -> list[Canco]:
        if pl.kind == SpotifyPlaylist.KIND_TOP:
            # FASE D: daily reads TopProvisional (rolling), weekly reads
            # TopSetmanal for the most recent published setmana (the
            # canonical chart, not yesterday's provisional estimate).
            if pl.freq == SpotifyPlaylist.FREQ_WEEKLY:
                latest = (
                    TopSetmanal.objects.filter(territori=pl.territori)
                    .order_by("-setmana")
                    .values_list("setmana", flat=True)
                    .first()
                )
                if latest is None:
                    # No setmanal data yet for this territori (e.g. ALT
                    # in its first weeks). Empty playlist is acceptable;
                    # better than failing the sync entirely.
                    return []
                rows = (
                    TopSetmanal.objects.filter(territori=pl.territori, setmana=latest)
                    .select_related("canco")
                    .order_by("posicio")[:40]
                )
                return [rs.canco for rs in rows if rs.canco]
            # Default and FREQ_DAILY: TopProvisional.
            rows = (
                TopProvisional.objects.filter(territori=pl.territori)
                .select_related("canco")
                .order_by("posicio")[:40]
            )
            return [rp.canco for rp in rows if rp.canco]

        if pl.kind == SpotifyPlaylist.KIND_NOVETATS:
            yesterday = (timezone.now() - timedelta(days=1)).date()
            return list(
                Canco.objects.filter(
                    data_llancament=yesterday,
                    activa=True,
                ).order_by(
                    "nom"
                )[:100]
            )

        if pl.kind == SpotifyPlaylist.KIND_NO_VERIFICADES:
            if pl.chunk_index is None or self._no_verif_window is None:
                self.stderr.write(
                    self.style.WARNING(
                        "  no_verificades sense chunk_index, salto la playlist"
                    )
                )
                return []
            start = pl.chunk_index * NO_VERIF_CHUNK_SIZE
            end = start + NO_VERIF_CHUNK_SIZE
            return self._no_verif_window[start:end]

        return []

    def _mark_failed(self, pl: SpotifyPlaylist, msg: str) -> None:
        """Persist a FAIL state on the playlist row so tq-health and
        check_spotify_coverage see it as a real cron failure."""
        with transaction.atomic():
            pl.last_sync_at = timezone.now()
            pl.last_sync_ok = False
            pl.last_sync_msg = msg[:500]
            pl.save(update_fields=["last_sync_at", "last_sync_ok", "last_sync_msg"])

    # ── per-canço URI resolution (CACHE ONLY) ───────────────────────────
    def _resolve_uri_cache_only(self, canco: Canco) -> str | None:
        """Return a Spotify URI for the Canço if (and only if)
        SpotifyMetadata.status == found.

        Never calls /v1/search. Returns None for not_attempted /
        not_found so the playlist write simply skips this slot. Process
        B (enriquir_spotify) is the only path that can promote a Canço
        into found status; calling it on its own throttled cron keeps
        the search rate-limit budget under control regardless of how
        often Process A runs.
        """
        # Try the OneToOne reverse accessor (.spotify); a Canço with no
        # SpotifyMetadata row is treated identically to not_attempted.
        sm = getattr(canco, "spotify", None)
        if sm is None:
            return None
        if sm.enrichment_status != SpotifyMetadata.STATUS_FOUND:
            return None
        if not sm.spotify_id:
            return None
        return f"spotify:track:{sm.spotify_id}"
