"""Feed artwork covers + the moviment tipus (2026-07).

Covers: duotone invariants; the no-regression pins (with the flags off
the covers never touch the duotone code and are byte-identical to the
explicit no-op params); the moviment selection rule; and the moviment
gate (flag off → no SocialPost row at all).
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from django.core.management import call_command
from PIL import Image

from social import duotone, feed_redesign, payload, top_redesign
from social.models import SocialPost

SM = datetime.date(2026, 6, 29)
THURSDAY = "2026-07-02"  # weekday() == 3
W, H = 1080, 1350


def _dummy_cover(color=(160, 110, 80)) -> Image.Image:
    return Image.new("RGB", (500, 500), color)


# ── duotone invariants ───────────────────────────────────────────────


def test_duotone_veil_stops_and_size():
    out = duotone.duotone_photo(_dummy_cover(), "rgb(250, 204, 21)", "#427c42", (W, H))
    assert out.size == (W, H) and out.mode == "RGBA"
    veil = duotone._veil((W, H))
    assert abs(veil.getpixel((W // 2, 0))[3] - round(0.66 * 255)) <= 1
    assert abs(veil.getpixel((W // 2, int(H * 0.43)))[3] - round(0.16 * 255)) <= 1
    assert abs(veil.getpixel((W // 2, H - 1))[3] - round(0.72 * 255)) <= 1


def test_duotone_mosaic_needs_two():
    with pytest.raises(ValueError):
        duotone.duotone_mosaic([_dummy_cover()], "rgb(250,204,21)", "#3a5a34", (W, H))


def test_duotone_mosaic_grid_shape():
    assert duotone._grid_shape(4) == (2, 2, 4)
    assert duotone._grid_shape(5) == (2, 2, 4)
    assert duotone._grid_shape(6) == (2, 3, 6)
    assert duotone._grid_shape(9) == (2, 3, 6)


# ── no-regression: flags off → untouched ─────────────────────────────


def test_top_cover_default_never_calls_duotone():
    """The default (flag-off) cover must not invoke the artwork code and
    must be byte-identical to the explicit no-op params."""
    with patch("social.duotone.duotone_photo", side_effect=AssertionError("called")):
        img = top_redesign.build_top_cover(SM, "ppcc")
    assert img.size == (W, H)
    assert (
        top_redesign.build_top_cover(SM, "ppcc").tobytes()
        == top_redesign.build_top_cover(SM, "ppcc", artwork=None, credit=None).tobytes()
    )


def test_novetats_cover_default_never_calls_duotone():
    with patch("social.duotone.duotone_mosaic", side_effect=AssertionError("called")):
        img = feed_redesign.build_cover("nous_albums", SM)
    assert img.size == (W, H)
    assert (
        feed_redesign.build_cover("nous_albums", SM).tobytes()
        == feed_redesign.build_cover("nous_albums", SM, covers=None).tobytes()
    )


# ── artwork path renders + credit truncation ─────────────────────────


def test_top_cover_artwork_differs_and_renders():
    default = top_redesign.build_top_cover(SM, "ppcc").tobytes()
    art = top_redesign.build_top_cover(
        SM, "ppcc", artwork=_dummy_cover(), credit=("Nº1", "Rosalía", "Divinize")
    )
    assert art.size == (W, H)
    assert art.tobytes() != default


def test_credit_megacollab_truncates_without_error():
    long_artist = ", ".join(f"Artista {i}" for i in range(40))
    img = top_redesign.build_top_cover(
        SM,
        "VAL",
        artwork=_dummy_cover(),
        credit=("Nº1", long_artist, "La Gent de la Mediterrània"),
    )
    assert img.size == (W, H)


def test_moviment_cover_renders_both_kinds():
    puja = {
        "kind": "pujada",
        "pos": 10,
        "pos_ant": 38,
        "delta": 28,
        "artist": "Maria Jaume",
        "title": "Es Teus Besos",
        "phrase": "del 38 al 10",
        "reentrada": False,
    }
    entr = {
        "kind": "entrada",
        "pos": 2,
        "pos_ant": None,
        "delta": None,
        "artist": "The Tyets",
        "title": "Era Això!",
        "phrase": "directa al 2",
        "reentrada": False,
    }
    for sel in (puja, entr):
        img = top_redesign.build_moviment_cover(SM, sel, artwork=_dummy_cover())
        assert img.size == (W, H)
    # renders even without artwork (plain global field fallback)
    assert top_redesign.build_moviment_cover(SM, puja, artwork=None).size == (W, H)


# ── moviment selection ───────────────────────────────────────────────


def _entry(pos, pos_ant, *, re=False, nom="C", artist="A", dz=1):
    return {
        "posicio": pos,
        "posicio_anterior": pos_ant,
        "reentrada": re,
        "canco_nom": nom,
        "artistes_noms": [artist],
        "artista_nom": artist,
        "cover_url": None,
        "album_deezer_id": dz,
    }


def test_moviment_entry_top10_wins_over_rise():
    entries = [
        _entry(1, 1),
        _entry(2, None, nom="Era Això!", artist="The Tyets"),
        _entry(10, 38, nom="Es Teus Besos", artist="Maria Jaume"),
    ]
    with patch("social.payload.build_top", return_value={"entries": entries}):
        sel = payload.build_moviment(SM, 5)
    assert sel["kind"] == "entrada"
    assert sel["pos"] == 2 and sel["title"] == "Era Això!"
    assert sel["phrase"] == "directa al 2"


def test_moviment_rise_when_no_top10_entry():
    entries = [
        _entry(1, 1),
        _entry(17, 31, nom="Sant Domingo Forever", artist="Maria Jaume"),
        _entry(19, None, nom="new outside top10"),  # new but pos > 10
    ]
    with patch("social.payload.build_top", return_value={"entries": entries}):
        sel = payload.build_moviment(SM, 5)
    assert sel["kind"] == "pujada" and sel["delta"] == 14
    assert sel["phrase"] == "del 31 al 17"


def test_moviment_rise_below_min_omits():
    entries = [_entry(1, 1), _entry(10, 12)]  # rise of 2 < 5
    with patch("social.payload.build_top", return_value={"entries": entries}):
        assert payload.build_moviment(SM, 5) is None


def test_moviment_no_data_returns_none():
    with patch("social.payload.build_top", return_value=None):
        assert payload.build_moviment(SM, 5) is None


# ── moviment gate at the command ─────────────────────────────────────


@pytest.fixture
def cfg(db):
    from ranking.models import ConfiguracioGlobal

    c = ConfiguracioGlobal.load()
    c.distribucio_activa = True
    c.instagram_actiu = True
    c.save()
    return c


def test_moviment_flag_off_creates_no_row(cfg):
    assert not cfg.moviment_actiu  # default
    call_command(
        "publicar_social",
        "--data",
        THURSDAY,
        "--tipus",
        "moviment",
        "--platform",
        "instagram_feed",
    )
    assert not SocialPost.objects.filter(tipus=SocialPost.TIPUS_MOVIMENT).exists()


def test_moviment_flag_on_no_content_omits(cfg):
    cfg.moviment_actiu = True
    cfg.save()
    with patch("social.payload.build_moviment", return_value=None):
        call_command(
            "publicar_social",
            "--data",
            THURSDAY,
            "--tipus",
            "moviment",
            "--platform",
            "instagram_feed",
        )
    post = SocialPost.objects.get(tipus=SocialPost.TIPUS_MOVIMENT)
    assert post.status == SocialPost.STATUS_OMES
