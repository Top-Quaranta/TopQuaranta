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
import math
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Q

from music.constants import DIES_CADUCITAT
from music.constants import TERRITORIS_AGREGATS as _TERRITORIS_AGREGATS_TUPLE
from music.constants import TERRITORIS_FIXOS as _TERRITORIS_FIXOS_TUPLE
from music.constants import TERRITORIS_OPCIONALS as _TERRITORIS_OPCIONALS_TUPLE
from music.models import Canco
from ranking import senyal_youtube
from ranking.models import ConfiguracioGlobal, SenyalDiari, TopSetmanal

logger = logging.getLogger(__name__)

# Canonical territori subsets live in music.constants as tuples;
# the algorithm uses set semantics for union / difference, so we
# wrap once here.
TERRITORIS_FIXOS = set(_TERRITORIS_FIXOS_TUPLE)
TERRITORIS_AGREGATS = set(_TERRITORIS_AGREGATS_TUPLE)
TERRITORIS_OPCIONALS = set(_TERRITORIS_OPCIONALS_TUPLE)

# When looking for a SenyalDiari "~ 7 days ago" we accept any row within
# this many days on either side; closest wins. Keeps gaps in ingestion
# from blanking out otherwise-healthy tracks.
_WEEK_WINDOW_DAYS = 3

# Step-robust weekly-plays guard (2026-06-06). Last.fm periodically
# merges scrobbles onto a canonical recording, doubling a track's
# CUMULATIVE playcount overnight while the track NAME stays unchanged
# (so the track-switch guard below does NOT catch it). The rolling
# 7-day delta then reads that one-day step as a full week of plays —
# 74/888 top entries and 7 false #1s in the 2026-04-22 / 2026-05-21
# events (sonda 2026-06-06). We excise the step and back-fill its day(s)
# with the song's own clean daily rhythm. A genuine viral week spreads
# across several days and is NOT a single-day outlier, so it survives.
# A merge step is flagged only when ALL three hold for one segment:
#   - daily rate ≥ _MERGE_RATE_OVER_MEDIAN × the song's own median rate,
#   - increment ≥ _MERGE_DOUBLING_FRAC × the cumulative at the step
#     (a near-doubling — the signature of a lifetime-scrobble merge),
#   - absolute increment ≥ _MERGE_ABS_FLOOR, a light noise guard so a
#     2→5 "doubling" on a near-silent track is left alone.
# The doubling + rate criteria are the real fingerprint; the absolute
# floor is deliberately low (a 958-play overnight doubling of «Sa
# Madona» in BAL, a small territory, was enough to fake a #1 — the
# 2026-06-06 calibration set it to 300 after an initial 1000 missed it).
_MERGE_ABS_FLOOR = 300
_MERGE_RATE_OVER_MEDIAN = 8.0
_MERGE_DOUBLING_FRAC = 0.4

# Adaptive soft-cap (2026-06-09). The knee K is derived per territori from
# the median weekly_plays of recently-charting songs, so each territori
# measures its own outliers (CAT charts in the hundreds, VAL/BAL in the
# tens). We read the median over the published-chart head (top N) of the
# last W weeks: the FULL top is dragged down by the near-floor tail, which
# would put the knee too low and compress ordinary hits. Stored on
# TopSetmanal.weekly_plays since this date; before any history exists the
# median query is empty and the configurable floor takes over.
_SOFT_CAP_WINDOW_WEEKS = 10
_SOFT_CAP_TOP_N = 10


def _setmana_en_curs(today: date) -> date:
    """Monday of the week being computed — mirrors `calcular_top`.

    Every TopSetmanal read in the algorithm must exclude it. `calcular_top`
    saves each territori before PPCC aggregates, and PPCC re-runs each
    source territori: without this filter that second run reads the rows
    the first one just wrote, so a song is penalised for the very position
    it is being awarded and the soft-cap knee shifts mid-run. The result
    was a non-idempotent ranking whose published CAT order could invert
    inside PPCC (2026-08-15: Bocc #1 CAT / Rosalía #1 PPCC, both CAT-only).
    """
    return today - timedelta(days=today.weekday())


def _robust_weekly_from_series(series: list[tuple[date, int]]) -> float | None:
    """Step-robust weekly plays from a daily cumulative `series`.

    `series` is ascending `(data, playcount)` pairs, already filtered to
    one recording identity (the track-switch guard runs upstream). The
    function looks for a single merge-step — an implausible one-day jump
    in the cumulative — drops it, and projects the remaining clean daily
    rhythm to 7 days.

    Returns the cleaned weekly figure ONLY when a merge step is detected.
    Returns `None` otherwise, so the caller keeps the legacy endpoint
    delta unchanged — non-merge weeks stay byte-identical to the previous
    behaviour, and the week AFTER a merge is correct for free (the step
    is already in the baseline and outside this window). Also returns
    `None` when there is too little daily data to judge an outlier."""
    pts = [(d, p) for d, p in series if p is not None]
    if len(pts) < 4:
        return None
    segs: list[tuple[int, int, int]] = []  # (span_days, increment, base)
    for (da, pa), (db, pb) in zip(pts, pts[1:]):
        span = (db - da).days
        if span <= 0:
            continue
        segs.append((span, max(0, pb - pa), pa))
    if len(segs) < 3:
        return None
    covered = sum(span for span, _, _ in segs)
    if covered < 4:
        return None
    med = median(inc / span for span, inc, _ in segs)
    clean_inc = 0.0
    clean_days = 0
    flagged = False
    for span, inc, base in segs:
        rate = inc / span
        if (
            inc >= _MERGE_ABS_FLOOR
            and rate >= _MERGE_RATE_OVER_MEDIAN * max(med, 1.0)
            and inc >= _MERGE_DOUBLING_FRAC * max(base, 1)
        ):
            flagged = True
            continue  # drop the merge step; back-filled by the clean rhythm
        clean_inc += inc
        clean_days += span
    if not flagged or clean_days <= 0:
        return None
    return clean_inc / clean_days * 7.0


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


def calcular_top_territori(
    territori: str, resultats_previs: dict[str, list[dict]] | None = None
) -> list[dict]:
    """Run the v2.0 ranking for a single territori.

    Returns a list of dicts sorted by posicio ascending:
        {canco_id, score_setmanal, posicio, posicio_anterior,
         canvi_posicio, weekly_plays}.
    Limit: top 100.
    """
    if territori == "PPCC":
        return _calcular_top_ppcc(resultats_previs)

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
        # 2026-05-07 audit follow-up: drift-flagged rows are kept in
        # the DB for staff inspection but excluded from the ranking
        # signal. Without this guard, a Fades→TheFades-style silent
        # autocorrect on the err=6 retry path could pump the wrong
        # band's playcount into our weekly chart.
        corregit=False,
        lastfm_playcount__isnull=False,
    ).only("canco_id", "data", "lastfm_playcount"):
        senyals_by_canco[s.canco_id].append(s)
    for lst in senyals_by_canco.values():
        lst.sort(key=lambda s: s.data)

    # Re-issue guard (2026-08-15): earliest release date per (artista,
    # normalised title). A single re-issued inside a later EP/album is a
    # second Canco (own ISRC) that Last.fm answers with the same lifetime
    # playcount as the original — the "fresh release" branch would then
    # bank a year of plays as one week's. Bocc «Ànima D'Acer» did exactly
    # that: 966 plays flat for 3 days, #1 CAT / #2 PPCC on zero movement.
    #
    # Queried over the artists' WHOLE catalogue, not just the candidate
    # pool: the original is typically older than DIES_CADUCITAT and so
    # absent from the pool — which is precisely why the re-issue looks
    # new. (First cut of this guard read the pool and caught nothing.)
    frescos = [
        c
        for c in cancons.values()
        if c.data_llancament and c.data_llancament > today - timedelta(days=7)
    ]
    primer_llancament: dict[tuple[int, str], date] = {}
    if frescos:
        for aid, nom, data in Canco.objects.filter(
            artista_id__in={c.artista_id for c in frescos},
            data_llancament__isnull=False,
        ).values_list("artista_id", "nom", "data_llancament"):
            k = (aid, _track_identity(nom))
            if k not in primer_llancament or data < primer_llancament[k]:
                primer_llancament[k] = data

    # Prior TopSetmanal entries per canço (for the past-top penalty).
    prior_positions_by_canco: dict[int, list[int]] = defaultdict(list)
    for rs_canco_id, rs_pos in TopSetmanal.objects.filter(
        canco_id__in=cancons.keys(),
        territori=territori,
        # PAST tops only — a song must not be penalised for the position
        # it is being given right now (see `_setmana_en_curs`).
        setmana__lt=_setmana_en_curs(today),
        posicio__lte=40,
    ).values_list("canco_id", "posicio"):
        prior_positions_by_canco[rs_canco_id].append(rs_pos)

    # Previous week for canvi_posicio lookup.
    prev_week_positions: dict[int, int] = {}
    prev_setmana = (
        TopSetmanal.objects.filter(territori=territori)
        # Not the week being computed: once `calcular_top` has saved it,
        # "the most recent setmana" IS this one, and the movement column
        # compares the week against itself (every row "="). Console-only
        # today — the API derives movement from its own query — but wrong
        # is wrong.
        .filter(setmana__lt=_setmana_en_curs(today))
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

    # ── YouTube com a segona font ───────────────────────────────────
    # S'activa sola quan hi ha prou història (vegeu `senyal_youtube.actiu`).
    # Activa, el senyal passa a ser
    #     escoltes × pes + visualitzacions
    # i el terra passa a `min_senyal_combinat`, perquè els dos números
    # deixen d'estar en unitats d'escoltes.
    #
    # Es multipliquen les escoltes en lloc de dividir les
    # visualitzacions: `min_escoltes_top` és absolut, i dividint, una
    # cançó amb 400 visualitzacions i cap escolta cauria a 2 i quedaria
    # fora — precisament la gent que la segona font existeix per a no
    # perdre.
    yt_actiu = senyal_youtube.actiu(
        today, int(getattr(cfg, "youtube_dies_minims", 7) or 0)
    )
    yt_pes = int(getattr(cfg, "youtube_pes_escolta", 1000) or 1000)
    yt_views: dict[int, float] = {}
    if yt_actiu:
        yt_views = senyal_youtube.visualitzacions_setmanals(list(cancons.keys()), today)
        min_plays = int(getattr(cfg, "min_senyal_combinat", 200) or 0)
    # Adaptive outlier knee for this territori (None when the cap is off).
    # Computed once: it depends on the territori's history, not the song.
    soft_cap_knee = _soft_cap_knee(territori, cfg, today)

    rows: list[dict] = []
    for canco in cancons.values():
        plays = _compute_weekly_plays(
            canco=canco,
            signals=senyals_by_canco.get(canco.pk, []),
            today=today,
            primer_llancament=primer_llancament,
        )
        if yt_actiu:
            # Les escoltes pugen a les unitats del senyal combinat i
            # s'hi sumen les visualitzacions de la setmana. Una cançó
            # sense parella de fotos comparables simplement no aporta
            # res per YouTube — mai un zero, que seria una afirmació.
            plays = plays * yt_pes + yt_views.get(canco.pk, 0.0)

        # Eligibility is judged on RAW plays; the soft cap only reshapes
        # how a song's plays translate into score.
        if plays < min_plays:
            continue

        plays_eff = _apply_soft_cap(plays, soft_cap_knee)
        age_factor = _age_factor(canco.data_llancament, today=today, exponent=exp)
        past_top_factor = _past_top_factor(
            prior_positions_by_canco.get(canco.pk, []), coef_top
        )

        base_score = plays_eff * age_factor * past_top_factor
        if base_score <= 0:
            continue

        rows.append(
            {
                "canco_id": canco.pk,
                "album_id": canco.album_id,
                "artista_id": canco.artista_id,
                # Raw plays: persisted + displayed + feeds the historical
                # median. `weekly_plays_eff` is the capped value scoring used.
                "weekly_plays": plays,
                "weekly_plays_eff": plays_eff,
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
                "weekly_plays_eff": r.get("weekly_plays_eff", r["weekly_plays"]),
                "age_factor": r["age_factor"],
                "past_top_factor": r["past_top_factor"],
                "monopoli_factor": r["monopoli_factor"],
            }
        )
    return results


# ── Weekly-plays estimator (with gap + fresh-release handling) ────────


def _track_identity(s: str) -> str:
    """Case + accents + punctuation collapsed — a *recording* identity.

    Deliberately NOT `_normalize_track` from the Last.fm client, which
    strips `(Live)` / `(Remaster)` / `(feat. X)`: here we WANT to tell
    live from studio apart.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(s.split())


# Quant abans ha d'haver-se publicat el vídeo perquè li fem cas per
# damunt de la nostra data de llançament. Mostra de 500 cançons el
# 22/08/2026: el 93,4 % dels Art Tracks cauen dins de ±30 dies de la
# data que tenim, no n'hi ha cap entre 61 i 180 dies, i el 2 % que passa
# de l'any són remasteritzacions i reedicions. El llindar va al mig del
# buit, no arran del soroll.
_MARGE_EVIDENCIA_EDAT = 180


def _compute_weekly_plays(
    canco: Canco,
    signals: list[SenyalDiari],
    today: date,
    primer_llancament: dict[tuple[int, str], date] | None = None,
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
    2. **Step-robust delta** (`_robust_weekly_from_series`): when a
       single-day merge step is present in the window (Last.fm doubling
       the cumulative overnight), excise it and project the clean daily
       rhythm to 7 days. Acts only when a merge is detected; otherwise
       falls through to (2b) unchanged.
    2b. **Rolling delta** (legacy, preferred when we have a baseline):
       newest signal as "today's" playcount; closest signal within
       ±_WEEK_WINDOW_DAYS of "today - 7d" as baseline; rescale the
       delta to a 7-day denominator. Negative deltas (Last.fm
       back-corrections) clamp to 0.
    3. **Older delta fallback** (any signal ≥4 days back): same idea,
       just with whatever historical sample we have.
    4. **No data → 0**: when the canço is older than 7 days and we
       lack any baseline (no SenyalDiari row at least 4 days back),
       return 0. We used to fall back to lifetime extrapolation
       (treating `playcount_today` as cumulative plays over the
       canço's life and rescaling to 7 days), but that conflated
       gradual long-tail accumulation with current-week activity:
       a 6-month-old song with 70 k Last.fm plays produced a fake
       weekly figure of ~2.7 k even when its actual recent listens
       were near zero. Decision 2026-05-07: trust only what
       SenyalDiari has actually observed. Newly-verified catalogue
       songs will appear in the ranking with a 1-2 week lag while
       their signal accumulates — accepted trade-off for the honest
       weekly number.
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
    # …unless an older homonym by the same artist exists: then this row
    # is a re-issue, Last.fm's playcount is the ORIGINAL's lifetime, and
    # the zero baseline is a lie. Inherit the age; fall through to the
    # baseline branches (→ 0 until SenyalDiari accumulates one).
    data_ref = canco.data_llancament
    if data_ref and primer_llancament:
        primera = primer_llancament.get((canco.artista_id, _track_identity(canco.nom)))
        if primera and primera < data_ref:
            data_ref = primera
    # …i tampoc si YouTube diu que la gravació ja existia. L'Art Track el
    # genera el distribuïdor el dia del llançament, així que data la
    # gravació i no l'edició: quan és molt anterior a la data que tenim,
    # la que va nàixer fa poc és l'edició, no la música. La guarda de
    # dalt només enxampa reedicions del mateix artista amb el mateix
    # títol; això és evidència directa i cobreix el 73 % del catàleg viu.
    if (
        data_ref
        and canco.youtube_publicat_at
        and canco.youtube_publicat_at < data_ref - timedelta(days=_MARGE_EVIDENCIA_EDAT)
    ):
        data_ref = canco.youtube_publicat_at
    if data_ref and data_ref > today - timedelta(days=7):
        return max(0.0, float(playcount_today))

    # Track-switch guard (2026-05-08): a baseline is only valid if it
    # was sampled against the SAME recording the latest signal points
    # at. When Last.fm's autocorrect/fallback shifts which track URL
    # answers our query (live → studio, remix → original, etc.), the
    # raw playcount delta no longer represents weekly activity — it's
    # the lifetime gap between two different recordings, which can
    # easily inflate a 1-play live track to 30 000 phantom plays in a
    # single day. Caught 2026-05-08: 53 cançons (Pau Vallvé live,
    # Sopa de Cabra live, Smoking Souls live, Enemic Interior
    # remasteritzades, etc.) all spiked overnight when Last.fm started
    # collapsing variant queries onto the main recording. Filtering
    # baseline candidates by normalised `lastfm_returned_track` keeps
    # the delta honest; cançons with no matching baseline fall through
    # to the no-data branch (4) and return 0 until SenyalDiari
    # accumulates a fresh baseline against the new track identity.
    #
    # We deliberately use a track-identity normaliser (case + accents
    # + punctuation collapsed to spaces) rather than the
    # `_normalize_track` helper from `ingesta.clients.lastfm`, which
    # is designed for retry queries and aggressively strips
    # `(Live)` / `(Remaster)` / `(feat. X)` parentheticals. That
    # stripping is the wrong semantics here — we WANT to distinguish
    # live from studio recordings, the whole point of the guard.

    ref_track_n = _track_identity(latest.lastfm_returned_track or "")

    def _same_recording(s: SenyalDiari) -> bool:
        if not ref_track_n:
            # We don't have a track identity to compare; fall back to
            # the legacy behaviour (no filter). Happens for very old
            # SenyalDiari rows that predate the `lastfm_returned_track`
            # column being populated.
            return True
        return _track_identity(s.lastfm_returned_track or "") == ref_track_n

    # 2) Step-robust 7-day delta. Build the daily series over the window
    # and let `_robust_weekly_from_series` excise a Last.fm scrobble-merge
    # step. It acts ONLY when a merge is found; otherwise it returns None
    # and we fall through to the legacy endpoint delta below, so non-merge
    # weeks are unchanged.
    # Strict 7-day window so the intervention is confined to the week
    # whose delta actually straddles the merge step. The week AFTER a
    # merge has the step before `today - 7`, so it sees no merge here and
    # stays byte-identical to the legacy path below.
    robust_series = [
        (s.data, s.lastfm_playcount)
        for s in signals
        if s.lastfm_playcount is not None
        and today - timedelta(days=7) <= s.data <= today
        and _same_recording(s)
    ]
    robust = _robust_weekly_from_series(robust_series)
    if robust is not None:
        return max(0.0, robust)

    # 2b) Preferred legacy path: rolling 7-day delta with ±window.
    target = today - timedelta(days=7)
    window_lo = today - timedelta(days=7 + _WEEK_WINDOW_DAYS)
    window_hi = today - timedelta(days=7 - _WEEK_WINDOW_DAYS)
    candidates = [
        s
        for s in signals
        if s is not latest
        and s.lastfm_playcount is not None
        and window_lo <= s.data <= window_hi
        and _same_recording(s)
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
        and _same_recording(s)
    ]
    if older:
        baseline = older[-1]
        gap_days = (latest.data - baseline.data).days
        if gap_days <= 0:
            return 0.0
        delta = playcount_today - baseline.lastfm_playcount
        return max(0.0, delta * 7.0 / gap_days)

    # 4) No data — return 0. See the docstring's branch (4) note.
    # Removed the lifetime-extrapolation fallback (2026-05-07) because
    # it conflated long-tail accumulated plays with current-week
    # activity. Newly-verified catalogue songs lag 1-2 weeks here as
    # their SenyalDiari accumulates; that's the accepted price of
    # never publishing a fabricated weekly number.
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


def _soft_cap_knee(
    territori: str, cfg: ConfiguracioGlobal, today: date
) -> float | None:
    """Adaptive plays knee for `territori`, or None when the cap is off.

    K = max(floor, multiplicador × median(top-N weekly_plays, last W weeks)).
    The median is read from stored TopSetmanal rows (positions ≤ N over the
    trailing window) so it costs one cheap query and never re-derives the
    signal. With no usable history the median is empty and we fall back to
    the floor (and to None when the floor is 0, i.e. no compression).
    """
    if not cfg.soft_cap_actiu:
        return None
    floor = float(cfg.soft_cap_floor_escoltes or 0)
    multiplicador = float(cfg.soft_cap_multiplicador or 0)
    top_n = int(cfg.soft_cap_base_top_n or _SOFT_CAP_TOP_N)
    window_start = today - timedelta(weeks=_SOFT_CAP_WINDOW_WEEKS)
    plays = list(
        TopSetmanal.objects.filter(
            territori=territori,
            setmana__gte=window_start,
            # …and strictly BEFORE the week being computed: see
            # `_setmana_en_curs`. Reading our own just-saved rows made the
            # knee move under us mid-run.
            setmana__lt=_setmana_en_curs(today),
            posicio__lte=top_n,
            weekly_plays__isnull=False,
        ).values_list("weekly_plays", flat=True)
    )
    if not plays:
        return floor if floor > 0 else None
    knee = max(floor, multiplicador * float(median(plays)))
    return knee if knee > 0 else None


def _apply_soft_cap(plays: float, knee: float | None) -> float:
    """Compress `plays` above `knee` logarithmically; leave it intact below.

    plays_eff = knee · (1 + ln(plays / knee))   for plays > knee > 0
    Monotone, so ordering among the compressed outliers is preserved; the
    whole normal range (plays ≤ knee) is returned unchanged.
    """
    if knee is None or knee <= 0 or plays <= knee:
        return plays
    return knee * (1.0 + math.log(plays / knee))


# ── PPCC aggregation ──────────────────────────────────────────────────


def _calcular_top_ppcc(
    resultats_previs: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Aggregate all non-PPCC rankings, penalise by source position, dedupe.

    The per-position penalty (`ppcc_penalitzacio_per_posicio`, default
    0.04) lives on `ConfiguracioGlobal` since 2026-04-25 (Sprint A);
    editing it from staff config now reaches the ranking without code.

    PPCC **aggregates, it does not compute** (CLAUDE.md §6). `calcular_top`
    passes the territorial results it has just produced via
    `resultats_previs`, so the global top is a re-scoring of exactly the
    numbers we published per territori. Recomputing them here instead is
    what let the two disagree on 2026-08-15: the command saves each
    territori before this runs, and the second pass read those fresh rows
    (see `_setmana_en_curs`). The recompute stays as the fallback for a
    standalone `--territori PPCC`, where nothing has been computed yet.
    """
    cfg = ConfiguracioGlobal.load()
    pos_penalty = float(cfg.ppcc_penalitzacio_per_posicio)
    source_territoris = [t for t in territoris_amb_top_propi() if t != "PPCC"]
    all_results: list[dict] = []
    for t in source_territoris:
        previs = (resultats_previs or {}).get(t)
        for r in previs if previs is not None else calcular_top_territori(t):
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
                "weekly_plays_eff": r.get("weekly_plays_eff", r.get("weekly_plays")),
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
