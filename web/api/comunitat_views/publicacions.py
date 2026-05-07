"""Publicacio CRUD + comments (author/viewer flows; staff moderation in sibling)."""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import Publicacio
from web.api.utils import paginate

from ._common import (
    _enviar_notificacio_comentari,
    _serialize_comentari,
    _serialize_publicacio,
    _validate_publicacio_body,
)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def publicacions(request: Request) -> Response:
    """List + create. List returns internal + public (authenticated view)."""
    if request.method == "POST":
        cleaned, errors = _validate_publicacio_body(request.data or {})
        save_as = (request.data or {}).get("save_as", "submit")
        if errors:
            return Response({"errors": errors}, status=400)
        user = request.user
        # Staff bypasses the pending queue for any visibility.
        # Regular users: `interna` → published directly;
        # `publica` → goes through the pending queue.
        if save_as == "draft":
            estat = Publicacio.ESTAT_ESBORRANY
            publicat_at = None
        elif user.is_staff or cleaned["visibilitat"] == Publicacio.VISIBILITAT_INTERNA:
            estat = Publicacio.ESTAT_PUBLICAT
            publicat_at = timezone.now()
        else:
            estat = Publicacio.ESTAT_PENDENT
            publicat_at = None

        pub = Publicacio.objects.create(
            autor=user,
            titol=cleaned["titol"],
            cos=cleaned["cos"],
            visibilitat=cleaned["visibilitat"],
            estat=estat,
            publicat_at=publicat_at,
        )
        return Response(_serialize_publicacio(pub), status=201)

    # ── GET: combined internal + own drafts/pending + public ───────────
    qs = Publicacio.objects.select_related("autor", "autor__perfil")
    # Show: (visibilitat=interna AND estat=publicat) + own in any state
    own = Q(autor=request.user)
    internal_published = Q(
        visibilitat=Publicacio.VISIBILITAT_INTERNA, estat=Publicacio.ESTAT_PUBLICAT
    )
    public_published = Q(
        visibilitat=Publicacio.VISIBILITAT_PUBLICA, estat=Publicacio.ESTAT_PUBLICAT
    )
    qs = qs.filter(own | internal_published | public_published)

    filter_mode = request.GET.get("filtre", "")
    if filter_mode == "meves":
        qs = qs.filter(autor=request.user)
    elif filter_mode == "internes":
        qs = qs.filter(internal_published)
    elif filter_mode == "publiques":
        qs = qs.filter(public_published)

    qs = qs.order_by("-publicat_at", "-created_at")
    page, meta = paginate(qs, request, default=20, cap=100)
    return Response(
        {"results": [_serialize_publicacio(p) for p in page.object_list], **meta}
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def publicacio_detail(request: Request, pk: int) -> Response:
    pub = get_object_or_404(
        Publicacio.objects.select_related("autor", "autor__perfil"), pk=pk
    )
    # Authorization: author can always see; staff can always see; other
    # users only if it's published.
    user = request.user
    can_view = (
        pub.autor_id == user.id
        or user.is_staff
        or pub.estat == Publicacio.ESTAT_PUBLICAT
    )
    if not can_view:
        return Response({"detail": "No trobat."}, status=404)

    if request.method == "DELETE":
        if pub.autor_id != user.id and not user.is_staff:
            return Response({"detail": "No autoritzat."}, status=403)
        pub.delete()
        return Response(status=204)

    if request.method == "PATCH":
        if pub.autor_id != user.id and not user.is_staff:
            return Response({"detail": "No autoritzat."}, status=403)
        cleaned, errors = _validate_publicacio_body(request.data or {})
        if errors:
            return Response({"errors": errors}, status=400)
        pub.titol = cleaned["titol"]
        pub.cos = cleaned["cos"]
        # Visibility change rules: staff free; author can only move
        # between esborrany/interna. Switching to `publica` resubmits
        # for approval unless staff.
        old_vis = pub.visibilitat
        pub.visibilitat = cleaned["visibilitat"]
        if not user.is_staff and old_vis != pub.visibilitat:
            if pub.visibilitat == Publicacio.VISIBILITAT_PUBLICA:
                pub.estat = Publicacio.ESTAT_PENDENT
                pub.publicat_at = None
            else:
                pub.estat = Publicacio.ESTAT_PUBLICAT
                pub.publicat_at = pub.publicat_at or timezone.now()
        pub.save()

    return Response(
        _serialize_publicacio(pub, for_staff=user.is_staff or pub.autor_id == user.id)
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def publicacions_publiques(request: Request) -> Response:
    """Public feed — visible without auth, only `publica + publicat`."""
    qs = (
        Publicacio.objects.filter(
            visibilitat=Publicacio.VISIBILITAT_PUBLICA,
            estat=Publicacio.ESTAT_PUBLICAT,
        )
        .select_related("autor", "autor__perfil")
        .order_by("-publicat_at")
    )
    page, meta = paginate(qs, request, default=20, cap=100)
    return Response(
        {"results": [_serialize_publicacio(p) for p in page.object_list], **meta}
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def publicacio_comentaris(request: Request, pk: int) -> Response:
    """List + create comments for a publication. List is public-ish
    (requires auth same as the containing post); create is authenticated."""
    pub = get_object_or_404(Publicacio, pk=pk)
    # Only allow comments on posts the viewer can see.
    if pub.estat != Publicacio.ESTAT_PUBLICAT:
        if not (request.user.is_staff or request.user.pk == pub.autor_id):
            return Response({"error": "Publicació no disponible."}, status=404)

    from comptes.models import Comentari

    if request.method == "GET":
        rows = list(
            pub.comentaris.select_related("autor__perfil").order_by("created_at")
        )
        return Response([_serialize_comentari(c) for c in rows])

    cos = (request.data.get("cos") or "").strip()
    if not cos:
        return Response({"error": "El comentari no pot estar buit."}, status=400)
    if len(cos) > 2000:
        return Response({"error": "Màxim 2 000 caràcters."}, status=400)

    c = Comentari.objects.create(publicacio=pub, autor=request.user, cos=cos)
    _enviar_notificacio_comentari(request, c)
    return Response(_serialize_comentari(c), status=201)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def comentari_esborrar(request: Request, pk: int) -> Response:
    from comptes.models import Comentari

    c = get_object_or_404(Comentari, pk=pk)
    # Author, post owner or staff can delete.
    if not (
        request.user.is_staff
        or request.user.pk == c.autor_id
        or request.user.pk == c.publicacio.autor_id
    ):
        return Response({"error": "No autoritzat."}, status=403)
    c.delete()
    return Response(status=204)
