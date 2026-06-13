import difflib
import fcntl
import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from ingesta.caducitat import caducitat_cutoff, is_caducat
from ingesta.clients import deezer
from ingesta.clients.deezer import _parse_date
from music.constants import DIES_CADUCITAT
from music.ml import classificar_i_guardar
from music.models import Album, Artista, ArtistaDeezer, Canco, HistorialRevisio
from music.titlecase_catala import titlecase_catala

logger = logging.getLogger(__name__)

RECORD_TYPE_MAP = {
    "album": "album",
    "single": "single",
    "ep": "ep",
    "compile": "album",
}


def _previously_rejected(isrc: str, deezer_id: int | None) -> bool:
    """Has this recording (by ISRC or by Deezer track id) ever been
    rejected by staff?

    Looks at HistorialRevisio, which keeps `canco_isrc` and
    `canco_deezer_id` denormalised so the rejection trail survives
    even when the Canco row itself was deleted (rebutjar_album does
    a `cancons.delete()`; netejar_caducades used to wipe rejected
    rows after 365 days too, until the May-2026 fix).

    Returns True for any prior `decisio="rebutjada"` match. Both
    ISRC and deezer_id are checked because a recording can come
    back via either path: same master under a re-issued album (new
    deezer_id, same ISRC) or under a re-uploaded track (new ISRC,
    same deezer_id — rare but possible). If either dimension flags
    a prior rejection, we skip.

    Sprint Workflow Sol·licituds (2026-05-20): rows with
    `reconsiderada=True` are treated as if they no longer block — the
    staff has explicitly re-opened the track via the workbench, and
    we want it back in the pipeline. If the track returns and gets
    rejected again, the new rejection lands as a fresh row with
    `reconsiderada=False`, and the filter blocks it once more.
    """
    if not isrc and not deezer_id:
        return False
    q = Q()
    if isrc:
        q |= Q(canco_isrc=isrc)
    if deezer_id:
        q |= Q(canco_deezer_id=deezer_id)
    return (
        HistorialRevisio.objects.filter(decisio="rebutjada", reconsiderada=False)
        .filter(q)
        .exists()
    )


def _lookup_artista_by_deezer(deezer_id: int) -> Artista | None:
    """Return an existing Artista that has `deezer_id` in any of its
    `ArtistaDeezer` rows, or None. Doesn't create anything — pendent
    creation has been moved to `aprovar_canco` (see
    `Canco.contributors_raw` docstring)."""
    if not deezer_id:
        return None
    ad = (
        ArtistaDeezer.objects.filter(deezer_id=deezer_id)
        .select_related("artista")
        .first()
    )
    return ad.artista if ad else None


def _defer_contributor(canco: Canco, deezer_id: int, name: str, role: str) -> None:
    """Append a contributor to `canco.contributors_raw` for later
    materialisation by `processar_collaboradors_pendents` on
    approval. No-ops if the entry is already present (dedup by
    deezer_id). Doesn't save — caller does it."""
    if not deezer_id:
        return
    raw = list(canco.contributors_raw or [])
    if any(entry.get("deezer_id") == deezer_id for entry in raw):
        return
    raw.append({"deezer_id": deezer_id, "name": name or "", "role": role})
    canco.contributors_raw = raw


class Command(BaseCommand):
    help = "Incremental Deezer ingestion with priority queue: P1=ISRC backfill, P2=album tracks, P3=new albums."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Max API calls.")
        parser.add_argument("--dry-run", action="store_true")
        # Caught 2026-05-05: a backfill / first-deploy run can sweep
        # thousands of artistes in a single hour, all getting
        # `last_checked_deezer` within minutes of each other. The
        # 24h cooldown then makes them all re-eligible together
        # 24h later → a "thundering herd" of re-checks one hour per
        # day, and silence the other 23. Capping the per-run P3
        # work keeps the timestamps spread out naturally.
        parser.add_argument(
            "--max-p3-per-run",
            type=int,
            default=200,
            help="Cap on P3 (per-artist) work per cron tick.",
        )

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
        max_p3 = int(options.get("max_p3_per_run") or 0)

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
                # Album-alien guard: resolve the album's Deezer titular ONCE
                # (one /album/{id} call, reused for every track). `own_album`
                # is True when the titular is one of our artista's Deezer
                # profiles → the whole album is ours and enters as before.
                # When the titular can't be resolved (None), stay conservative
                # (treat as own) so a transient API hiccup never drops tracks.
                own_album = self._resolve_own_album(album)
                created = 0
                for track_data in tracks:
                    was_new = self._create_track(album, track_data, own_album=own_album)
                    if was_new:
                        created += 1
                    calls += 1  # each track = 1 API call in get_album_tracks

                # Always update the timestamp — even if Deezer
                # returned an empty list this time. The cooldown
                # alone decides when we look again.
                album.last_album_check = now_ts
                album.save(update_fields=["last_album_check"])
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

            # Per-tick P3 cap (see --max-p3-per-run docstring above).
            if max_p3 and p3 >= max_p3:
                self.stdout.write(
                    f"  P3 cap hit ({max_p3}). Stopping; "
                    f"next cron tick will pick up where we left off."
                )
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
                # `source_deezer_id` records which Deezer profile of
                # the artista this row was sourced from. Lets the
                # smart homonym-unlink in `services.py` scope its
                # action to one specific profile when the artista
                # has several (e.g. autoedit + label).
                was_new = self._create_album(
                    artista, album_data, source_deezer_id=dz_principal
                )
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
            main_deezer_ids = set(
                canco.artista.deezer_ids.values_list("deezer_id", flat=True)
            )
            if contributors:
                main = contributors[0]
                main_id = main.get("id")
                main_name = main.get("name", "")
                if main_id and main_id not in main_deezer_ids:
                    # Deezer disagrees about who the main artist is.
                    # Existing Artista mapped to that Deezer ID (if any)
                    # gets reused as the canco's main; otherwise we keep
                    # the current canco.artista and defer creation —
                    # staff will resolve at verification.
                    real_artista = _lookup_artista_by_deezer(main_id)
                    if real_artista:
                        canco.artista = real_artista
                    else:
                        _defer_contributor(canco, main_id, main_name, "main")

                # Secondary contributors — reuse existing Artistas as
                # `artistes_col` immediately; defer net-new ones.
                for c in contributors[1:]:
                    c_id = c.get("id")
                    c_name = c.get("name", "")
                    if not c_id or c_id in main_deezer_ids:
                        continue
                    collab = _lookup_artista_by_deezer(c_id)
                    if collab and collab.pk != canco.artista_id:
                        canco.artistes_col.add(collab)
                    elif not collab:
                        _defer_contributor(canco, c_id, c_name, "secondary")

            canco.save(
                update_fields=[
                    "isrc",
                    "preview_url",
                    "artista_id",
                    "data_llancament",
                    "contributors_raw",
                ]
            )
        finally:
            classificar_i_guardar(canco)

    def _resolve_own_album(self, album: Album) -> bool:
        """True when `album`'s Deezer titular is one of the album.artista's
        Deezer profiles (the album is genuinely ours → ingest the whole
        album, guests included). False when the titular is a different artist
        (foreign album → only the tracks our artista actually contributes to
        enter; enforced in `_create_track`).

        Conservative on failure: if the titular can't be resolved (network /
        API error, deleted album), return True so we keep the pre-guard
        behaviour and never drop real tracks because of a transient hiccup.
        """
        titular_id = deezer.get_album_titular_id(album.deezer_id)
        if titular_id is None:
            logger.warning(
                "Album %s (%s): could not resolve Deezer titular; keeping "
                "conservative ingest (treating as own album).",
                album.deezer_id,
                album.nom,
            )
            return True
        owner_ids = set(album.artista.deezer_ids.values_list("deezer_id", flat=True))
        return titular_id in owner_ids

    def _create_track(
        self, album: Album, track_data: dict, *, own_album: bool = True
    ) -> bool:
        """Create a Canco from track data, or merge into existing by ISRC. Returns True if new.

        `own_album` (resolved once per album by `_resolve_own_album`) gates the
        album-alien guard: when False, a track is only created under
        `album.artista` if that artista appears among the track's live Deezer
        contributors. Defaults to True so any caller that doesn't pass it keeps
        the pre-guard behaviour.
        """
        dz_id = track_data["id"]
        isrc = track_data.get("isrc", "")

        # Skip if already exists by deezer_id
        if Canco.objects.filter(deezer_id=dz_id).exists():
            return False

        # Rejection memory: if this ISRC or this deezer_id has ever
        # been rejected by staff, skip creation. Without this guard,
        # songs that came in via a rejected album reappear as soon
        # as Deezer re-publishes the same recording under a different
        # `deezer_id` (re-issue, label change) or under a different
        # album of the same artist — the original Canco row is gone
        # (rebutjar_album physically deletes it) so the dedup-by-row
        # checks above find nothing. HistorialRevisio keeps the
        # rejection trail denormalised on `canco_isrc` /
        # `canco_deezer_id` precisely for this case.
        if _previously_rejected(isrc, dz_id):
            logger.info(
                "Skipping track «%s» (deezer_id=%s isrc=%s) — "
                "previously rejected by staff.",
                track_data.get("title", "?"),
                dz_id,
                isrc or "—",
            )
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
                        collab = _lookup_artista_by_deezer(main_id)
                        if collab and collab.pk != existing.artista_id:
                            existing.artistes_col.add(collab)
                        elif not collab:
                            _defer_contributor(existing, main_id, main_name, "main")
                            existing.save(update_fields=["contributors_raw"])
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
        # phantom duplicate. Net-new "main" disagreements are
        # deferred via `contributors_raw` (see helper docstring).
        contributors = track_data.get("contributors", [])
        artista = album.artista
        deferred_main: tuple[int, str] | None = None
        if contributors:
            main = contributors[0]
            main_id = main.get("id")
            main_name = main.get("name", "")
            main_deezer_ids = set(
                artista.deezer_ids.values_list("deezer_id", flat=True)
            )
            if main_id and main_id not in main_deezer_ids:
                resolved = _lookup_artista_by_deezer(main_id)
                if resolved:
                    artista = resolved
                else:
                    deferred_main = (main_id, main_name)

        # Album-alien guard: create under `album.artista` only when the album
        # is genuinely theirs (`own_album`) OR our artista appears among the
        # track's LIVE contributors. We read `contributors` here, never the
        # persisted `contributors_raw` (its role labels are unreliable — dedup
        # is first-write-wins). If the main-resolution above already
        # reassigned `artista` to the track's real main, the row no longer
        # belongs to the album's owner, so the guard stands down (the track is
        # legitimately created under that resolved artista).
        if not own_album and artista is album.artista:
            owner_ids = set(
                album.artista.deezer_ids.values_list("deezer_id", flat=True)
            )
            track_contributor_ids = {c.get("id") for c in contributors}
            if not (owner_ids & track_contributor_ids):
                logger.info(
                    "Skipping track «%s» (deezer_id=%s) — foreign album %s "
                    "and «%s» is not among its contributors.",
                    track_data.get("title", "?"),
                    dz_id,
                    album.deezer_id,
                    album.artista.nom,
                )
                return False

        # Fix album date
        album_date_str = track_data.get("album_release_date", "")
        if album_date_str:
            album_date = _parse_date(album_date_str)
            if album_date and (
                not album.data_llancament or album_date < album.data_llancament
            ):
                album.data_llancament = album_date
                album.save(update_fields=["data_llancament"])

        # DIES_CADUCITAT guard at the creation frontier — see
        # `ingesta/caducitat.py` for the full rationale (June 2026:
        # Tres Fan Ball 1994/1997/2005/2013 albums recreating ~38
        # pendents every ~30 days). Evaluated *after* the "Fix album
        # date" block above so we read the rewound (track-effective)
        # date, not the artist-albums-level summary.
        cutoff = caducitat_cutoff()
        if is_caducat(album.data_llancament, cutoff):
            logger.info(
                "Skipping track «%s» (deezer_id=%s album=%s data_llancament=%s) — "
                "older than DIES_CADUCITAT (%s).",
                track_data.get("title", "?"),
                dz_id,
                album.pk,
                album.data_llancament.isoformat(),
                cutoff.isoformat(),
            )
            return False

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
            dirty = False
            if deferred_main:
                _defer_contributor(canco, deferred_main[0], deferred_main[1], "main")
                dirty = True
            if contributors:
                main_deezer_ids = set(
                    canco.artista.deezer_ids.values_list("deezer_id", flat=True)
                )
                for c in contributors[1:]:
                    c_id = c.get("id")
                    c_name = c.get("name", "")
                    if not c_id or c_id in main_deezer_ids:
                        continue
                    collab = _lookup_artista_by_deezer(c_id)
                    if collab and collab.pk != canco.artista_id:
                        canco.artistes_col.add(collab)
                    elif not collab:
                        _defer_contributor(canco, c_id, c_name, "secondary")
                        dirty = True
            if dirty:
                canco.save(update_fields=["contributors_raw"])
        finally:
            classificar_i_guardar(canco)
        return True

    def _create_album(
        self,
        artista: Artista,
        album_data: dict,
        source_deezer_id: int | None = None,
    ) -> bool:
        """Create an Album if it doesn't exist. Returns True if new.

        `source_deezer_id` records which Deezer profile of the artista
        produced this row, so the smart homonym-unlink can target one
        specific profile.
        """
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
                source_deezer_id=source_deezer_id,
                # Deezer's `album.label` is the record-label string
                # ("Halley Records", autoedit names, etc.). Useful as
                # ML signal + staff-curation cue. Empty when Deezer
                # omits the field.
                label=(album_data.get("label") or "").strip()[:200],
            )
        except IntegrityError:
            return False
        return True
