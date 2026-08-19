"""Public analytics ingest endpoints for the SPA.

The SPA is served as static `dist/` files by Caddy without going
through Django, so the `AnalyticsMiddleware` never sees React-router
navigations. These endpoints fill that gap with two small POST
beacons. Both are aggregate-only — the request body is the entire
input surface; we never read IP, UA, referer, cookies, or session.

Endpoints
---------
POST /api/v1/analytics/pageview/   {path, utm_source?, utm_campaign?}
POST /api/v1/analytics/event/      {clau, dim1?, dim2?}

`event/` accepts a strict allowlist of `clau` values to prevent
the SPA (or anyone forging requests) from polluting the table with
arbitrary keys. Throttled per-IP at 60/min via the project default.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from analytics.bots import CLASS_HUMAN
from analytics.events import register

# Whitelist of `clau` values the SPA is allowed to push. New events
# require backend code to land first — that's by design (analytics
# rows are forever, schema discipline matters).
_PUBLIC_EVENT_KEYS = frozenset(
    {
        "spa_route_view",  # tracks router navigations (dim1=route name)
        "search_query",  # dim1 = scope (artistes/albums/cançons)
        "share_click",  # dim1 = surface, dim2 = network
        "escolta_click",  # dim1 = dsp (spotify/deezer/yt/apple)
        "play_preview",  # dim1 = surface (canco/album/artista)
        "newsletter_signup",  # form-side counter (cf. registre with dim1=newsletter)
        "directori_filter",  # dim1 = filter type
        "mapa_zoom",  # dim1 = level (territori/comarca/municipi)
        # Community funnel (Slice E). dm_enviat / denuncia_creada /
        # bloqueig_creat are fired server-side via register(), not here.
        "onboarding_inici",  # onboarding page mounted
        "onboarding_pas",  # first meaningful field interaction
        "onboarding_complet",  # saved with onboarding_complet=true
        "onboarding_saltat",  # skipped via "Saltar"
        "comunitat_directori_vista",  # directory page viewed
        "comunitat_directori_filtre",  # dim1 = filter key
        "perfil_visible_toggle",  # dim1 = "on"|"off"
    }
)


def _clean(value: object, max_len: int = 80) -> str:
    """Normalize a posted dimension to a safe lower-case slug-ish value."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()[:max_len]


@api_view(["POST"])
@permission_classes([AllowAny])
def pageview(request: Request) -> Response:
    """Record a SPA pageview + optional UTM landing.

    Body: {"path": "/top", "utm_source": "...", "utm_campaign": "..."}
    Returns 204 on success (no body needed; SPA fire-and-forgets).
    """
    data = request.data or {}
    path = _clean(data.get("path") or "/", max_len=80)
    # Classified **by construction**, without reading anything about the
    # caller: this endpoint is only reached when the SPA's JavaScript
    # runs, which is the definition of a real visit here. Crawlers get
    # the server-rendered pages and are classified by the middleware.
    #
    # Until 2026-08-17 these rows carried no class at all, so the weekly
    # digest — which filters on `dimensio_2="human"` — excluded every
    # real SPA visit and reported only the Django-served leftovers. The
    # week of 10/08 that was 98 "humans" (mostly sitemap fetches) while
    # 373 actual visits sat unclassified.
    register("pageview", dim1=path or "/", dim2=CLASS_HUMAN)

    utm_source = _clean(data.get("utm_source"), max_len=80)
    if utm_source:
        utm_campaign = _clean(data.get("utm_campaign"), max_len=80)
        register("utm_landing", dim1=utm_source, dim2=utm_campaign)
    return Response(status=204)


@api_view(["POST"])
@permission_classes([AllowAny])
def event(request: Request) -> Response:
    """Record an arbitrary event from the SPA.

    Body: {"clau": "<one of _PUBLIC_EVENT_KEYS>", "dim1": "...", "dim2": "..."}
    Unknown `clau` values return 400 — analytics schema is closed.
    """
    data = request.data or {}
    clau = _clean(data.get("clau"), max_len=80)
    if clau not in _PUBLIC_EVENT_KEYS:
        return Response({"error": "unknown clau"}, status=400)
    dim1 = _clean(data.get("dim1"))
    dim2 = _clean(data.get("dim2"))
    register(clau, dim1=dim1, dim2=dim2)
    return Response(status=204)
