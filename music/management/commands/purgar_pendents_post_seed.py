"""Hard-delete post-seed pending artists with no verified Cançó.

Decision (more aggressive than the casc-buit 0/0/0 rule): keep only the
original seed (pendents created before `--keep-before`, default 2026-05-01 —
the April manual Catalan seed). Every pendent that entered AFTER and has NOT
earned a verified Cançó is hard-deleted.

Why hard delete (not rebuig): a plain delete does NOT write a HistorialRevisio
rejection, so `_previously_rejected()` stays clear and the artist can re-enter
later via Last.fm / Deezer / manual add. It blocks nothing and undoes nothing
— it only trims the backlog.

Cohort:
    aprovat=False AND pendent_review=True
    AND created_at >= keep_before                 (entered after the seed)
    AND no verified Cançó (FK Canco.artista nor M2M artistes_col, verificada=True)
    AND not user-claimed (UserArtista) nor user-proposed (PropostaArtista)

Safety:
  - DEFAULT IS dry-run; pass --execute to delete.
  - Per-batch pre-guard re-asserts 0 UserArtista / 0 PropostaArtista.
  - One transaction per batch; logged.
  - Post: recompute nb_similars_lastfm on affected approved sources.
Does NOT touch the seed (created < keep_before) nor descartats.
"""

from __future__ import annotations

import datetime
import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef

from comptes.models import PropostaArtista, UserArtista
from music.models import Artista, ArtistaLastfmSimilar, Canco

logger = logging.getLogger(__name__)

BATCH = 2000
DEFAULT_KEEP_BEFORE = "2026-05-01"

_VERIFIED_FK = Exists(Canco.objects.filter(artista_id=OuterRef("pk"), verificada=True))
_VERIFIED_M2M = Exists(
    Canco.objects.filter(artistes_col=OuterRef("pk"), verificada=True)
)
_USER_CLAIMED = Exists(UserArtista.objects.filter(artista_id=OuterRef("pk")))
_USER_PROPOSED = Exists(PropostaArtista.objects.filter(artista_creat_id=OuterRef("pk")))


def cohort_qs(keep_before: datetime.date):
    """Post-seed pendents with no verified Cançó and no user link."""
    return (
        Artista.objects.filter(
            aprovat=False, pendent_review=True, created_at__gte=keep_before
        )
        .annotate(
            _vfk=_VERIFIED_FK,
            _vm2=_VERIFIED_M2M,
            _claimed=_USER_CLAIMED,
            _proposed=_USER_PROPOSED,
        )
        .filter(_vfk=False, _vm2=False, _claimed=False, _proposed=False)
    )


class Command(BaseCommand):
    help = "Hard-delete post-seed pendents with no verified Cançó. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--batch", type=int, default=BATCH)
        parser.add_argument(
            "--keep-before",
            default=DEFAULT_KEEP_BEFORE,
            help="ISO date; pendents created before this are the seed and are "
            f"kept untouched (default {DEFAULT_KEEP_BEFORE}).",
        )

    def handle(self, *args, **opts):
        keep_before = datetime.date.fromisoformat(opts["keep_before"])
        execute = opts["execute"]
        batch = opts["batch"]
        total = cohort_qs(keep_before).count()
        self.stdout.write(
            f"Post-seed pendents (created >= {keep_before}, no verified Cançó, "
            f"no user link): {total}."
        )

        if not execute:
            self.stdout.write("DRY-RUN (no --execute) — sample of 20:")
            for a in cohort_qs(keep_before).order_by("pk")[:20]:
                self.stdout.write(f"  {a.pk:<7} {a.created_at.date()} {a.nom[:50]}")
            self.stdout.write("Nothing deleted. Re-run with --execute to delete.")
            return

        affected_sources = set(
            ArtistaLastfmSimilar.objects.filter(
                target__in=cohort_qs(keep_before)
            ).values_list("source_id", flat=True)
        )
        deleted = 0
        while True:
            batch_pks = list(
                cohort_qs(keep_before).values_list("pk", flat=True)[:batch]
            )
            if not batch_pks:
                break
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
                "purgar_pendents_post_seed: deleted %d (total %d)",
                len(batch_pks),
                deleted,
            )
            self.stdout.write(f"  deleted {len(batch_pks)} (total {deleted})")

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
