"""El correu diari reparteix feina, no només estat.

El descobriment automàtic ja ha passat per tot el catàleg: el que queda
del buit només el tanca una persona mirant vídeos i canals un per un. La
promesa d'aquest bloc és que eixa persona òbriga el correu i tinga deu
coses concretes per fer, amb la cerca escrita i el lloc on desar-ho — i
que la llista **es buide**: una tasca contestada no torna l'endemà.

El parany que guarda: una cua que no distingeix «ningú ho ha mirat» de
«mirat, no en té» repeteix les mateixes deu files per sempre, i un
correu que demana el mateix cada matí s'ignora al tercer dia.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime

import pytest

from music.models import Album, Artista, Canco, CancoYouTubeVideo, Territori
from ranking.models import SenyalDiari

AVUI = datetime.date(2026, 8, 19)


def _artista(nom, *, canal_topic="UC" + "x" * 22, revisat=False, terr="VAL"):
    t, _ = Territori.objects.get_or_create(codi=terr, defaults={"nom": terr})
    a = Artista.objects.create(
        nom=nom,
        lastfm_nom=nom,
        aprovat=True,
        youtube_channel_id=canal_topic,
        youtube_canal_revisat=revisat,
    )
    a.territoris.add(t)
    return a


def _canco(artista, nom, *, video="", dies=30, revisat=False):
    album, _ = Album.objects.get_or_create(
        artista=artista,
        nom="Disc",
        defaults={"data_llancament": AVUI - datetime.timedelta(days=30)},
    )
    return Canco.objects.create(
        artista=artista,
        album=album,
        nom=nom,
        data_llancament=AVUI - datetime.timedelta(days=dies),
        verificada=True,
        activa=True,
        youtube_video_id=video,
        youtube_revisat=revisat,
    )


def _veu_lastfm(canco):
    """Last.fm la veu: queda fora del punt cec."""
    SenyalDiari.objects.create(
        canco=canco, data=AVUI, lastfm_playcount=500, error=False
    )


def _accions(avui=AVUI):
    from analytics.management.commands.enviar_informe_youtube import build_context

    return build_context(avui)["accions"]


@pytest.mark.django_db
def test_a_blind_song_without_a_video_is_given_as_a_task():
    """El pitjor cas del catàleg: ni Last.fm ni YouTube la veuen.

    Mentre estiga així no pot entrar al top per cap via, i és l'única
    fila del correu que es resol amb un sol enllaç enganxat.
    """
    a = _artista("Els Cecs")
    c = _canco(a, "Ningú no la sent")

    files = _accions()["files"]
    meua = next(f for f in files if f["titol"] == "Ningú no la sent")
    assert meua["tipus"] == "canco"
    assert meua["on"] == f"/staff/cancons/{c.pk}"
    # La cerca ha de portar artista i títol: buscar només el títol torna
    # el món sencer, i el punt de la fila és que siga un clic.
    assert "Els+Cecs" in meua["cerca"] and "Ning" in meua["cerca"]


@pytest.mark.django_db
def test_an_answered_song_never_comes_back():
    """«Revisada: no en té» és una resposta vàlida i final.

    Sense això la cua no es buida mai: les cançons que de veres no són a
    YouTube tornarien cada matí fins que el correu s'ignore sencer.
    """
    a = _artista("Els Cecs")
    _canco(a, "No hi és", revisat=True)
    _canco(a, "Sí que hi és", video="abcdefghijk")

    titols = [f["titol"] for f in _accions()["files"]]
    assert "No hi és" not in titols, "una cançó contestada torna a la cua"
    assert "Sí que hi és" not in titols, "una cançó amb vídeo torna a la cua"


@pytest.mark.django_db
def test_a_song_measured_through_the_official_lane_is_not_a_task():
    """Hi ha dos carrils, i el mesurador compta amb qualsevol dels dos.

    `obtenir_senyal_youtube` fotografia una cançó si té Art Track **o**
    vídeo del canal propi. Mirar només l'Art Track posava a la llista
    cançons que ja s'estaven mesurant — feina inventada.
    """
    a = _artista("Amb videoclip")
    c = _canco(a, "Només al canal propi")
    CancoYouTubeVideo.objects.create(canco=c, video_id="zyxwvutsrqp", titol="clip")

    assert "Només al canal propi" not in [f["titol"] for f in _accions()["files"]]


@pytest.mark.django_db
def test_an_artist_with_no_channel_at_all_outranks_the_songs():
    """Un canal en desbloqueja diverses cançons; un vídeo, una.

    Si l'artista no té ni canal Topic ni resposta humana, cap cançó seua
    es pot mesurar: preguntar per una sola cançó seua seria demanar el
    treball petit havent-hi el gran.
    """
    fosc = _artista("Totalment fosc", canal_topic="")
    for i in range(3):
        _canco(fosc, f"Fosca {i}")
    clar = _artista("Amb Topic")
    _canco(clar, "Cega però mesurable")

    files = _accions()["files"]
    assert files[0]["titol"] == "Totalment fosc"
    assert files[0]["tipus"] == "artista"
    assert files[0]["on"] == "/staff/artistes/sense-youtube"
    # El perquè ha de portar el número que justifica l'ordre.
    assert "3" in files[0]["motiu"]


@pytest.mark.django_db
def test_the_own_channel_slot_never_dies_just_because_nobody_charted():
    """Ordenat per aparicions al top, no filtrat per elles.

    El 2026-08-19 els 172 artistes que havien estat al top ja tenien el
    canal revisat: la cua de staff s'ordena per `-n_top` i s'havia
    treballat per dalt. Exigir `n_top > 0` deixava aquest calaix mort
    per sempre — el correu no tornava a demanar un canal propi mai més.
    """
    a = _artista("Mai al top", revisat=False)
    _canco(a, "Una qualsevol")

    files = _accions()["files"]
    demanats = [f["titol"] for f in files if f["tipus"] == "artista"]
    assert "Mai al top" in demanats


@pytest.mark.django_db
def test_a_single_song_is_asked_about_in_the_singular():
    """«1 cançó que no es poden mesurar» delata que ningú llig el correu."""
    fosc = _artista("Només una", canal_topic="")
    _canco(fosc, "L'única")

    fila = next(f for f in _accions()["files"] if f["titol"] == "Només una")
    assert "1 cançó que ara mateix no es pot mesurar" in fila["motiu"]


@pytest.mark.django_db
def test_the_list_says_how_much_is_left_so_ten_rows_are_not_read_as_done():
    """Deu files sense el total es lligen com «ja estem»."""
    a = _artista("Molta faena")
    for i in range(14):
        _canco(a, f"Cançó {i}")

    ac = _accions()
    assert len(ac["files"]) == 10, "la llista d'un matí no pot ser infinita"
    assert ac["resten_cancons"] == 14


@pytest.mark.django_db
def test_songs_only_lastfm_sees_still_get_asked_about_last():
    """El farciment existeix, però va darrere del punt cec.

    Una cançó que Last.fm ja veu pot entrar al top avui; una cega, no.
    L'ordre entre elles és tota la diferència entre una llista útil i
    una llista de catàleg.
    """
    a = _artista("Barreja")
    vista = _canco(a, "Last.fm la veu", dies=1)
    _veu_lastfm(vista)
    _canco(a, "Ningú la veu", dies=300)

    titols = [f["titol"] for f in _accions()["files"]]
    assert titols.index("Ningú la veu") < titols.index("Last.fm la veu")


@pytest.mark.django_db
def test_no_demana_el_canal_dun_artista_encara_pendent():
    """Un artista sense decidir no genera feina de canal.

    Cas real del 22/08/2026: «Hores Extres» és verificada perquè els
    col·laboradors sí que estan aprovats, però l'artista principal
    —Sr. À— continua a la cua de pendents. El correu li demanava el
    canal i enviava a `/staff/artistes/sense-youtube`, que filtra
    `aprovat=1`: l'artista no hi apareixia i la fila tornava cada matí
    sense poder-se contestar. La cançó sí que és feina d'avui.
    """
    pendent = Artista.objects.create(
        nom="Sr. À", lastfm_nom="Sr. À", aprovat=False, pendent_review=True
    )
    _canco(pendent, "Hores Extres")

    ac = _accions()
    assert "Sr. À" not in [f["titol"] for f in ac["files"]]
    assert "Hores Extres" in [f["titol"] for f in ac["files"]]
    # I tampoc infla el compte del que queda per fer.
    assert ac["resten_artistes"] == 0
