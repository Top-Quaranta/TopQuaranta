"""Daily snapshot of pipeline-state gauges into MetricaPipeline.

Runs once a day at 23:00 UTC (cron line in deploy/cron.topquaranta).
Idempotent: re-running on the same day overwrites that day's values
(via update_or_create on the unique (data, clau, dim1) constraint),
so a manual re-run after a fix is safe.

Each measurement is a small ORM query. Total runtime ~1-2 s on
the current DB. We deliberately don't recompute weekly/monthly
aggregates here — those derive on-demand from the daily series in
the staff /analytics endpoint.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from analytics.models import MetricaPipeline
from comptes.models import PerfilUsuari, Usuari
from music.constants import TERRITORIS_VALIDS
from music.models import Artista, Canco

logger = logging.getLogger(__name__)


def _set_int(today, clau: str, value: int, dim1: str = "") -> None:
    MetricaPipeline.objects.update_or_create(
        data=today,
        clau=clau,
        dimensio_1=dim1,
        defaults={"valor_int": int(value), "valor_float": None},
    )


def _set_float(today, clau: str, value: float, dim1: str = "") -> None:
    MetricaPipeline.objects.update_or_create(
        data=today,
        clau=clau,
        dimensio_1=dim1,
        defaults={"valor_int": None, "valor_float": float(value)},
    )


class Command(BaseCommand):
    help = "Snapshot daily pipeline-state gauges into MetricaPipeline."

    def handle(self, *args, **options) -> None:
        today = timezone.localdate()
        with transaction.atomic():
            self._catalog(today)
            self._cobertura(today)
            self._usuaris(today)
            self._per_territori(today)
        self.stdout.write(self.style.SUCCESS(f"Pipeline snapshot stored for {today}"))

    # ── Catalog totals ───────────────────────────────────────────────
    def _catalog(self, today) -> None:
        verif = Canco.objects.filter(verificada=True, activa=True).count()
        pendents = Canco.objects.filter(verificada=False, activa=True).count()
        rebutjades = Canco.objects.filter(activa=False).count()
        aprovats = Artista.objects.filter(aprovat=True).count()
        pendents_a = Artista.objects.filter(pendent_review=True).count()

        _set_int(today, "cancons_verificades", verif)
        _set_int(today, "cancons_pendents", pendents)
        _set_int(today, "cancons_rebutjades_acumulades", rebutjades)
        _set_int(today, "artistes_aprovats", aprovats)
        _set_int(today, "artistes_pendents", pendents_a)

    # ── Coverage of metadata sources ─────────────────────────────────
    def _cobertura(self, today) -> None:
        # Whisper LID coverage on the active pool — proxies "how
        # confident are we about language assignments?".
        active = Canco.objects.filter(activa=True)
        active_count = active.count() or 1  # avoid div-by-zero on day 0
        whisper_done = active.filter(whisper_processat_at__isnull=False).count()
        _set_float(
            today,
            "cobertura_whisper",
            round(100.0 * whisper_done / active_count, 2),
        )

        # MusicBrainz coverage on approved artistes.
        aprovats = Artista.objects.filter(aprovat=True)
        aprovats_count = aprovats.count() or 1
        mb_done = (
            aprovats.exclude(musicbrainz_id="")
            .exclude(musicbrainz_id__isnull=True)
            .count()
        )
        _set_float(
            today,
            "cobertura_mb",
            round(100.0 * mb_done / aprovats_count, 2),
        )

    # ── Community/account gauges ─────────────────────────────────────
    def _usuaris(self, today) -> None:
        _set_int(today, "usuaris_actius", Usuari.objects.filter(is_active=True).count())
        _set_int(
            today,
            "newsletter_subscriptors",
            PerfilUsuari.objects.filter(vol_newsletter=True).count(),
        )
        _set_int(
            today,
            "directori_visibles",
            PerfilUsuari.objects.filter(visible_directori=True).count(),
        )

    # ── Per-territori catalog distribution ───────────────────────────
    def _per_territori(self, today) -> None:
        for codi in TERRITORIS_VALIDS:
            n = (
                Canco.objects.filter(
                    verificada=True,
                    activa=True,
                    artista__territoris__codi=codi,
                )
                .distinct()
                .count()
            )
            _set_int(today, "cancons_per_territori", n, dim1=codi)
