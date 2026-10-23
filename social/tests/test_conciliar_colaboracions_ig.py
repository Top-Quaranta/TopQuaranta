"""`conciliar_colaboracions_ig` — llegir del post qui ha acceptat.

Spec: docs/architecture/social.md §Instagram tagging, handles, collaborators
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from music.models import Artista
from ranking.models import ConfiguracioGlobal
from social.management.commands import conciliar_colaboracions_ig as cmd
from social.models import InvitacioColaboracioIG as I

# MOCK — reprodueix l'estructura de `instagram.com/p/<codi>/embed/captioned/`
# tal com la serveix Instagram el 2026-09-26: capçalera amb els co-autors,
# després el comptador de seguidors i, molt més avall, el peu de foto amb
# els artistes mencionats amb @.
_EMBED = """<html><head><title>x</title><style>.a{{color:red}}</style></head><body>
<script>window.__d=1;</script>
<div class="EmbedTitle">Instagram</div>
<div class="Header">{capcal}</div>
<div class="Followers">835 followers</div>
<div class="Profile">topquaranta 226 posts</div>
<div class="Caption">topquaranta {peu}</div>
</body></html>"""


def _embed(capcal: str, peu: str = "") -> str:
    return _EMBED.format(capcal=capcal, peu=peu)


@pytest.fixture
def cfg(db):
    return ConfiguracioGlobal.objects.create(pk=1, ig_collaboradors_actiu=True)


def _inv(username, *, estat=I.ESTAT_CADUCADA, media="1800000000000000", dies=3):
    a = Artista.objects.create(nom=username, lastfm_nom=username, aprovat=True)
    return I.objects.create(
        artista=a,
        username_snapshot=username,
        ig_media_id=media,
        tipus_publicacio="nous_singles",
        data_invitacio=timezone.now() - timedelta(days=dies),
        estat=estat,
        data_resolucio=(
            timezone.now() - timedelta(days=dies) if estat != I.ESTAT_PENDENT else None
        ),
    )


def _run(html, **kw):
    with (
        patch.object(
            cmd.ig, "permalink", return_value="https://www.instagram.com/p/AB/"
        ),
        patch.object(cmd, "_descarrega", return_value=html),
        patch.object(cmd, "PAUSA_S", 0),
    ):
        out = StringIO()
        call_command("conciliar_colaboracions_ig", stdout=out, **kw)
        return out.getvalue()


@pytest.mark.django_db
class TestConciliar:
    def test_un_coautor_a_la_capcalera_es_una_acceptacio(self, cfg):
        inv = _inv("cantautoret")
        _run(_embed("topquaranta and cantautoret"))
        inv.refresh_from_db()
        assert inv.estat == I.ESTAT_ACCEPTADA
        assert inv.data_resolucio is not None

    def test_una_mencio_al_peu_de_foto_NO_es_una_acceptacio(self, cfg):
        """La promesa que més importa. L'artista convidat surt mencionat al
        peu del mateix post al qual el vam convidar, sempre. Si el lector
        mirara la pàgina sencera, TOTA invitació constaria acceptada i el
        registre seria soroll amb forma de dada."""
        inv = _inv("cantautoret")
        _run(_embed("topquaranta", peu="Nou single de @cantautoret, escolteu-lo!"))
        inv.refresh_from_db()
        assert inv.estat == I.ESTAT_CADUCADA

    def test_sense_coautor_no_toca_res(self, cfg):
        inv = _inv("cantautoret", estat=I.ESTAT_PENDENT)
        _run(_embed("topquaranta"))
        inv.refresh_from_db()
        assert inv.estat == I.ESTAT_PENDENT

    def test_una_pagina_illegible_mai_es_un_rebuig(self, cfg):
        """Sense capçalera no sabem res, i no saber res no és que hagen
        dit que no. L'ordre té una sola transició."""
        inv = _inv("cantautoret", estat=I.ESTAT_PENDENT)
        _run("<html><body>res</body></html>")
        inv.refresh_from_db()
        assert inv.estat == I.ESTAT_PENDENT

    def test_nomes_confirma_qui_haviem_convidat(self, cfg):
        """El capçal porta un co-autor que no vam convidar en aquest post:
        no inventem una invitació ni toquem la que sí que hi és."""
        inv = _inv("cantautoret", estat=I.ESTAT_PENDENT)
        _run(_embed("topquaranta and unaltrecompte"))
        inv.refresh_from_db()
        assert inv.estat == I.ESTAT_PENDENT
        assert I.objects.count() == 1

    def test_un_handle_que_es_prefix_d_un_altre_no_compta(self, cfg):
        inv = _inv("bocc", estat=I.ESTAT_PENDENT)
        _run(_embed("topquaranta and boccofdoom"))
        inv.refresh_from_db()
        assert inv.estat == I.ESTAT_PENDENT

    def test_dry_run_no_escriu(self, cfg):
        inv = _inv("cantautoret")
        sortida = _run(_embed("topquaranta and cantautoret"), **{"dry_run": True})
        inv.refresh_from_db()
        assert inv.estat == I.ESTAT_CADUCADA
        assert "dry-run" in sortida

    def test_el_flag_mestre_apaga_l_ordre(self, db):
        ConfiguracioGlobal.objects.create(pk=1, ig_collaboradors_actiu=False)
        inv = _inv("cantautoret")
        _run(_embed("topquaranta and cantautoret"))
        inv.refresh_from_db()
        assert inv.estat == I.ESTAT_CADUCADA

    def test_una_capcalera_truncada_es_diu_en_veu_alta(self, cfg):
        """«and 2 others» amaga noms: el que es veu es confirma, i la resta
        queda sense confirmar amb un avís, no silenciosament."""
        vist = _inv("cantautoret", estat=I.ESTAT_PENDENT)
        amagat = _inv("sr.corella", estat=I.ESTAT_PENDENT)
        sortida = _run(_embed("topquaranta, cantautoret and 2 others"))
        vist.refresh_from_db()
        amagat.refresh_from_db()
        assert vist.estat == I.ESTAT_ACCEPTADA
        assert amagat.estat == I.ESTAT_PENDENT
        assert "truncades: 1" in sortida


class TestCapcalera:
    """La funció pura, sense DB."""

    def test_separa_capcalera_de_peu(self):
        h = _embed("topquaranta and tesaaltesa", peu="amb @sr.corella")
        assert cmd._capcalera(h) == "topquaranta and tesaaltesa"

    def test_sense_capcalera_torna_none(self):
        assert cmd._capcalera("<html><body>res</body></html>") is None

    def test_un_punt_al_handle_no_es_un_comodi(self):
        trobats, _ = cmd._coautors(_embed("topquaranta and srxcorella"), {"sr.corella"})
        assert trobats == set()
