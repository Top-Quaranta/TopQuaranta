from django.db.models import Count, Max
from django.views.decorators.http import condition
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from music.models import Artista, ArtistaLocalitat, Municipi
from ranking.models import SenyalDiari, TopSetmanal
from web.api.utils import cache_for_anon


def _mapa_last_modified(request, *args, **kwargs):
    """Most recent SenyalDiari date — drives map cache invalidation.
    A new daily senyal is the only thing that meaningfully changes
    the artist ranking served by `mapa_artistes_top`."""
    import datetime as _dt

    d = SenyalDiari.objects.aggregate(Max("data"))["data__max"]
    if d is None:
        return None
    return _dt.datetime.combine(d, _dt.time.min, tzinfo=_dt.timezone.utc)


def _mapa_etag(request, *args, **kwargs):
    lm = _mapa_last_modified(request, *args, **kwargs)
    if lm is None:
        return None
    qs = request.META.get("QUERY_STRING", "")
    return f'W/"mapa-{int(lm.timestamp())}-{hash(qs) & 0xffffffff:08x}"'


# ── Location API — single source of truth ──
#
# These endpoints expose public, non-sensitive reference data (the list of
# Catalan territories / comarques / municipis). They are consumed both by the
# public proposal form (no auth) and by staff pages (artist edit, pending
# approval). There is no reason to require auth for these GET endpoints.
# Both web/api/urls.py and web/views/staff/urls.py route to these same
# functions so staff template {% url %} tags keep working without change.
#
# S9: all @api_view-decorated handlers inherit the DRF throttle classes
# configured at settings.REST_FRAMEWORK — 60/min anon, 300/min user.


@api_view(["GET"])
def api_territoris(request: Request) -> Response:
    """List territories as shown in the cascade picker.

    Returns every Territori that has at least one Municipi *plus* the
    always-available ALT bucket (free-text localities outside PPCC —
    there are no curated municipis for it by design, so it wouldn't
    surface from the Municipi join alone).
    """
    from music.models import Territori

    result = []
    seen: set[str] = set()
    for m in Municipi.objects.values("territori__codi", "territori__nom").distinct():
        codi = m["territori__codi"]
        if codi not in seen:
            result.append({"codi": codi, "nom": m["territori__nom"]})
            seen.add(codi)
    if "ALT" not in seen:
        alt = Territori.objects.filter(codi="ALT").values("codi", "nom").first()
        if alt:
            result.append({"codi": alt["codi"], "nom": alt["nom"]})
    result.sort(key=lambda x: x["codi"])
    return Response(result)


@api_view(["GET"])
def api_comarques(request: Request) -> Response:
    """List comarques for a territory."""
    territori = request.GET.get("territori", "")
    if not territori:
        return Response([])
    comarques = list(
        Municipi.objects.filter(territori__codi=territori)
        .values_list("comarca", flat=True)
        .distinct()
        .order_by("comarca")
    )
    return Response(comarques)


@api_view(["GET"])
def api_municipis(request: Request) -> Response:
    """List municipis for a comarca.

    Returns objects `[{pk, nom}, …]`. Callers that only need the name
    (e.g. the public artist-filter dropdown) can map to `.nom`; the
    staff pendents approval needs the pk so it doesn't have to do a
    second lookup on submit.
    """
    comarca = request.GET.get("comarca", "")
    if not comarca:
        return Response([])
    municipis = list(
        Municipi.objects.filter(comarca=comarca).values("pk", "nom").order_by("nom")
    )
    return Response(municipis)


@api_view(["GET"])
def api_municipi_lookup(request: Request) -> Response:
    """Find a municipi by name and comarca, return its PK."""
    nom = request.GET.get("nom", "").strip()
    comarca = request.GET.get("comarca", "").strip()
    if not nom or not comarca:
        return Response({"error": "Cal nom i comarca"}, status=400)
    try:
        m = Municipi.objects.get(nom=nom, comarca=comarca)
        return Response(
            {
                "pk": m.pk,
                "nom": m.nom,
                "comarca": m.comarca,
                "territori": m.territori_id,
            }
        )
    except Municipi.DoesNotExist:
        return Response({"error": "Municipi no trobat"}, status=404)


@api_view(["GET"])
def mapa_artistes(request: Request) -> Response:
    """Map data for three zoom levels: territories, comarques, municipis.

    Returns artist data grouped at each level for the latest ranking week.
    An artist with multiple locations appears in all corresponding municipis.
    """
    latest = (
        TopSetmanal.objects.order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )

    # Artist ranking appearances for latest week
    artist_ids: dict[int, int] = {}
    if latest:
        for row in (
            TopSetmanal.objects.filter(setmana=latest)
            .values("canco__artista_id")
            .annotate(aparicions=Count("id"))
            .order_by("-aparicions")
        ):
            artist_ids[row["canco__artista_id"]] = row["aparicions"]

    # Load all municipis from Municipi model
    all_municipis = list(
        Municipi.objects.select_related("territori").values(
            "nom", "comarca", "territori__nom"
        )
    )

    # Load artists with their locations via ArtistaLocalitat
    artista_by_localitat: dict[str, list[dict]] = {}
    artista_by_comarca: dict[str, dict] = {}

    if artist_ids:
        # Get all ArtistaLocalitat for ranked artists
        localitats = ArtistaLocalitat.objects.filter(
            artista__aprovat=True,
            artista_id__in=artist_ids.keys(),
            municipi__isnull=False,
        ).select_related("artista", "municipi", "municipi__territori")
        for al in localitats:
            artista = al.artista
            info = {
                "nom": artista.nom,
                "slug": artista.slug,
                "aparicions": artist_ids.get(artista.id, 0),
                "territori": al.municipi.territori_id,
            }

            # Group by localitat (municipi name) for municipis level
            loc = al.municipi.nom.lower()
            artista_by_localitat.setdefault(loc, []).append(info)

            # Group by comarca — keep top artist
            com = al.municipi.comarca.lower()
            if (
                com not in artista_by_comarca
                or info["aparicions"] > artista_by_comarca[com]["aparicions"]
            ):
                artista_by_comarca[com] = info

    # Build comarques data
    comarques: dict[str, dict] = {}
    for m in all_municipis:
        com = m["comarca"].lower()
        if com not in comarques:
            comarques[com] = {
                "nom": m["comarca"],
                "territori": m["territori__nom"],
                "artista": artista_by_comarca.get(com),
            }

    # Build municipis data
    municipis_data: dict[str, dict] = {}
    for m in all_municipis:
        nom_lower = m["nom"].lower()
        artistes = artista_by_localitat.get(nom_lower, [])
        municipis_data[nom_lower] = {
            "nom": m["nom"],
            "comarca": m["comarca"],
            "territori": m["territori__nom"],
            "n_artistes": len(artistes),
            "artistes": sorted(artistes, key=lambda a: -a["aparicions"])[:5],
        }

    return Response(
        {
            "comarques": comarques,
            "municipis": municipis_data,
        }
    )


# ─────────────────────────────────────────────────────────────────────────
# Map stats — /mapa drill-down (territori → comarca → municipi)
# ─────────────────────────────────────────────────────────────────────────

_MAPA_STATS_CACHE: dict = {"key": None, "data": None, "ts": 0.0}
_MAPA_STATS_TTL = 600  # seconds


@api_view(["GET"])
def mapa_stats(request: Request) -> Response:
    """Per-region stats for the /mapa drill-down page.

    Query params:
      * `level` — "territori" (default), "comarca" or "municipi".
      * `parent` — when `level=comarca`, the parent territori code.
                   When `level=municipi`, the parent comarca name.
      * `territori` — optional when `level=municipi`, disambiguates
                      comarques that share a name across territoris.

    Returns `[ { codi?, nom, n_artistes, n_albums, n_cancons, n_ranking } ]`.
    Only counts approved artists with a linked Municipi (localitat_manual
    without municipi is excluded, per design).
    """
    import time

    from django.db.models import Count
    from django.db.models.functions import Lower

    from comptes.models import Usuari  # noqa: F401 (keeps import graph stable)
    from music.models import (
        Album,
        ArtistaLocalitat,
        Canco,
        Municipi,
        Territori,
    )
    from ranking.models import TopSetmanal

    level = (request.GET.get("level") or "territori").strip()
    parent = (request.GET.get("parent") or "").strip()
    parent_territori = (request.GET.get("territori") or "").strip()

    if level not in {"territori", "comarca", "municipi"}:
        return Response({"error": "level invàlid"}, status=400)

    cache_key = (level, parent, parent_territori)
    now = time.time()
    cached = _MAPA_STATS_CACHE
    if (
        cached["key"] == cache_key
        and cached["data"] is not None
        and (now - cached["ts"]) < _MAPA_STATS_TTL
    ):
        return Response(cached["data"])

    # Latest setmanal week — fallback to any setmanal we have, else empty set.
    latest_setmana = (
        TopSetmanal.objects.order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    ranking_canco_ids: set[int] = set()
    if latest_setmana is not None:
        ranking_canco_ids = set(
            TopSetmanal.objects.filter(setmana=latest_setmana)
            .values_list("canco_id", flat=True)
            .distinct()
        )

    # All (artista, municipi) pairs for approved artists with a linked
    # Municipi. Deduplicated per (artista_id, municipi_id).
    al_qs = ArtistaLocalitat.objects.filter(
        artista__aprovat=True, municipi__isnull=False
    ).values_list(
        "artista_id",
        "municipi_id",
        "municipi__territori_id",
        "municipi__comarca",
        "municipi__nom",
    )
    pairs = list(al_qs)
    if not pairs:
        return Response([])

    # For each artista_id collect the set of albums / cancons so we can
    # aggregate per region without double-counting.
    artista_ids = {p[0] for p in pairs}
    cancons_by_artista: dict[int, set[int]] = {a: set() for a in artista_ids}
    albums_by_artista: dict[int, set[int]] = {a: set() for a in artista_ids}
    for c_pk, a_pk, alb_pk in Canco.objects.filter(
        artista_id__in=artista_ids
    ).values_list("pk", "artista_id", "album_id"):
        cancons_by_artista[a_pk].add(c_pk)
        if alb_pk:
            albums_by_artista[a_pk].add(alb_pk)

    # Aggregate into the requested level.
    groups: dict[tuple, dict] = {}
    for a_pk, m_pk, ter_id, comarca, mun_nom in pairs:
        if level == "territori":
            key = (ter_id,)
            display = {"codi": ter_id}
        elif level == "comarca":
            if parent and ter_id != parent:
                continue
            key = (ter_id, comarca)
            display = {"codi": ter_id, "comarca": comarca}
        else:  # municipi
            if parent_territori and ter_id != parent_territori:
                continue
            if parent and comarca != parent:
                continue
            key = (ter_id, comarca, mun_nom)
            display = {"codi": ter_id, "comarca": comarca, "municipi": mun_nom}

        slot = groups.get(key)
        if slot is None:
            slot = {
                **display,
                "artistes": set(),
                "albums": set(),
                "cancons": set(),
                "ranking_cancons": set(),
            }
            groups[key] = slot
        slot["artistes"].add(a_pk)
        for alb in albums_by_artista.get(a_pk, ()):
            slot["albums"].add(alb)
        for c in cancons_by_artista.get(a_pk, ()):
            slot["cancons"].add(c)
            if c in ranking_canco_ids:
                slot["ranking_cancons"].add(c)

    results = []
    for slot in groups.values():
        row = {
            k: v
            for k, v in slot.items()
            if k not in {"artistes", "albums", "cancons", "ranking_cancons"}
        }
        row["n_artistes"] = len(slot["artistes"])
        row["n_albums"] = len(slot["albums"])
        row["n_cancons"] = len(slot["cancons"])
        row["n_ranking"] = len(slot["ranking_cancons"])
        results.append(row)

    results.sort(key=lambda r: -r["n_artistes"])
    _MAPA_STATS_CACHE.update({"key": cache_key, "data": results, "ts": now})
    return Response(results)


@api_view(["GET"])
def mapa_municipi_artistes(request: Request) -> Response:
    """Approved artists living in a specific municipi.

    Query: `territori` (code), `comarca` (name), `municipi` (name).
    Returns a compact list sorted alphabetically, with basic ranking
    info to drive the side-panel detail view on /mapa.
    """
    from music.models import ArtistaLocalitat
    from ranking.models import TopSetmanal

    ter = (request.GET.get("territori") or "").strip()
    com = (request.GET.get("comarca") or "").strip()
    mun = (request.GET.get("municipi") or "").strip()
    if not (ter and com and mun):
        return Response({"error": "Cal territori, comarca i municipi"}, status=400)

    qs = (
        ArtistaLocalitat.objects.filter(
            artista__aprovat=True,
            municipi__isnull=False,
            municipi__territori_id=ter,
            municipi__comarca=com,
            municipi__nom=mun,
        )
        .select_related("artista")
        .order_by("artista__nom")
    )

    # Which of their songs are in the latest weekly ranking?
    latest_setmana = (
        TopSetmanal.objects.order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    ranking_by_artista: dict[int, int] = {}
    if latest_setmana is not None:
        from django.db.models import Count

        for row in (
            TopSetmanal.objects.filter(setmana=latest_setmana)
            .values("canco__artista_id")
            .annotate(n=Count("pk", distinct=True))
        ):
            ranking_by_artista[row["canco__artista_id"]] = row["n"]

    seen = set()
    results = []
    for al in qs:
        a = al.artista
        if a.pk in seen:
            continue
        seen.add(a.pk)
        results.append(
            {
                "pk": a.pk,
                "nom": a.nom,
                "slug": a.slug,
                "n_ranking": ranking_by_artista.get(a.pk, 0),
            }
        )
    return Response(results)


@condition(etag_func=_mapa_etag, last_modified_func=_mapa_last_modified)
@api_view(["GET"])
@cache_for_anon(60, key_prefix="mapa")
def mapa_artistes_top(request: Request) -> Response:
    """Artistes for the /mapa side panel, sorted by listens, any level.

    Query (all optional — no filters → all PPCC):
      * `territori` — restrict to a territori code.
      * `comarca`   — restrict to a comarca within that territori.
      * `municipi`  — restrict to a specific municipi.
      * `limit`     — max rows (default 60, max 200).

    Sort key: the sum, across the artista's cançons, of the most
    recent Last.fm playcount we stored (SenyalDiari.lastfm_playcount
    is cumulative, so the max across days per canco ≈ the latest
    non-zero value). Artists with no senyal data yet tie-break by
    name alphabetically.
    """
    from django.db.models import Max

    from music.models import Album, ArtistaLocalitat, Canco

    ter = (request.GET.get("territori") or "").strip()
    com = (request.GET.get("comarca") or "").strip()
    mun = (request.GET.get("municipi") or "").strip()
    try:
        limit = min(int(request.GET.get("limit") or 60), 200)
    except ValueError:
        limit = 60

    # Scope artistes via their linked Municipi (localitat_manual without
    # municipi is excluded by design — those are the ALT bucket).
    al_qs = ArtistaLocalitat.objects.filter(
        artista__aprovat=True, municipi__isnull=False
    )
    if ter:
        al_qs = al_qs.filter(municipi__territori_id=ter)
    if com:
        al_qs = al_qs.filter(municipi__comarca=com)
    if mun:
        al_qs = al_qs.filter(municipi__nom=mun)

    artista_ids = set(al_qs.values_list("artista_id", flat=True))
    if not artista_ids:
        return Response([])

    # Per-canco max playcount (cumulative metric so max == latest),
    # then fold into per-artista totals in one pass.
    #
    # Restrict to `verificada=True` cançons. Otherwise a Deezer ID
    # collision (a Catalan artist sharing an ID with a popular
    # international homonym) inflates the artist's apparent listens
    # with material that staff has already deemed not theirs — they
    # ranked at the top of the map without a single verified track.
    canco_rows = (
        Canco.objects.filter(artista_id__in=artista_ids, verificada=True)
        .annotate(plays=Max("senyals__lastfm_playcount"))
        .values_list("artista_id", "plays")
    )
    plays_by_artista: dict[int, int] = {}
    for artista_id, plays in canco_rows:
        plays_by_artista[artista_id] = plays_by_artista.get(artista_id, 0) + (
            plays or 0
        )

    # Latest album cover per artista (for the grid thumbnail). Same
    # `verificada=True` guard as the play-count aggregation above:
    # a Deezer ID collision can otherwise surface a cover from the
    # homonym's catalogue, even when our artist has no real material.
    cover_rows = (
        Album.objects.filter(artista_id__in=artista_ids, cancons__verificada=True)
        .exclude(imatge_url="")
        .order_by("artista_id", "-data_llancament")
        .values_list("artista_id", "imatge_url")
        .distinct()
    )
    cover_by_artista: dict[int, str] = {}
    for artista_id, url in cover_rows:
        cover_by_artista.setdefault(artista_id, url)

    # Pull artistes we kept, sort by plays desc then name.
    from music.models import Artista

    rows = list(Artista.objects.filter(pk__in=artista_ids).values("pk", "nom", "slug"))
    rows.sort(key=lambda r: (-plays_by_artista.get(r["pk"], 0), r["nom"].lower()))
    rows = rows[:limit]

    return Response(
        [
            {
                "pk": r["pk"],
                "nom": r["nom"],
                "slug": r["slug"],
                "imatge_url": cover_by_artista.get(r["pk"]) or None,
                "plays": plays_by_artista.get(r["pk"], 0),
            }
            for r in rows
        ]
    )
