"""No-regression pins + smoke for the novetats feed renderer.

The editorial redesign is the only path (the gate + legacy layout were removed
2026-06-11). These pins assert (a) `render_feed_novetats` delegates to the
redesign builders, (b) the three builders produce a valid 1080×1350 image incl.
the cover==null fallback, (c) deterministic output, and (d) the pixel-measured
fidelity milestones. No network: the Deezer cover fetch is monkeypatched.
"""

from __future__ import annotations

import datetime

import numpy as np
import pytest
from PIL import Image, ImageDraw

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


# ── render path: novetats slides come from the redesign (the only path) ──


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
    """Comparing renders, not measuring the canvas: if the cap holds,
    what the 11th item onwards SAY cannot reach the image. The old
    assertion was `img.size == (1080, 1350)`, true of any canvas
    including a blank one — deleting the cap left it green (audit
    2026-08-15)."""
    # No PPCC rows here on purpose: the builder drops them first, which
    # compacts the list and promotes later items into the drawn set — so
    # a fixture with PPCC in it cannot express "the 11th is never drawn".
    vint = [
        {
            "nom": f"Cançó {i}",
            "artista_nom": f"Banda {i}",
            "artista_territori": "CAT",
            "cover_url": "x",
        }
        for i in range(20)
    ]
    # Change what the 11th onwards SAY. If the cap holds they are never
    # drawn, so the render cannot move. (Comparing 10 items against 20
    # would not work: an overflow cue legitimately differs.)
    canviats = vint[:10] + [dict(e, nom="ZZZ", artista_nom="ZZZ") for e in vint[10:]]

    original = feed_redesign.build_singles(vint, 1, 2).tobytes()
    assert feed_redesign.build_singles(canviats, 1, 2).tobytes() == original

    # …and rows do get drawn, or the comparison above would hold on a
    # blank canvas too.
    assert feed_redesign.build_singles(vint[:9], 1, 2).tobytes() != original


def test_singles_blinds_ppcc(fake_cover):
    """A PPCC (global aggregate) row is never rendered as a territory."""
    items = [
        {"nom": "A", "artista_nom": "x", "artista_territori": "PPCC", "cover_url": "x"},
        {"nom": "B", "artista_nom": "y", "artista_territori": "CAT", "cover_url": "x"},
    ]
    only_ppcc = [items[0]]
    nomes_cat = [items[1]]

    buit = feed_redesign.build_singles([], 1, 1).tobytes()
    # All-PPCC chunk → the PPCC row is dropped, so nothing is drawn: the
    # result must equal the empty render, not merely be canvas-sized.
    assert feed_redesign.build_singles(only_ppcc, 1, 1).tobytes() == buit
    # Mixed → identical to passing the CAT row alone: PPCC contributes
    # nothing. And it must NOT equal the empty render, or "drops
    # everything" would pass as "drops PPCC".
    barrejat = feed_redesign.build_singles(items, 1, 1).tobytes()
    assert barrejat == feed_redesign.build_singles(nomes_cat, 1, 1).tobytes()
    assert barrejat != buit


def test_territori_full_name_present():
    assert feed_redesign.territori("VAL")["name"] == "País Valencià"
    assert feed_redesign.territori("CNO")["name"] == "Catalunya Nord"


# ── determinism ──────────────────────────────────────────────────────


def test_render_is_deterministic(fake_cover):
    a = feed_redesign.build_album(ALBUM).tobytes()
    b = feed_redesign.build_album(ALBUM).tobytes()
    assert a == b


# ── territory resolver ───────────────────────────────────────────────


@pytest.mark.parametrize("code", ["ZZZ", "PPCC", "", None])
def test_territori_unknown_falls_back_to_green(code):
    # Aggregate/unknown codes resolve to a green fallback (never raises).
    # Property asserted now (rewrite 2026-08-18): the resolver is total —
    # every unknown/aggregate code yields a complete palette entry whose
    # colours parse, with a distinct deep/accent pair — no exact RGB pinned.
    t = feed_redesign.territori(code)
    assert {"deep", "accent", "abbr", "short", "name"} <= set(t)
    deep, accent = feed_redesign._col(t["deep"]), feed_redesign._col(t["accent"])
    assert deep != accent and all(len(c) == 4 for c in (deep, accent))
    assert t["abbr"] and t["name"] and t["short"]


def test_col_parses_rgba():
    assert feed_redesign._col("rgb(10, 20, 30)") == (10, 20, 30, 255)
    assert feed_redesign._col("rgba(255, 255, 255, 0.5)")[3] == 128


@pytest.mark.parametrize(
    "long",
    [
        "Camí Llarguíssim de la Tramuntana Ventosa",
        "Camí Llarguíssim de la Tramuntana Ventosa i Gelada del Nord",
    ],
)
def test_album_title_never_ellipsised(fake_cover, monkeypatch, long):
    # A very long title wraps / shrinks but must not contain an ellipsis.
    # Property asserted now (rewrite 2026-08-18): the title lines drawn
    # (captured at the `_text` primitive) carry no "…", each fits inside the
    # canvas, and together they reproduce the title's words in order from
    # its start (the whole title when it fits the 2-line budget at min
    # size). `img.size` alone said nothing about the title (audit
    # 2026-08-15).
    drawn = []
    real_text = feed_redesign._text

    def spy(img, x, y, text, font, fill, **kw):
        drawn.append((text, font, x))
        return real_text(img, x, y, text, font, fill, **kw)

    monkeypatch.setattr(feed_redesign, "_text", spy)
    img = feed_redesign.build_album({**ALBUM, "nom": long})
    assert img.size == (1080, 1350)
    words = long.split()
    title_lines = [(t, f, x) for t, f, x in drawn if set(t.split()) & set(words)]
    assert title_lines, "title not drawn"
    assert not any("…" in t for t, _, _ in title_lines), title_lines
    drawn_words = " ".join(t for t, _, _ in title_lines).split()
    assert len(drawn_words) >= 2 and drawn_words == words[: len(drawn_words)]
    if len(long) < 45:  # fits the 2-line budget at min size → all of it
        assert drawn_words == words
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for t, f, x in title_lines:
        assert x + d.textlength(t, font=f) <= 1080, (t, x)


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


def test_chip_shows_recoloured_silhouette_not_text(fake_cover):
    """The singles chip contains the territory silhouette in its accent colour,
    optically sized (height ≈ optH from the fitxa) and vertically centred in the
    92×85 chip — a stable proxy for 'logo, not abbr text' (the old abbr was
    top-anchored 26 px text; the silhouette is centred and optH-tall). 'No glyph'
    isn't asserted directly (hard to measure robustly); the abbr code path is
    gone — see build_singles.

    Property asserted now (rewrite 2026-08-18): an accent-coloured
    silhouette is present inside the chip box for every territory that has
    a logo spec, and its ink stays inside the chip (no bleed) — the optH
    height and the pixel-centre pins are gone."""
    R = feed_redesign.tokens()["singles"]["rows"]
    y0, rh = int(R["y0"]), R["h"]
    ch = R["chip"]
    logos = feed_redesign.tokens()["territory_logos"]["per_territory"]
    codes = [c for c, k in feed_redesign._CODE_TO_KEY.items() if k in logos]
    assert {"CAT", "VAL"} <= set(codes)  # val exercises the maxW cap
    for code in codes:
        row = [
            {
                "nom": "X",
                "artista_nom": "Y",
                "artista_territori": code,
                "cover_url": "x",
            }
        ]
        img = feed_redesign.build_singles(row, 1, 1)
        a = np.asarray(img.convert("RGB"), np.int16)
        terr = feed_redesign.territori(code)
        ar, ag, ab, _ = feed_redesign._col(terr["accent"])
        # accent pixels (close to the territory accent) around the chip box,
        # with a margin so bleed outside the box would be visible
        m = 12
        region = a[y0 - m : y0 + rh + m, ch["x"] - m : ch["x"] + ch["w"] + m, :]
        d = (
            np.abs(region[..., 0] - ar)
            + np.abs(region[..., 1] - ag)
            + np.abs(region[..., 2] - ab)
        )
        ys, xs = np.where(d < 40)
        assert ys.size > 60, f"{code}: expected an accent silhouette in the chip"
        assert m <= ys.min() and ys.max() < m + rh, f"{code}: silhouette bleeds (y)"
        assert m <= xs.min() and xs.max() < m + ch["w"], f"{code}: bleeds (x)"
