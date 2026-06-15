"""Internal 1-to-1 messaging endpoints."""

from __future__ import annotations

from django.conf import settings as _settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import BloqueigUsuari, Missatge
from comptes.models import Usuari as _U
from web.api.compte_views._common import _DMSendThrottle

from ._common import _enviar_notificacio_missatge, _serialize_missatge


def _dm_block_reason(viewer, dest) -> str | None:
    """Return a Catalan reason string if `viewer` may NOT DM `dest`, else
    None. The admin support inbox is always reachable. A block in either
    direction, or the recipient's `accepta_dm=False`, denies the DM."""
    admin_username = getattr(_settings, "ADMIN_INBOX_USERNAME", "admin")
    if dest.username == admin_username:
        return None
    if BloqueigUsuari.objects.filter(
        Q(blocker=viewer, blocked=dest) | Q(blocker=dest, blocked=viewer)
    ).exists():
        return "No pots enviar missatges a aquest usuari."
    perfil = getattr(dest, "perfil", None)
    if perfil is not None and not perfil.accepta_dm:
        return "Aquest usuari no accepta missatges nous."
    return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def missatges_inbox(request: Request) -> Response:
    """Conversation list: latest message per other user, with unread counter."""
    viewer = request.user

    # Aggregate per "altre usuari": most recent message timestamp + unread count.
    qs = (
        Missatge.objects.filter(Q(remitent=viewer) | Q(destinatari=viewer))
        .filter(ocult=False)  # hidden-by-moderation messages are never served
        .select_related("remitent__perfil", "destinatari__perfil")
    )

    per_altre: dict[int, dict] = {}
    for m in qs.order_by("-created_at"):
        other_id = m.remitent_id if m.destinatari_id == viewer.pk else m.destinatari_id
        if other_id is None or other_id == viewer.pk:
            continue
        slot = per_altre.get(other_id)
        if slot is None:
            other = m.remitent if m.destinatari_id == viewer.pk else m.destinatari
            slot = {
                "altre": {
                    "pk": other.pk,
                    "username": other.username,
                    "nom_public": getattr(
                        getattr(other, "perfil", None), "nom_public", ""
                    ),
                    "imatge_url": getattr(
                        getattr(other, "perfil", None), "imatge_url", ""
                    ),
                },
                "darrer_missatge": _serialize_missatge(m, viewer),
                "no_llegits": 0,
            }
            per_altre[other_id] = slot
        # Count unread (only incoming + not yet read).
        if m.destinatari_id == viewer.pk and m.llegit_at is None:
            slot["no_llegits"] += 1

    converses = sorted(
        per_altre.values(),
        key=lambda x: x["darrer_missatge"]["created_at"] or "",
        reverse=True,
    )
    return Response(
        {
            "results": converses,
            "no_llegits_total": sum(c["no_llegits"] for c in converses),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def missatges_amb_usuari(request: Request, altre_pk: int) -> Response:
    """Thread of messages exchanged with `altre_pk`, oldest → newest.

    Marks all incoming-from-altre as read as a side effect.
    """
    viewer = request.user
    altre = get_object_or_404(_U, pk=altre_pk)
    if altre.pk == viewer.pk:
        return Response({"error": "No pots xatejar amb tu mateix."}, status=400)

    qs = (
        Missatge.objects.filter(
            (Q(remitent=viewer) & Q(destinatari=altre))
            | (Q(remitent=altre) & Q(destinatari=viewer))
        )
        .filter(ocult=False)  # hidden-by-moderation messages are never served
        .select_related("remitent__perfil", "destinatari__perfil")
        .order_by("created_at")
    )
    msgs = list(qs)
    Missatge.objects.filter(
        remitent=altre, destinatari=viewer, llegit_at__isnull=True
    ).update(llegit_at=timezone.now())

    return Response(
        {
            "altre": {
                "pk": altre.pk,
                "username": altre.username,
                "nom_public": getattr(getattr(altre, "perfil", None), "nom_public", ""),
                "imatge_url": getattr(getattr(altre, "perfil", None), "imatge_url", ""),
            },
            "missatges": [_serialize_missatge(m, viewer) for m in msgs],
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([_DMSendThrottle])
def missatge_crear(request: Request) -> Response:
    """Send a new message. Body: `{destinatari_pk, assumpte, cos}`."""
    viewer = request.user
    data = request.data or {}
    try:
        dest_pk = int(data.get("destinatari_pk"))
    except (TypeError, ValueError):
        return Response({"error": "Destinatari invàlid."}, status=400)
    if dest_pk == viewer.pk:
        return Response(
            {"error": "No pots enviar-te un missatge a tu mateix."}, status=400
        )
    destinatari = get_object_or_404(_U, pk=dest_pk)
    block_reason = _dm_block_reason(viewer, destinatari)
    if block_reason:
        return Response({"error": block_reason}, status=403)
    cos = (data.get("cos") or "").strip()
    if not cos:
        return Response({"error": "El missatge no pot estar buit."}, status=400)
    if len(cos) > 10000:
        return Response({"error": "Màxim 10 000 caràcters."}, status=400)
    assumpte = (data.get("assumpte") or "")[:200]

    m = Missatge.objects.create(
        remitent=viewer,
        destinatari=destinatari,
        assumpte=assumpte,
        cos=cos,
    )
    _enviar_notificacio_missatge(request, m)
    from analytics.events import register

    register("dm_enviat")  # Slice E: connection-funnel counter (no PII)
    return Response(_serialize_missatge(m, viewer), status=201)
