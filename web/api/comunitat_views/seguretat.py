"""Community safety endpoints (Slice A): block / unblock / report.

Member-facing trust-and-safety primitives. Staff resolution of reports
lives in `staff_moderacio.py`.
"""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import (
    BloqueigUsuari,
    Comentari,
    DenunciaUsuari,
    Missatge,
    Publicacio,
)
from comptes.models import Usuari as _U


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bloquejar(request: Request) -> Response:
    """Block a user. Body: `{usuari_pk}`. Idempotent."""
    viewer = request.user
    try:
        pk = int((request.data or {}).get("usuari_pk"))
    except (TypeError, ValueError):
        return Response({"error": "Usuari invàlid."}, status=400)
    if pk == viewer.pk:
        return Response({"error": "No pots bloquejar-te a tu mateix."}, status=400)
    target = get_object_or_404(_U, pk=pk)
    if target.username == getattr(settings, "ADMIN_INBOX_USERNAME", "admin"):
        return Response({"error": "No pots bloquejar el compte oficial."}, status=400)
    _, created = BloqueigUsuari.objects.get_or_create(blocker=viewer, blocked=target)
    if created:
        from analytics.events import register

        register("bloqueig_creat")  # Slice E (no PII)
    return Response({"ok": True, "blocked": pk}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def desbloquejar(request: Request) -> Response:
    """Unblock a user. Body: `{usuari_pk}`. Idempotent."""
    viewer = request.user
    try:
        pk = int((request.data or {}).get("usuari_pk"))
    except (TypeError, ValueError):
        return Response({"error": "Usuari invàlid."}, status=400)
    BloqueigUsuari.objects.filter(blocker=viewer, blocked_id=pk).delete()
    return Response({"ok": True, "unblocked": pk})


_TIPUS_RESOLVERS = {
    DenunciaUsuari.TIPUS_USUARI: (_U, "usuari_denunciat"),
    DenunciaUsuari.TIPUS_PUBLICACIO: (Publicacio, "publicacio"),
    DenunciaUsuari.TIPUS_COMENTARI: (Comentari, "comentari"),
    DenunciaUsuari.TIPUS_MISSATGE: (Missatge, "missatge"),
}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def denunciar(request: Request) -> Response:
    """Report a user, publication, comment or DM. Body:
    `{tipus, target_pk, motiu}`."""
    viewer = request.user
    data = request.data or {}
    tipus = (data.get("tipus") or "").strip()
    if tipus not in _TIPUS_RESOLVERS:
        return Response({"error": "Tipus de denúncia invàlid."}, status=400)
    try:
        target_pk = int(data.get("target_pk"))
    except (TypeError, ValueError):
        return Response({"error": "Objectiu invàlid."}, status=400)
    model, fk_field = _TIPUS_RESOLVERS[tipus]
    target = get_object_or_404(model, pk=target_pk)
    motiu = (data.get("motiu") or "").strip()[:2000]

    denuncia = DenunciaUsuari.objects.create(
        reporter=viewer,
        tipus=tipus,
        motiu=motiu,
        **{fk_field: target},
    )
    from analytics.events import register

    register("denuncia_creada", dim1=tipus)  # Slice E (no PII)
    return Response({"ok": True, "denuncia_id": denuncia.pk}, status=201)
