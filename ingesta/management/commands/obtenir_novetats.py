import difflib
import fcntl
import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from ingesta.clients import deezer
from ingesta.clients.deezer import _parse_date
from music.constants import DIES_CADUCITAT
from music.ml import classificar_i_guardar
from music.models import Album, Artista, ArtistaDeezer, Canco
from music.titlecase_catala import titlecase_catala

logger = logging.getLogger(__name__)

RECORD_TYPE_MAP = {
    "album": "album",
    "single": "single",
    "ep": "ep",
    "compile": "album",
}


def _get_or_create_artista(deezer_id: int, name: str) -> Artista | None:
    """Look up artist by Deezer ID (via ArtistaDeezer), or create new."""
    ad = (
        ArtistaDeezer.objects.filter(deezer_id=deezer_id)
        .select_related("artista")
        .first()
    )
    if ad:
        return ad.artista
    try:
        artista = Artista.objects.create(
            nom=name,
            lastfm_nom=name,
            aprovat=False,
            auto_descobert=True,
            pendent_review=True,
            font_descoberta="deezer_contributor",
        )
        ArtistaDeezer.objects.get_or_create(
            deezer_id=deezer_id,
            defaults={"artista": artista, "principal": True},
        )
        return artista
    except IntegrityError:
        ad = (
            ArtistaDeezer.objects.filter(deezer_id=deezer_id)
            .select_related("artista")
            .first()
        )
        return ad.artista if ad else None


class Command(BaseCommand):
    help = "Incremental Deezer ingestion with priority queue: P1=ISRC backfill, P2=album tracks, P3=new albums."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Max API calls.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        # `SingletonLock` exits with code 75 (EX_TEMPFAIL) if the
        # lock is already held — `tq-run` then writes
        # `status=SKIPPED_BY_LOCK` without refreshing `last_run`,
        # so a hung instance triggers `tq-health` STALE after the
        # max-age window. See `music.locks` docstring for context.
        from music.locks import SingletonLock

        with SingletonLock("obtenir_novetats"):
            self._run(*args, **options)

    def _run(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no DB writes."))

        calls = 0
        p1 = 0
        p2 = 0
        p3 = 0
        cutoff = date.today() - timedelta(days=DIES_CADUCITAT)
        # Track seen IDs in dry-run to avoid infinite loops
        seen_p1: set[int] = set()
        seen_p2: set[int] = set()
        seen_p3: set[int] = set()

        while True:
            if deezer.quota_exhausted():
                self.stdout.write(self.style.ERROR("Quota Deezer exhaurida."))
                break

            if limit and calls >= limit:
                break

            # --- P1: tracks with deezer_id but no ISRC ---
            p1_qs = Canco.objects.filter(
                deezer_id__isnull=False, isrc=""
            ).select_related("artista", "album")
            if seen_p1:
                p1_qs = p1_qs.exclude(pk__in=seen_p1)
            canco = p1_qs.first()
            if canco:
                calls += 1
                p1 += 1
                if dry_run:
                    self.stdout.write(f"  P1 track {canco.deezer_id} ({canco.nom})")
                    seen_p1.add(canco.pk)
                    continue

                data = deezer._get(f"{deezer.API_BASE}/track/{canco.deezer_id}")
                if deezer.quota_exhausted():
                    break
                if data:
                    self._process_track_data(canco, data)
                    self.stdout.write(
                        f"  P1 track {canco.deezer_id} → ISRC={canco.isrc}"
                    )
                continue

            # --- P2: albums with deezer_id but cancons_obtingudes=False ---
            p2_qs = Album.objects.filter(
                deezer_id__isnull=False, cancons_obtingudes=False, descartat=False
            ).select_related("artista")
            if seen_p2:
                p2_qs = p2_qs.exclude(pk__in=seen_p2)
            album = p2_qs.first()
            if album:
                calls += 1
                p2 += 1
                if dry_run:
                    self.stdout.write(f"  P2 album {album.deezer_id} ({album.nom})")
                    seen_p2.add(album.pk)
                    continue

                tracks = deezer.get_album_tracks(album.deezer_id)
                if deezer.quota_exhausted():
                    break
                created = 0
                for track_data in tracks:
                    was_new = self._create_track(album, track_data)
                    if was_new:
                        created += 1
                    calls += 1  # each track = 1 API call in get_album_tracks

                # Deezer often returns an empty track list the first hours /
                # days after an album ships — their index lags behind the
                # album endpoint. Don't mark `cancons_obtingudes=True` yet if
                # the album is fresh; retry next run. After 30 days give up
                # (a truly empty album never appears).
                # NOTE: never re-import `date` / `timedelta` here. A local
                # `from datetime import …` inside this method shadows the
                # module-level import on line 4 and turns the early
                # `cutoff = date.today() - …` (line 93) into an
                # UnboundLocalError, leaving the lock-file held by a
                # zombie process and blocking every subsequent hourly run.
                album_old = (
                    album.data_llancament
                    and album.data_llancament < date.today() - timedelta(days=30)
                )
                if tracks or album_old:
                    album.cancons_obtingudes = True
                    album.save(update_fields=["cancons_obtingudes"])
                self.stdout.write(
                    f"  P2 album {album.deezer_id} ({album.nom}) → {created} cançons creades"
                    + (
                        ""
                        if (tracks or album_old)
                        else "  [retry — Deezer 0 tracks, àlbum fresc]"
                    )
                )
                continue

            # --- P3: approved artists, oldest checked first ---
            p3_qs = (
                Artista.objects.filter(
                    aprovat=True,
                    deezer_ids__isnull=False,
                )
                .distinct()
                .order_by(F("last_checked_deezer").asc(nulls_first=True))
            )
            if seen_p3:
                p3_qs = p3_qs.exclude(pk__in=seen_p3)
            artista = p3_qs.first()
            if not artista:
                self.stdout.write("  No more work to do.")
                break

            calls += 1
            p3 += 1
            dz_principal = artista.deezer_id_principal
            if dry_run:
                self.stdout.write(
                    f"  P3 artista {artista.nom} (dz={dz_principal}, "
                    f"last_checked={artista.last_checked_deezer})"
                )
                seen_p3.add(artista.pk)
                continue

            albums_data = deezer.get_artist_albums(dz_principal, min_date=cutoff)
            if deezer.quota_exhausted():
                break
            new_albums = 0
            for album_data in albums_data:
                was_new = self._create_album(artista, album_data)
                if was_new:
                    new_albums += 1
            artista.last_checked_deezer = timezone.now()
            artista.save(update_fields=["last_checked_deezer"])
            self.stdout.write(
                f"  P3 artista {artista.nom} → {new_albums} àlbums nous "
                f"(de {len(albums_data)} totals)"
            )

            if calls % 100 == 0:
                self.stdout.write(f"  ... {calls} crides (P1={p1}, P2={p2}, P3={p3})")

        quota_msg = "Sí" if deezer.quota_exhausted() else "No"
        self.stdout.write(
            self.style.SUCCESS(
                f"\nTotal crides: {calls} | P1: {p1} | P2: {p2} | P3: {p3} | "
                f"Quota exhaurida: {quota_msg}"
            )
        )

    def _process_track_data(self, canco: Canco, data: dict) -> None:
        """Update a Canco with full track data from Deezer."""
        canco.isrc = data.get("isrc", "") or canco.isrc
        canco.preview_url = data.get("preview", "") or canco.preview_url

        # Fix album date if track.album.release_date is earlier
        album_date_str = data.get("album", {}).get("release_date", "")
        if album_date_str:
            album_date = _parse_date(album_date_str)
            if album_date and (
                not canco.album.data_llancament
                or album_date < canco.album.data_llancament
            ):
                canco.album.data_llancament = album_date
                canco.album.save(update_fields=["data_llancament"])
                canco.data_llancament = album_date

        # Best-effort guarantee (R10b lesson): classify even if the
        # contributor resolution below raises.
        try:
            contributors = data.get("contributors", [])
            if contributors:
                main = contributors[0]
                main_id = main.get("id")
                main_name = main.get("name", "")
                if main_id and main_id != canco.artista.deezer_id_principal:
                    real_artista = _get_or_create_artista(main_id, main_name)
                    if real_artista:
                        canco.artista = real_artista

                # Add secondary contributors
                for c in contributors[1:]:
                    c_id = c.get("id")
                    c_name = c.get("name", "")
                    if c_id and c_id != canco.artista.deezer_id_principal:
                        collab = _get_or_create_artista(c_id, c_name)
                        if collab:
                            canco.artistes_col.add(collab)

            canco.save(
                update_fields=["isrc", "preview_url", "artista_id", "data_llancament"]
            )
        finally:
            classificar_i_guardar(canco)

    def _create_track(self, album: Album, track_data: dict) -> bool:
        """Create a Canco from track data, or merge into existing by ISRC. Returns True if new."""
        dz_id = track_data["id"]
        isrc = track_data.get("isrc", "")

        # Skip if already exists by deezer_id
        if Canco.objects.filter(deezer_id=dz_id).exists():
            return False

        # ISRC dedup: if a Canco with this ISRC already exists, merge into it
        if isrc:
            existing = Canco.objects.filter(isrc=isrc).first()
            if existing:
                updated_fields = []
                if not existing.deezer_id:
                    existing.deezer_id = dz_id
                    updated_fields.append("deezer_id")
                preview = track_data.get("preview", "")
                if preview and preview != existing.preview_url:
                    existing.preview_url = preview
                    updated_fields.append("preview_url")
                if updated_fields:
                    existing.save(update_fields=updated_fields)
                # Add main artist as collaborator if different
                contributors = track_data.get("contributors", [])
                if contributors:
                    main = contributors[0]
                    main_id = main.get("id")
                    main_name = main.get("name", "")
                    if main_id and main_id != existing.artista.deezer_id_principal:
                        collab = _get_or_create_artista(main_id, main_name)
                        if collab:
                            existing.artistes_col.add(collab)
                logger.info(
                    "ISRC %s: merged deezer_id=%s into existing canco id=%s",
                    isrc,
                    dz_id,
                    existing.pk,
                )
                return False

        # Resolve main artist
        contributors = track_data.get("contributors", [])
        artista = album.artista
        if contributors:
            main = contributors[0]
            main_id = main.get("id")
            main_name = main.get("name", "")
            if main_id and main_id != artista.deezer_id_principal:
                resolved = _get_or_create_artista(main_id, main_name)
                if resolved:
                    artista = resolved

        # Fix album date
        album_date_str = track_data.get("album_release_date", "")
        if album_date_str:
            album_date = _parse_date(album_date_str)
            if album_date and (
                not album.data_llancament or album_date < album.data_llancament
            ):
                album.data_llancament = album_date
                album.save(update_fields=["data_llancament"])

        try:
            canco = Canco.objects.create(
                deezer_id=dz_id,
                nom=titlecase_catala(track_data["title"]),
                album=album,
                artista=artista,
                durada_ms=(
                    track_data.get("duration", 0) * 1000
                    if track_data.get("duration")
                    else None
                ),
                isrc=isrc,
                preview_url=track_data.get("preview", ""),
                data_llancament=album.data_llancament,
                verificada=False,
            )
        except IntegrityError:
            return False

        # Best-effort guarantee: classify the Canco even if adding
        # collaborators below raises. A brief regression (R10b) left
        # tracks unclassified when the collaborator loop failed after
        # the Canco was already persisted. recalcular_ml eventually
        # rescued them, but the window was visible in the staff panel
        # as tracks with ml_classe=''. classificar_i_guardar is
        # idempotent, so running it once here is fine.
        try:
            if contributors:
                for c in contributors[1:]:
                    c_id = c.get("id")
                    c_name = c.get("name", "")
                    if c_id and c_id != artista.deezer_id_principal:
                        collab = _get_or_create_artista(c_id, c_name)
                        if collab:
                            canco.artistes_col.add(collab)
        finally:
            classificar_i_guardar(canco)
        return True

    def _create_album(self, artista: Artista, album_data: dict) -> bool:
        """Create an Album if it doesn't exist. Returns True if new."""
        dz_id = album_data["id"]
        if Album.objects.filter(deezer_id=dz_id).exists():
            return False

        tipus = RECORD_TYPE_MAP.get(album_data.get("record_type", "album"), "album")
        try:
            Album.objects.create(
                deezer_id=dz_id,
                nom=titlecase_catala(album_data["title"]),
                artista=artista,
                data_llancament=album_data.get("release_date"),
                tipus=tipus,
                imatge_url=album_data.get("cover_xl", ""),
                cancons_obtingudes=False,
            )
        except IntegrityError:
            return False
        return True
