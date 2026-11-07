"""Staff ↔ user conversation, shown on a sol·licitud's detail page.

Comments on a proposal or a review request are just the DM thread
between the requester and the `admin` support inbox: staff write as
TopQuaranta (any staff member sees the replies, and a reply from the
user's normal inbox lands in the same thread and fans out to every staff
mail). No new model — the inbox, its mail heads-up and its moderation
already exist.

ponytail: messages are sent as `admin`, so which staff member wrote one
isn't recorded; add an author column if that ever matters.

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.community_bridge import _admin_user
from comptes.models import Missatge, Usuari
from web.api.comunitat_views._common import (
    _enviar_notificacio_missatge,
    _serialize_missatge,
)

from ._common import IsStaff


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsStaff])
def conversa(request: Request, pk: int) -> Response:
    """GET: thread admin ↔ user `pk`, oldest first (`meu` = sent by
    TopQuaranta). POST `{cos, assumpte?}`: send as TopQuaranta."""
    usuari = get_object_or_404(Usuari, pk=pk)
    admin = _admin_user()
    if request.method == "POST":
        data = request.data or {}
        cos = (data.get("cos") or "").strip()
        if not cos:
            return Response({"error": "El missatge no pot estar buit."}, status=400)
        if len(cos) > 10000:
            return Response({"error": "Màxim 10 000 caràcters."}, status=400)
        m = Missatge.objects.create(
            remitent=admin,
            destinatari=usuari,
            assumpte=(data.get("assumpte") or "")[:200],
            cos=cos,
        )
        _enviar_notificacio_missatge(request, m)
        return Response(_serialize_missatge(m, admin), status=201)

    msgs = (
        Missatge.objects.filter(
            Q(remitent=admin, destinatari=usuari)
            | Q(remitent=usuari, destinatari=admin)
        )
        .filter(ocult=False)
        .select_related("remitent__perfil", "destinatari__perfil")
        .order_by("created_at")
    )
    return Response({"missatges": [_serialize_missatge(m, admin) for m in msgs]})
