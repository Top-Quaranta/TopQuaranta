"""An inbox name is only trusted when it points at exactly one artist."""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command

from music.models import Artista
from social.models import SenyalDM


@pytest.mark.django_db
def test_nomes_es_desa_el_que_casa_amb_un_sol_artista_aprovat(tmp_path):
    bo = Artista.objects.create(nom="Durum Hawai", slug="durum-hawai", aprovat=True)
    Artista.objects.create(nom="Cor", slug="cor", aprovat=True)
    Artista.objects.create(nom="COR", slug="cor-2", aprovat=True)
    Artista.objects.create(nom="Descartat", slug="descartat", aprovat=False)
    f = tmp_path / "s.json"
    f.write_text(
        json.dumps(
            [
                ["DURUM HAWAI", 15, 5, 3, "2026-10-30"],
                ["Cor", 2, 0, 6, "2026-10-15"],
                ["Descartat", 1, 0, 0, ""],
                ["Ningú conegut", 1, 0, 0, ""],
            ]
        )
    )

    call_command("importar_senyals_dm", str(f))
    call_command("importar_senyals_dm", str(f))  # idempotent

    s = SenyalDM.objects.get()
    assert s.artista == bo
    assert (s.missatges, s.mencions, s.reaccions) == (15, 5, 3)
