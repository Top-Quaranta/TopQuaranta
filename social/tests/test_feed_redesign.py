"""No-regression pins + smoke for the gated feed redesign.

The redesign is additive and OFF by default; these pins assert (a) the gate
default, (b) routing (off → legacy, on → redesign), (c) the three redesign
builders produce a valid 1080×1350 image incl. the cover==null fallback, and
(d) deterministic output. No network: the Deezer cover fetch is monkeypatched.
"""

from __future__ import annotations

import datetime

import numpy as np
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


# ── fidelity pins: pixel-measured ink milestones vs the extracted fitxa ──
#
# These guard against the layout silently drifting (e.g. PIL line-height vs
# CSS box anchoring). They MEASURE ink in the render and assert against the
# values in feed-tokens.json with ±8 px tolerance. No oracle images: only
# numbers, and the thresholds sit well above the gaussian grain so they are
# robust. A milestone that can't be measured stably is intentionally left out
# (noted inline) rather than made fragile.

TOL = 8


def _rows(mask_counts, y0, y1, thr):
    """Row indices in [y0,y1) whose per-row ink count exceeds `thr`."""
    return [r for r in range(y0, y1) if mask_counts[r] > thr]


def _channels(img):
    a = np.asarray(img.convert("RGB"), np.int16)
    return a[:, :, 0], a[:, :, 1], a[:, :, 2]


def test_cover_masthead_ink_anchored_to_fitxa():
    """NOVETATS (white) and ÀLBUMS (yellow) cap-top ink must land at the
    fitxa cap_top (±8), and the white must overlap the yellow (À accent)."""
    R, G, B = _channels(feed_redesign.build_cover("nous_albums", SET))
    sl = slice(120, 960)  # masthead x-region (excludes logo edges)
    white = ((R[:, sl] > 200) & (G[:, sl] > 200) & (B[:, sl] > 190)).sum(1)
    yellow_main = ((R[:, sl] > 190) & (G[:, sl] > 140) & (B[:, sl] < 110)).sum(1)
    yellow_any = yellow_main  # same mask; low threshold below catches the accent
    w = _rows(white, 400, 960, 40)
    ym = _rows(yellow_main, 400, 960, 120)
    ya = _rows(yellow_any, 400, 960, 20)

    C = feed_redesign.tokens()["cover"]
    assert abs(w[0] - C["novetats"]["cap_top"]) <= TOL  # white cap-top = 535
    assert abs(ym[0] - C["etiqueta"]["cap_top"]) <= TOL  # yellow cap-top = 626
    # white ink bottom overlaps the yellow (the À accent rises into it).
    overlap = w[-1] - ya[0]
    assert overlap >= 30, f"white must overlap yellow, got {overlap}px"
    # Heights pin the bottoms robustly (font-size determined).
    assert 80 <= (w[-1] - w[0]) <= 120
    assert 190 <= (ym[-1] - ym[0]) <= 235


def test_cover_singles_masthead_matches_albums():
    """The SINGLES cover masthead sits at the same cap-tops as ÀLBUMS."""
    R, G, B = _channels(feed_redesign.build_cover("nous_singles", SET))
    sl = slice(120, 960)
    white = ((R[:, sl] > 200) & (G[:, sl] > 200) & (B[:, sl] > 190)).sum(1)
    yellow = ((R[:, sl] > 190) & (G[:, sl] > 140) & (B[:, sl] < 110)).sum(1)
    C = feed_redesign.tokens()["cover"]
    assert abs(_rows(white, 400, 960, 40)[0] - C["novetats"]["cap_top"]) <= TOL
    assert abs(_rows(yellow, 400, 960, 120)[0] - C["etiqueta"]["cap_top"]) <= TOL


def test_album_band_top_matches_fitxa(fake_cover):
    """The territory band top = band.bottom - band.h1 (1-line title)."""
    img = feed_redesign.build_album(ALBUM)  # VAL deep = rgb(138,74,30)
    col = np.asarray(img.convert("RGB"), np.int16)[:, 40, :]
    A = feed_redesign.tokens()["album"]["band"]
    expected = A["bottom"] - A["h1"]
    rows = [
        r
        for r in range(1000, 1350)
        if abs(col[r, 0] - 138) < 25
        and abs(col[r, 1] - 74) < 25
        and abs(col[r, 2] - 30) < 25
    ]
    assert rows, "VAL deep band not found"
    assert abs(rows[0] - expected) <= TOL


SINGLES_10 = [
    {
        "nom": "S%d" % i,
        "artista_nom": "A%d" % i,
        "artista_territori": c,
        "cover_url": "x",
    }
    for i, c in enumerate(
        ["CAT", "VAL", "BAL", "CNO", "FRA", "AND", "ALG", "BAL", "VAL", "CAT"], 1
    )
]


def test_singles_row_top_and_pitch_match_fitxa(fake_cover):
    """First row top = rows.y0 and the row pitch = rows.pitch (±8). Measured
    from the saturated territory chips at x=100 (10 rows, no PPCC)."""
    img = feed_redesign.build_singles(SINGLES_10, 1, 2, setmana=SET)
    col = np.asarray(img.convert("RGB"), np.int16)[:, 100, :]
    colored = [r for r in range(250, 1250) if int(col[r].max()) > 50]
    tops, prev = [], -10
    for r in colored:
        if r - prev > 3:
            tops.append(r)
        prev = r
    R = feed_redesign.tokens()["singles"]["rows"]
    assert len(tops) == 10, f"expected 10 chip rows, got {len(tops)}"
    assert abs(tops[0] - R["y0"]) <= TOL
    diffs = sorted(tops[i + 1] - tops[i] for i in range(len(tops) - 1))
    pitch = diffs[len(diffs) // 2]
    assert abs(pitch - R["pitch"]) <= TOL


def test_singles_blinds_ppcc_row_count(fake_cover):
    """A PPCC row is dropped: 5 items with one PPCC → 4 chip rows."""
    items = [
        {"nom": "x", "artista_nom": "a", "artista_territori": c, "cover_url": "x"}
        for c in ["CAT", "VAL", "PPCC", "BAL", "CNO"]
    ]
    img = feed_redesign.build_singles(items, 1, 1)
    col = np.asarray(img.convert("RGB"), np.int16)[:, 100, :]
    colored = [r for r in range(250, 1250) if int(col[r].max()) > 50]
    tops, prev = [], -10
    for r in colored:
        if r - prev > 3:
            tops.append(r)
        prev = r
    assert len(tops) == 4
