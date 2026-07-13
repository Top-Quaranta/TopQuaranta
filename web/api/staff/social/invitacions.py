"""IG collaborator invitations — staff registry list + manual acceptance.

  GET  /api/v1/staff/social/invitacions/          — full registry,
                                                    newest first
  POST /api/v1/staff/social/invitacions/acceptar/ — mark one invite
                                                    accepted (body: `id`)

ADR-0015 §5.5 definitive cycle (2026-07-13): acceptances are marked
manually when staff observes them in the Instagram app. There is
deliberately NO manual reject action — the automatic pendent→caducada
pass at 14 days covers silence and rejection alike (both are category
C with the 90-day cooldown to the policy).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from music.audit import log_staff_action
from social.models import InvitacioColaboracioIG
from web.api.staff._common import IsStaff


def _row(inv: InvitacioColaboracioIG) -> dict:
    return {
        "id": inv.id,
        "artista_id": inv.artista_id,
        "artista_nom": inv.artista.nom,
        "username": inv.username_snapshot,
        "ig_media_id": inv.ig_media_id,
        "tipus": inv.tipus_publicacio,
        "data_invitacio": inv.data_invitacio,
        "estat": inv.estat,
        "data_resolucio": inv.data_resolucio,
    }


@api_view(["GET"])
@permission_classes([IsStaff])
def social_invitacions(request: Request) -> Response:
    """The whole invitation registry, newest first. The registry grows
    by ≤3 rows per feed post (Meta's collaborator cap), so no
    pagination is needed."""
    rows = InvitacioColaboracioIG.objects.select_related("artista").order_by(
        "-data_invitacio", "-id"
    )
    return Response({"invitacions": [_row(i) for i in rows]})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_invitacio_acceptar(request: Request) -> Response:
    """Mark one invitation accepted (`estat=acceptada` +
    `data_resolucio=now`). Idempotent: accepting an already-accepted
    row returns it unchanged. Allowed from any other estat — if staff
    observes a real acceptance after the 14-day expiry, the observed
    truth wins over `caducada`."""
    try:
        pk = int(request.data.get("id"))
    except (TypeError, ValueError):
        return Response({"error": "invitació desconeguda"}, status=404)
    inv = (
        InvitacioColaboracioIG.objects.select_related("artista").filter(pk=pk).first()
    )
    if inv is None:
        return Response({"error": "invitació desconeguda"}, status=404)
    if inv.estat == InvitacioColaboracioIG.ESTAT_ACCEPTADA:
        return Response(_row(inv))
    anterior = inv.estat
    with transaction.atomic():
        inv.estat = InvitacioColaboracioIG.ESTAT_ACCEPTADA
        inv.data_resolucio = timezone.now()
        inv.save(update_fields=["estat", "data_resolucio"])
        log_staff_action(
            request,
            "collab_invitacio_acceptada",
            target=inv.artista,
            username=inv.username_snapshot,
            ig_media_id=inv.ig_media_id,
            anterior=anterior,
        )
    return Response(_row(inv))
