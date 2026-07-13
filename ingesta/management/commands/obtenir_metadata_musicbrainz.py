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

import logging
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
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
        # See `music.locks.SingletonLock` for why we exit 75 on lock
        # contention rather than 0 (preserves `last_run` so health
        # checks fire when an instance hangs).
        # Shared `"ram_heavy"` lock with `analitzar_whisper`: both
        # commands load multi-GB resources (MB doesn't, but its long
        # tail of HTTP waits would have prevented Whisper from
        # acquiring memory in time). On a 4 GB Hetzner CX22 this
        # mutual exclusion prevents the OOM-kill we hit 2026-05-04.
        from music.locks import SingletonLock

        with SingletonLock("ram_heavy"):
            self._run(**opts)

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
        n_fails = 0
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
            if not self._process(a):
                n_fails += 1
            processed += 1
            if limit and processed >= limit:
                self.stdout.write(f"Límit de {limit} artistes aconseguit. Sortint.")
                break

        # E2 (C-14, 2026-05-19): the cron runs every 15 min. Before
        # this guard, a per-iteration `except Exception` swallow +
        # `mb_last_sync=now` write meant a full broken-API run would
        # silently mark every artista as "synced" and `tq-health`
        # never noticed. Now we count failures and propagate via
        # CommandError when >50% of the batch flipped the swallow.
        if processed > 0 and n_fails / processed > 0.5:
            raise CommandError(
                f"MB sync: {n_fails}/{processed} artistes failed "
                f"(>50% threshold). MB API outage or schema change? "
                f"See logs for per-artista errors."
            )
        self.stdout.write(f"MB sync summary: processed={processed} fails={n_fails}")

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
        # Clear every artist-level mb_* field copied from the wrong
        # MBID. Otherwise the dashboard keeps showing stale data
        # (caught with Guillotina 2026-04-30: the Mexican band's
        # `mb_end_date=2011-01-01`, `mb_area='Mexico'`, etc. lingered
        # on our PPCC artist after unassign, making the Estat panel
        # report a live PPCC band as "dissolved"). `mb_last_sync`
        # stays so the cron's queue ordering doesn't loop on this
        # row; `mb_blocked_mbids` and `mb_auto_match_disabled` stay
        # for the same reason — they're staff-side controls.
        artista.mb_type = ""
        artista.mb_gender = ""
        artista.mb_area = ""
        artista.mb_area_hierarchy = []
        artista.mb_begin_date = None
        artista.mb_end_date = None
        artista.mb_disambiguation = ""
        artista.mb_sort_name = ""
        artista.mb_aliases = []
        artista.mb_tags = []
        artista.mb_rating = None
        artista.mb_discography_cache = {}
        artista.save(
            update_fields=[
                "mb_blocked_mbids",
                "musicbrainz_id",
                "mb_type",
                "mb_gender",
                "mb_area",
                "mb_area_hierarchy",
                "mb_begin_date",
                "mb_end_date",
                "mb_disambiguation",
                "mb_sort_name",
                "mb_aliases",
                "mb_tags",
                "mb_rating",
                "mb_discography_cache",
            ]
        )

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

    def _process(self, artista: Artista) -> bool:
        """Return True on success, False if the iteration swallowed
        an exception. The outer loop counts failures and raises if
        more than 50% of the batch fails (E2 C-14, 2026-05-19)."""
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
                    # Pre-flight uniqueness check. The DB has a UNIQUE
                    # constraint on `musicbrainz_id`, and `resolve_mbid`
                    # can pick the same MBID for two distinct Artistas
                    # whose names share a Last.fm canonical (e.g.
                    # "Cecilio G" pk=5025 vs "Cecilio.G" pk=18813 →
                    # both → 03ee196d-...). Without this guard the cron
                    # raises IntegrityError and the whole iteration is
                    # lost. Caught 2026-05-07.
                    other = (
                        Artista.objects.filter(musicbrainz_id=mbid)
                        .exclude(pk=artista.pk)
                        .only("pk", "nom")
                        .first()
                    )
                    if other is not None:
                        logger.warning(
                            "MBID collision: %s (pk=%s) wanted %s but "
                            "it's already on %s (pk=%s) — blocking + skipping",
                            artista.nom,
                            artista.pk,
                            mbid,
                            other.nom,
                            other.pk,
                        )
                        # Add to blocked list so subsequent runs don't
                        # re-attempt the same dead-end.
                        blocked = list(artista.mb_blocked_mbids or [])
                        if mbid not in blocked:
                            blocked.append(mbid)
                            artista.mb_blocked_mbids = blocked
                        artista.mb_last_sync = timezone.now()
                        artista.save(update_fields=["mb_blocked_mbids", "mb_last_sync"])
                        self.stdout.write(
                            f"  [collision] {artista.nom} → {mbid} blocked "
                            f"(taken by pk={other.pk} {other.nom!r})"
                        )
                        time.sleep(0.2)
                        return True
                    artista.musicbrainz_id = mbid
                    artista.save(update_fields=["musicbrainz_id"])
                    self.stdout.write(f"  [name] {artista.nom} → MBID {mbid}")
                else:
                    # No MBID found: still mark as synced so we don't thrash.
                    artista.mb_last_sync = timezone.now()
                    artista.save(update_fields=["mb_last_sync"])
                    self.stdout.write(f"  [no-match] {artista.nom} (pk={artista.pk})")
                    time.sleep(0.2)
                    return True
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
            time.sleep(0.2)
            return False
        # Small extra pause between artistes to stay polite.
        time.sleep(0.2)
        return True
