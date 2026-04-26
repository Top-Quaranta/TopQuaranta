"""Daily Spotify playlist sync.

For each configured `SpotifyPlaylist`:
  * top-<territori>: TopProvisional.filter(territori=X) ordered by
    posicio, capped at 40.
  * novetats: Canco with data_llancament = yesterday, activa=True, cap
    at 100.

Each Canço is resolved to a Spotify track URI by ISRC search. The
result is cached on Canco.spotify_id so subsequent runs don't
re-search. Mismatches are silently skipped (per design — we don't
want to blur the playlist with noise).

The Spotify playlist is rewritten in place via PUT /playlists/<id>/
tracks so the public URL + follower count survive every run.

Run daily at 07:15 UTC via `cron.topquaranta`, shortly after the
provisional ranking recalc finishes.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ingesta.clients.spotify import UserSpotifyClient
from music.models import Canco, SpotifyAuth, SpotifyPlaylist
from ranking.models import TopProvisional


class Command(BaseCommand):
    help = "Daily sync of the configured Spotify playlists from live rankings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute the track lists and ISRC matches but don't hit Spotify.",
        )
        parser.add_argument(
            "--only",
            default="",
            help="Sync only the playlist with this codi (else: all).",
        )

    def handle(self, *args, **opts):
        auth = SpotifyAuth.load()
        if not auth:
            raise CommandError(
                "No hi ha autorització Spotify. Executa "
                "`manage.py autoritzar_spotify` primer."
            )

        client = UserSpotifyClient(auth)

        qs = SpotifyPlaylist.objects.exclude(spotify_playlist_id="")
        only = (opts.get("only") or "").strip()
        if only:
            qs = qs.filter(codi=only)
        playlists = list(qs)
        if not playlists:
            self.stdout.write(
                self.style.WARNING(
                    "Cap SpotifyPlaylist amb spotify_playlist_id configurat. "
                    "Executa `configurar_spotify_playlists` primer."
                )
            )
            return

        dry = opts.get("dry_run", False)
        for pl in playlists:
            self._sync_one(client, pl, dry)

    # ── per-playlist sync ────────────────────────────────────────────────
    def _sync_one(
        self, client: UserSpotifyClient, pl: SpotifyPlaylist, dry: bool
    ) -> None:
        self.stdout.write(f"\n[{pl.codi}] {pl.kind} territori={pl.territori or '-'}")

        cancons = self._select_cancons(pl)
        self.stdout.write(f"  cançons candidates: {len(cancons)}")

        uris: list[str] = []
        matched = 0
        for canco in cancons:
            uri = self._resolve_uri(client, canco)
            if uri:
                uris.append(uri)
                matched += 1

        self.stdout.write(f"  ISRC match: {matched}/{len(cancons)}")

        if dry:
            self.stdout.write("  (dry-run — no s'escriu a Spotify)")
            return

        error_msg = ""
        ok = True
        try:
            client.replace_playlist_tracks(pl.spotify_playlist_id, uris)
        except Exception as exc:  # noqa: BLE001 — we log and carry on
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
            self.stdout.write(self.style.SUCCESS(f"  OK — {matched} tracks a Spotify"))

    # ── selection ────────────────────────────────────────────────────────
    def _select_cancons(self, pl: SpotifyPlaylist) -> list[Canco]:
        if pl.kind == SpotifyPlaylist.KIND_TOP:
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

        return []

    # ── per-canço URI resolution ─────────────────────────────────────────
    def _resolve_uri(self, client: UserSpotifyClient, canco: Canco) -> str | None:
        # Cache hit: Canco.spotify_id is a persistent cache of the ISRC
        # search result. Trust it even if Spotify's catalogue changes —
        # worst case the URI becomes stale and the PUT will surface an
        # error next time we try to add it, at which point staff can
        # clear the cache via the edit page.
        if canco.spotify_id:
            return f"spotify:track:{canco.spotify_id}"

        if not canco.isrc:
            return None

        try:
            uri = client.search_isrc(canco.isrc)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(
                self.style.WARNING(f"  search fails for ISRC {canco.isrc}: {exc}")
            )
            return None

        if uri:
            # Cache: URIs are "spotify:track:XXX" — we only keep the ID.
            spotify_id = uri.rsplit(":", 1)[-1]
            Canco.objects.filter(pk=canco.pk).update(spotify_id=spotify_id)

        return uri
