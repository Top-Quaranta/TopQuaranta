"""Hard-delete the casc-buit cohort: pendent artists with zero value.

Cohort (see neteja-pendents-recon.md PART A):
    aprovat=False AND pendent_review=True
    AND no Cançó (FK Canco.artista nor M2M artistes_col)
    AND no anchor (no ArtistaDeezer, musicbrainz_id empty/null,
        spotify_artist_ids_distints empty/null)
    AND no signal (lastfm_te_scrobbles=False AND
        lastfm_playcount_total in (0,NULL) AND lastfm_listeners in (0,NULL))

These are the residue of the old Last.fm getSimilar cascade that added the
similars of *pending* artists as pending too (now stopped: only approved
artists are discovery sources). Recon count: ~30 244. No tombstone by
decision: anything genuinely wanted re-enters via the normal path.

Safety:
  - DEFAULT IS --dry-run: prints the count + a sample, deletes nothing.
    Pass --execute to actually delete.
  - Per-batch pre-guard: re-assert 0 UserArtista and 0 PropostaArtista on
    the batch before deleting (aborts the run if any appears).
  - One transaction per batch. Deletion cascades ArtistaLastfmSimilar edges
    (where these are TARGETs of approved sources) and the tiny territoris/
    localitats M2M rows.
  - Post: recompute nb_similars_lastfm on the affected approved sources
    (the deleted targets leave their source caches slightly high).

Does NOT touch descartats (aprovat=False, pendent_review=False) — that
terminal cohort is out of scope by decision.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from comptes.models import PropostaArtista, UserArtista
from music.models import Artista, ArtistaLastfmSimilar, Canco

logger = logging.getLogger(__name__)

BATCH = 2000

_HAS_FK = Exists(Canco.objects.filter(artista_id=OuterRef("pk")))
_HAS_M2M = Exists(Canco.objects.filter(artistes_col=OuterRef("pk")))
_ANCHOR = (
    Q(deezer_ids__isnull=False)
    | (~Q(musicbrainz_id__isnull=True) & ~Q(musicbrainz_id=""))
    | (
        ~Q(spotify_artist_ids_distints=[])
        & ~Q(spotify_artist_ids_distints__isnull=True)
    )
)
_SIGNAL = (
    Q(lastfm_te_scrobbles=True)
    | Q(lastfm_playcount_total__gt=0)
    | Q(lastfm_listeners__gt=0)
)


def cohort_qs(pks=None):
    """The exact casc-buit cohort queryset (re-evaluated each call).

    `pks` (optional) restricts to those primary keys — but ALWAYS
    intersected with the full 0/0/0 cohort rule, so an explicit pk list can
    never delete anything outside the cohort (a wrong pk is simply ignored).
    """
    qs = (
        Artista.objects.filter(aprovat=False, pendent_review=True)
        .annotate(_fk=_HAS_FK, _m2m=_HAS_M2M)
        .filter(_fk=False, _m2m=False)
        .exclude(_ANCHOR)
        .exclude(_SIGNAL)
    )
    if pks:
        qs = qs.filter(pk__in=pks)
    return qs


class Command(BaseCommand):
    help = (
        "Hard-delete the casc-buit cohort (empty pending artists). Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete. Without it the command is a dry-run "
            "(prints count + sample, deletes nothing).",
        )
        parser.add_argument("--batch", type=int, default=BATCH)
        parser.add_argument(
            "--pks",
            default="",
            help="Comma-separated pks to restrict the delete to (still "
            "intersected with the 0/0/0 cohort, so it can never delete "
            "outside it). Empty = the whole cohort.",
        )

    def handle(self, *args, **opts):
        execute = opts["execute"]
        batch = opts["batch"]
        pks = [int(x) for x in opts["pks"].split(",") if x.strip()] or None
        total = cohort_qs(pks).count()
        scope = f" (restricted to {len(pks)} pks)" if pks else ""
        self.stdout.write(f"Casc-buit cohort{scope}: {total} artistes.")

        if not execute:
            self.stdout.write("DRY-RUN (no --execute) — sample of 20:")
            for a in cohort_qs(pks).order_by("pk")[:20]:
                self.stdout.write(
                    f"  {a.pk:<7} {a.created_at.date()} sim={a.nb_similars_lastfm} {a.nom[:48]}"
                )
            self.stdout.write("Nothing deleted. Re-run with --execute to delete.")
            return

        # Capture affected approved sources BEFORE deleting, to recompute
        # their nb_similars_lastfm cache afterwards.
        affected_sources = set(
            ArtistaLastfmSimilar.objects.filter(target__in=cohort_qs(pks)).values_list(
                "source_id", flat=True
            )
        )
        deleted = 0
        while True:
            batch_pks = list(cohort_qs(pks).values_list("pk", flat=True)[:batch])
            if not batch_pks:
                break
            # Pre-guard: never delete a user-claimed or user-proposed artist.
            claimed = UserArtista.objects.filter(artista_id__in=batch_pks).count()
            proposed = PropostaArtista.objects.filter(
                artista_creat_id__in=batch_pks
            ).count()
            if claimed or proposed:
                raise RuntimeError(
                    f"ABORT: batch has {claimed} UserArtista / {proposed} "
                    f"PropostaArtista links — cohort definition violated."
                )
            with transaction.atomic():
                Artista.objects.filter(pk__in=batch_pks).delete()
            deleted += len(batch_pks)
            logger.info(
                "purgar_pendents_buits: deleted %d (total %d)",
                len(batch_pks),
                deleted,
            )
            self.stdout.write(f"  deleted {len(batch_pks)} (total {deleted})")

        # Recompute nb_similars_lastfm on the approved sources whose targets
        # we removed (cache, not critical, but keep it honest).
        recomputed = 0
        for sid in affected_sources:
            cnt = ArtistaLastfmSimilar.objects.filter(source_id=sid).count()
            Artista.objects.filter(pk=sid).update(nb_similars_lastfm=cnt)
            recomputed += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Deleted {deleted}; recomputed nb_similars_lastfm on "
                f"{recomputed} approved sources."
            )
        )
