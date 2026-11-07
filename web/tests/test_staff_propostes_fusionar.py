"""Fusionar una proposta amb un artista existent l'aprova.

La promesa: si l'staff fusiona una proposta humana amb un artista que
encara no està aprovat — pendent de revisió o descartat per la neteja
automàtica — i l'artista té ancoratge Deezer, l'artista queda aprovat.
La proposta no pot dir «aprovada» mentre l'artista continua fora
(sanrruu, 2026-11-07).
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from comptes.models import PropostaArtista, Usuari
from music.models import Artista, ArtistaDeezer


@pytest.mark.django_db
@pytest.mark.parametrize("pendent_review", [True, False], ids=["pendent", "descartat"])
def test_fusionar_aprova_l_artista_no_aprovat(pendent_review):
    staff = Usuari.objects.create_user(
        username="st", email="st@example.test", password="x", is_staff=True
    )
    proposant = Usuari.objects.create_user(
        username="pr", email="pr@example.test", password="x"
    )
    target = Artista.objects.create(
        nom="EXEMPLE Fus", aprovat=False, pendent_review=pendent_review
    )
    ArtistaDeezer.objects.create(artista=target, deezer_id=777, principal=True)
    p = PropostaArtista.objects.create(
        usuari=proposant, nom="EXEMPLE Fus", justificacio="x" * 30, deezer_ids=[777]
    )
    c = APIClient()
    c.force_authenticate(user=staff)
    r = c.post(
        f"/api/v1/staff/propostes/{p.pk}/fusionar/",
        {"artista_pk": target.pk},
        format="json",
    )
    assert r.status_code == 200
    target.refresh_from_db()
    assert target.aprovat and not target.pendent_review
