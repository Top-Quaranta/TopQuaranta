"""Ranking endpoints for the React SPA.

GET /api/v1/ranking/?territori=CAT&setmana=2026-04-13
    Weekly ranking (top 40) for a territory. `setmana` optional — if
    absent, returns the most recent stored week for that territory.
    Falls back to TopProvisional when no weekly row exists yet.
"""

import datetime

from django.db.models import Max
from django.views.decorators.http import condition
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from music.constants import (
    MAX_POSICIONS_TOP,
    TERRITORI_NOMS,
    TERRITORIS_PPCC_SOURCES,
)
from music.dates import project_week_number
from ranking.models import TopProvisional, TopSetmanal
from web.api.serializers import artista_minimal
from web.api.utils import cache_for_anon

# Canonical preference order for the single territory chip shown next to
# an artist on the (global) top: real PPCC territories first, then CAR,
# then the ALT catch-all. An artist in several territoris shows the
# highest-priority one. (Redisseny: the global top has no per-row
# territori otherwise — additive field, breaks nothing.)
_TERR_CHIP_ORDER = (*TERRITORIS_PPCC_SOURCES, "CAR", "ALT")


def _primary_territori(artista) -> str | None:
    """First territori code (chip-priority order) for `artista`, or None.
    Reads the prefetched `territoris` M2M — keep the queryset's
    `prefetch_related("canco__artista__territoris")` in sync to avoid N+1."""
    if artista is None:
        return None
    codis = set(artista.territoris.values_list("codi", flat=True))
    if not codis:
        return None
    for code in _TERR_CHIP_ORDER:
        if code in codis:
            return code
    return next(iter(codis))


# Territories the public API accepts — the five ranking-eligible plus
# the smaller ones that fall back to ALT (AND, CNO, FRA, ALG). Caller
# can pass any of these; the fallback logic below redirects empty ones.
API_TERRITORIS = tuple(TERRITORI_NOMS.keys())


def _serialize_entry(entry, is_provisional: bool, posicio_anterior=None) -> dict:
    """Shape used by the React RankingPage — one row per track.

    `posicio_anterior` is injected by the caller after a single batched
    lookup across the ranking set (avoids a per-entry query). Used in
    the UI to show ↑ (improved) or "nou" (not ranked last week).
    """
    canco = entry.canco
    artista = canco.artista if canco else None
    album = canco.album if canco else None
    # Collaborators — prefetched on the queryset, cap at 3 for the
    # public list so the UI can render them in a single line without
    # runaway overflow. Extra credits stay visible on the track page.
    col_list = []
    if canco is not None:
        try:
            col_list = [artista_minimal(a) for a in canco.artistes_col.all()[:3]]
        except Exception:  # noqa: BLE001 — defensive; never block the ranking
            col_list = []
    return {
        "posicio": entry.posicio,
        "posicio_anterior": posicio_anterior,
        "canco": {
            "id": canco.pk if canco else None,
            "nom": canco.nom if canco else getattr(entry, "canco_nom_snapshot", ""),
            "slug": canco.slug if canco else None,
            "isrc": canco.isrc if canco else None,
            "preview_url": canco.preview_url if canco else None,
            "deezer_id": canco.deezer_id if canco else None,
            "data_llancament": (
                canco.data_llancament.isoformat()
                if canco and canco.data_llancament
                else None
            ),
        },
        "artista": (
            {
                "id": artista.pk if artista else None,
                "nom": (
                    artista.nom
                    if artista
                    else getattr(entry, "artista_nom_snapshot", "")
                ),
                "slug": artista.slug if artista else None,
                # Additive (redisseny): primary territori code for the
                # row chip. None for snapshot-only rows / no territori.
                "territori": _primary_territori(artista),
            }
            if artista or getattr(entry, "artista_nom_snapshot", "")
            else None
        ),
        "artistes_col": col_list,
        "album": (
            {
                "id": album.pk if album else None,
                "slug": album.slug if album else None,
                "nom": album.nom if album else None,
                "imatge_url": (
                    (getattr(album, "imatge_url", None) or None) if album else None
                ),
            }
            if album
            else None
        ),
    }


def _prev_week_positions(territori: str, setmana) -> dict[int, int]:
    """Map canco_id → posicio for the TopSetmanal just before `setmana`.

    Used to compute up-arrow / "new" indicators. Empty dict if there's
    no prior week (first run for that territori).
    """
    prev_setmana = (
        TopSetmanal.objects.filter(territori=territori, setmana__lt=setmana)
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    if prev_setmana is None:
        return {}
    return dict(
        TopSetmanal.objects.filter(
            territori=territori, setmana=prev_setmana
        ).values_list("canco_id", "posicio")
    )


def _latest_week_positions(territori: str) -> dict[int, int]:
    """Map canco_id → posicio for the most recent weekly row in territori.

    Used by the provisional branch as "last week" baseline.
    """
    prev_setmana = (
        TopSetmanal.objects.filter(territori=territori)
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    if prev_setmana is None:
        return {}
    return dict(
        TopSetmanal.objects.filter(
            territori=territori, setmana=prev_setmana
        ).values_list("canco_id", "posicio")
    )


def _top_last_modified(request, *args, **kwargs):
    """Most-recent timestamp for any ranking row of the requested
    territori. Drives both Last-Modified and ETag for the public
    /api/v1/ranking/ endpoint.

    Falls back across (provisional → setmanal → None) so a 304 reply
    is well-defined regardless of which side of the daily cron we're on.
    Returns None when the territori has no data yet (Django's condition
    decorator then skips the header — no 304 possible — and the view
    runs normally to produce a 200).
    """
    t = (request.GET.get("territori") or "").strip().upper()
    if not t:
        return None
    prov = TopProvisional.objects.filter(territori=t).aggregate(Max("data_calcul"))[
        "data_calcul__max"
    ]
    if prov is not None:
        # data_calcul is a DateField — promote to a datetime at midnight UTC.
        return datetime.datetime.combine(
            prov, datetime.time.min, tzinfo=datetime.timezone.utc
        )
    setm = TopSetmanal.objects.filter(territori=t).aggregate(Max("created_at"))[
        "created_at__max"
    ]
    return setm


def _top_etag(request, *args, **kwargs):
    lm = _top_last_modified(request, *args, **kwargs)
    if lm is None:
        return None
    # Weak ETag: territori + week-pin + last-mod timestamp. Same scheme
    # for every endpoint so debugging is uniform.
    setmana = (request.GET.get("setmana") or "").strip()
    territori = (request.GET.get("territori") or "").strip().upper()
    return f'W/"rank-{territori}-{setmana}-{int(lm.timestamp())}"'


@condition(etag_func=_top_etag, last_modified_func=_top_last_modified)
@api_view(["GET"])
@permission_classes([AllowAny])
@cache_for_anon(300, key_prefix="ranking")
def ranking(request: Request) -> Response:
    """Top 40 for a territory + week. Defaults to latest week.

    Query params:
      - territori: one of TERRITORIS_VALIDS (required)
      - setmana:   YYYY-MM-DD, Monday of the ISO week (optional)

    Anonymous reads cached for 60 s in the per-worker `pagecache`
    LocMem alias. ETag + Last-Modified set from the most recent
    `TopProvisional.data_calcul` (fallback `TopSetmanal.created_at`)
    for the requested territori — clients with `If-None-Match`/
    `If-Modified-Since` get a 304 when nothing has changed.
    """
    territori = (request.GET.get("territori") or "").strip().upper()
    if territori not in API_TERRITORIS:
        return Response(
            {"error": f"Invalid territori. Must be one of {list(API_TERRITORIS)}."},
            status=400,
        )

    setmana_raw = (request.GET.get("setmana") or "").strip()
    setmana = None
    if setmana_raw:
        try:
            setmana = datetime.date.fromisoformat(setmana_raw)
        except ValueError:
            return Response(
                {"error": "Invalid setmana format. Expected YYYY-MM-DD."}, status=400
            )

    # Sprint I: `oficial=true` forces a TopSetmanal-only response. The
    # default behaviour falls back to TopProvisional when no weekly row
    # exists yet, which is correct for the live /top page but wrong for
    # the HomePage hero (we want the hero to feature the *officially
    # published* top, not yesterday's provisional).
    oficial_only = (request.GET.get("oficial") or "").strip().lower() in (
        "1",
        "true",
    )

    # Optional `limit` (capped at MAX_POSICIONS_TOP) so the HomePage can
    # request only the first 10 entries cheaply. Default keeps the
    # existing top-40 behaviour for the /top page.
    try:
        limit = max(
            1,
            min(
                int(request.GET.get("limit", str(MAX_POSICIONS_TOP))), MAX_POSICIONS_TOP
            ),
        )
    except ValueError:
        limit = MAX_POSICIONS_TOP

    # Small territories (AND, CNO, FRA, ALG) fold their tracks into ALT
    # when they don't reach the 20-track threshold, so if the caller
    # asked for one of those and we have nothing stored, we redirect to
    # ALT for the same week and tell the client via `fallback_from`.
    FALLBACK_TERRITORIS = {"AND", "CNO", "FRA", "ALG", "CAR"}

    def _latest_week(t: str):
        return (
            TopSetmanal.objects.filter(territori=t)
            .order_by("-setmana")
            .values_list("setmana", flat=True)
            .first()
        )

    fallback_from = None
    actual_territori = territori

    if setmana is None:
        setmana = _latest_week(territori)
        if setmana is None and territori in FALLBACK_TERRITORIS:
            setmana = _latest_week("ALT")
            if setmana is not None:
                fallback_from = territori
                actual_territori = "ALT"
        if setmana is None:
            if oficial_only:
                # No official weekly row anywhere — return an explicit
                # empty response so the HomePage can hide the section.
                return Response(
                    {
                        "territori": territori,
                        "fallback_from": None,
                        "setmana": None,
                        "setmana_dissabte": None,
                        "setmana_numero": None,
                        "es_provisional": False,
                        "data_calcul": None,
                        "entries": [],
                    }
                )
            # Fall back to provisional for the originally-requested territory.
            prov = list(
                TopProvisional.objects.select_related(
                    "canco", "canco__artista", "canco__album"
                )
                .prefetch_related("canco__artistes_col", "canco__artista__territoris")
                .filter(territori=territori)
                .order_by("posicio")[:limit]
            )
            prev_pos = _latest_week_positions(territori)
            return Response(
                {
                    "territori": territori,
                    "fallback_from": None,
                    "setmana": None,
                    "setmana_dissabte": None,
                    "setmana_numero": None,
                    "es_provisional": True,
                    "data_calcul": prov[0].data_calcul.isoformat() if prov else None,
                    "entries": [
                        _serialize_entry(
                            e,
                            is_provisional=True,
                            posicio_anterior=prev_pos.get(e.canco_id),
                        )
                        for e in prov
                    ],
                }
            )

    entries = list(
        TopSetmanal.objects.select_related("canco", "canco__artista", "canco__album")
        .prefetch_related("canco__artistes_col", "canco__artista__territoris")
        .filter(territori=actual_territori, setmana=setmana)
        .order_by("posicio")[:limit]
    )

    # If the caller pinned a specific setmana and the small-territory
    # row came up empty, try ALT for the same week.
    if not entries and territori in FALLBACK_TERRITORIS and fallback_from is None:
        alt_entries = list(
            TopSetmanal.objects.select_related(
                "canco", "canco__artista", "canco__album"
            )
            .prefetch_related("canco__artistes_col", "canco__artista__territoris")
            .filter(territori="ALT", setmana=setmana)
            .order_by("posicio")[:MAX_POSICIONS_TOP]
        )
        if alt_entries:
            fallback_from = territori
            actual_territori = "ALT"
            entries = alt_entries

    prev_pos = _prev_week_positions(actual_territori, setmana) if setmana else {}
    # The top is published on Saturday of the ISO week (setmana is stored
    # as the Monday of that week). Dates on the site reference that
    # Saturday so the week label doesn't look stale.
    setmana_dissabte = setmana + datetime.timedelta(days=5) if setmana else None

    # Sprint J — week navigator. The previous/next setmana fields let the
    # SPA render disabled buttons when the boundary is reached, so a
    # visitor can flip through history without ever landing on an empty
    # week. Computed against the actual stored snapshots for the
    # resolved (post-fallback) territori — that's what the user is
    # currently looking at.
    prev_setmana = (
        TopSetmanal.objects.filter(territori=actual_territori, setmana__lt=setmana)
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    next_setmana = (
        TopSetmanal.objects.filter(territori=actual_territori, setmana__gt=setmana)
        .order_by("setmana")
        .values_list("setmana", flat=True)
        .first()
    )

    return Response(
        {
            "territori": actual_territori,
            "fallback_from": fallback_from,
            "setmana": setmana.isoformat() if setmana else None,
            "setmana_dissabte": (
                setmana_dissabte.isoformat() if setmana_dissabte else None
            ),
            # Single source of truth for the project week number lives in
            # music.dates (also used by the social kit). The SPA only
            # paints it — no client-side anchor (redisseny amendment 4).
            "setmana_numero": project_week_number(setmana) if setmana else None,
            "prev_setmana": prev_setmana.isoformat() if prev_setmana else None,
            "next_setmana": next_setmana.isoformat() if next_setmana else None,
            "es_provisional": False,
            "data_calcul": None,
            "entries": [
                _serialize_entry(
                    e,
                    is_provisional=False,
                    posicio_anterior=prev_pos.get(e.canco_id),
                )
                for e in entries
            ],
        }
    )
