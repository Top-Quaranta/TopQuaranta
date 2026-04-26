"""
One-off ranking simulation using real Last.fm data + percent_rank formula.
Read-only — no DB writes. Run with: .venv/bin/python scripts/simular_ranking.py
"""

import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from scipy.stats import percentileofscore

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "topquaranta.settings.production")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from ranking.models import ConfiguracioGlobal, SenyalDiari

# ── Step 1: Load data and compute score_entrada via percent_rank ──


def load_config():
    """Load algorithm coefficients from ConfiguracioGlobal."""
    cfg = ConfiguracioGlobal.load()
    return {
        "penalitzacio_descens": float(cfg.penalitzacio_descens),
        "exponent_penalitzacio_antiguitat": float(cfg.exponent_penalitzacio_antiguitat),
        "max_factor_a": float(cfg.max_factor_a),
        "max_factor_b": float(cfg.max_factor_b),
        "max_factor_c": float(cfg.max_factor_c),
        "max_factor_final": float(cfg.max_factor_final),
        "penalitzacio_album_per_canco": float(cfg.penalitzacio_album_per_canco),
        "penalitzacio_artista_per_canco": float(cfg.penalitzacio_artista_per_canco),
        "coeficient_penalitzacio_top": float(cfg.coeficient_penalitzacio_top),
        "penalitzacio_setmana_0": float(cfg.penalitzacio_setmana_0),
        "penalitzacio_setmana_1": float(cfg.penalitzacio_setmana_1),
        "penalitzacio_setmana_2": float(cfg.penalitzacio_setmana_2),
        "suavitat": float(cfg.suavitat),
    }


def load_senyal_data():
    """Load all SenyalDiari for the last 5 available dates.
    Returns (dates_sorted, senyal_by_canco) where senyal_by_canco maps
    canco_id -> {data: {playcount, listeners}}.
    """
    # Find available dates
    available_dates = list(
        SenyalDiari.objects.filter(error=False, lastfm_playcount__isnull=False)
        .values_list("data", flat=True)
        .distinct()
        .order_by("-data")[:5]
    )
    if not available_dates:
        print("No SenyalDiari data found!")
        sys.exit(1)

    dates_sorted = sorted(available_dates)
    latest = dates_sorted[-1]

    print(f"Available dates: {', '.join(str(d) for d in dates_sorted)}")
    print(f"Latest date: {latest}")
    print(f"Days span: {(dates_sorted[-1] - dates_sorted[0]).days}")

    # Load all SenyalDiari for these dates with related objects
    qs = SenyalDiari.objects.filter(
        data__in=dates_sorted, error=False, lastfm_playcount__isnull=False
    ).select_related(
        "canco",
        "canco__artista",
        "canco__album",
    )

    # Prefetch territories in a single query
    from music.models import Artista

    artista_ids = set()
    rows = list(qs)
    for row in rows:
        artista_ids.add(row.canco.artista_id)

    # Load all territory mappings at once
    from django.db import connection

    artista_territoris = defaultdict(set)
    if artista_ids:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT artista_id, territori_id FROM music_artista_territoris WHERE artista_id IN %s",
                [tuple(artista_ids)],
            )
            for art_id, terr_code in cursor.fetchall():
                artista_territoris[art_id].add(terr_code)

    # Build per-canco data structure
    senyal_by_canco = {}
    for row in rows:
        cid = row.canco_id
        if cid not in senyal_by_canco:
            canco = row.canco
            terrs = artista_territoris.get(canco.artista_id, set())
            senyal_by_canco[cid] = {
                "nom": canco.nom,
                "artista_nom": canco.artista.nom,
                "artista_id": canco.artista_id,
                "album_id": canco.album_id,
                "album_nom": canco.album.nom if canco.album else "",
                "album_data": canco.album.data_llancament if canco.album else None,
                "territoris": terrs,
                "daily": {},
            }
        senyal_by_canco[cid]["daily"][row.data] = {
            "playcount": row.lastfm_playcount,
            "listeners": row.lastfm_listeners,
        }

    print(f"Tracks loaded: {len(senyal_by_canco)}")
    print(f"Total SenyalDiari rows: {len(rows)}")

    return dates_sorted, latest, senyal_by_canco


def compute_score_entrada(senyal_by_canco, dates_sorted):
    """Compute percent_rank score_entrada for each day.
    Returns score_entrada_map: {canco_id: {data: score}}.
    """
    scores = {}

    for d in dates_sorted:
        # Collect all playcounts for this day
        day_plays = []
        day_cancons = []
        for cid, info in senyal_by_canco.items():
            if d in info["daily"]:
                pc = info["daily"][d]["playcount"]
                day_plays.append(pc)
                day_cancons.append(cid)

        if not day_plays:
            continue

        sorted_plays = sorted(day_plays)
        for i, cid in enumerate(day_cancons):
            pc = senyal_by_canco[cid]["daily"][d]["playcount"]
            score = percentileofscore(sorted_plays, pc, kind="rank")
            if cid not in scores:
                scores[cid] = {}
            scores[cid][d] = score

    return scores


# ── Step 3: The ranking algorithm in pure Python ──


def run_ranking(territori, senyal_by_canco, scores, dates_sorted, latest, cfg):
    """Run the full 14-CTE equivalent algorithm for one territory.
    Returns list of dicts sorted by score_setmanal DESC.
    """
    today = latest

    # Filter cancons that appear in this territory and have score data
    cancons = []
    for cid, info in senyal_by_canco.items():
        if territori not in info["territoris"]:
            continue
        if cid not in scores:
            continue
        # Must have at least 1 day of data
        days_with_data = [d for d in dates_sorted if d in scores.get(cid, {})]
        if not days_with_data:
            continue
        cancons.append((cid, info, days_with_data))

    if not cancons:
        return []

    # ── base CTE ──
    base_rows = []
    for cid, info, days in cancons:
        day_scores = [scores[cid][d] for d in days]

        # popularitat_mitjana: mean of all available days
        popularitat_mitjana = sum(day_scores) / len(day_scores)

        # popularitat_inici: days -7 to -5 from latest
        inici_days = [d for d in days if (today - d).days >= 5]
        popularitat_inici = (
            sum(scores[cid][d] for d in inici_days) / len(inici_days)
            if inici_days
            else 0.0
        )

        # popularitat_final: days -2 to 0 from latest
        final_days = [d for d in days if (today - d).days <= 2]
        popularitat_final = (
            sum(scores[cid][d] for d in final_days) / len(final_days)
            if final_days
            else 0.0
        )

        dies_en_top = len(days)

        # antiguitat_dies
        album_data = info["album_data"]
        if album_data:
            antiguitat_dies = (today - album_data).days
        else:
            antiguitat_dies = 180

        # Latest day playcount for display
        latest_pc = info["daily"].get(today, {}).get("playcount", 0)

        base_rows.append(
            {
                "cid": cid,
                "nom": info["nom"],
                "artista_nom": info["artista_nom"],
                "artista_id": info["artista_id"],
                "album_id": info["album_id"],
                "album_nom": info["album_nom"],
                "popularitat_mitjana": popularitat_mitjana,
                "popularitat_inici": popularitat_inici,
                "popularitat_final": popularitat_final,
                "dies_en_top": dies_en_top,
                "setmanes_top": 0,
                "antiguitat_dies": antiguitat_dies,
                "posicio_anterior": None,
                "playcount": latest_pc,
            }
        )

    # ── fase_a ──
    for row in base_rows:
        ant = row["antiguitat_dies"]
        pen_ant = min(1.0, (ant / 365.0) ** cfg["exponent_penalitzacio_antiguitat"])
        pen_desc = (
            cfg["penalitzacio_descens"]
            if row["popularitat_final"] < row["popularitat_inici"]
            else 0.0
        )
        pes_est = min(row["dies_en_top"] / 7.0, 1.0)
        pen_top = 0.0  # no history

        factor_a = min(
            max(1.0 - pen_ant - pen_desc - pen_top, -1.0), cfg["max_factor_a"]
        )
        score_a = row["popularitat_mitjana"] * pes_est * factor_a

        row["pen_antiguitat"] = pen_ant
        row["pen_descens"] = pen_desc
        row["pes_estabilitat"] = pes_est
        row["pen_top"] = pen_top
        row["factor_a"] = factor_a
        row["score_a"] = score_a

    # Sort by score_a DESC → posicio_a
    base_rows.sort(key=lambda r: r["score_a"], reverse=True)
    for i, row in enumerate(base_rows):
        row["posicio_a"] = i + 1

    # ── fase_b (monopoly penalties) ──
    # Count how many tracks from same album/artist rank higher
    for row in base_rows:
        pen_album = 0
        pen_artista = 0
        for other in base_rows:
            if other["posicio_a"] >= row["posicio_a"]:
                continue
            if other["album_id"] == row["album_id"]:
                pen_album += 1
            if other["artista_id"] == row["artista_id"] and other["cid"] != row["cid"]:
                pen_artista += 1

        row["pen_album_count"] = pen_album
        row["pen_artista_count"] = pen_artista
        row["pen_album"] = pen_album * cfg["penalitzacio_album_per_canco"]
        row["pen_artista"] = pen_artista * cfg["penalitzacio_artista_per_canco"]
        factor_b = min(
            max(row["factor_a"] - row["pen_album"] - row["pen_artista"], -1.0),
            cfg["max_factor_b"],
        )
        row["factor_b"] = factor_b
        row["score_b"] = row["popularitat_mitjana"] * row["pes_estabilitat"] * factor_b

    # Sort by score_b DESC → posicio_b
    base_rows.sort(key=lambda r: r["score_b"], reverse=True)
    for i, row in enumerate(base_rows):
        row["posicio_b"] = i + 1

    # ── fase_c (anti-hype) ──
    for row in base_rows:
        sw = row["setmanes_top"]
        pb = row["posicio_b"]
        if sw == 0 and pb <= 20:
            pen_entrada = cfg["penalitzacio_setmana_0"]
        elif sw == 1 and pb <= 10:
            pen_entrada = cfg["penalitzacio_setmana_1"]
        elif sw == 2 and pb <= 5:
            pen_entrada = cfg["penalitzacio_setmana_2"]
        else:
            pen_entrada = 0.0

        pos_ant = row["posicio_anterior"] if row["posicio_anterior"] is not None else 41
        canvi_b = pos_ant - min(pb, 41)

        row["pen_entrada"] = pen_entrada
        row["canvi_posicio_b"] = canvi_b

    # ── fase_final (smoothing) ──
    for row in base_rows:
        factor_suav = row["canvi_posicio_b"] / (100.0 * cfg["suavitat"])
        factor_final = min(
            max(row["factor_b"] - row["pen_entrada"] - factor_suav, 0.0),
            cfg["max_factor_final"],
        )
        score_setmanal = (
            row["popularitat_mitjana"] * row["pes_estabilitat"] * factor_final
        )

        row["factor_suavitat"] = factor_suav
        row["factor_final"] = factor_final
        row["score_setmanal"] = score_setmanal

    # Sort by score_setmanal DESC → posicio final
    base_rows.sort(key=lambda r: r["score_setmanal"], reverse=True)
    for i, row in enumerate(base_rows):
        row["posicio"] = i + 1

    return base_rows


# ── Step 4: Output ──


def print_ranking(territori, rows, dates_sorted, latest):
    top40 = [r for r in rows if r["posicio"] <= 40]
    total = len(rows)

    print(f"\n{'='*80}")
    print(f"  TOP 40 {territori} — simulacio {latest}")
    print(f"  ({len(dates_sorted)} dies de dades, score_entrada=percent_rank)")
    print(f"{'='*80}")
    print(
        f"  {'#':>3s}  {'Score':>7s}  {'Plays':>8s}  {'Dies':>4s}  {'Antig':>6s}  "
        f"{'fA':>5s} {'fB':>5s} {'fF':>5s}  Artista — Canco"
    )
    print(
        f"  {'---':>3s}  {'------':>7s}  {'------':>8s}  {'----':>4s}  {'-----':>6s}  "
        f"{'---':>5s} {'---':>5s} {'---':>5s}  {'─'*40}"
    )

    for r in top40:
        ant_str = f"{r['antiguitat_dies']}d"
        print(
            f"  {r['posicio']:3d}  {r['score_setmanal']:7.2f}  {r['playcount']:8,d}  "
            f"{r['dies_en_top']:4d}  {ant_str:>6s}  "
            f"{r['factor_a']:5.2f} {r['factor_b']:5.2f} {r['factor_final']:5.2f}  "
            f"{r['artista_nom']} — {r['nom']}"
        )

    outside = total - min(len(top40), 40)
    print(f"\n  Total cancons amb dades: {total}")
    print(f"  Dins del top 40: {len(top40)}")
    print(f"  Fora del top 40: {outside}")

    # Most penalized by album monopoly
    album_penalized = sorted(rows, key=lambda r: r["pen_album"], reverse=True)[:3]
    if album_penalized and album_penalized[0]["pen_album"] > 0:
        print(f"\n  Top 3 penalitzades per monopoli d'album:")
        for r in album_penalized:
            if r["pen_album"] > 0:
                print(
                    f"    pos_a={r['posicio_a']:3d} → pos_b={r['posicio_b']:3d} | "
                    f"pen_album={r['pen_album']:.2f} ({r['pen_album_count']} tracks davant) | "
                    f"{r['artista_nom']} — {r['nom']} (album: {r['album_nom']})"
                )

    # Most penalized by artist monopoly
    artista_penalized = sorted(rows, key=lambda r: r["pen_artista"], reverse=True)[:3]
    if artista_penalized and artista_penalized[0]["pen_artista"] > 0:
        print(f"\n  Top 3 penalitzades per monopoli d'artista:")
        for r in artista_penalized:
            if r["pen_artista"] > 0:
                print(
                    f"    pos_a={r['posicio_a']:3d} → pos_b={r['posicio_b']:3d} | "
                    f"pen_artista={r['pen_artista']:.2f} ({r['pen_artista_count']} tracks davant) | "
                    f"{r['artista_nom']} — {r['nom']}"
                )


def main():
    print("Loading configuration...")
    cfg = load_config()
    print(f"  penalitzacio_descens={cfg['penalitzacio_descens']}")
    print(f"  exponent_antiguitat={cfg['exponent_penalitzacio_antiguitat']}")
    print(f"  max_factor_final={cfg['max_factor_final']}")

    print("\nLoading signal data...")
    dates_sorted, latest, senyal_by_canco = load_senyal_data()

    print("\nComputing score_entrada (percent_rank)...")
    scores = compute_score_entrada(senyal_by_canco, dates_sorted)

    # Quick stats on score_entrada for latest day
    latest_scores = [scores[cid][latest] for cid in scores if latest in scores[cid]]
    if latest_scores:
        import numpy as np

        arr = np.array(latest_scores)
        print(
            f"  score_entrada on {latest}: n={len(arr)}, "
            f"min={arr.min():.1f}, median={np.median(arr):.1f}, max={arr.max():.1f}, "
            f"std={arr.std():.1f}"
        )

    # Run ranking per territory
    for territori in ["CAT", "VAL", "BAL"]:
        print(f"\nRunning ranking for {territori}...")
        rows = run_ranking(
            territori, senyal_by_canco, scores, dates_sorted, latest, cfg
        )
        if rows:
            print_ranking(territori, rows, dates_sorted, latest)
        else:
            print(f"  No tracks for {territori}")

    print(f"\n{'='*80}")
    print("  Done.")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
