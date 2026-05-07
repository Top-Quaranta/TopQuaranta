"""Staff-only moderation endpoints for publications + directori."""

from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import PerfilUsuari, Publicacio
from web.api.search_utils import normalize_search_term, unaccent_field
from web.api.staff_views import IsStaff
from web.api.utils import paginate

from ._common import _serialize_publicacio


@api_view(["GET"])
@permission_classes([IsStaff])
def staff_publicacions(request: Request) -> Response:
    qs = Publicacio.objects.select_related("autor", "autor__perfil")
    estat = request.GET.get("estat", "pendent")
    if estat in {k for k, _ in Publicacio.ESTAT_CHOICES}:
        qs = qs.filter(estat=estat)
    q = (request.GET.get("q") or "").strip()
    if q:
        nq = normalize_search_term(q)
        qs = qs.annotate(
            _titol_norm=unaccent_field("titol"),
            _cos_norm=unaccent_field("cos"),
            _user_norm=unaccent_field("autor__username"),
            _email_norm=unaccent_field("autor__email"),
        ).filter(
            Q(_titol_norm__contains=nq)
            | Q(_cos_norm__contains=nq)
            | Q(_user_norm__contains=nq)
            | Q(_email_norm__contains=nq)
        )
    qs = qs.order_by("-created_at")
    page, meta = paginate(qs, request, default=25, cap=100)
    return Response(
        {
            "results": [
                _serialize_publicacio(p, for_staff=True) for p in page.object_list
            ],
            **meta,
            "estat_choices": list(Publicacio.ESTAT_CHOICES),
        }
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def staff_publicacio_decidir(request: Request, pk: int) -> Response:
    """Publish, reject or unpublish a publication.

    Body: {action: "publicar" | "rebutjar" | "despublicar", notes_staff?}.
    """
    pub = get_object_or_404(Publicacio, pk=pk)
    data = request.data or {}
    action = (data.get("action") or "").strip()
    notes = (data.get("notes_staff") or "").strip()

    if action == "publicar":
        pub.estat = Publicacio.ESTAT_PUBLICAT
        pub.publicat_at = pub.publicat_at or timezone.now()
    elif action == "rebutjar":
        pub.estat = Publicacio.ESTAT_REBUTJAT
        pub.publicat_at = None
    elif action == "despublicar":
        pub.estat = Publicacio.ESTAT_ESBORRANY
        pub.publicat_at = None
    else:
        return Response({"error": "Acció no vàlida."}, status=400)

    pub.notes_staff = notes
    pub.save()
    return Response(_serialize_publicacio(pub, for_staff=True))


@api_view(["GET"])
@permission_classes([IsStaff])
def staff_directori_usuaris(request: Request) -> Response:
    """Staff view over every PerfilUsuari regardless of visible_directori."""
    qs = (
        PerfilUsuari.objects.select_related("usuari", "localitat")
        .annotate(n_publicacions=Count("usuari__publicacions"))
        .order_by("usuari__username")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        nq = normalize_search_term(q)
        qs = qs.annotate(
            _user_norm=unaccent_field("usuari__username"),
            _email_norm=unaccent_field("usuari__email"),
            _nom_norm=unaccent_field("nom_public"),
        ).filter(
            Q(_user_norm__contains=nq)
            | Q(_email_norm__contains=nq)
            | Q(_nom_norm__contains=nq)
        )
    visible = request.GET.get("visible", "")
    if visible == "1":
        qs = qs.filter(visible_directori=True)
    elif visible == "0":
        qs = qs.filter(visible_directori=False)

    page, meta = paginate(qs, request, default=30, cap=100)
    rows = []
    for p in page.object_list:
        loc = p.localitat
        rows.append(
            {
                "usuari_id": p.usuari_id,
                "username": p.usuari.username,
                "email": p.usuari.email,
                "nom_public": p.nom_public,
                "rol_musical": p.rol_musical,
                "obert_colaboracions": p.obert_colaboracions,
                "visible_directori": p.visible_directori,
                "onboarding_complet": p.onboarding_complet,
                "localitat": (
                    f"{loc.nom}, {loc.comarca} ({loc.territori_id})" if loc else ""
                ),
                "n_publicacions": p.n_publicacions,
                "is_staff": p.usuari.is_staff,
                "is_active": p.usuari.is_active,
            }
        )
    return Response({"results": rows, **meta})


@api_view(["POST"])
@permission_classes([IsStaff])
def staff_directori_toggle_visible(request: Request, usuari_id: int) -> Response:
    p = get_object_or_404(PerfilUsuari, usuari_id=usuari_id)
    p.visible_directori = not p.visible_directori
    p.save(update_fields=["visible_directori", "updated_at"])
    return Response({"usuari_id": usuari_id, "visible_directori": p.visible_directori})
