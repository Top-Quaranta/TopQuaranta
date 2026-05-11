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
    # Indexability requires the artiste to have at least one verified
    # active cançó; otherwise the SEO view returns 404. Mirror the same
    # predicate here so Last-Modified is None for ghost profiles.
    a = (
        Artista.objects.filter(
            slug=slug,
            aprovat=True,
            cancons__verificada=True,
            cancons__activa=True,
        )
        .distinct()
        .only("updated_at")
        .first()
    )
    return a.updated_at if a else None


def _album_lm(request, slug):
    # Same indexability rule as album_seo: at least one verified active
    # cançó. Returning None here when the album is empty keeps
    # If-Modified-Since negotiation consistent with the 404 path.
    al = (
        Album.objects.filter(
            slug=slug,
            descartat=False,
            artista__aprovat=True,
            cancons__verificada=True,
            cancons__activa=True,
        )
        .distinct()
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
        Artista.objects.public()
        .annotate(
            n_cancons=Count(
                "cancons",
                filter=Q(cancons__verificada=True, cancons__activa=True),
                distinct=True,
            )
        )
        # Skip ghost profiles (no verified active cançó). They are not
        # linked from individual /artista/ pages either, since those
        # now 404 in the SEO view.
        .filter(n_cancons__gt=0)
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
    """`/artista/<slug>` — full artiste page. 404 when un-approved or
    when the artiste has no verified active cançó, so de-indexing is
    automatic. The empty-discography case is a ghost page in Google's
    eyes and matches what the public profile would render: nothing
    indexable."""
    a = get_object_or_404(
        Artista.objects.prefetch_related(
            "localitats__municipi__territori",
            "deezer_ids",
        )
        .filter(cancons__verificada=True, cancons__activa=True)
        .distinct(),
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
    """`/album/<slug>`. 404 if discarded, parent artiste un-approved, or
    no verified active cançó. Indexability requires at least one
    verified song, consistent with the /artista/ profile filter — an
    empty tracklist is a ghost page in Google's eyes."""
    al = get_object_or_404(
        Album.objects.select_related("artista")
        .filter(cancons__verificada=True, cancons__activa=True)
        .distinct(),
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
def top_historic_seo(
    request: HttpRequest, territori: str, year_week: str
) -> HttpResponse:
    """`/top/<territori>/setmana/<YYYY-WW>` — historical weekly chart.

    Sprint S Block C: long-tail SEO surface. Each (territori, setmana)
    pair gets its own canonical URL so queries like 'top música català
    setmana 35 2025' land on the right historical chart instead of the
    live `/top` page.

    Forward-compatible with the sitemap entries from Block B.
    """
    territori = territori.upper()
    if territori not in meta.TERRITORI_NOMS:
        from django.http import Http404 as _H

        raise _H()
    try:
        # ISO week format `YYYY-WNN` — Python's `%G-W%V` round-trip.
        year, week = year_week.split("-W") if "-W" in year_week else (None, None)
        if not year or not week:
            raise ValueError
        year_i = int(year)
        week_i = int(week)
        # ISO week → Monday of that week.
        monday = datetime.date.fromisocalendar(year_i, week_i, 1)
    except (ValueError, TypeError):
        from django.http import Http404 as _H

        raise _H()

    entries = list(
        TopSetmanal.objects.filter(territori=territori, setmana=monday)
        .select_related("canco__artista", "canco__album")
        .order_by("posicio")
    )
    if not entries:
        from django.http import Http404 as _H

        raise _H()

    nom_terr = meta.TERRITORI_NOMS.get(territori, territori)
    title = f"Top {nom_terr} — Setmana {week_i} de {year_i} · TopQuaranta"
    desc = (
        f"Les 40 cançons en català més escoltades de {nom_terr} la "
        f"setmana {week_i} de {year_i} ({monday.strftime('%d/%m/%Y')}). "
        "Top setmanal mesurat amb dades reals."
    )
    canonical = f"https://www.topquaranta.cat/top/{territori}/setmana/{year_week}"
    page_meta = meta.Meta(
        title=title,
        description=desc,
        canonical_url=canonical,
        og_image=f"https://www.topquaranta.cat/og/top/{territori}.png",
        og_type="website",
        keywords=[
            f"top {nom_terr.lower()}",
            f"música català {year_i}",
            f"setmana {week_i}",
        ],
    )

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
    blocks = [
        jsonld.top_jsonld(territori, monday, entries_for_jsonld),
        jsonld.breadcrumbs_jsonld(
            [
                ("Inici", "/"),
                ("Top", "/top"),
                (f"{nom_terr}", f"/top?territori={territori}"),
                (f"Setmana {week_i} {year_i}", canonical),
            ]
        ),
    ]
    return render(
        request,
        "seo/top_historic.html",
        {
            "meta": page_meta,
            "jsonld_blocks": blocks,
            "territori": territori,
            "territori_nom": nom_terr,
            "entries": entries,
            "monday": monday,
            "year": year_i,
            "week": week_i,
        },
    )


@require_safe
@_vary_ua
def territori_seo(request: HttpRequest, codi: str) -> HttpResponse:
    """`/territori/<codi>` — landing page per territori with KPIs +
    top + featured artistes. Programmatic SEO surface."""
    codi = codi.upper()
    if codi not in meta.TERRITORI_NOMS or codi == "ALT":
        from django.http import Http404 as _H

        raise _H()
    nom = meta.TERRITORI_NOMS[codi]
    artistes = list(
        Artista.objects.public()
        .filter(localitats__municipi__territori_id=codi)
        .annotate(
            n_cancons=Count(
                "cancons",
                filter=Q(cancons__verificada=True, cancons__activa=True),
                distinct=True,
            )
        )
        .distinct()
        .order_by("-n_cancons", "nom")[:60]
    )
    top_entries = list(
        TopProvisional.objects.filter(territori=codi)
        .select_related("canco__artista")
        .order_by("posicio")[:10]
    )
    page_meta = meta.Meta(
        title=f"Música en català de {nom} · TopQuaranta",
        description=meta._trim(
            f"Tota la música en català de {nom}: artistes, top setmanal "
            "i discografia. El catàleg complet d'aquest territori al "
            "sistema TopQuaranta."
        ),
        canonical_url=f"https://www.topquaranta.cat/territori/{codi}",
        og_image=f"https://www.topquaranta.cat/og/top/{codi}.png",
        og_type="website",
        keywords=[
            f"música {nom}",
            f"artistes {nom}",
            "música en català",
            f"top {nom}",
        ],
    )
    blocks = [
        jsonld.breadcrumbs_jsonld(
            [
                ("Inici", "/"),
                ("Mapa", "/mapa"),
                (nom, f"/territori/{codi}"),
            ]
        ),
    ]
    return render(
        request,
        "seo/territori.html",
        {
            "meta": page_meta,
            "jsonld_blocks": blocks,
            "codi": codi,
            "nom": nom,
            "artistes": artistes,
            "top_entries": top_entries,
        },
    )


@require_safe
@_vary_ua
def comarca_seo(request: HttpRequest, slug: str) -> HttpResponse:
    """`/comarca/<slug>` — landing page per comarca. Aggregates
    `Artista` rows whose `localitats.municipi.comarca` matches.
    """
    from django.utils.text import slugify

    from music.models import Municipi

    # Find a real comarca name matching the slug. Comarca isn't a
    # model — it's a free-text CharField on Municipi. Build the slug
    # → name map from distinct values.
    distinct_comarques = (
        Municipi.objects.values_list("comarca", flat=True)
        .distinct()
        .order_by("comarca")
    )
    slug_to_name = {slugify(c): c for c in distinct_comarques if c}
    nom_comarca = slug_to_name.get(slug)
    if not nom_comarca:
        from django.http import Http404 as _H

        raise _H()

    artistes = list(
        Artista.objects.public()
        .filter(localitats__municipi__comarca=nom_comarca)
        .annotate(
            n_cancons=Count(
                "cancons",
                filter=Q(cancons__verificada=True, cancons__activa=True),
                distinct=True,
            )
        )
        .distinct()
        .order_by("-n_cancons", "nom")[:60]
    )
    if len(artistes) < 3:
        # Don't render thin pages — they'd be flagged as low-quality.
        from django.http import Http404 as _H

        raise _H()

    page_meta = meta.Meta(
        title=f"Música en català de {nom_comarca} · TopQuaranta",
        description=meta._trim(
            f"Artistes de música en català de la comarca de {nom_comarca}. "
            f"{len(artistes)} bandes i cantants verificats al sistema "
            "TopQuaranta."
        ),
        canonical_url=f"https://www.topquaranta.cat/comarca/{slug}",
        og_image=f"https://www.topquaranta.cat/og/default.png",
        og_type="website",
        keywords=[
            f"música {nom_comarca}",
            f"artistes {nom_comarca}",
            "música en català",
        ],
    )
    blocks = [
        jsonld.breadcrumbs_jsonld(
            [
                ("Inici", "/"),
                ("Mapa", "/mapa"),
                (nom_comarca, f"/comarca/{slug}"),
            ]
        ),
    ]
    return render(
        request,
        "seo/comarca.html",
        {
            "meta": page_meta,
            "jsonld_blocks": blocks,
            "nom_comarca": nom_comarca,
            "artistes": artistes,
        },
    )


@require_safe
@_vary_ua
def decada_seo(request: HttpRequest, decada: str) -> HttpResponse:
    """`/decada/<XXX0>` — música en català per dècada. Filters
    cançons by `data_llancament.year` falling in the decade range.
    """
    if not (decada.isdigit() and len(decada) == 4 and decada.endswith("0")):
        from django.http import Http404 as _H

        raise _H()
    year_start = int(decada)
    year_end = year_start + 9

    cancons = list(
        Canco.objects.filter(
            verificada=True,
            activa=True,
            data_llancament__year__gte=year_start,
            data_llancament__year__lte=year_end,
        )
        .select_related("artista", "album")
        .order_by("-data_llancament")[:50]
    )
    if len(cancons) < 5:
        from django.http import Http404 as _H

        raise _H()

    title = f"Música en català dels {decada} · TopQuaranta"
    desc = meta._trim(
        f"Cançons en català publicades entre {year_start} i {year_end}. "
        f"{len(cancons)} cançons verificades al sistema TopQuaranta — "
        "el millor de la dècada de la nostra música."
    )
    page_meta = meta.Meta(
        title=title,
        description=desc,
        canonical_url=f"https://www.topquaranta.cat/decada/{decada}",
        og_image=f"https://www.topquaranta.cat/og/default.png",
        og_type="website",
        keywords=[
            f"música català dècada {decada}",
            f"cançons {year_start}",
            f"cançons {year_end}",
        ],
    )
    blocks = [
        jsonld.breadcrumbs_jsonld(
            [("Inici", "/"), (f"Dècada {decada}", f"/decada/{decada}")]
        ),
    ]
    return render(
        request,
        "seo/decada.html",
        {
            "meta": page_meta,
            "jsonld_blocks": blocks,
            "decada": decada,
            "year_start": year_start,
            "year_end": year_end,
            "cancons": cancons,
        },
    )


@require_safe
@_vary_ua
def genere_seo(request: HttpRequest, slug: str) -> HttpResponse:
    """`/genere/<slug>` — música en català per gènere canònic.

    Sprint S Bloc D pt 3 (2026-05-06): programmatic SEO surface
    backed by `Artista.genere_canonical` (data-driven inference
    from Last.fm + MB tags).
    """
    valid = {k for k, _ in Artista.GENERE_CANONICAL_CHOICES}
    if slug not in valid:
        from django.http import Http404 as _H

        raise _H()

    label = dict(Artista.GENERE_CANONICAL_CHOICES)[slug]
    artistes = list(
        Artista.objects.public()
        .filter(genere_canonical=slug)
        .annotate(
            n_cancons=Count(
                "cancons",
                filter=Q(cancons__verificada=True, cancons__activa=True),
                distinct=True,
            )
        )
        .order_by("-n_cancons", "nom")[:80]
    )
    if len(artistes) < 3:
        from django.http import Http404 as _H

        raise _H()

    page_meta = meta.Meta(
        title=f"{label} en català · TopQuaranta",
        description=meta._trim(
            f"Artistes de {label.lower()} en català. {len(artistes)} bandes "
            "i cantants verificats al sistema TopQuaranta."
        ),
        canonical_url=f"https://www.topquaranta.cat/genere/{slug}",
        og_image=f"https://www.topquaranta.cat/og/default.png",
        og_type="website",
        keywords=[
            f"{label} català",
            f"música {label.lower()}",
            "música en català",
        ],
    )
    blocks = [
        jsonld.breadcrumbs_jsonld(
            [
                ("Inici", "/"),
                ("Artistes", "/artistes"),
                (label, f"/genere/{slug}"),
            ]
        ),
    ]
    return render(
        request,
        "seo/genere.html",
        {
            "meta": page_meta,
            "jsonld_blocks": blocks,
            "slug": slug,
            "label": label,
            "artistes": artistes,
        },
    )


@require_safe
@_vary_ua
def com_funciona_seo(request: HttpRequest) -> HttpResponse:
    """`/com-funciona` — methodology + governance page (bot path).

    Mirrors the SPA's ComFuncionaPage so crawlers index the actual
    content (mission, ranking method, what counts as Catalan music,
    governance, what we'll never do, how to participate) instead of
    the empty SPA shell.
    """
    return render(
        request,
        "seo/com_funciona.html",
        {
            "meta": meta.for_com_funciona(),
            "jsonld_blocks": [
                jsonld.breadcrumbs_jsonld(
                    [("Inici", "/"), ("Com funciona", "/com-funciona")]
                ),
            ],
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
    blocks: list = []
    if entity == "homepage":
        m = meta.for_homepage()
        blocks = [jsonld.website_jsonld()]
    elif entity == "top":
        territori = (request.GET.get("territori") or "PPCC").upper()
        m = meta.for_top(territori)
        # Top blocks: include MusicPlaylist + breadcrumbs.
        today = timezone.localdate()
        monday = today - datetime.timedelta(days=today.weekday())
        entries_qs = TopSetmanal.objects.filter(
            territori=territori, setmana=monday
        ).select_related("canco__artista")
        if not entries_qs.exists():
            entries_qs = (
                TopProvisional.objects.filter(territori=territori)
                .select_related("canco__artista")
                .order_by("posicio")[:40]
            )
        entries = [
            {
                "posicio": e.posicio,
                "canco_nom": e.canco.nom,
                "canco_slug": e.canco.slug,
                "artista_nom": e.canco.artista.nom,
                "artista_slug": e.canco.artista.slug,
            }
            for e in entries_qs
        ]
        blocks = [
            jsonld.top_jsonld(territori, monday, entries),
            jsonld.breadcrumbs_jsonld([("Inici", "/"), ("Top", "/top")]),
        ]
    elif entity == "artistes":
        m = meta.for_artistes_list()
        blocks = [
            jsonld.breadcrumbs_jsonld([("Inici", "/"), ("Artistes", "/artistes")])
        ]
    elif entity == "mapa":
        m = meta.for_mapa()
        blocks = [jsonld.breadcrumbs_jsonld([("Inici", "/"), ("Mapa", "/mapa")])]
    elif entity == "artista":
        a = (
            Artista.objects.filter(slug=slug, aprovat=True)
            .prefetch_related("localitats__municipi__territori")
            .first()
        )
        if not a:
            return JsonResponse({"error": "not_found"}, status=404)
        m = meta.for_artista(a)
        blocks = [
            jsonld.artista_jsonld(a),
            jsonld.breadcrumbs_jsonld(
                [
                    ("Inici", "/"),
                    ("Artistes", "/artistes"),
                    (a.nom, f"/artista/{a.slug}"),
                ]
            ),
        ]
    elif entity == "album":
        al = (
            Album.objects.filter(slug=slug, descartat=False, artista__aprovat=True)
            .select_related("artista")
            .first()
        )
        if not al:
            return JsonResponse({"error": "not_found"}, status=404)
        m = meta.for_album(al)
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
    elif entity == "canco":
        c = (
            Canco.objects.filter(slug=slug, verificada=True, activa=True)
            .select_related("artista", "album")
            .first()
        )
        if not c:
            return JsonResponse({"error": "not_found"}, status=404)
        m = meta.for_canco(c)
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
    else:
        return JsonResponse({"error": "unknown_entity"}, status=400)
    payload = m.asdict()
    payload["jsonld"] = blocks
    resp = JsonResponse(payload)
    resp["Cache-Control"] = "public, max-age=300"  # 5 min TTL
    return resp
