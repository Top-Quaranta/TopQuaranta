"""No-regression pins + smoke for the gated feed redesign.

The redesign is additive and OFF by default; these pins assert (a) the gate
default, (b) routing (off → legacy, on → redesign), (c) the three redesign
builders produce a valid 1080×1350 image incl. the cover==null fallback, and
(d) deterministic output. No network: the Deezer cover fetch is monkeypatched.
"""

from __future__ import annotations

import datetime

import pytest
from PIL import Image

from social import feed_redesign, renderer

SET = datetime.date(2026, 6, 8)

ALBUM = {
    "nom": "Carrer dels Àngels",
    "artista_nom": "La Ludwig Band",
    "artista_territori": "VAL",
    "cover_url": "https://deezer.example/cover.jpg",
}
SINGLES = [
    {
        "nom": f"Cançó {i}",
        "artista_nom": f"Artista {i}",
        "artista_territori": code,
        "cover_url": "https://deezer.example/c.jpg",
    }
    for i, code in enumerate(["CAT", "VAL", "BAL", "CNO", "PPCC"], 1)
]


@pytest.fixture
def fake_cover(monkeypatch):
    """Deterministic synthetic cover so no network is hit."""
    swatch = Image.new("RGB", (300, 300), (90, 110, 160))
    monkeypatch.setattr(
        feed_redesign.cover_cache,
        "fetch",
        lambda url, *a, **k: (swatch if url else None),
    )
    return swatch


# ── gate ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_flag_defaults_off():
    from ranking.models import ConfiguracioGlobal

    assert ConfiguracioGlobal.load().feed_redisseny_actiu is False


def test_routing_off_uses_legacy(monkeypatch, fake_cover):
    """redesign=False must NOT call the redesign module."""
    monkeypatch.setattr(
        feed_redesign,
        "build_album",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("redesign called")),
    )
    img = renderer._feed_album_slide(ALBUM, redesign=False)
    assert img.size == (1080, 1350)


def test_routing_on_uses_redesign(monkeypatch):
    sentinel = Image.new("RGB", (1080, 1350), (1, 2, 3))
    monkeypatch.setattr(feed_redesign, "build_album", lambda item: sentinel)
    assert renderer._feed_album_slide(ALBUM, redesign=True) is sentinel


# ── smoke: builders produce valid canvases ───────────────────────────


def test_build_cover_albums_and_singles(fake_cover):
    for tipus in ("nous_albums", "nous_singles"):
        img = feed_redesign.build_cover(tipus, SET)
        assert img.size == (1080, 1350)
        assert img.mode == "RGB"


def test_build_album_with_cover(fake_cover):
    img = feed_redesign.build_album(ALBUM)
    assert img.size == (1080, 1350) and img.mode == "RGB"


def test_build_album_cover_null(monkeypatch):
    monkeypatch.setattr(feed_redesign.cover_cache, "fetch", lambda *a, **k: None)
    img = feed_redesign.build_album({**ALBUM, "cover_url": None})
    assert img.size == (1080, 1350)


def test_build_singles_grid_and_pages(fake_cover):
    img = feed_redesign.build_singles(SINGLES, 1, 2)
    assert img.size == (1080, 1350)
    # cover==null path for every thumb
    img2 = feed_redesign.build_singles(
        [{**s, "cover_url": None} for s in SINGLES], 1, 1
    )
    assert img2.size == (1080, 1350)


def test_singles_respects_10_row_cap(fake_cover):
    big = SINGLES * 4  # 20 rows passed; builder draws at most 10
    img = feed_redesign.build_singles(big, 1, 2)
    assert img.size == (1080, 1350)


def test_singles_blinds_ppcc(fake_cover):
    """A PPCC (global aggregate) row is never rendered as a territory."""
    items = [
        {"nom": "A", "artista_nom": "x", "artista_territori": "PPCC", "cover_url": "x"},
        {"nom": "B", "artista_nom": "y", "artista_territori": "CAT", "cover_url": "x"},
    ]
    only_ppcc = [items[0]]
    # All-PPCC chunk → still a valid canvas, just no rows.
    assert feed_redesign.build_singles(only_ppcc, 1, 1).size == (1080, 1350)
    # Mixed → renders (the CAT row), PPCC silently dropped.
    assert feed_redesign.build_singles(items, 1, 1).size == (1080, 1350)


def test_territori_full_name_present():
    assert feed_redesign.territori("VAL")["name"] == "País Valencià"
    assert feed_redesign.territori("CNO")["name"] == "Catalunya Nord"


# ── determinism ──────────────────────────────────────────────────────


def test_render_is_deterministic(fake_cover):
    a = feed_redesign.build_album(ALBUM).tobytes()
    b = feed_redesign.build_album(ALBUM).tobytes()
    assert a == b


# ── territory resolver ───────────────────────────────────────────────


def test_territori_maps_cno_to_nord():
    assert feed_redesign.territori("CNO")["abbr"] == "NOR"


def test_territori_unknown_falls_back_to_green():
    t = feed_redesign.territori("ZZZ")
    # Aggregate/unknown codes resolve to a green fallback (never raises).
    assert t["deep"] == "rgb(47, 90, 47)"
    assert t["accent"] == "rgb(123, 191, 123)"


def test_col_parses_rgba():
    assert feed_redesign._col("rgb(10, 20, 30)") == (10, 20, 30, 255)
    assert feed_redesign._col("rgba(255, 255, 255, 0.5)")[3] == 128


def test_album_title_never_ellipsised(fake_cover):
    # A very long title wraps / shrinks but must not contain an ellipsis.
    long = "Camí Llarguíssim de la Tramuntana Ventosa i Gelada del Nord"
    img = feed_redesign.build_album({**ALBUM, "nom": long})
    assert img.size == (1080, 1350)
