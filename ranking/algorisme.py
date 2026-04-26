"""Ranking algorithm v2.0 (2026-04-23).

Rewrote the former 14-CTE SQL into a Python-first pipeline. The old
algorithm read a pre-normalised `score_entrada` (percentile of daily
playcount) and mixed in descent / novelty / smoothing heuristics; it
was brittle and hard to reason about.

v2.0 operates directly on the raw `SenyalDiari.lastfm_playcount`
snapshots. For each eligible track we compute:

  1. weekly_plays  — playcount today minus playcount 7 days ago.
                     Handles release <7 days ago (linear extrapolation),
                     gaps in the signal (closest neighbour ± a few days),
                     and Last.fm backfills that produce negatives
                     (clamped to 0).
  2. age_factor    — `1 - min(1, (dies / 365)^exponent)` with
                     `exponent_penalitzacio_antiguitat` (default 2.5).
  3. past_top_factor — `max(0, 1 - Σ coef / 2^(posicio-1))` across every
                     prior TopSetmanal row for this (canço, territori)
                     at posicions ≤ 40. Position 1 costs 4%, position 2
                     costs 2%, etc. — accumulates without floor.
  4. Monopoly post-process — after sorting by base_score, apply
                     multiplicative penalties: ×(1 - penalitzacio_album)
                     per earlier track from same album, ×(1 - penalitzacio
                     _artista) per earlier track from same main artist.
                     Re-sort by final score, top 100.

PPCC is still an aggregate across non-PPCC rankings, with a 4% position
penalty per source position and dedup by canço.

ALT is an umbrella for below-threshold optional territoris (CNO / AND /
FRA / ALG / CAR) plus literal ALT (artists from outside the PPCC).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from music.constants import DIES_CADUCITAT
from music.models import Canco
from ranking.models import ConfiguracioGlobal, SenyalDiari, TopSetmanal

logger = logging.getLogger(__name__)

# Territori buckets.
TERRITORIS_FIXOS = {"CAT", "VAL", "BAL"}
TERRITORIS_AGREGATS = {"ALT", "PPCC"}
TERRITORIS_OPCIONALS = {"CNO", "AND", "FRA", "ALG", "CAR"}

# When looking for a SenyalDiari "~ 7 days ago" we accept any row within
# this many days on either side; closest wins. Keeps gaps in ingestion
# from blanking out otherwise-healthy tracks.
_WEEK_WINDOW_DAYS = 3


def territoris_amb_top_propi() -> list[str]:
    """Codis dels territoris que tenen prou cançons per un top propi.

    Sempre: CAT, VAL, BAL, ALT, PPCC.
    Opcionals (CNO / AND / FRA / ALG / CAR) entren si tenen
    `min_cancons_ranking_propi` cançons verificades actives amb
    llançament dins la finestra `DIES_CADUCITAT`.
    """
    config = ConfiguracioGlobal.load()
    threshold = config.min_cancons_ranking_propi
    cutoff = date.today() - timedelta(days=DIES_CADUCITAT)

    result = sorted(TERRITORIS_FIXOS | TERRITORIS_AGREGATS)
    for codi in sorted(TERRITORIS_OPCIONALS):
        count = Canco.objects.filter(
            verificada=True,
            activa=True,
            data_llancament__gte=cutoff,
            artista__territoris__codi=codi,
        ).count()
        if count >= threshold:
            result.append(codi)
    return result


# ── Per-territori computation ─────────────────────────────────────────


def calcular_top_territori(territori: str) -> list[dict]:
    """Run the v2.0 ranking for a single territori.

    Returns a list of dicts sorted by posicio ascending:
        {canco_id, score_setmanal, posicio, posicio_anterior,
         canvi_posicio, weekly_plays}.
    Limit: top 100.
    """
    if territori == "PPCC":
        return _calcular_top_ppcc()

    # ALT collects literal-ALT artists + any optional territori below
    # its own-top threshold.
    if territori == "ALT":
        eligible = set(territoris_amb_top_propi())
        territoris_match = ["ALT"] + sorted(TERRITORIS_OPCIONALS - eligible)
    else:
        territoris_match = [territori]

    cfg = ConfiguracioGlobal.load()
    return _top_for_territoris(
        territori=territori, territoris_match=territoris_match, cfg=cfg
    )


def _top_for_territoris(
    territori: str, territoris_match: list[str], cfg: ConfiguracioGlobal
) -> list[dict]:
    """Core: eligible cançons × weekly_plays × age × past_top, then monopoly."""
    today = date.today()
    cutoff = today - timedelta(days=DIES_CADUCITAT)

    # Cançons whose main artist OR any collaborator lives in any of the
    # matched territoris. `distinct` to avoid dupes from the OR.
    cancons_qs = (
        Canco.objects.filter(
            verificada=True,
            activa=True,
            data_llancament__gte=cutoff,
        )
        .filter(
            Q(artista__territoris__codi__in=territoris_match)
            | Q(artistes_col__territoris__codi__in=territoris_match)
        )
        .select_related("album", "artista")
        .distinct()
    )
    cancons = {c.pk: c for c in cancons_qs}
    if not cancons:
        return []

    # Pull a fortnight of signal in one query. Enough slack to find a
    # "~ 7 days ago" row even when some days are missing.
    window_start = today - timedelta(days=14)
    senyals_by_canco: dict[int, list[SenyalDiari]] = defaultdict(list)
    for s in SenyalDiari.objects.filter(
        canco_id__in=cancons.keys(),
        data__gte=window_start,
        error=False,
        lastfm_playcount__isnull=False,
    ).only("canco_id", "data", "lastfm_playcount"):
        senyals_by_canco[s.canco_id].append(s)
    for lst in senyals_by_canco.values():
        lst.sort(key=lambda s: s.data)

    # Prior TopSetmanal entries per canço (for the past-top penalty).
    prior_positions_by_canco: dict[int, list[int]] = defaultdict(list)
    for rs_canco_id, rs_pos in TopSetmanal.objects.filter(
        canco_id__in=cancons.keys(),
        territori=territori,
        posicio__lte=40,
    ).values_list("canco_id", "posicio"):
        prior_positions_by_canco[rs_canco_id].append(rs_pos)

    # Previous week for canvi_posicio lookup.
    prev_week_positions: dict[int, int] = {}
    prev_setmana = (
        TopSetmanal.objects.filter(territori=territori)
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    if prev_setmana is not None:
        for c_id, pos in TopSetmanal.objects.filter(
            territori=territori, setmana=prev_setmana
        ).values_list("canco_id", "posicio"):
            prev_week_positions[c_id] = pos

    exp = float(cfg.exponent_penalitzacio_antiguitat)
    coef_top = float(cfg.coeficient_penalitzacio_top)
    pen_album = float(cfg.penalitzacio_album_per_canco)
    pen_artista = float(cfg.penalitzacio_artista_per_canco)
    # Editorial floor: songs below `min_escoltes_top` weekly plays
    # don't even enter the candidate pool, so the tail of every
    # territori top is meaningful instead of a parade of 1-2 play
    # entries. If this leaves a territori with <40 candidates the
    # top is shorter — no padding with noise.
    min_plays = int(cfg.min_escoltes_top or 0)

    rows: list[dict] = []
    for canco in cancons.values():
        plays = _compute_weekly_plays(
            canco=canco, signals=senyals_by_canco.get(canco.pk, []), today=today
        )
        if plays < min_plays:
            continue

        age_factor = _age_factor(canco.data_llancament, today=today, exponent=exp)
        past_top_factor = _past_top_factor(
            prior_positions_by_canco.get(canco.pk, []), coef_top
        )

        base_score = plays * age_factor * past_top_factor
        if base_score <= 0:
            continue

        rows.append(
            {
                "canco_id": canco.pk,
                "album_id": canco.album_id,
                "artista_id": canco.artista_id,
                "weekly_plays": plays,
                "age_factor": age_factor,
                "past_top_factor": past_top_factor,
                "base_score": base_score,
            }
        )

    if not rows:
        return []

    # Sort by base_score DESC so monopoly sees earlier-ranked first.
    rows.sort(key=lambda r: -r["base_score"])

    seen_albums: dict[int, int] = defaultdict(int)
    seen_artists: dict[int, int] = defaultdict(int)
    for r in rows:
        alb_seen = seen_albums[r["album_id"]] if r["album_id"] else 0
        art_seen = seen_artists[r["artista_id"]] if r["artista_id"] else 0
        monopoly = ((1.0 - pen_album) ** alb_seen) * ((1.0 - pen_artista) ** art_seen)
        r["monopoli_factor"] = monopoly
        r["final_score"] = r["base_score"] * monopoly
        if r["album_id"]:
            seen_albums[r["album_id"]] = alb_seen + 1
        if r["artista_id"]:
            seen_artists[r["artista_id"]] = art_seen + 1

    # Monopoly may reorder: sort by final_score and truncate.
    # Also drop anything that rounds to zero (final_score < 1) — see
    # the editorial floor in `min_escoltes_top` for context. The plays
    # floor catches noise at the input; this catches songs that
    # cleared the plays floor but got crushed by past-top + monopoli.
    rows.sort(key=lambda r: -r["final_score"])
    rows = [r for r in rows if r["final_score"] >= 1.0]
    top = rows[:100]

    results: list[dict] = []
    for i, r in enumerate(top, start=1):
        prev_pos = prev_week_positions.get(r["canco_id"])
        canvi = (prev_pos - i) if prev_pos is not None else None
        results.append(
            {
                "canco_id": r["canco_id"],
                "score_setmanal": round(r["final_score"], 2),
                "posicio": i,
                "posicio_anterior": prev_pos,
                "canvi_posicio": canvi,
                "weekly_plays": r["weekly_plays"],
                "age_factor": r["age_factor"],
                "past_top_factor": r["past_top_factor"],
                "monopoli_factor": r["monopoli_factor"],
            }
        )
    return results


# ── Weekly-plays estimator (with gap + fresh-release handling) ────────


def _compute_weekly_plays(
    canco: Canco, signals: list[SenyalDiari], today: date
) -> float:
    """Estimate plays gained in the last 7 days for `canco`.

    `signals` is pre-sorted ascending by date. Strategy, in priority
    order:

    1. **Fresh release** (release < 7 days ago): the canço didn't
       exist a week ago, so `playcount 7 d ago == 0` by definition.
       `weekly_plays = playcount_today` — every play it has is "this
       week". **No extrapolation**: projecting a 2-day pace to 7 days
       turns a 2-day-old release with a launch spike into a phantom
       weekly figure (e.g. «Alba» de Suc i Sopes hit 2 541 against
       a real Last.fm count of 726). Cap at `playcount_today` is the
       only honest answer when the song's whole life ≤ the window.
    2. **Rolling delta** (preferred when we have a baseline):
       newest signal as "today's" playcount; closest signal within
       ±_WEEK_WINDOW_DAYS of "today - 7d" as baseline; rescale the
       delta to a 7-day denominator. Negative deltas (Last.fm
       back-corrections) clamp to 0.
    3. **Older delta fallback** (any signal ≥4 days back): same idea,
       just with whatever historical sample we have.
    4. **Lifetime extrapolation**: when the canço is **older than 7
       days** but we still lack a baseline (no SenyalDiari row from
       a week ago — typically newly-ingested catalogue), treat
       `playcount_today` as cumulative plays over the canço's life
       and rescale to 7 days. Capped denominator at DIES_CADUCITAT.
       This branch is **specifically not** for fresh releases
       (branch 1 already handles those without inflation).
    """
    if not signals:
        return 0.0

    latest = signals[-1]
    playcount_today = latest.lastfm_playcount
    if playcount_today is None:
        return 0.0

    # 1) Fresh release branch — we know the baseline (zero) without
    # needing any historical SenyalDiari row, because the canço
    # literally didn't exist 7 days ago.
    if canco.data_llancament and canco.data_llancament > today - timedelta(days=7):
        return max(0.0, float(playcount_today))

    # 2) Preferred: rolling 7-day delta with ±window.
    target = today - timedelta(days=7)
    window_lo = today - timedelta(days=7 + _WEEK_WINDOW_DAYS)
    window_hi = today - timedelta(days=7 - _WEEK_WINDOW_DAYS)
    candidates = [
        s
        for s in signals
        if s is not latest
        and s.lastfm_playcount is not None
        and window_lo <= s.data <= window_hi
    ]
    if candidates:
        baseline = min(candidates, key=lambda s: abs((s.data - target).days))
        delta = playcount_today - baseline.lastfm_playcount
        gap_days = (latest.data - baseline.data).days or 7
        return max(0.0, delta * 7.0 / gap_days)

    # 3) Older delta fallback.
    older = [
        s
        for s in signals
        if s is not latest
        and s.lastfm_playcount is not None
        and s.data <= today - timedelta(days=4)
    ]
    if older:
        baseline = older[-1]
        gap_days = (latest.data - baseline.data).days
        if gap_days <= 0:
            return 0.0
        delta = playcount_today - baseline.lastfm_playcount
        return max(0.0, delta * 7.0 / gap_days)

    # 4) Lifetime extrapolation — last resort. Cap denominator at
    # DIES_CADUCITAT so very old tracks don't get a microscopic value
    # (they're already filtered out by the eligibility query upstream
    # but the cap keeps the math honest if the function is used
    # standalone). Falls back to release date if available, otherwise
    # to the gap between the latest signal and the canço's creation.
    if canco.data_llancament:
        lifetime_days = max((today - canco.data_llancament).days, 1)
        lifetime_days = min(lifetime_days, DIES_CADUCITAT)
        return max(0.0, playcount_today * 7.0 / lifetime_days)
    return 0.0


# ── Factors ───────────────────────────────────────────────────────────


def _age_factor(data_llancament: date | None, today: date, exponent: float) -> float:
    """1 - min(1, (dies/365)^exponent). Newer = closer to 1, older → 0."""
    if data_llancament is None:
        return 1.0
    days = max((today - data_llancament).days, 0)
    penalty = min(1.0, (days / 365.0) ** exponent)
    return max(0.0, 1.0 - penalty)


def _past_top_factor(prior_positions: list[int], coef_base: float) -> float:
    """Multiplicative factor for prior weeks at top.

    Each past position N contributes `coef_base / 2^(N-1)` to a cumulative
    penalty. Factor = max(0, 1 - total_penalty).
    """
    if not prior_positions:
        return 1.0
    total = 0.0
    for pos in prior_positions:
        if pos < 1:
            continue
        total += coef_base / (2.0 ** (pos - 1))
    return max(0.0, 1.0 - total)


# ── PPCC aggregation ──────────────────────────────────────────────────


def _calcular_top_ppcc() -> list[dict]:
    """Aggregate all non-PPCC rankings, penalise by source position, dedupe.

    The per-position penalty (`ppcc_penalitzacio_per_posicio`, default
    0.04) lives on `ConfiguracioGlobal` since 2026-04-25 (Sprint A);
    editing it from staff config now reaches the ranking without code.
    """
    cfg = ConfiguracioGlobal.load()
    pos_penalty = float(cfg.ppcc_penalitzacio_per_posicio)
    source_territoris = [t for t in territoris_amb_top_propi() if t != "PPCC"]
    all_results: list[dict] = []
    for t in source_territoris:
        for r in calcular_top_territori(t):
            r = dict(r)
            r["territori_original"] = t
            all_results.append(r)

    if not all_results:
        return []

    for r in all_results:
        pos = r.get("posicio", 1)
        score = float(r.get("score_setmanal") or 0.0)
        r["score_global"] = round(score * (1.0 - (pos - 1) * pos_penalty), 4)

    best_by_canco: dict[int, dict] = {}
    for r in all_results:
        cid = r["canco_id"]
        if (
            cid not in best_by_canco
            or r["score_global"] > best_by_canco[cid]["score_global"]
        ):
            best_by_canco[cid] = r

    deduped = sorted(best_by_canco.values(), key=lambda x: -x["score_global"])
    out: list[dict] = []
    for i, r in enumerate(deduped[:100], start=1):
        out.append(
            {
                "canco_id": r["canco_id"],
                "score_setmanal": r["score_global"],
                "posicio": i,
                "posicio_anterior": r.get("posicio_anterior"),
                "canvi_posicio": r.get("canvi_posicio"),
                "weekly_plays": r.get("weekly_plays"),
                "age_factor": r.get("age_factor"),
                "past_top_factor": r.get("past_top_factor"),
                "monopoli_factor": r.get("monopoli_factor"),
            }
        )
    return out


# Historical: keep Decimal imported so tests that inspect module-level
# names don't regress; not used in live code but signals the v2.0 sweep
# touched this module.
_ = Decimal
