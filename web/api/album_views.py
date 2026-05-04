"""Public album endpoints for the React SPA.

GET /api/v1/albums/                — paginated list with filter/order
                                     (Sprint I: feeds the HomePage
                                     "Últims llançaments" section)
GET /api/v1/albums/<slug>/         — album metadata + track listing
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from music.models import Album, Canco
from ranking.models import TopProvisional, TopSetmanal
from web.api.utils import cache_for_anon


@api_view(["GET"])
@permission_classes([AllowAny])
@cache_for_anon(300, key_prefix="albums-list")
def album_list(request: Request) -> Response:
    """List albums for the public catalogue / HomePage strip.

    Query params:
      ordering          — only `-data_llancament` and `data_llancament`
                          are accepted (default: `-data_llancament`).
      amb_verificades   — when "true" / "1", only albums with at least
                          one `Canco(verificada=True, activa=True)` row.
      limit             — capped at 24.
    """
    ordering_raw = (request.GET.get("ordering") or "-data_llancament").strip()
    if ordering_raw not in ("-data_llancament", "data_llancament"):
        ordering_raw = "-data_llancament"

    amb_v = (request.GET.get("amb_verificades") or "").strip().lower() in ("1", "true")

    try:
        limit = max(1, min(int(request.GET.get("limit", "12")), 24))
    except ValueError:
        limit = 12

    qs = Album.objects.select_related("artista").exclude(data_llancament=None)
    if amb_v:
        qs = qs.annotate(
            n_verificades=Count(
                "cancons", filter=Q(cancons__verificada=True, cancons__activa=True)
            )
        ).filter(n_verificades__gt=0)
    else:
        qs = qs.annotate(
            n_verificades=Count(
                "cancons", filter=Q(cancons__verificada=True, cancons__activa=True)
            )
        )

    qs = qs.order_by(ordering_raw, "-id")[:limit]

    return Response(
        {
            "results": [
                {
                    "pk": a.pk,
                    "slug": a.slug,
                    "nom": a.nom,
                    "imatge_url": getattr(a, "imatge_url", None) or None,
                    "data_llancament": (
                        a.data_llancament.isoformat() if a.data_llancament else None
                    ),
                    "n_verificades": getattr(a, "n_verificades", 0) or 0,
                    "artista": (
                        {"nom": a.artista.nom, "slug": a.artista.slug}
                        if a.artista
                        else None
                    ),
                }
                for a in qs
            ]
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def album_detail(request: Request, slug: str) -> Response:
    album = get_object_or_404(
        Album.objects.select_related("artista"),
        slug=slug,
    )

    # Only verified tracks surface publicly. Unverified/discarded tracks
    # are noise for the listener (think Rosalía's latest album with 1
    # Catalan track vs 15 Spanish-only ones we chose not to publish).
    cancons = list(
        album.cancons.filter(verificada=True)
        .select_related("artista")
        .prefetch_related("artistes_col")
        .order_by("id")
    )
    canco_ids = [c.pk for c in cancons]

    ranked_ids = set(
        TopSetmanal.objects.filter(canco_id__in=canco_ids)
        .values_list("canco_id", flat=True)
        .distinct()
    ) | set(
        TopProvisional.objects.filter(canco_id__in=canco_ids)
        .values_list("canco_id", flat=True)
        .distinct()
    )

    return Response(
        {
            "pk": album.pk,
            "slug": album.slug,
            "nom": album.nom,
            "data_llancament": (
                album.data_llancament.isoformat() if album.data_llancament else None
            ),
            "imatge_url": getattr(album, "imatge_url", None) or None,
            "deezer_id": album.deezer_id,
            "artista": (
                {
                    "nom": album.artista.nom,
                    "slug": album.artista.slug,
                }
                if album.artista
                else None
            ),
            "cancons": [
                {
                    "pk": c.pk,
                    "slug": c.slug,
                    "nom": c.nom,
                    "isrc": c.isrc or None,
                    "durada_ms": c.durada_ms,
                    "preview_url": c.preview_url or None,
                    "deezer_id": c.deezer_id,
                    "al_top": c.pk in ranked_ids,
                    "artistes_col": [
                        {"nom": a.nom, "slug": a.slug} for a in c.artistes_col.all()
                    ],
                }
                for c in cancons
            ],
        }
    )
