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
from web.api.serializers import album_card, artista_minimal, canco_card
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
                    **album_card(a),
                    "n_verificades": getattr(a, "n_verificades", 0) or 0,
                    "artista": artista_minimal(a.artista) if a.artista else None,
                }
                for a in qs
            ]
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def album_detail(request: Request, slug: str) -> Response:
    # Same indexability gate as the SEO view (web/seo/views.py): parent
    # artiste approved, album not discarded, and at least one verified
    # active cançó. Staff editing flows hit /api/v1/staff/albums/*
    # instead, so the public detail has no legitimate empty-album use.
    album = get_object_or_404(
        Album.objects.select_related("artista")
        .filter(cancons__verificada=True, cancons__activa=True)
        .distinct(),
        slug=slug,
        descartat=False,
        artista__aprovat=True,
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
            **album_card(album),
            "deezer_id": album.deezer_id,
            "artista": artista_minimal(album.artista) if album.artista else None,
            "cancons": [canco_card(c, ranked_ids=ranked_ids) for c in cancons],
        }
    )
