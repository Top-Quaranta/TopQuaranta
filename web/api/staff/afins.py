"""Staff read-only view: artists with a track record of engaging with us.

Nothing is stored here. Every column is counted from a table that
already records the interaction (collab invitations, story probes,
managers, proposals), so the view can never drift from them.

# Spec: docs/architecture/web.md
"""

from __future__ import annotations

from django.db.models import Count, Max
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import PropostaArtista, UserArtista
from music.models import Artista
from social.models import InvitacioColaboracioIG, SondaStoryIG
from web.api.staff._common import IsStaff


@api_view(["GET"])
@permission_classes([IsStaff])
def artistes_afins(request: Request) -> Response:
    """Artists with at least one positive signal, strongest first."""
    acceptades = {
        r["artista"]: r
        for r in InvitacioColaboracioIG.objects.filter(
            estat=InvitacioColaboracioIG.ESTAT_ACCEPTADA
        )
        .values("artista")
        .annotate(n=Count("pk"), ultima=Max("data_invitacio"))
    }
    reaccions = dict(
        SondaStoryIG.objects.filter(reaccio_auto=True)
        .values_list("artista")
        .annotate(n=Count("pk"))
    )
    gestors = set(
        UserArtista.objects.filter(estat=UserArtista.ESTAT_APROVAT).values_list(
            "artista_id", flat=True
        )
    )
    proposats = set(
        PropostaArtista.objects.filter(
            estat=PropostaArtista.ESTAT_APROVAT, artista_creat__isnull=False
        ).values_list("artista_creat_id", flat=True)
    )
    ids = set(acceptades) | set(reaccions) | gestors | proposats
    # Invitations sent, so "2 of 2 accepted" reads differently from "2 of 9".
    convidades = dict(
        InvitacioColaboracioIG.objects.filter(artista__in=ids)
        .values_list("artista")
        .annotate(n=Count("pk"))
    )

    files = []
    for a in Artista.objects.filter(pk__in=ids).only(
        "pk", "nom", "slug", "aprovat", "instagram_url"
    ):
        acc = acceptades.get(a.pk)
        files.append(
            {
                "pk": a.pk,
                "nom": a.nom,
                "slug": a.slug,
                "aprovat": a.aprovat,
                "instagram_url": a.instagram_url,
                "collabs_acceptades": acc["n"] if acc else 0,
                "collabs_convidades": convidades.get(a.pk, 0),
                "ultima_collab": acc["ultima"].date().isoformat() if acc else None,
                "reaccions_sonda": reaccions.get(a.pk, 0),
                "te_gestor": a.pk in gestors,
                "proposat_per_usuari": a.pk in proposats,
            }
        )
    files.sort(
        key=lambda f: (
            -f["collabs_acceptades"],
            not f["te_gestor"],
            -f["reaccions_sonda"],
            f["nom"].lower(),
        )
    )
    return Response({"results": files})
