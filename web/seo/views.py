"""SSR views for SEO + JS-disabled clients.

Mounted at the URL paths the SPA also handles. Caddy's `@bot`
matcher reverse-proxies bot UAs here; humans go to the SPA shell.
The matcher is at `deploy/Caddyfile`.

Indexability rules — see `docs/architecture/seo.md`. When an entity
loses its indexability flag (artiste un-approved, cançó un-verified),
the view returns 404 so Google de-indexes it within hours.
"""

from __future__ import annotations

import datetime
import json
from functools import wraps

from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import cache_control
from django.views.decorators.http import condition, require_safe


def _vary_ua(view_func):
    """Stamp `Vary: User-Agent` on the response. Critical for caches
    because Caddy's `@bot` matcher serves a *different* HTML body to
    bot UAs than humans for the same URL — without `Vary`, an
    intermediate cache could serve the bot version to a human and
    vice-versa."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        patch_vary_headers(response, ["User-Agent"])
        return response

    return wrapped


from music.models import Album, Artista, Canco
from ranking.models import TopProvisional, TopSetmanal

from . import jsonld, meta

# ── Conditional GET helpers ─────────────────────────────────────────


def _last_modified(request, **kwargs):
    """Used by `@condition` so Django emits Last-Modified + 304s.
    Each view that wraps with `@condition(last_modified_func=...)`
    points to one of these. Returning a `datetime` lets Django
    handle the If-Modified-Since negotiation; returning None means
    "no last-modified info" and the response is always full.
    """
    return None


def _artista_lm(request, slug):
    a = Artista.objects.filter(slug=slug, aprovat=True).only("updated_at").first()
    return a.updated_at if a else None


def _album_lm(request, slug):
    al = (
        Album.objects.filter(slug=slug, descartat=False, artista__aprovat=True)
        .only("updated_at")
        .first()
    )
    return al.updated_at if al else None


def _canco_lm(request, slug):
    c = (
        Canco.objects.filter(slug=slug, verificada=True, activa=True)
        .only("updated_at")
        .first()
    )
    return c.updated_at if c else None


# ── Per-entity SSR views ────────────────────────────────────────────


@require_safe
@_vary_ua
def homepage_seo(request: HttpRequest) -> HttpResponse:
    """`/` — server-rendered homepage (bot path).

    Shows the current week's top 5 + a couple of paragraphs about
    what TopQuaranta is. The SPA homepage has more (carousels, links
    to Comunitat etc.) but for SEO purposes those are secondary.
    """
    top5 = (
        TopProvisional.objects.filter(territori="PPCC", posicio__lte=5)
        .select_related("canco__artista", "canco__album")
        .order_by("posicio")
    )
    return render(
        request,
        "seo/homepage.html",
        {
            "meta": meta.for_homepage(),
            "jsonld_blocks": [jsonld.website_jsonld()],
            "top5": top5,
            "now": timezone.now(),
        },
    )


@require_safe
@_vary_ua
def top_seo(request: HttpRequest) -> HttpResponse:
    """`/top` — current weekly top per territori (default PPCC).

    Server-rendered table with all 40 positions + per-row link to the
    cançó page. Pre-renders both the provisional (mid-week) and
    official (Saturday-locked) tops with a fallback chain.
    """
    territori = (request.GET.get("territori") or "PPCC").upper()
    if territori not in meta.TERRITORI_NOMS:
        territori = "PPCC"

    # Try TopSetmanal first (Saturday-locked, the canonical chart);
    # fall back to TopProvisional if no official chart exists yet
    # for this week.
    today = timezone.localdate()
    monday = today - datetime.timedelta(days=today.weekday())
    entries = list(
        TopSetmanal.objects.filter(territori=territori, setmana=monday)
        .select_related("canco__artista", "canco__album")
        .order_by("posicio")
    )
    is_provisional = False
    if not entries:
        entries = list(
            TopProvisional.objects.filter(territori=territori)
            .select_related("canco__artista", "canco__album")
            .order_by("posicio")[:40]
        )
        is_provisional = True

    # Prepare for jsonld.top_jsonld which expects dict-like rows.
    entries_for_jsonld = [
        {
            "posicio": e.posicio,
            "canco_nom": e.canco.nom,
            "canco_slug": e.canco.slug,
            "artista_nom": e.canco.artista.nom,
            "artista_slug": e.canco.artista.slug,
        }
        for e in entries
    ]
    blocks = [jsonld.top_jsonld(territori, monday, entries_for_jsonld)]
    blocks.append(jsonld.breadcrumbs_jsonld([("Inici", "/"), ("Top", "/top")]))

    return render(
        request,
        "seo/top.html",
        {
            "meta": meta.for_top(territori),
            "jsonld_blocks": blocks,
            "territori": territori,
            "territori_nom": meta.TERRITORI_NOMS.get(territori, territori),
            "entries": entries,
            "is_provisional": is_provisional,
            "monday": monday,
        },
    )


@require_safe
@_vary_ua
def artistes_list_seo(request: HttpRequest) -> HttpResponse:
    """`/artistes` — directori, paginat. Mostra els 200 més
    rellevants ordenats per nº de cançons al top.
    """
    qs = (
        Artista.objects.filter(aprovat=True)
        .annotate(
            n_cancons=Count(
                "cancons",
                filter=Q(cancons__verificada=True, cancons__activa=True),
                distinct=True,
            )
        )
        .order_by("-n_cancons", "nom")[:200]
    )
    return render(
        request,
        "seo/artistes_list.html",
        {
            "meta": meta.for_artistes_list(),
            "jsonld_blocks": [
                jsonld.breadcrumbs_jsonld([("Inici", "/"), ("Artistes", "/artistes")]),
            ],
            "artistes": qs,
        },
    )


@require_safe
@_vary_ua
@condition(last_modified_func=_artista_lm)
def artista_seo(request: HttpRequest, slug: str) -> HttpResponse:
    """`/artista/<slug>` — full artiste page. 404 when un-approved
    so de-indexing is automatic."""
    a = get_object_or_404(
        Artista.objects.prefetch_related(
            "localitats__municipi__territori",
            "deezer_ids",
        ),
        slug=slug,
        aprovat=True,
    )
    albums = list(
        Album.objects.filter(artista=a, descartat=False).order_by("-data_llancament")
    )
    cancons = list(
        Canco.objects.filter(artista=a, verificada=True, activa=True)
        .select_related("album")
        .order_by("-data_llancament")[:50]
    )
    # Similar artists from the Last.fm-similars edges in the DB.
    # The FK reverse-name is `recomanat_per` on Artista, pointing
    # at ArtistaLastfmSimilar rows where this artiste is the source.
    # We surface targets (the recommended ones) that are already
    # approved at our system. `recomanat_per` is *being recommended*;
    # `similars_recomanats` is *who I recommend*. We want the latter.
    similars = list(
        Artista.objects.filter(
            recomanat_per__source=a,
            aprovat=True,
        )
        .distinct()
        .order_by("-recomanat_per__match")[:8]
    )
    blocks = [
        jsonld.artista_jsonld(a),
        jsonld.breadcrumbs_jsonld(
            [("Inici", "/"), ("Artistes", "/artistes"), (a.nom, f"/artista/{a.slug}")]
        ),
    ]
    return render(
        request,
        "seo/artista.html",
        {
            "meta": meta.for_artista(a),
            "jsonld_blocks": blocks,
            "artista": a,
            "albums": albums,
            "cancons": cancons,
            "similars": similars,
        },
    )


@require_safe
@_vary_ua
@condition(last_modified_func=_album_lm)
def album_seo(request: HttpRequest, slug: str) -> HttpResponse:
    """`/album/<slug>`. 404 if discarded or parent artiste un-approved."""
    al = get_object_or_404(
        Album.objects.select_related("artista"),
        slug=slug,
        descartat=False,
        artista__aprovat=True,
    )
    tracks = list(al.cancons.filter(activa=True).order_by("id"))
    blocks = [
        jsonld.album_jsonld(al),
        jsonld.breadcrumbs_jsonld(
            [
                ("Inici", "/"),
                ("Artistes", "/artistes"),
                (al.artista.nom, f"/artista/{al.artista.slug}"),
                (al.nom, f"/album/{al.slug}"),
            ]
        ),
    ]
    return render(
        request,
        "seo/album.html",
        {
            "meta": meta.for_album(al),
            "jsonld_blocks": blocks,
            "album": al,
            "tracks": tracks,
        },
    )


@require_safe
@_vary_ua
@condition(last_modified_func=_canco_lm)
def canco_seo(request: HttpRequest, slug: str) -> HttpResponse:
    """`/canco/<slug>`. 404 if un-verified or inactive."""
    c = get_object_or_404(
        Canco.objects.select_related("artista", "album"),
        slug=slug,
        verificada=True,
        activa=True,
    )
    # Recent positions across territoris (TopProvisional + TopSetmanal,
    # latest snapshot per territori). Cheap queries — at most 9 rows.
    posicions_actuals = list(
        TopProvisional.objects.filter(canco=c).order_by("territori")
    )
    blocks = [
        jsonld.canco_jsonld(c),
        jsonld.breadcrumbs_jsonld(
            [
                ("Inici", "/"),
                ("Artistes", "/artistes"),
                (c.artista.nom, f"/artista/{c.artista.slug}"),
                (c.nom, f"/canco/{c.slug}"),
            ]
        ),
    ]
    return render(
        request,
        "seo/canco.html",
        {
            "meta": meta.for_canco(c),
            "jsonld_blocks": blocks,
            "canco": c,
            "posicions_actuals": posicions_actuals,
        },
    )


@require_safe
@_vary_ua
def mapa_seo(request: HttpRequest) -> HttpResponse:
    """`/mapa` — basic SSR fallback. Doesn't render the SVG (heavy);
    instead lists territoris with their KPIs + links to the per-territori
    top. Crawlers don't need the interactive map; they need the entry
    points to deeper content.
    """
    territoris = []
    for codi, nom in meta.TERRITORI_NOMS.items():
        if codi == "ALT":
            continue
        n = (
            Artista.objects.filter(
                aprovat=True, localitats__municipi__territori_id=codi
            )
            .distinct()
            .count()
        )
        territoris.append({"codi": codi, "nom": nom, "n_artistes": n})
    return render(
        request,
        "seo/mapa.html",
        {
            "meta": meta.for_mapa(),
            "jsonld_blocks": [
                jsonld.breadcrumbs_jsonld([("Inici", "/"), ("Mapa", "/mapa")]),
            ],
            "territoris": territoris,
        },
    )


# ── /api/v1/seo/<entity>/<slug>/ — for the SPA Helmet hooks ─────────


@require_safe
def seo_api(request: HttpRequest, entity: str, slug: str = "") -> JsonResponse:
    """Read-only JSON endpoint that returns the same `Meta` payload
    the SSR templates use, so `react-helmet-async` on the SPA side
    sets the exact same `<head>` for human users. Cached lightly per
    entity; no PII.
    """
    if entity == "homepage":
        m = meta.for_homepage()
    elif entity == "top":
        m = meta.for_top(request.GET.get("territori"))
    elif entity == "artistes":
        m = meta.for_artistes_list()
    elif entity == "mapa":
        m = meta.for_mapa()
    elif entity == "artista":
        a = (
            Artista.objects.filter(slug=slug, aprovat=True)
            .prefetch_related("localitats__municipi")
            .first()
        )
        if not a:
            return JsonResponse({"error": "not_found"}, status=404)
        m = meta.for_artista(a)
    elif entity == "album":
        al = (
            Album.objects.filter(slug=slug, descartat=False, artista__aprovat=True)
            .select_related("artista")
            .first()
        )
        if not al:
            return JsonResponse({"error": "not_found"}, status=404)
        m = meta.for_album(al)
    elif entity == "canco":
        c = (
            Canco.objects.filter(slug=slug, verificada=True, activa=True)
            .select_related("artista", "album")
            .first()
        )
        if not c:
            return JsonResponse({"error": "not_found"}, status=404)
        m = meta.for_canco(c)
    else:
        return JsonResponse({"error": "unknown_entity"}, status=400)
    resp = JsonResponse(m.asdict())
    resp["Cache-Control"] = "public, max-age=300"  # 5 min TTL
    return resp
