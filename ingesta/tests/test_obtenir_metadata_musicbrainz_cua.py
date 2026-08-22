"""Qui entra a la rotació de MusicBrainz i qui no.

La promesa: el cron horari sincronitza el catàleg viu —aprovats primer,
pendents després, que és on l'oracle de desambiguació decideix res— i
no gasta ni una petició en artistes descartats.

El parany que guarda: els descartats només existeixen per integritat
d'FK, però són majoria (14.731 de 24.518 el 22/08/2026). Amb ells dins,
la cua no s'acaba mai: el 22/08 tot el catàleg viu estava fresc i el
cron passava l'hora sencera repassant rebutjats, s'allargava més enllà
de l'hora, el següent run saltava per lock i el watchdog cantava STUCK
cada matí.

# Spec: docs/architecture/ingesta.md
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from music.models import Artista


def _artista(nom, **estat):
    return Artista.objects.create(nom=nom, lastfm_nom=nom, **estat)


@pytest.mark.django_db
def test_la_rotacio_ignora_els_descartats():
    aprovat = _artista("Viu", aprovat=True)
    pendent = _artista("Per decidir", aprovat=False, pendent_review=True)
    _artista("Rebutjat", aprovat=False, pendent_review=False)

    def _fet(artista):
        # El que fa el `_process` real i que la cua mira per avançar.
        Artista.objects.filter(pk=artista.pk).update(mb_last_sync=timezone.now())
        return True

    with patch(
        "ingesta.management.commands.obtenir_metadata_musicbrainz.Command._process",
        side_effect=_fet,
    ) as proc:
        call_command("obtenir_metadata_musicbrainz")

    sincronitzats = [c.args[0].pk for c in proc.call_args_list]
    assert sincronitzats == [
        aprovat.pk,
        pendent.pk,
    ], "o s'ha colat un descartat, o s'ha perdut l'ordre aprovat → pendent"
