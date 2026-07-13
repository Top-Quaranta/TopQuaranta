"""Public song endpoints.

GET /api/v1/cancons/<slug>/                — song metadata + weekly chart history.
GET /api/v1/cancons/<slug>/top-breakdown/  — algorithm transparency block.
"""

import datetime

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import UserArtista
from music.constants import TERRITORI_NOMS, TERRITORIS_PPCC_SOURCES
from music.models import Canco
from ranking.algorisme import (
    _age_factor,
    _apply_soft_cap,
    _compute_weekly_plays,
    _past_top_factor,
    _soft_cap_knee,
    territoris_amb_top_propi,
)
from ranking.models import (
    ConfiguracioGlobal,
    SenyalDiari,
    TopProvisional,
    TopSetmanal,
)
from web.api.serializers import album_card, artista_minimal, canco_card

# Public display name: the PPCC aggregate renders as "Global" (Sprint I
# bis), never "Països Catalans" — which the canonical `TERRITORI_NOMS`
# still carries as the internal name. Other territories keep their full
# canonical name.
_TERRITORI_DISPLAY = {**TERRITORI_NOMS, "PPCC": "Global"}


@api_view(["GET"])
@permission_classes([AllowAny])
def canco_detail(request: Request, slug: str) -> Response:
    canco = get_object_or_404(
        Canco.objects.select_related("artista", "album", "spotify").prefetch_related(
            "artistes_col"
        ),
        slug=slug,
    )

    # Weekly ranking history per territory. Shape designed to feed a
    # Recharts LineChart with `setmana` on the X axis and one line per
    # territori (posicio on Y, inverted — lower is better).
    rows = list(
        TopSetmanal.objects.filter(canco=canco)
        .order_by("setmana", "territori")
        .values("setmana", "territori", "posicio")
    )
    # Group by week → one record per week with one key per territori.
    by_week: dict = {}
    territoris_vistos: set[str] = set()
    for r in rows:
        wk = r["setmana"].isoformat()
        by_week.setdefault(wk, {"setmana": wk})
        by_week[wk][r["territori"]] = r["posicio"]
        territoris_vistos.add(r["territori"])

    historial = [by_week[k] for k in sorted(by_week.keys())]

    provisional = list(
        TopProvisional.objects.filter(canco=canco)
        .order_by("territori")
        .values("territori", "posicio", "data_calcul")
    )
    provisional_out = [
        {
            "territori": p["territori"],
            "posicio": p["posicio"],
            "data_calcul": p["data_calcul"].isoformat() if p["data_calcul"] else None,
        }
        for p in provisional
    ]

    return Response(
        {
            **canco_card(canco),
            "data_llancament": (
                canco.data_llancament.isoformat() if canco.data_llancament else None
            ),
            "artista": artista_minimal(canco.artista) if canco.artista else None,
            "album": ({**album_card(canco.album)} if canco.album else None),
            # Exact Spotify track id (Process B enrichment) for a direct
            # link + embed; null when not yet enriched.
            "spotify_id": (
                getattr(getattr(canco, "spotify", None), "spotify_id", "") or None
            ),
            "ml_classe": canco.ml_classe or None,
            "whisper_lang": canco.whisper_lang or None,
            "whisper_p": canco.whisper_p,
            "territoris_historial": sorted(territoris_vistos),
            "historial": historial,
            "provisional": provisional_out,
        }
    )


# ─────────────────────────────────────────────────────────────────────
# Top breakdown — algorithm transparency
# ─────────────────────────────────────────────────────────────────────


def _viewer_is_elevated(request, canco) -> bool:
    """True when the request comes from staff or from a user who has a
    verified `UserArtista` link to the song's main artist. Drives the
    payload differentiation in `canco_top_breakdown`."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return False
    if user.is_staff:
        return True
    if canco.artista_id is None:
        return False
    return UserArtista.objects.filter(
        usuari=user, artista_id=canco.artista_id, verificat=True
    ).exists()


def _factor_to_pct(factor):
    """Convert a multiplicative factor in [0,1] to a penalty percentage.

    factor=1.0 → 0 % penalty, factor=0.8 → 20 % penalty, factor=None
    → 0. Used uniformly for past_top, monopoli_album, monopoli_artista.
    """
    if factor is None:
        return 0.0
    return round(max(0.0, (1.0 - float(factor)) * 100), 1)


def _setmanes_al_top(canco, territori, *, limit=5):
    rows = (
        TopSetmanal.objects.filter(canco=canco, territori=territori)
        .order_by("-setmana")[:limit]
        .values("setmana", "posicio")
    )
    return [
        {"setmana": r["setmana"].isoformat(), "posicio": r["posicio"]} for r in rows
    ]


def _derive_plays_eff(rp):
    """Recover the *effective* plays the real calc fed into the score for a
    persisted TopProvisional row, plus whether the soft cap touched it.

    We do NOT recompute the knee here. The knee is time-dependent (median
    of the trailing 10 weeks of finalized tops) and drifts after the row is
    persisted, so recomputing it now would no longer reconcile with the
    stored score. Instead we invert the stored score:

        score = plays_eff · age · past_top · monopoli      (algorisme.py)
        ⇒ plays_eff = score / (age · past_top · monopoli)

    All four are persisted on the row, so this reproduces exactly what the
    real calc used. `soft_cap_aplicat` is True when the effective plays sit
    meaningfully below the raw `escoltes_setmanals` (a small relative margin
    absorbs score rounding so uncapped rows are never falsely flagged).
    """
    plays_raw = rp.escoltes_setmanals or 0
    age = float(rp.age_factor) if rp.age_factor is not None else 1.0
    past_top = float(rp.past_top_factor) if rp.past_top_factor is not None else 1.0
    monopoli = float(rp.monopoli_factor) if rp.monopoli_factor is not None else 1.0
    denom = age * past_top * monopoli
    if plays_raw <= 0 or denom <= 0:
        return plays_raw, False
    plays_eff = float(rp.score_setmanal) / denom
    soft_cap_aplicat = (plays_raw - plays_eff) > max(1.0, 0.005 * plays_raw)
    return plays_eff, soft_cap_aplicat


def _entry_from_provisional(rp):
    """Shape one TopProvisional row for the breakdown payload.

    A row in TopProvisional implies the algorithm successfully
    computed `weekly_plays` (>0), so `senyal_disponible` is True by
    construction here.

    `score_final` is the persisted `score_setmanal`, kept as-is. The
    raw→effective plays split shown to the user is derived from that same
    score (see `_derive_plays_eff`) so it always reconciles.
    """
    plays_raw = rp.escoltes_setmanals or 0
    plays_eff, soft_cap_aplicat = _derive_plays_eff(rp)
    return {
        "territori": rp.territori,
        "nom_territori": _TERRITORI_DISPLAY.get(rp.territori, rp.territori),
        "posicio": rp.posicio,
        "escoltes_setmanals": plays_raw,
        "weekly_plays_eff": int(round(plays_eff)),
        "soft_cap_aplicat": soft_cap_aplicat,
        "senyal_disponible": True,
        "age_factor": rp.age_factor,
        "past_top_penalty_pct": _factor_to_pct(rp.past_top_factor),
        "monopoli_album_pct": (
            _factor_to_pct(rp.monopoli_factor)
            if rp.monopoli_factor is not None and rp.monopoli_factor < 1.0
            else 0.0
        ),
        # We store a single combined `monopoli_factor` per row, so we
        # surface it once under album. Splitting album vs artista
        # would need re-running the per-track pass; left as future work.
        "monopoli_artista_pct": 0.0,
        "score_final": round(float(rp.score_setmanal), 2),
        "is_at_top": True,
    }


def _theoretical_entry(canco, territori, cfg):
    """Compute factors + theoretical score for a Canço NOT in the
    current TopProvisional. Reproduces the v2.0 algorithm's per-track
    math from the live SenyalDiari + TopSetmanal state. Excludes the
    monopoli post-process (would require knowing other tracks' final
    base scores; we surface the score WITHOUT monopoli and tag the row
    so the UI can be honest about it).
    """
    today = datetime.date.today()

    senyals = list(
        SenyalDiari.objects.filter(
            canco_id=canco.pk,
            data__gte=today - datetime.timedelta(days=14),
            error=False,
            lastfm_playcount__isnull=False,
        )
        .only("canco_id", "data", "lastfm_playcount")
        .order_by("data")
    )
    weekly_plays = _compute_weekly_plays(canco=canco, signals=senyals, today=today)
    # `metode_calcul` distinguishes the four branches of the
    # algorithm so the UI can be honest with the user:
    #   - "delta_setmanal": real delta between today and ~7 days ago.
    #   - "delta_parcial":  delta from any older sample (≥4 d back),
    #     rescaled to a 7-day denominator.
    #   - "mitjana_vida":   no historical baseline; lifetime average
    #     extrapolated from `playcount_today × 7 / dies_des_release`.
    #   - "release_recent": release < 7 days ago, scaled from
    #     accumulated plays since release.
    #   - None: no signals at all (or only same-day, no release date).
    has_recent_baseline = any(
        s.data <= today - datetime.timedelta(days=10)  # rough "7d ± window"
        and s.data >= today - datetime.timedelta(days=14)
        for s in senyals[:-1]
        if senyals
    )
    has_older_baseline = (
        any(s.data <= today - datetime.timedelta(days=4) for s in senyals[:-1])
        if len(senyals) >= 2
        else False
    )
    metode_calcul = None
    if not senyals:
        metode_calcul = None
    elif canco.data_llancament and canco.data_llancament > today - datetime.timedelta(
        days=7
    ):
        metode_calcul = "release_recent"
    elif has_recent_baseline:
        metode_calcul = "delta_setmanal"
    elif has_older_baseline:
        metode_calcul = "delta_parcial"
    elif weekly_plays > 0:
        metode_calcul = "mitjana_vida"
    senyal_disponible = bool(senyals) and weekly_plays > 0
    age = _age_factor(
        canco.data_llancament,
        today=today,
        exponent=float(cfg.exponent_penalitzacio_antiguitat),
    )
    prior = list(
        TopSetmanal.objects.filter(
            canco_id=canco.pk, territori=territori, posicio__lte=40
        ).values_list("posicio", flat=True)
    )
    past_top = _past_top_factor(prior, float(cfg.coeficient_penalitzacio_top))
    # Apply the SAME per-territori outlier knee + log compression the real
    # calc uses (ranking/algorisme.py), before the base score. Without this
    # an outlier's theoretical score reads HIGHER than its real one.
    knee = _soft_cap_knee(territori, cfg, today)
    plays_eff = _apply_soft_cap(float(weekly_plays), knee)
    soft_cap_aplicat = plays_eff < weekly_plays
    base_score = plays_eff * age * past_top
    return {
        "territori": territori,
        "nom_territori": _TERRITORI_DISPLAY.get(territori, territori),
        "posicio": None,
        "escoltes_setmanals": int(weekly_plays),
        "weekly_plays_eff": int(round(plays_eff)),
        "soft_cap_aplicat": soft_cap_aplicat,
        "senyal_disponible": senyal_disponible,
        "metode_calcul": metode_calcul,
        "age_factor": round(age, 4),
        "past_top_penalty_pct": _factor_to_pct(past_top),
        "monopoli_album_pct": 0.0,
        "monopoli_artista_pct": 0.0,
        "score_final": round(base_score, 2),
        "is_at_top": False,
    }


def _eligible_territoris_for(canco) -> list[str]:
    """Territoris where this Canço could conceivably appear at the top:
    any of `territoris_amb_top_propi()` whose code matches the artist's
    own territoris (or collaborator's). Filters down the universe so
    elevated users don't get ALT/PPCC noise that doesn't apply."""
    own = (
        set(canco.artista.territoris.values_list("codi", flat=True))
        if canco.artista_id
        else set()
    )
    for collab in canco.artistes_col.all():
        own.update(collab.territoris.values_list("codi", flat=True))
    eligible = set(territoris_amb_top_propi())
    # PPCC is always shown if the artist belongs to any PPCC territori;
    # ALT only if they're literally tagged ALT.
    keep = own & eligible
    if "PPCC" in eligible and own & set(TERRITORIS_PPCC_SOURCES):
        keep.add("PPCC")
    return sorted(keep)


@api_view(["GET"])
@permission_classes([AllowAny])
def canco_top_breakdown(request: Request, slug: str) -> Response:
    """Algorithm transparency block for one Canço.

    Anonymous (or logged-in but unrelated) viewers see ONLY the
    territoris where the song currently sits in `TopProvisional`.

    Staff and verified `UserArtista` (over the song's main artist)
    see the full eligible-territori list, including theoretical
    scores for territoris where the song hasn't broken into the
    top yet — so they can diagnose what's keeping it out.

    The shape is uniform across both audiences; the difference is
    the set of entries returned.
    """
    canco = get_object_or_404(
        Canco.objects.select_related("artista").prefetch_related(
            "artistes_col__territoris", "artista__territoris"
        ),
        slug=slug,
    )
    elevated = _viewer_is_elevated(request, canco)
    today = datetime.date.today()
    days_since = (today - canco.data_llancament).days if canco.data_llancament else None

    provisional_rows = list(
        TopProvisional.objects.filter(canco=canco).order_by("territori")
    )
    in_top_territoris = {rp.territori for rp in provisional_rows}

    # Loaded once for the theoretical entries (knee recompute). The
    # persisted rows derive their effective plays from the stored score.
    cfg = ConfiguracioGlobal.load()

    entries = []
    for rp in provisional_rows:
        e = _entry_from_provisional(rp)
        e["dies_des_del_llancament"] = days_since
        e["setmanes_al_top"] = _setmanes_al_top(canco, rp.territori)
        entries.append(e)

    if elevated:
        for t in _eligible_territoris_for(canco):
            if t in in_top_territoris:
                continue
            e = _theoretical_entry(canco, t, cfg)
            e["dies_des_del_llancament"] = days_since
            e["setmanes_al_top"] = _setmanes_al_top(canco, t)
            entries.append(e)
        entries.sort(key=lambda x: (x["posicio"] is None, x["territori"]))

    return Response(
        {
            "canco_slug": canco.slug,
            "canco_nom": canco.nom,
            "elevated_view": elevated,
            "data_llancament": (
                canco.data_llancament.isoformat() if canco.data_llancament else None
            ),
            "dies_des_del_llancament": days_since,
            "entries": entries,
        }
    )
