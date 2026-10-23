"""La finestra de `build_novetats`: cursor d'ingesta, no de data d'estrena.

Spec: docs/architecture/social.md §Novetats
"""

from __future__ import annotations

import datetime
import itertools

import pytest
from django.utils import timezone

from music.models import Album, Artista, Canco
from social.models import SocialPost
from social.payload import build_novetats

DIVENDRES = datetime.date(2026, 9, 11)
_DZ = itertools.count(900001)


def _aware(d: datetime.date, h: int, m: int = 0):
    return timezone.make_aware(
        datetime.datetime(d.year, d.month, d.day, h, m),
        timezone.get_default_timezone(),
    )


def _llancament(nom, *, estrena, ingerit, tipus="single"):
    a = Artista.objects.create(nom=f"A{nom}", lastfm_nom=f"A{nom}", aprovat=True)
    alb = Album.objects.create(
        artista=a, nom=nom, tipus=tipus, data_llancament=estrena, deezer_id=next(_DZ)
    )
    Canco.objects.create(
        artista=a,
        album=alb,
        nom=nom,
        data_llancament=estrena,
        verificada=True,
        activa=True,
    )
    # `created_at` és auto_now_add: el reescrivim per a situar la ingesta.
    Album.objects.filter(pk=alb.pk).update(created_at=ingerit)
    return alb


def _post_publicat(tipus, quan):
    p = SocialPost.objects.create(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
        tipus=tipus,
        setmana=DIVENDRES - datetime.timedelta(days=DIVENDRES.weekday()),
        status=SocialPost.STATUS_PUBLICAT,
    )
    SocialPost.objects.filter(pk=p.pk).update(published_at=quan)
    return p


def _noms(payload):
    return {i["nom"] for i in (payload or {}).get("items", [])}


@pytest.mark.django_db
class TestFinestraNovetats:
    def test_una_estrena_ingerida_despres_del_post_ix_al_seguent(self):
        """La promesa. «Flama», de Marta Shanti: estrena el divendres
        11/09, post de nous_singles publicat eixe matí a les 10:01,
        àlbum ingerit a les 16:13. Amb la finestra sobre `data_llancament`
        i el tall a «publicació anterior + 1 dia», no podia eixir mai:
        el 18/09 la seua data d'estrena ja quedava darrere del tall.
        Amb el cursor d'ingesta ix al primer post posterior a la
        ingesta, que és el que vol dir «novetat»."""
        _post_publicat("nous_singles", _aware(DIVENDRES, 10, 1))
        _llancament("Flama", estrena=DIVENDRES, ingerit=_aware(DIVENDRES, 16, 13))

        seguent = DIVENDRES + datetime.timedelta(days=7)
        assert "Flama" in _noms(
            build_novetats("nous_singles", seguent, publish_date=seguent)
        )

    def test_no_es_pot_anunciar_dues_vegades(self):
        """L'altra cara: el cursor avança i el que ja va eixir no torna."""
        _post_publicat("nous_singles", _aware(DIVENDRES, 10, 1))
        _llancament("Vella", estrena=DIVENDRES, ingerit=_aware(DIVENDRES, 9, 0))

        seguent = DIVENDRES + datetime.timedelta(days=7)
        assert "Vella" not in _noms(
            build_novetats("nous_singles", seguent, publish_date=seguent)
        )

    def test_una_importacio_tardana_no_es_una_novetat(self):
        """Un àlbum de fa dos mesos que arriba avui al catàleg és feina
        de catàleg, no una estrena («La Guardiola Groga», 18/07 estrenat,
        18/09 ingerit)."""
        _post_publicat("nous_singles", _aware(DIVENDRES, 10, 1))
        _llancament(
            "Antiga",
            estrena=DIVENDRES - datetime.timedelta(days=60),
            ingerit=_aware(DIVENDRES, 16, 0),
        )

        seguent = DIVENDRES + datetime.timedelta(days=7)
        assert "Antiga" not in _noms(
            build_novetats("nous_singles", seguent, publish_date=seguent)
        )

    def test_el_cursor_es_per_tipus(self):
        """Publicar àlbums no ha de moure el cursor dels singles."""
        _post_publicat("nous_albums", _aware(DIVENDRES, 10, 1))
        _llancament("Single", estrena=DIVENDRES, ingerit=_aware(DIVENDRES, 16, 13))

        seguent = DIVENDRES + datetime.timedelta(days=3)
        assert "Single" in _noms(
            build_novetats("nous_singles", seguent, publish_date=seguent)
        )

    def test_primera_execucio_sense_historial(self):
        _llancament(
            "Primera",
            estrena=DIVENDRES,
            ingerit=_aware(DIVENDRES, 16, 13),
        )
        seguent = DIVENDRES + datetime.timedelta(days=2)
        assert "Primera" in _noms(
            build_novetats("nous_singles", seguent, publish_date=seguent)
        )


@pytest.mark.django_db
class TestAnunciatAt:
    def test_una_publicacio_segella_el_que_ha_portat(self):
        from social.payload import marca_anunciats

        alb = _llancament("Nou", estrena=DIVENDRES, ingerit=_aware(DIVENDRES, 16, 0))
        assert alb.anunciat_at is None
        marca_anunciats([{"album_id": alb.pk}])
        alb.refresh_from_db()
        assert alb.anunciat_at is not None

    def test_qui_mana_es_la_primera_vegada(self):
        """Una republicació no ha de reescriure la data en què el públic
        ho va vore."""
        from social.payload import marca_anunciats

        alb = _llancament("Nou", estrena=DIVENDRES, ingerit=_aware(DIVENDRES, 16, 0))
        marca_anunciats([{"album_id": alb.pk}], quan=_aware(DIVENDRES, 10, 0))
        marca_anunciats([{"album_id": alb.pk}], quan=_aware(DIVENDRES, 18, 0))
        alb.refresh_from_db()
        assert alb.anunciat_at == _aware(DIVENDRES, 10, 0)

    def test_un_top_no_segella_res(self):
        """El payload d'un top porta `entries`, no `items`."""
        from social.payload import marca_anunciats

        assert marca_anunciats(None) == 0
        assert marca_anunciats([{"canco_id": 1, "posicio": 1}]) == 0

    def test_un_album_ja_anunciat_no_torna_encara_que_el_cursor_l_agafe(self):
        """El cursor diu quina finestra toca; `anunciat_at` diu si això ja
        va eixir mai. Si el cursor recula —republicació, re-execució a mà,
        un arreglo de dades— el segell ho atura igual."""
        alb = _llancament("Ja", estrena=DIVENDRES, ingerit=_aware(DIVENDRES, 16, 0))
        Album.objects.filter(pk=alb.pk).update(anunciat_at=_aware(DIVENDRES, 18, 0))

        seguent = DIVENDRES + datetime.timedelta(days=2)
        assert "Ja" not in _noms(
            build_novetats("nous_singles", seguent, publish_date=seguent)
        )
