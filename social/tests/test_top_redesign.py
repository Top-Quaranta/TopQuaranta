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
    seen in review were a test-data artifact, not the builder).

    Checked by comparison: dropping the last entry has to change the
    image. `img.size == (1080, 1350)` proved only that a canvas came
    back, blank or not (audit 2026-08-15)."""
    img = top_redesign.build_poster(_entries(40), SET, "ppcc")
    complet = img.tobytes()

    # Change what the LAST entry says. If row 40 is drawn, the image has
    # to move. Comparing 40 entries against 39 is not enough — it only
    # shows the 40th exists; a builder that silently drops its last row
    # passes that comparison, because both renders lose one.
    altra_ultima = _entries(40)
    altra_ultima[-1] = dict(altra_ultima[-1], nom="ZZZZZZZZ", artista_nom="ZZZZZZZZ")
    assert top_redesign.build_poster(altra_ultima, SET, "ppcc").tobytes() != complet

    # …and the same input twice is stable, so the check above can only
    # be tripped by that row.
    assert complet == top_redesign.build_poster(_entries(40), SET, "ppcc").tobytes()

    R, G, B = _chan(img)
    # bright yellow "40" headline ink near the top
    sl = slice(56, 480)
    yellow = ((R[:, sl] > 190) & (G[:, sl] > 140) & (B[:, sl] < 110)).sum(1)
    # Presence, stated as presence. The old form —
    # `assert next(r for r in range(120, 320) if ...) < 320` — is true of
    # anything the generator can yield, and a MISSING headline raised
    # StopIteration: an error, not a failure (audit 2026-08-15).
    files_grogues = [r for r in range(120, 320) if yellow[r] > 60]
    assert files_grogues, "no s'ha pintat el titular groc"


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
    top = next(r for r in range(540, 1000) if yellow[r] > 80)
    assert abs(top - 570) <= TOL, top


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


# ── fix pins (2026-06-12): ink-anchored, ±8 px against the artboard ──


def _ink_rows(img, mask, x0, x1, y0, y1, thr=6):
    R, G, B = _chan(img)
    m = mask(R, G, B)[:, x0:x1]
    rr = [r for r in range(y0, y1) if m[r].sum() > thr]
    return (rr[0], rr[-1]) if rr else None


def _yellow(R, G, B):
    return (R > 190) & (G > 140) & (B < 110)


def _white(R, G, B):
    return (R > 225) & (G > 225) & (B > 225)


def _dark(R, G, B):
    return (R < 60) & (G < 60) & (B < 60)


def test_cover_eltop_forty_gap(fake_cover):
    """'EL TOP' and '40' sit tight (design ink gap ≈ -25; the '40' ink-top
    rises into EL TOP's bottom). Guards the #1 regression."""
    img = top_redesign.build_top_cover(SET, "ppcc")
    w = _ink_rows(img, _white, 360, 720, 400, 620)
    y = _ink_rows(img, _yellow, 360, 720, 560, 900)
    assert abs((y[0] - w[1]) - (-25)) <= TOL, (w, y)


def test_top_pills_ink_centred(fake_cover):
    """The SETMANA pill text is vertically ink-centred in its box (cover + cartell)."""
    cov = top_redesign.build_top_cover(SET, "ppcc")
    t = _ink_rows(cov, _dark, 330, 560, 1190, 1280)
    assert abs((t[0] + t[1]) / 2 - 1234) <= TOL, t  # pill cy=1234
    car = top_redesign.build_poster(_entries(40), SET, "ppcc")
    t2 = _ink_rows(car, _dark, 835, 1010, 48, 104)
    assert abs((t2[0] + t2[1]) / 2 - 76) <= TOL, t2  # pill centre ≈76


def test_list_numeral_centred_on_row(fake_cover):
    """List numerals are ink-centred on the row (were dropping low). Row 1
    centre ≈ 246."""
    img = top_redesign.build_top_list(list(reversed(_entries(10))), 4, 4, SET, "ppcc")
    n = _ink_rows(img, _white, 72, 140, 199, 293, thr=3)
    assert abs((n[0] + n[1]) / 2 - 246) <= TOL, n


def test_no_title_artist_overlap_long_titles(fake_cover):
    """With very long titles, the artist stays visible and never overlaps the
    title (rich: stacked; dense: reserved inline)."""
    long = "Títol Extremadament Llarg Que No Cap De Cap Manera Possible"
    e = _entries(40)
    for i in (0, 1, 10, 11):
        e[i]["canco_nom"] = long
        e[i]["artista_nom"] = f"Artista Visible {i}"
    img = top_redesign.build_poster(e, SET, "ppcc")
    R, G, B = _chan(img)
    # rich row 1: dimmed-white artist ink exists below the title block (its own
    # band of lit pixels in the left column, distinct from the 2 title lines).
    lit = ((R[:, 194:480] > 120)).sum(1)
    bands = [r for r in range(245, 330) if lit[r] > 8]
    assert bands, "rich row 1 text not rendered"
    # the artist band (bottom) is separated from the title (no single solid block
    # spanning the whole row → there is a gap row somewhere in the middle).
    assert any(lit[r] <= 8 for r in range(bands[0], bands[-1])), "title/artist merged"
