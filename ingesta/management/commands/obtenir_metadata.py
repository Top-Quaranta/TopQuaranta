import difflib
import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from ingesta.clients import deezer
from music.constants import DIES_CADUCITAT
from music.models import Album, Artista, ArtistaDeezer, Canco, HistorialRevisio
from music.titlecase_catala import titlecase_catala

logger = logging.getLogger(__name__)


def _previously_rejected(isrc: str, deezer_id: int | None) -> bool:
    """Has this recording (by ISRC or by Deezer track id) ever been
    rejected by staff? See the equivalent helper in `obtenir_novetats`
    for the full rationale — both ingest paths share the rejection-
    memory check.
    """
    if not isrc and not deezer_id:
        return False
    q = Q()
    if isrc:
        q |= Q(canco_isrc=isrc)
    if deezer_id:
        q |= Q(canco_deezer_id=deezer_id)
    return HistorialRevisio.objects.filter(decisio="rebutjada").filter(q).exists()


RECORD_TYPE_MAP = {
    "album": "album",
    "single": "single",
    "ep": "ep",
    "compile": "album",
}


class Command(BaseCommand):
    help = "Fetch Deezer metadata (albums + tracks) for approved artists."

    def add_arguments(self, parser):
        parser.add_argument(
            "--artista-id",
            type=int,
            default=None,
            help="Only process this Artista PK.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-fetch even if albums/tracks already exist.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fetched without calling Deezer or writing to DB.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of artists to process.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        artista_id = options["artista_id"]
        limit = options["limit"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN — no API calls, no DB writes.\n")
            )

        qs = Artista.objects.public()

        if artista_id:
            qs = qs.filter(pk=artista_id)
            if not qs.exists():
                raise CommandError(f"No approved Artista with pk={artista_id}.")
        else:
            # Only re-query Deezer for artists genuinely unresolved
            # (no ArtistaDeezer link); --force re-checks everyone.
            if not force:
                qs = qs.filter(deezer_ids__isnull=True)

        total = qs.count()
        self.stdout.write(f"Artists to process: {total}")

        if limit:
            qs = qs[:limit]
            self.stdout.write(f"  Limited to: {limit}")

        cutoff = date.today() - timedelta(days=DIES_CADUCITAT)
        self.stdout.write(f"Release cutoff: {cutoff}")

        if dry_run:
            for a in qs[:20]:
                dz = a.deezer_id_principal
                status = f"deezer_id={dz}" if dz else "needs lookup"
                self.stdout.write(f"  Would fetch: {a.nom} ({status})")
            if total > 20:
                self.stdout.write(f"  ... and {total - 20} more")
            return

        artists_ok = 0
        artists_not_found = 0
        artists_err = 0
        albums_created = 0
        albums_updated = 0
        tracks_created = 0
        tracks_updated = 0

        iterable = qs if limit else qs.iterator()
        for i, artista in enumerate(iterable, 1):
            try:
                result = self._process_artist(artista, cutoff, force)
                if result is None:
                    artists_not_found += 1
                else:
                    a_new, a_upd, t_new, t_upd = result
                    albums_created += a_new
                    albums_updated += a_upd
                    tracks_created += t_new
                    tracks_updated += t_upd
                    artists_ok += 1
            except Exception as exc:
                logger.error("Error processing %s: %s", artista.nom, exc)
                artists_err += 1

            if i % 50 == 0:
                self.stdout.write(
                    f"  Processed {i}/{total}... "
                    f"(ok={artists_ok}, not_found={artists_not_found}, "
                    f"err={artists_err})"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nMetadata ingestion complete:\n"
                f"  Artists OK: {artists_ok}\n"
                f"  Artists not found on Deezer: {artists_not_found}\n"
                f"  Artists errors: {artists_err}\n"
                f"  Albums created: {albums_created}\n"
                f"  Albums updated: {albums_updated}\n"
                f"  Tracks created: {tracks_created}\n"
                f"  Tracks updated: {tracks_updated}"
            )
        )

        # E2 (C-4, 2026-05-19): if more than 50% of the iteration
        # failed the cron is in real trouble (Deezer API outage,
        # schema change, auth revoked). Propagate so `tq-run` sees a
        # non-zero exit and `tq-health` flags the cron as failing.
        # Below the threshold the per-artist `logger.error` plus the
        # counter in the summary above are the visible signal.
        processed = artists_ok + artists_not_found + artists_err
        if processed > 0 and artists_err / processed > 0.5:
            raise CommandError(
                f"Metadata sync: {artists_err}/{processed} artists failed "
                f"(>50% threshold). See logs for per-artist errors."
            )

    def _process_artist(
        self,
        artista: Artista,
        cutoff: date,
        force: bool,
    ) -> tuple[int, int, int, int] | None:
        """
        Fetch and store albums + tracks for one artist via Deezer.
        Returns (albums_created, albums_updated, tracks_created, tracks_updated)
        or None if artist not found/validated on Deezer.
        """
        # Step 1: resolve deezer_id(s). An artista may have several
        # ArtistaDeezer rows when Deezer keeps multiple profiles for
        # the same person (e.g. a self-edited early catalogue + a
        # later label profile that Deezer never merged). We process
        # all of them so the new profile's albums get ingested too.
        # The principal one comes first; the rest follow.
        deezer_ids = list(
            artista.deezer_ids.order_by("-principal", "deezer_id").values_list(
                "deezer_id", flat=True
            )
        )
        if not deezer_ids:
            resolved = self._resolve_deezer_id(artista)
            if not resolved:
                return None
            deezer_ids = [resolved]

        a_created = 0
        a_updated = 0
        t_created = 0
        t_updated = 0

        for deezer_id in deezer_ids:
            # Step 2: fetch albums for this Deezer profile. The
            # `source_deezer_id` is recorded on the Album so the
            # smart homonym-unlink can later scope to this profile.
            albums_data = deezer.get_artist_albums(deezer_id, min_date=cutoff)

            for album_data in albums_data:
                album, was_created = self._upsert_album(
                    artista, album_data, force, source_deezer_id=deezer_id
                )
                if was_created:
                    a_created += 1
                elif force:
                    a_updated += 1

                tracks_data = deezer.get_album_tracks(album_data["id"])
                if not tracks_data:
                    continue

                for track_data in tracks_data:
                    was_new = self._upsert_track(artista, album, track_data, force)
                    if was_new:
                        t_created += 1
                    elif force:
                        t_updated += 1

        return a_created, a_updated, t_created, t_updated

    def _resolve_deezer_id(self, artista: Artista) -> int | None:
        """
        Search Deezer for this artist, validate via ISRC cross-check,
        and persist deezer_id if validated.
        Returns deezer_id or None.
        """
        result = deezer.search_artist(artista.nom)
        if not result:
            logger.info("Deezer: no match for '%s'", artista.nom)
            artista.last_checked_deezer = timezone.now()
            artista.save(update_fields=["last_checked_deezer"])
            return None

        candidate_id = result["id"]
        candidate_name = result["name"]

        # ISRC validation: find a known Canco with ISRC for this artist
        known_track = (
            Canco.objects.filter(artista=artista)
            .exclude(isrc="")
            .exclude(isrc__isnull=True)
            .first()
        )

        if known_track:
            # Fetch albums from candidate to find a track with matching ISRC
            validated = self._validate_via_isrc(candidate_id, known_track.isrc)
            if not validated:
                logger.warning(
                    "Deezer ISRC validation failed for '%s' "
                    "(candidate='%s' id=%d, expected ISRC=%s)",
                    artista.nom,
                    candidate_name,
                    candidate_id,
                    known_track.isrc,
                )
                artista.last_checked_deezer = timezone.now()
                artista.save(update_fields=["last_checked_deezer"])
                return None
            logger.info(
                "Deezer ISRC validated for '%s' → '%s' (id=%d)",
                artista.nom,
                candidate_name,
                candidate_id,
            )
        else:
            # No ISRC to validate against — accept name match only
            logger.info(
                "Deezer name-only match for '%s' → '%s' (id=%d, no ISRC to validate)",
                artista.nom,
                candidate_name,
                candidate_id,
            )

        # Populate Deezer metadata
        self._populate_deezer_metadata(artista, candidate_id, candidate_name)

        try:
            with transaction.atomic():
                artista.last_checked_deezer = timezone.now()
                artista.save(
                    update_fields=[
                        "last_checked_deezer",
                        "deezer_nb_fan",
                        "deezer_nb_album",
                        "deezer_nom",
                        "deezer_nom_similitud",
                    ]
                )
                # R10: ArtistaDeezer is the single source of truth now.
                ArtistaDeezer.objects.get_or_create(
                    deezer_id=candidate_id,
                    defaults={"artista": artista, "principal": True},
                )
        except IntegrityError:
            logger.warning(
                "Deezer ID %d already assigned to another artist — skipping '%s'",
                candidate_id,
                artista.nom,
            )
            artista.refresh_from_db()
            return None
        return candidate_id

    def _validate_via_isrc(self, deezer_artist_id: int, expected_isrc: str) -> bool:
        """
        Check if any track from this Deezer artist has the expected ISRC.
        Fetches up to 3 albums and checks their tracks.
        """
        albums = deezer.get_artist_albums(deezer_artist_id)
        for album in albums[:3]:
            tracks = deezer.get_album_tracks(album["id"])
            for track in tracks:
                if track.get("isrc", "").upper() == expected_isrc.upper():
                    return True
        return False

    def _populate_deezer_metadata(
        self, artista: Artista, deezer_id: int, deezer_name: str
    ) -> None:
        """Fetch and set Deezer metadata fields on the artista (not saved yet)."""
        info = deezer.get_artist_info(deezer_id)
        if info:
            artista.deezer_nb_fan = info["nb_fan"]
            artista.deezer_nb_album = info["nb_album"]
        artista.deezer_nom = deezer_name
        artista.deezer_nom_similitud = difflib.SequenceMatcher(
            None, artista.nom.lower(), deezer_name.lower()
        ).ratio()

    def _upsert_album(
        self,
        artista: Artista,
        data: dict,
        force: bool,
        source_deezer_id: int | None = None,
    ) -> tuple[Album, bool]:
        """Create or update an Album from Deezer data.

        `source_deezer_id` records which Deezer profile of the
        artista produced this row (when the artista has several
        profiles, e.g. autoedit + label). Lets the smart homonym-
        unlink in `services.py` scope to one specific profile.
        """
        tipus = RECORD_TYPE_MAP.get(data.get("record_type", "album"), "album")

        defaults = {
            "nom": data["title"],
            "artista": artista,
            "data_llancament": data.get("release_date"),
            "tipus": tipus,
            "imatge_url": data.get("cover_xl", ""),
            # Deezer's `album.label` (record-label string). See
            # `Album.label` docstring for usage. Empty when omitted.
            "label": (data.get("label") or "").strip()[:200],
        }
        if source_deezer_id is not None:
            defaults["source_deezer_id"] = source_deezer_id

        with transaction.atomic():
            if force:
                album, created = Album.objects.update_or_create(
                    deezer_id=data["id"],
                    defaults=defaults,
                )
            else:
                album, created = Album.objects.get_or_create(
                    deezer_id=data["id"],
                    defaults=defaults,
                )

        return album, created

    def _resolve_main_artist(
        self, artista: Artista, contributors: list[dict]
    ) -> tuple[Artista, tuple[int, str] | None]:
        """Determine the real main artist from Deezer contributors.

        Returns `(artista_to_use, deferred_main)` where
        `deferred_main` is `(deezer_id, name)` when Deezer's main
        contributor doesn't match the album's artista AND no Artista
        with that Deezer ID exists yet — caller stores it on
        `Canco.contributors_raw` for later materialisation by
        `aprovar_canco`. Avoids creating pendents from cançons that
        end up rebutjades (76 % of rejection cases per 2026-05-07
        audit). Existing ArtistaDeezer matches are reused immediately.
        """
        if not contributors:
            return artista, None

        main = contributors[0]
        main_id = main.get("id")
        main_name = main.get("name", "")

        all_deezer_ids = set(artista.deezer_ids.values_list("deezer_id", flat=True))
        if not main_id or main_id in all_deezer_ids:
            return artista, None

        ad = (
            ArtistaDeezer.objects.filter(deezer_id=main_id)
            .select_related("artista")
            .first()
        )
        if ad:
            return ad.artista, None

        # Net-new "main" — defer creation until the canco is verified.
        return artista, (main_id, main_name)

    def _upsert_track(
        self, artista: Artista, album: Album, data: dict, force: bool
    ) -> bool:
        """Create or update a Canco from Deezer data. Returns True if new."""
        # Fix album date from track.album.release_date (original, not re-release)
        track_album_date_str = data.get("album_release_date", "")
        if track_album_date_str:
            from ingesta.clients.deezer import _parse_date

            track_album_date = _parse_date(track_album_date_str)
            if track_album_date and (
                not album.data_llancament or track_album_date < album.data_llancament
            ):
                album.data_llancament = track_album_date
                album.save(update_fields=["data_llancament"])

        # Resolve the real main artist from contributors
        contributors = data.get("contributors", [])
        real_artista, deferred_main = self._resolve_main_artist(artista, contributors)

        defaults = {
            "nom": titlecase_catala(data["title"]),
            "album": album,
            "artista": real_artista,
            "durada_ms": (
                data.get("duration", 0) * 1000 if data.get("duration") else None
            ),
            "isrc": data.get("isrc", ""),
            "preview_url": data.get("preview", ""),
            "data_llancament": album.data_llancament,
            "verificada": False,
        }

        # Rejection memory (May-2026): if this ISRC or this Deezer
        # track id has ever been rejected by staff, skip creation.
        # Without this guard, songs that came in via a rejected
        # album reappear as soon as Deezer re-publishes the recording
        # under a different `deezer_id` (re-issue, label change) or
        # under another album of the same artist — the original Canco
        # row is gone (rebutjar_album physically deletes it) so the
        # dedup-by-row checks below find nothing. HistorialRevisio
        # keeps the trail denormalised on `canco_isrc` /
        # `canco_deezer_id` precisely for this case.
        isrc_check = defaults.get("isrc") or ""
        if _previously_rejected(isrc_check, data["id"]):
            logger.info(
                "Skipping track «%s» (deezer_id=%s isrc=%s) — "
                "previously rejected by staff.",
                data.get("title", "?"),
                data["id"],
                isrc_check or "—",
            )
            return False

        # ISRC collisions on Deezer are routine and harmless: a single
        # is reissued inside a full album, or a featuring track is
        # listed under both contributors. Both Deezer track_ids point
        # to the same recording (same ISRC), but our `canco_isrc_unique_when_set`
        # constraint only allows one row per ISRC. If the row already
        # exists under another deezer_id (or another artista as a
        # collab-target), skip without crashing — otherwise the
        # IntegrityError aborts the transaction and kills the whole
        # artist's remaining tracks (Sprint K bug, May 2026).
        try:
            with transaction.atomic():
                if force:
                    canco, created = Canco.objects.update_or_create(
                        deezer_id=data["id"],
                        defaults=defaults,
                    )
                else:
                    canco, created = Canco.objects.get_or_create(
                        deezer_id=data["id"],
                        defaults=defaults,
                    )
        except IntegrityError as exc:
            isrc = defaults.get("isrc") or ""
            if isrc and "isrc" in str(exc).lower():
                existing = Canco.objects.filter(isrc=isrc).first()
                if existing:
                    logger.info(
                        "ISRC collision skipped: deezer_id=%s isrc=%s already "
                        "stored as «%s» (id=%s) under %s — leaving the "
                        "canonical row in place.",
                        data["id"],
                        isrc,
                        existing.nom,
                        existing.pk,
                        existing.artista.nom,
                    )
                    return False
            raise

        # Best-effort guarantee (R10b lesson): classify the Canco even
        # if adding collaborators below raises. See the equivalent
        # pattern in ingesta/management/commands/obtenir_novetats.py.
        try:
            if (created or force) and (contributors or deferred_main):
                # Build the set of *all* Deezer IDs that map to the
                # main artista (not just the principal). When an
                # artista has several profiles (e.g. autoedit + label),
                # any of them appearing as a contributor would be a
                # self-collab, which signal D5 forbids.
                main_deezer_ids = set(
                    real_artista.deezer_ids.values_list("deezer_id", flat=True)
                )
                dirty = False
                if deferred_main:
                    raw = list(canco.contributors_raw or [])
                    if not any(e.get("deezer_id") == deferred_main[0] for e in raw):
                        raw.append(
                            {
                                "deezer_id": deferred_main[0],
                                "name": deferred_main[1],
                                "role": "main",
                            }
                        )
                        canco.contributors_raw = raw
                        dirty = True
                for contributor in contributors:
                    c_id = contributor.get("id")
                    c_name = contributor.get("name", "")
                    if not c_id or c_id in main_deezer_ids:
                        continue
                    ad = (
                        ArtistaDeezer.objects.filter(deezer_id=c_id)
                        .select_related("artista")
                        .first()
                    )
                    if ad:
                        collab = ad.artista
                        if collab.pk != canco.artista_id:
                            canco.artistes_col.add(collab)
                    else:
                        # Defer pendent-Artista creation until the
                        # canco is verified (see Canco.contributors_raw
                        # docstring + music.services.processar_
                        # collaboradors_pendents).
                        raw = list(canco.contributors_raw or [])
                        if not any(e.get("deezer_id") == c_id for e in raw):
                            raw.append(
                                {
                                    "deezer_id": c_id,
                                    "name": c_name or "",
                                    "role": "secondary",
                                }
                            )
                            canco.contributors_raw = raw
                            dirty = True
                if dirty:
                    canco.save(update_fields=["contributors_raw"])
        finally:
            if created or force:
                from music.ml import classificar_i_guardar

                classificar_i_guardar(canco)

        return created
