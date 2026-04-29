"""Continuously enrich our Artista/Album/Canço rows with MusicBrainz data.

Usage:
    ./manage.py obtenir_metadata_musicbrainz
    ./manage.py obtenir_metadata_musicbrainz --refresh-days 7 --limit 300
    ./manage.py obtenir_metadata_musicbrainz --artista-id 3663

Behaviour:
  * A single-instance lock (fcntl) keeps concurrent crons from stepping
    on each other. If locked, the second invocation exits cleanly.
  * Processes one artist per iteration: lookup MBID by name if missing,
    otherwise pull + reconcile discography.
  * MusicBrainz is rate-limited globally to 1 req/s; expect ~5 reqs
    per artist synced (core + paginated RGs + 1-2 recordings fetches).
  * Stops when no artist needs attention (queue empty: `mb_last_sync`
    is NULL for none, or all sync timestamps are within `--refresh-days`).
"""

from __future__ import annotations

import fcntl
import logging
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from music.audit import log_staff_action
from music.mb_sync import resolve_mbid, sync_from_mbid, validate_artista_area
from music.models import Album, Artista, Canco

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pull MusicBrainz metadata (artist + discography) into our DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh-days",
            type=int,
            default=7,
            help="Skip artists synced more recently than N days ago.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max artists to process this invocation (default: run until "
            "the queue is empty).",
        )
        parser.add_argument(
            "--artista-id",
            type=int,
            default=None,
            help="Process only this Artista pk (ignores --refresh-days).",
        )

    def handle(self, *args, **opts):
        lock_file = "/tmp/mb_sync.lock"
        try:
            lock = open(lock_file, "w")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            self.stdout.write("Ja hi ha una instància corrent. Sortint.")
            return

        try:
            self._run(**opts)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def _run(self, **opts):
        refresh_days = opts["refresh_days"]
        limit = opts["limit"]
        artista_id = opts["artista_id"]

        if artista_id:
            try:
                a = Artista.objects.get(pk=artista_id)
            except Artista.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"No Artista pk={artista_id}"))
                return
            self._process(a)
            return

        processed = 0
        cutoff = timezone.now() - timedelta(days=refresh_days)

        while True:
            qs = (
                Artista.objects
                # Approved artists get first dibs, then pendents, then descartats.
                .annotate(
                    prio=Case(
                        When(aprovat=True, then=Value(0)),
                        When(pendent_review=True, then=Value(1)),
                        default=Value(2),
                        output_field=IntegerField(),
                    )
                )
                .filter(Q(mb_last_sync__isnull=True) | Q(mb_last_sync__lt=cutoff))
                .order_by("prio", "mb_last_sync", "pk")
            )
            a = qs.first()
            if not a:
                self.stdout.write(self.style.SUCCESS("Cua buida — tot fresc. Sortint."))
                break
            self._process(a)
            processed += 1
            if limit and processed >= limit:
                self.stdout.write(f"Límit de {limit} artistes aconseguit. Sortint.")
                break

    def _unassign_wrong_mbid(
        self, artista: Artista, bad_mbid: str, reason: str
    ) -> None:
        """Drop a wrongly-assigned MBID, block it, and reset cançons/
        albums tagged from its discography.

        Mirrors the reset block at the start of `sync_from_mbid()` but
        runs *before* the new MBID is resolved — necessary because the
        new MBID may not be found in this iteration (multi-PPCC
        ambiguity → staff disambiguation), and we don't want stale MB
        IDs surviving in that case.

        Adds the bad MBID to `mb_blocked_mbids` so `resolve_mbid()`
        skips it on the retry. Logs an audit row.
        """
        blocked = list(artista.mb_blocked_mbids or [])
        if bad_mbid not in blocked:
            blocked.append(bad_mbid)
        artista.mb_blocked_mbids = blocked
        artista.musicbrainz_id = None
        artista.save(update_fields=["mb_blocked_mbids", "musicbrainz_id"])

        Album.objects.filter(artista=artista).update(
            mb_release_group_id="",
            mb_type_secondary="",
            mb_status="",
            mbrainz_confirmed=None,
        )
        Canco.objects.filter(artista=artista).update(
            mb_recording_id="",
            mb_work_id="",
            mb_lyrics_language="",
            mbrainz_confirmed=None,
        )

        try:
            log_staff_action(
                None,
                "artista_mbid_auto_unassign",
                target=artista,
                mbid=bad_mbid,
                reason=reason,
            )
        except Exception:
            logger.exception("Audit log failed for auto-unassign")

    def _process(self, artista: Artista) -> None:
        try:
            # Step 1: validate the existing MBID against our own
            # location data. If MB says "United States" and we have
            # PPCC localitats, the MBID was almost certainly assigned
            # by a previous run that trusted Lucene score over
            # location (caught 2026-04-29 with the "Casual" case).
            # Unassign + block + reset stale Canco/Album MB fields,
            # then fall through to step 2 to find the right MBID.
            if artista.musicbrainz_id:
                mismatch, reason = validate_artista_area(artista)
                if mismatch:
                    bad_mbid = artista.musicbrainz_id
                    self._unassign_wrong_mbid(artista, bad_mbid, reason)
                    self.stdout.write(
                        f"  [unassign] {artista.nom} (pk={artista.pk}) "
                        f"MBID {bad_mbid} dropped: {reason}"
                    )

            # Step 2: assign an MBID if missing (post-step-1 the
            # artista may have just had its bad MBID stripped).
            if not artista.musicbrainz_id:
                mbid = resolve_mbid(artista)
                if mbid:
                    artista.musicbrainz_id = mbid
                    artista.save(update_fields=["musicbrainz_id"])
                    self.stdout.write(f"  [name] {artista.nom} → MBID {mbid}")
                else:
                    # No MBID found: still mark as synced so we don't thrash.
                    artista.mb_last_sync = timezone.now()
                    artista.save(update_fields=["mb_last_sync"])
                    self.stdout.write(f"  [no-match] {artista.nom} (pk={artista.pk})")
                    return
            counters = sync_from_mbid(artista)
            self.stdout.write(
                "  [sync] {nom} → urls={u} albums={am}/{rgs} "
                "cançons={cm}/{rec} isrcs={i} cat_work={cat}".format(
                    nom=artista.nom,
                    u=counters["urls_filled"],
                    am=counters["albums_matched"],
                    rgs=counters["rgs"],
                    cm=counters["cancons_matched"],
                    rec=counters["recordings"],
                    i=counters["isrcs"],
                    cat=counters["cat_work"],
                )
            )
        except Exception:
            logger.exception("MB sync failed for %s (pk=%s)", artista.nom, artista.pk)
            artista.mb_last_sync = timezone.now()
            artista.save(update_fields=["mb_last_sync"])
        # Small extra pause between artistes to stay polite.
        time.sleep(0.2)
