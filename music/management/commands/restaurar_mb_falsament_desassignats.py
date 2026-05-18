"""Restore MBIDs auto-unassigned by the buggy `validate_artista_area`.

Background — caught 2026-04-30:

The defence-in-depth cron added 2026-04-29 (`obtenir_metadata_musicbrainz`)
calls `validate_artista_area()` on every artist with an MBID, and
auto-unassigns when the MB record's `area` doesn't read as PPCC. The
first version had two false-positive sources:

  1. `area="Spain"` was treated as non-PPCC, but Spain is the country
     that *contains* PPCC territory — many MB records haven't been
     drilled down past country level. Result: 207 PPCC artists with
     correct MBIDs got their MBID auto-stripped just because MB hadn't
     refined their area.
  2. PPCC municipalities (Vic, Mataró, Pego, Bunyola, Olot, …) weren't
     in the hardcoded `_PPCC_AREA_TOKENS` set. Another ~30 false
     positives.

`mb_sync._looks_ppcc` and `validate_artista_area` were fixed
2026-04-30 (Municipi table cross-reference + inconclusive countries).
This command sweeps the StaffAuditLog `artista_mbid_auto_unassign`
entries and re-evaluates each MBID against the new logic. Where the
new logic says "ok", we:

  * Re-assign the MBID on the Artista.
  * Drop the MBID from `mb_blocked_mbids`.
  * Log a `artista_mbid_auto_restore` audit row.

The cron will re-sync the artist's MB metadata on its next pass,
restoring `mb_area`, `mb_end_date`, `mb_aliases`, etc. — and
re-tagging Albums/Cançons via ISRC. We don't try to re-fetch the
metadata here: 1 MB API call per artist × ~250 artists = 250 s, vs.
the cron picking them up at its own rate-limited pace.

Modes:
  --dry-run   list what would be restored (default)
  --apply     execute the restore
  --artist-pk N   restrict to one artist (sanity-check first)
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from music.audit import log_staff_action
from music.mb_sync import _is_inconclusive_country, _looks_ppcc
from music.models import Artista, StaffAuditLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Reassign MBIDs auto-unassigned by the buggy first version of "
        "validate_artista_area (Spain / PPCC-town false positives)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--artist-pk", type=int, default=None)

    def handle(self, *args, **opts):
        apply = opts["apply"]
        artist_pk = opts["artist_pk"]

        # Pull every auto-unassign action ever logged. The reason
        # string carries the MB area we keyed off ("mb-area-non-ppcc:Vic").
        qs = StaffAuditLog.objects.filter(action="artista_mbid_auto_unassign")
        if artist_pk:
            qs = qs.filter(target_id=artist_pk)
        # Most recent first per target — only consider the latest
        # unassign per artist (older actions could have been
        # superseded by a manual re-assign + re-unassign).
        seen: set[int] = set()
        candidates: list[tuple[StaffAuditLog, str, str]] = []
        for entry in qs.order_by("-created_at"):
            if entry.target_id in seen:
                continue
            seen.add(entry.target_id)
            mbid = (entry.metadata or {}).get("mbid", "")
            reason = (entry.metadata or {}).get("reason", "")
            if not mbid or not reason.startswith("mb-area-non-ppcc:"):
                continue
            area = reason.split(":", 1)[1]
            candidates.append((entry, mbid, area))

        restored = 0
        skipped_real_mismatch = 0
        skipped_already_assigned = 0
        skipped_artist_gone = 0

        for entry, mbid, area in candidates:
            try:
                a = Artista.objects.get(pk=entry.target_id)
            except Artista.DoesNotExist:
                skipped_artist_gone += 1
                continue
            # If staff already re-assigned (or the cron found a
            # different MBID), don't clobber.
            if a.musicbrainz_id:
                skipped_already_assigned += 1
                continue
            # Re-evaluate with the new logic.
            if not (_looks_ppcc(area) or _is_inconclusive_country(area)):
                # Still a real mismatch (USA, Mexico, Japan, …) —
                # leave the unassignment in place.
                skipped_real_mismatch += 1
                continue

            self.stdout.write(
                f"{'restore' if apply else '[DRY] would-restore'} "
                f"{a.nom!r:30s} (pk={a.pk}) MBID={mbid} area={area!r}"
            )
            if apply:
                # Drop the MBID from the block-list and reassign.
                blocked = list(a.mb_blocked_mbids or [])
                if mbid in blocked:
                    blocked.remove(mbid)
                a.mb_blocked_mbids = blocked
                a.musicbrainz_id = mbid
                # Force the cron to pick it up again on the next pass
                # so MB metadata gets re-synced.
                a.mb_last_sync = None
                a.save(
                    update_fields=[
                        "mb_blocked_mbids",
                        "musicbrainz_id",
                        "mb_last_sync",
                    ]
                )
                try:
                    log_staff_action(
                        None,
                        "artista_mbid_auto_restore",
                        target=a,
                        mbid=mbid,
                        original_reason=area,
                    )
                except Exception:
                    # E2 (B-1): audit-log writes are subsidiary —
                    # the restore itself already succeeded, but
                    # silently swallowing made post-mortem hard.
                    # Log + carry on; this is a one-shot manual
                    # command, no need to propagate.
                    logger.warning(
                        "audit log_staff_action failed for artista pk=%s nom=%r",
                        a.pk,
                        a.nom,
                        exc_info=True,
                    )
            restored += 1

        self.stdout.write("")
        self.stdout.write(f"Total candidate unassigns: {len(candidates)}")
        verb = "Restored" if apply else "Would restore"
        self.stdout.write(f"{verb}: {restored}")
        self.stdout.write(f"Skipped (still-real mismatch): {skipped_real_mismatch}")
        self.stdout.write(f"Skipped (already re-assigned): {skipped_already_assigned}")
        self.stdout.write(f"Skipped (artist deleted): {skipped_artist_gone}")
        if not apply and restored:
            self.stdout.write("\nRe-run with --apply to commit.")
