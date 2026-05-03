import difflib
import fcntl
import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.db.models import F, Q
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

            # --- P2: re-scan albums on a per-album cooldown ---
            #
            # Sprint May 2026 redesign. The old logic used
            # `cancons_obtingudes=False` as a gate and marked albums
            # OK as soon as Deezer returned *any* track list — even
            # an empty one for old albums. That left ~3.7k phantom
            # albums in the DB marked "done" but holding zero tracks
            # (Deezer flake + the `album_old` shortcut).
            #
            # New rule: every non-discarded album with a deezer_id
            # is rechecked periodically. Cooldown depends on age:
            #   - <30 days since release  → 24h
            #   - 30-365 days             → 7 days
            #   - >365 days               → 30 days
            # `descartat=True` is the only permanent exclusion.
            # The per-track dedup (`Canco.objects.filter(deezer_id=…)`
            # then ISRC) inside `_create_track` makes the rescan
            # idempotent — we don't duplicate anything we already have,
            # we only catch what was previously missed.
            now_ts = timezone.now()
            p2_qs = (
                Album.objects.filter(
                    deezer_id__isnull=False,
                    descartat=False,
                )
                .select_related("artista")
                .filter(
                    Q(last_album_check__isnull=True)
                    | Q(
                        # recent: re-check every 24h
                        data_llancament__gte=date.today() - timedelta(days=30),
                        last_album_check__lt=now_ts - timedelta(hours=24),
                    )
                    | Q(
                        # mid-aged: re-check weekly
                        data_llancament__gte=date.today() - timedelta(days=365),
                        data_llancament__lt=date.today() - timedelta(days=30),
                        last_album_check__lt=now_ts - timedelta(days=7),
                    )
                    | Q(
                        # old: re-check monthly. Catches reissues,
                        # late-arriving tracks, and previous-flake
                        # ghosts on a slow but guaranteed cadence.
                        data_llancament__lt=date.today() - timedelta(days=365),
                        last_album_check__lt=now_ts - timedelta(days=30),
                    )
                    | Q(
                        # legacy: albums without a known release date
                        # also rechecked monthly so they don't hide.
                        data_llancament__isnull=True,
                        last_album_check__lt=now_ts - timedelta(days=30),
                    )
                )
                # Never-checked albums first; among the rest, oldest
                # check first (LRU) so the queue drains evenly.
                .order_by(F("last_album_check").asc(nulls_first=True))
            )
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

                # Always update the timestamp — even if Deezer
                # returned an empty list this time. The cooldown
                # alone decides when we look again. Keep the legacy
                # `cancons_obtingudes` flag in sync (set True if we
                # got a non-empty track list) for any code that may
                # still read it informationally; nothing filters on it.
                album.last_album_check = now_ts
                update_fields = ["last_album_check"]
                if tracks and not album.cancons_obtingudes:
                    album.cancons_obtingudes = True
                    update_fields.append("cancons_obtingudes")
                album.save(update_fields=update_fields)
                self.stdout.write(
                    f"  P2 album {album.deezer_id} ({album.nom}) → "
                    f"{created} cançons noves"
                    + ("  [Deezer 0 tracks — retry quan toqui]" if not tracks else "")
                )
                continue

            # --- P3: approved artists, oldest checked first ---
            #
            # Filter to artists either never checked OR last checked
            # ≥24h ago. Without this gate the QuerySet was always
            # non-empty (just re-ordering existing rows), the
            # `if not artista: break` never fired, and a single
            # invocation kept iterating the queue forever — caught
            # 2026-05-01 with the 12-day-stuck process. Now the
            # natural exit is: when every approved+deezer artist has
            # been refreshed within the cooldown window, the query
            # returns nothing → break.
            #
            # Cadence implication: hourly cron + 24h cooldown means
            # ~70-80 artistes/hour become eligible at steady state
            # (1.860 ÷ 24). First post-deploy run does the full
            # initial sweep (~30 min); subsequent ticks handle only
            # the rolling slice.
            check_cutoff = timezone.now() - timedelta(hours=24)
            p3_qs = (
                Artista.objects.filter(
                    aprovat=True,
                    deezer_ids__isnull=False,
                )
                .filter(
                    Q(last_checked_deezer__isnull=True)
                    | Q(last_checked_deezer__lt=check_cutoff)
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
                # Add main artist as collaborator if different. Compare
                # against *all* Deezer IDs of the existing main artista
                # (not just the principal) — when an artista has several
                # Deezer profiles (autoedit + label), any of them
                # appearing as a contributor would be a self-collab,
                # which signal D5 forbids and used to crash the hourly
                # cron (May 2026).
                contributors = track_data.get("contributors", [])
                if contributors:
                    main = contributors[0]
                    main_id = main.get("id")
                    main_name = main.get("name", "")
                    main_deezer_ids = set(
                        existing.artista.deezer_ids.values_list("deezer_id", flat=True)
                    )
                    if main_id and main_id not in main_deezer_ids:
                        collab = _get_or_create_artista(main_id, main_name)
                        if collab and collab.pk != existing.artista_id:
                            existing.artistes_col.add(collab)
                logger.info(
                    "ISRC %s: merged deezer_id=%s into existing canco id=%s",
                    isrc,
                    dz_id,
                    existing.pk,
                )
                return False

        # Resolve main artist. Same multi-Deezer-ID guard as above:
        # if any of the album.artista's Deezer profiles is the main
        # contributor, keep the album's artista — don't create a
        # phantom duplicate.
        contributors = track_data.get("contributors", [])
        artista = album.artista
        if contributors:
            main = contributors[0]
            main_id = main.get("id")
            main_name = main.get("name", "")
            main_deezer_ids = set(
                artista.deezer_ids.values_list("deezer_id", flat=True)
            )
            if main_id and main_id not in main_deezer_ids:
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
