"""The nightly Instagram-suggestion seeder.

The behaviour that matters most is the negative one: a handle the
operator dismissed with ✕ must never come back, whatever source keeps
publishing it.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from music.models import Album, Artista, Canco


def _artista(nom, **kw):
    a = Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=True, **kw)
    alb = Album.objects.create(
        artista=a, nom="X", data_llancament=date.today() - timedelta(days=3)
    )
    Canco.objects.create(
        artista=a,
        album=alb,
        nom=f"Viva {nom}",
        data_llancament=date.today() - timedelta(days=3),
        verificada=True,
        activa=True,
    )
    return a


@pytest.mark.django_db
def test_seeds_a_candidate_from_viasona():
    a = _artista("Innat")
    with patch(
        "ingesta.management.commands.suggerir_instagram._handles_de",
        return_value=["innatgrup"],
    ):
        call_command("suggerir_instagram", stdout=StringIO())
    a.refresh_from_db()
    assert a.instagram_suggerit == "innatgrup"


@pytest.mark.django_db
def test_never_resuggests_a_dismissed_handle():
    a = _artista("Sellen", instagram_suggerits_descartats=["john_sellen"])
    with patch(
        "ingesta.management.commands.suggerir_instagram._handles_de",
        return_value=["john_sellen"],
    ):
        call_command("suggerir_instagram", stdout=StringIO())
    a.refresh_from_db()
    assert a.instagram_suggerit == ""


@pytest.mark.django_db
def test_a_different_handle_can_still_be_suggested():
    """Dismissal bans the handle, not the artist: a better candidate from
    another source must still get through."""
    a = _artista("Güil", instagram_suggerits_descartats=["compte_dolent"])
    with patch(
        "ingesta.management.commands.suggerir_instagram._handles_de",
        return_value=["compte_dolent", "guil.musiq"],
    ):
        call_command("suggerir_instagram", stdout=StringIO())
    a.refresh_from_db()
    assert a.instagram_suggerit == "guil.musiq"
