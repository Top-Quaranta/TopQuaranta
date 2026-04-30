"""Detect Cançons / Albums with stale MusicBrainz fields after their
artist's MBID changed.

Background — caught 2026-04-29 on the "Casual" case:

The renderer of the staff page (`/staff/cancons` MB filter) trusts the
`mbrainz_confirmed` / `mb_recording_id` columns on each Canco. Those
columns get set by `sync_from_mbid()` when the artist has an MBID and
its discography matches our titles. Until 2026-04-29 the staff PATCH
that *changes* the MBID on an Artista did NOT trigger a re-sync, so
those columns survived as ghosts pointing at the previous (wrong) MB
artist's recordings. The auto-match had also been too aggressive —
"Casual" got the US rapper's MBID despite our Casual being from
Catalonia (fixed in `resolve_mbid`).

This command sweeps the existing data and fixes the residue.

Modes:
  --dry-run           list orphans without touching anything (default)
  --apply             reset stale fields where confirmed orphans
  --artist-pk N       restrict to one artist (sanity check first)

A row is "orphan" when its `mb_recording_id` (or `mb_release_group_id`
on Albums) is non-empty AND that ID is NOT in the artist's current MB
discography cache. The current cache is refreshed on every
`sync_from_mbid()` call, so a stale row is one whose MB ID points at a
different MB artist.

Usage:
    .venv/bin/python manage.py auditar_mb_orphans              # dry-run
    .venv/bin/python manage.py auditar_mb_orphans --apply
    .venv/bin/python manage.py auditar_mb_orphans --artist-pk 3773
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from music.models import Album, Artista, Canco


def _artist_disco_ids(artista: Artista) -> tuple[set[str], set[str]]:
    """Return (release_group_ids, recording_ids) currently believed to
    belong to `artista` according to the cached MB discography."""
    cache = artista.mb_discography_cache or {}
    rg_ids = set()
    rec_ids = set()
    # `mb_discography_cache` shape (per `mb_sync.sync_from_mbid`): list
    # of {title, rg, date}. The cache as-is doesn't store IDs — we
    # need to re-derive from current Albums/Cançons that have IDs and
    # ARE the canonical artist's. As a proxy: if an Album/Canço of THIS
    # artist still has the ID, it's "current". Anything mismatched means
    # the row was matched against a different MB artist before.
    for alb in Album.objects.filter(artista=artista).exclude(mb_release_group_id=""):
        rg_ids.add(alb.mb_release_group_id)
    for c in Canco.objects.filter(artista=artista).exclude(mb_recording_id=""):
        rec_ids.add(c.mb_recording_id)
    return rg_ids, rec_ids


class Command(BaseCommand):
    help = "Audit stale MusicBrainz reconciliation fields on Cançons + Albums."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--artist-pk", type=int, default=None)

    def handle(self, *args, **opts):
        apply = opts["apply"]
        artist_pk = opts["artist_pk"]

        # Strategy: compare each Artista's CURRENT MBID against the
        # Cançons/Albums that have MB fields populated. Re-fetch their
        # MB discography (one call per artist) and reset rows whose
        # IDs don't appear in the fresh discography.
        from ingesta.clients import musicbrainz as mb

        qs = Artista.objects.exclude(musicbrainz_id__isnull=True).exclude(
            musicbrainz_id=""
        )
        if artist_pk:
            qs = qs.filter(pk=artist_pk)
        # Only artists that actually have something tagged.
        qs = qs.filter(
            Q(cancons__mb_recording_id__gt="") | Q(albums__mb_release_group_id__gt="")
        ).distinct()

        total_orphan_albums = 0
        total_orphan_cancons = 0
        artists_touched = 0

        for art in qs.iterator():
            # Fetch fresh discography from MB for the *current* MBID.
            try:
                rgs = mb.get_artist_release_groups(art.musicbrainz_id) or []
            except Exception:
                self.stderr.write(
                    f"  [skip] MB fetch failed for {art.nom!r} ({art.musicbrainz_id})"
                )
                continue
            valid_rg_ids = {rg.get("id") for rg in rgs if rg.get("id")}
            valid_rec_ids = set()
            for rg in rgs:
                rg_id = rg.get("id")
                if not rg_id:
                    continue
                try:
                    detail = mb.get_release_group_with_recordings(rg_id) or {}
                except Exception:
                    continue
                rel = detail.get("_picked_release") or {}
                for medium in rel.get("media", []) or []:
                    for tr in medium.get("tracks", []) or []:
                        rec = tr.get("recording") or {}
                        if rec.get("id"):
                            valid_rec_ids.add(rec["id"])

            orphan_albs = list(
                Album.objects.filter(artista=art)
                .exclude(mb_release_group_id="")
                .exclude(mb_release_group_id__in=valid_rg_ids)
            )
            orphan_cancons = list(
                Canco.objects.filter(artista=art)
                .exclude(mb_recording_id="")
                .exclude(mb_recording_id__in=valid_rec_ids)
            )

            if not orphan_albs and not orphan_cancons:
                continue

            artists_touched += 1
            self.stdout.write(f"\n{art.nom!r} (pk={art.pk}, MBID={art.musicbrainz_id})")
            for a in orphan_albs:
                self.stdout.write(
                    f"  [album] {a.nom!r:40s} stale rg_id={a.mb_release_group_id}"
                )
            for c in orphan_cancons:
                self.stdout.write(
                    f"  [canço] {c.nom!r:40s} stale rec_id={c.mb_recording_id}"
                )
            total_orphan_albums += len(orphan_albs)
            total_orphan_cancons += len(orphan_cancons)

            if apply:
                Album.objects.filter(pk__in=[a.pk for a in orphan_albs]).update(
                    mb_release_group_id="",
                    mb_type_secondary="",
                    mb_status="",
                    mbrainz_confirmed=None,
                )
                Canco.objects.filter(pk__in=[c.pk for c in orphan_cancons]).update(
                    mb_recording_id="",
                    mb_work_id="",
                    mb_lyrics_language="",
                    mbrainz_confirmed=None,
                )

        verb = "Reset" if apply else "Would reset"
        self.stdout.write(
            f"\n{verb} {total_orphan_albums} albums + {total_orphan_cancons} "
            f"cançons across {artists_touched} artists."
        )

        # ── Pass 2: Artist-level orphan metadata ─────────────────────────
        # Artists whose MBID has been auto-unassigned (or staff-cleared)
        # but whose mb_area / mb_end_date / mb_disambiguation / etc.
        # still hold the wrong artist's data. Caught with Guillotina
        # 2026-04-30: MBID was correctly auto-unassigned (Mexican
        # dissolved band) but `mb_end_date=2011-01-01` lingered, making
        # the staff Estat panel show a live PPCC band as "dissolved".
        #
        # Detection: musicbrainz_id is empty/null AND any of the
        # discography-derived fields are populated. Reset is total —
        # nothing about a former MB artist should bleed into our row.
        artist_meta_fields = (
            "mb_type",
            "mb_gender",
            "mb_area",
            "mb_disambiguation",
            "mb_sort_name",
            "mb_begin_date",
            "mb_end_date",
        )
        meta_qs = Artista.objects.filter(
            Q(musicbrainz_id__isnull=True) | Q(musicbrainz_id="")
        )
        if artist_pk:
            meta_qs = meta_qs.filter(pk=artist_pk)
        cond = Q()
        for f in artist_meta_fields:
            cond |= (
                ~Q(**{f: ""})
                if f not in ("mb_begin_date", "mb_end_date")
                else Q(**{f"{f}__isnull": False})
            )
        meta_qs = meta_qs.filter(cond)

        meta_orphans = list(meta_qs)
        if meta_orphans:
            self.stdout.write(
                f"\nArtistes sense MBID però amb metadata MB residual "
                f"({len(meta_orphans)}):"
            )
            for a in meta_orphans:
                bits = []
                if a.mb_area:
                    bits.append(f"area={a.mb_area!r}")
                if a.mb_end_date:
                    bits.append(f"end_date={a.mb_end_date}")
                if a.mb_disambiguation:
                    bits.append(f"disamb={a.mb_disambiguation!r}")
                self.stdout.write(
                    f"  [artist] {a.nom!r:30s} (pk={a.pk}) {' '.join(bits)}"
                )
            if apply:
                meta_qs.update(
                    mb_type="",
                    mb_gender="",
                    mb_area="",
                    mb_area_hierarchy=[],
                    mb_begin_date=None,
                    mb_end_date=None,
                    mb_disambiguation="",
                    mb_sort_name="",
                    mb_aliases=[],
                    mb_tags=[],
                    mb_rating=None,
                    mb_discography_cache={},
                )

        if not apply and (total_orphan_albums or total_orphan_cancons or meta_orphans):
            self.stdout.write("\nRe-run with --apply to commit.")
