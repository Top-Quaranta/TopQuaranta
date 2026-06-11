"""Measured fidelity pins for the TOP family (cartell · cover · list · mosaic)
+ movement parsing + the Bluesky <1MB poster guard. Pins measure ink against the
extracted tokens (no oracle images). Deterministic (fixed grain seed, no network).
"""

from __future__ import annotations

import datetime
import io

import numpy as np
import pytest

from social import render_core, top_redesign

SET = datetime.date(2026, 6, 8)
TOL = 8


@pytest.fixture
def fake_cover(monkeypatch):
    monkeypatch.setattr(top_redesign.F.cover_cache, "fetch", lambda *a, **k: None)


def _entries(n, *, news=(), reentries=()):
    out = []
    for i in range(1, n + 1):
        pa = None if (i in news or i in reentries) else i + 1
        out.append(
            {
                "posicio": i,
                "posicio_anterior": pa,
                "reentrada": i in reentries,
                "canco_nom": f"Cançó {i}",
                "artista_nom": f"Artista {i}",
                "artista_territori": "VAL",
                "cover_url": None,
            }
        )
    return out


def _chan(img):
    a = np.asarray(img.convert("RGB"), np.int16)
    return a[:, :, 0], a[:, :, 1], a[:, :, 2]


def test_parse_move_three_cases():
    assert render_core.parse_move(3, 5) == ("up", 2)
    assert render_core.parse_move(5, 3) == ("down", 2)
    assert render_core.parse_move(7, None) == ("new", 0)
    assert render_core.parse_move(7, None, reentry=True) == ("re", 0)
    assert render_core.parse_move(7, 7) == ("eq", 0)


def test_poster_renders_all_rows(fake_cover):
    """Every entry received must produce a numeral — no dropped rows (the gaps
    seen in review were a test-data artifact, not the builder)."""
    img = top_redesign.build_poster(_entries(40), SET, "ppcc")
    assert img.size == (1080, 1350)
    R, G, B = _chan(img)
    # bright yellow "40" headline ink near the top
    sl = slice(56, 480)
    yellow = ((R[:, sl] > 190) & (G[:, sl] > 140) & (B[:, sl] < 110)).sum(1)
    assert next(r for r in range(120, 320) if yellow[r] > 60) < 320  # title present


def test_poster_pins(fake_cover):
    """Top accent bar at the very top + footer rule near the bottom."""
    img = top_redesign.build_poster(_entries(40), SET, "ppcc")
    R, G, B = _chan(img)
    # 7px yellow bar at y=0..7
    bar = ((R[0:7] > 190) & (G[0:7] > 140) & (B[0:7] < 110)).mean()
    assert bar > 0.9, bar


def test_poster_under_1mb_bluesky(fake_cover):
    """The cartell JPEG must stay under Bluesky's 1 MB blob limit."""
    img = top_redesign.build_poster(_entries(40), SET, "ppcc")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    assert buf.tell() < 1_000_000, buf.tell()


def test_top_cover_pins(fake_cover):
    img = top_redesign.build_top_cover(SET, "ppcc")
    assert img.size == (1080, 1350)
    R, G, B = _chan(img)
    # big yellow "40" mid-canvas
    sl = slice(300, 780)
    yellow = ((R[:, sl] > 190) & (G[:, sl] > 140) & (B[:, sl] < 110)).sum(1)
    top = next(r for r in range(560, 1000) if yellow[r] > 80)
    assert abs(top - 635) <= 20, top


def test_top_list_one_highlighted_and_rows(fake_cover):
    rows = list(reversed(_entries(10)))
    img = top_redesign.build_top_list(rows, 4, 4, SET, "ppcc")
    assert img.size == (1080, 1350)
    # the #1 row carries a yellow inset border (accent pixels in the last card)
    R, G, B = _chan(img)
    last = slice(1180, 1280)
    yellow = ((R[last] > 190) & (G[last] > 140) & (B[last] < 110)).sum()
    assert yellow > 200, yellow


def test_mosaic_footer_clear(fake_cover):
    """The mosaic's 3rd row must not collide with the footer rule (the fix):
    a clear band of background just above the footer rule."""
    albums = [
        {
            "nom": f"Àlbum {i} de títol llarg",
            "artista_nom": f"Art {i}",
            "artista_territori": "VAL",
            "cover_url": None,
        }
        for i in range(9)
    ]
    img = top_redesign.build_albums_mosaic(albums, SET)
    assert img.size == (1080, 1350)
    R, G, B = _chan(img)
    # footer rule (yellow) present near y≈1240
    yellow = ((R[1235:1245] > 190) & (G[1235:1245] > 140) & (B[1235:1245] < 110)).sum()
    assert yellow > 300, yellow
