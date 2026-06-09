import logging
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from music.constants import DIES_CADUCITAT
from music.models import Canco, Territori
from ranking.algorisme import (
    TERRITORIS_AGREGATS,
    TERRITORIS_FIXOS,
    TERRITORIS_OPCIONALS,
    calcular_top_territori,
    territoris_amb_top_propi,
)
from ranking.models import (
    ConfiguracioGlobal,
    SenyalDiari,
    TopProvisional,
    TopSetmanal,
)

logger = logging.getLogger(__name__)

ALL_TERRITORIS = sorted(TERRITORIS_FIXOS | TERRITORIS_AGREGATS | TERRITORIS_OPCIONALS)

# R1: semantic tag for the current ranking algorithm. Bump when the formula
# changes in a way that affects results. Historical rows keep their own tag.
# v2.0 (2026-04-23) replaced the 14-CTE score_entrada pipeline with a
# weekly-plays Python algorithm.
ALGORITHM_VERSION = "v2.0"

# R1: coefficients we snapshot into each TopSetmanal row. Only the
# fields that still live on ConfiguracioGlobal after the v2.0 simplification.
_CONFIG_SNAPSHOT_FIELDS = [
    "dia_setmana_ranking",
    "exponent_penalitzacio_antiguitat",
    "penalitzacio_album_per_canco",
    "penalitzacio_artista_per_canco",
    "coeficient_penalitzacio_top",
    "min_cancons_ranking_propi",
    "soft_cap_actiu",
    "soft_cap_multiplicador",
    "soft_cap_floor_escoltes",
]


def _build_config_snapshot() -> dict:
    """R1: capture the full ConfiguracioGlobal as a JSON-safe dict."""
    cfg = ConfiguracioGlobal.load()
    return {
        field: float(v) if isinstance(v := getattr(cfg, field), Decimal) else v
        for field in _CONFIG_SNAPSHOT_FIELDS
    }


class Command(BaseCommand):
    help = "Calculate weekly ranking for one or all territories."

    def add_arguments(self, parser):
        parser.add_argument(
            "--setmana",
            type=str,
            default=None,
            help="Ranking week date (YYYY-MM-DD, must be Monday). Default: current week's Monday.",
        )
        parser.add_argument(
            "--territori",
            type=str,
            default=None,
            help="Single territory code (e.g. CAT). Default: all eligible.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print results without writing to DB.",
        )
        parser.add_argument(
            "--provisional",
            action="store_true",
            help="Write to TopProvisional (rolling daily) instead of TopSetmanal.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        provisional = options["provisional"]

        # Parse setmana (must be Monday) — only for non-provisional
        if options["setmana"]:
            try:
                setmana = date.fromisoformat(options["setmana"])
            except ValueError:
                raise CommandError(
                    f"Invalid date: {options['setmana']}. Use YYYY-MM-DD."
                )
            if setmana.weekday() != 0:
                raise CommandError(
                    f"{setmana} is not a Monday (weekday={setmana.weekday()})."
                )
        else:
            today = date.today()
            setmana = today - timedelta(days=today.weekday())

        # Territories to process
        # PPCC must run LAST because it aggregates results from all other territories.
        if options["territori"]:
            territoris = [options["territori"].upper()]
        else:
            # Same set for provisional and setmanal: fixed + aggregates (+ optional for provisional).
            # Aggregates run LAST so they can read the just-computed individual results.
            if provisional:
                non_agg = sorted(
                    t for t in ALL_TERRITORIS if t not in TERRITORIS_AGREGATS
                )
            else:
                non_agg = sorted(TERRITORIS_FIXOS)
            agg = sorted(TERRITORIS_AGREGATS)
            territoris = non_agg + agg

        mode = "PROVISIONAL" if provisional else "SETMANAL"
        self.stdout.write(f"Mode: {mode}")
        self.stdout.write(f"Ranking week: {setmana}")
        self.stdout.write(f"Territories: {', '.join(territoris)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no DB writes.\n"))

        # Pre-flight: check data availability
        total_verified = Canco.objects.filter(
            verificada=True,
            activa=True,
            data_llancament__gte=date.today() - timedelta(days=DIES_CADUCITAT),
        ).count()
        with_plays = (
            SenyalDiari.objects.filter(
                data__gte=date.today() - timedelta(days=7),
                error=False,
                lastfm_playcount__isnull=False,
            )
            .values("canco_id")
            .distinct()
            .count()
        )

        coverage = (with_plays / total_verified * 100) if total_verified > 0 else 0
        self.stdout.write(
            f"Pre-flight: {with_plays}/{total_verified} verified tracks "
            f"have Last.fm playcount in last 7 days ({coverage:.0f}%)"
        )
        if coverage < 50:
            self.stdout.write(
                self.style.WARNING(
                    "  WARNING: coverage below 50%. Results may be incomplete."
                )
            )

        # Distinct dates with data
        distinct_dates = (
            SenyalDiari.objects.filter(
                data__gte=date.today() - timedelta(days=7),
                error=False,
                lastfm_playcount__isnull=False,
            )
            .values_list("data", flat=True)
            .distinct()
            .count()
        )
        self.stdout.write(f"  Days with data in window: {distinct_dates}")

        # Run ranking per territory
        summary = []
        for territori in territoris:
            self.stdout.write(f"\nCalculating {territori}...")
            results = calcular_top_territori(territori)

            top40 = [r for r in results if r["posicio"] <= 40]

            if not results:
                # Clear any stale rows from earlier runs so a formerly-
                # ranked canco doesn't linger once its territori drops
                # out (e.g. artist M2M corrected, ALT loses all feeders).
                if not dry_run:
                    if provisional:
                        TopProvisional.objects.filter(territori=territori).delete()
                    else:
                        TopSetmanal.objects.filter(
                            territori=territori, setmana=setmana
                        ).delete()
                if territori in (TERRITORIS_AGREGATS | TERRITORIS_OPCIONALS):
                    self.stdout.write(
                        f"  No data for {territori} — cleared stale rows."
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  No results for {territori} — cleared stale rows."
                        )
                    )
                continue

            summary.append((territori, len(top40)))

            if dry_run:
                self._print_top(territori, top40[:20])
            elif provisional:
                self._save_provisional(territori, top40)
                self.stdout.write(
                    f"  Saved {len(top40)} provisional positions for {territori}"
                )
            else:
                self._save_ranking(territori, setmana, top40)
                self.stdout.write(f"  Saved {len(top40)} positions for {territori}")

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                "\n" + " | ".join(f"{t}: {n} posicions" for t, n in summary)
            )
        )

    def _print_top(self, territori: str, rows: list[dict]) -> None:
        """Print ranking table for dry-run."""
        canco_ids = [r["canco_id"] for r in rows]
        cancons = {
            c.id: c
            for c in Canco.objects.filter(id__in=canco_ids).select_related("artista")
        }

        self.stdout.write(f"\n  TOP {len(rows)} {territori}:")
        self.stdout.write(f"  {'#':>3s}  {'Score':>7s}  {'Canvi':>5s}  Artista — Cançó")
        self.stdout.write(f"  {'---':>3s}  {'------':>7s}  {'-----':>5s}  {'─'*50}")

        for r in rows:
            c = cancons.get(r["canco_id"])
            nom = f"{c.artista.nom} — {c.nom}" if c else f"(id={r['canco_id']})"
            canvi = r["canvi_posicio"]
            canvi_str = f"{canvi:+d}" if canvi is not None else "NEW"
            score = r["score_setmanal"] if r["score_setmanal"] is not None else 0.0
            self.stdout.write(
                f"  {r['posicio']:3d}  {score:7.2f}  {canvi_str:>5s}  {nom}"
            )

    def _save_ranking(self, territori: str, setmana: date, rows: list[dict]) -> None:
        """Replace ranking results for (territori, setmana) with the new top 40.

        Each row carries (R1) the algorithm version + config snapshot and
        (R2) denormalised name snapshots for survivability across later
        artist / track deletions.
        """
        config_snapshot = _build_config_snapshot()

        # Fetch canco + artist names in a single query for the snapshot.
        canco_ids = [r["canco_id"] for r in rows]
        names = {
            c.pk: (c.nom, c.artista.nom)
            for c in Canco.objects.filter(pk__in=canco_ids).select_related("artista")
        }

        with transaction.atomic():
            TopSetmanal.objects.filter(
                territori=territori,
                setmana=setmana,
            ).delete()
            objs = []
            for r in rows:
                canco_nom, artista_nom = names.get(r["canco_id"], ("", ""))
                objs.append(
                    TopSetmanal(
                        canco_id=r["canco_id"],
                        territori=territori,
                        setmana=setmana,
                        posicio=r["posicio"],
                        score_setmanal=r["score_setmanal"] or 0.0,
                        weekly_plays=r.get("weekly_plays"),
                        canco_nom_snapshot=(canco_nom or "")[:500],
                        artista_nom_snapshot=(artista_nom or "")[:255],
                        algorithm_version=ALGORITHM_VERSION,
                        config_snapshot=config_snapshot,
                    )
                )
            TopSetmanal.objects.bulk_create(objs)

    def _save_provisional(self, territori: str, rows: list[dict]) -> None:
        """Replace provisional ranking for a territory.

        v2.0: `escoltes_setmanals` stores the rolling 7-day plays delta
        (same figure that feeds the algorithm as `weekly_plays`).
        Renamed from `lastfm_playcount` on 2026-04-25 (Sprint A) to
        match its actual semantics; the legacy `dies_en_top` companion
        column was dropped at the same time.
        """
        with transaction.atomic():
            TopProvisional.objects.filter(territori=territori).delete()
            objs = []
            for r in rows:
                objs.append(
                    TopProvisional(
                        canco_id=r["canco_id"],
                        territori=territori,
                        posicio=r["posicio"],
                        score_setmanal=r["score_setmanal"] or 0.0,
                        escoltes_setmanals=int(r.get("weekly_plays") or 0),
                        age_factor=r.get("age_factor"),
                        past_top_factor=r.get("past_top_factor"),
                        monopoli_factor=r.get("monopoli_factor"),
                    )
                )
            TopProvisional.objects.bulk_create(objs)
