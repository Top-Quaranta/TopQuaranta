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


def test_poster_under_1mb_bluesky(fake_cover):
    """The cartell JPEG must stay under Bluesky's 1 MB blob limit."""
    img = top_redesign.build_poster(_entries(40), SET, "ppcc")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    assert buf.tell() < 1_000_000, buf.tell()


def _row_bands():
    """Row bands of the list slide, derived from the design tokens (the
    source of truth for the geometry) — not from pinned pixel coordinates."""
    rw = top_redesign.tokens()["top_list"]["rows"]
    return [
        (int(rw["y0"] + i * rw["pitch"]), int(rw["y0"] + i * rw["pitch"] + rw["h"]))
        for i in range(rw["count"])
    ], (int(rw["x"]), int(rw["x"] + rw["w"]))


def test_top_list_one_highlighted_and_rows(fake_cover):
    """The #1 row is visually highlighted (accent-coloured treatment) and no
    other row is; every row is painted.

    Property asserted now (rewrite 2026-08-18): the row holding posició 1
    carries far more accent-coloured ink than any other row band — wherever
    that row sits on the slide — and every row band carries some ink. Row
    geometry comes from `tokens()`, the accent from `_list_palette`, so a
    re-layout that keeps the promise keeps the test green."""
    rows = list(reversed(_entries(10)))  # countdown order, #1 last (as prod)
    img = top_redesign.build_top_list(rows, 4, 4, SET, "ppcc")
    assert img.size == (1080, 1350)
    acc = top_redesign._list_palette("ppcc")[0][:3]
    a = np.asarray(img.convert("RGB"), np.int16)
    bands, (x0, x1) = _row_bands()
    dist = np.abs(a[:, x0:x1, :] - np.array(acc, np.int16)).sum(2)
    accent_per_row = [int((dist[y0:y1] < 90).sum()) for y0, y1 in bands]
    lit_per_row = [int((a[y0:y1, x0:x1].max(2) > 60).sum()) for y0, y1 in bands]
    idx1 = next(i for i, e in enumerate(rows) if e["posicio"] == 1)

    assert all(n > 0 for n in lit_per_row), lit_per_row  # every row painted
    others = [n for i, n in enumerate(accent_per_row) if i != idx1]
    assert accent_per_row[idx1] > 5 * max(others), accent_per_row


def _rule_row(a, x0, x1, y_from):
    """First image row (≥ y_from) that is a near-full-width yellow rule."""
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    yel = _yellow(R, G, B)[:, x0:x1].mean(1)
    return next((r for r in range(y_from, a.shape[0]) if yel[r] > 0.8), None)


@pytest.mark.parametrize(
    "title",
    [
        "Àlbum {i} de títol llarg",
        "Àlbum {i} de títol llarguíssim que no cap de cap manera",
    ],
)
def test_mosaic_footer_clear(fake_cover, title):
    """The mosaic's 3rd row must not collide with the footer rule (the fix):
    a clear band of background just above the footer rule.

    Property asserted now (rewrite 2026-08-18): the footer rule exists (a
    near-full-width yellow row in the lower part of the board, located by
    scanning — not pinned at y≈1240) and, with a full 9-album grid whose
    titles wrap to the max line count, no grid ink touches it: at least one
    ink-free row separates the last content row from the rule."""
    albums = [
        {
            "nom": title.format(i=i),
            "artista_nom": f"Art {i}",
            "artista_territori": "VAL",
            "cover_url": None,
        }
        for i in range(9)
    ]
    img = top_redesign.build_albums_mosaic(albums, SET)
    assert img.size == (1080, 1350)
    a = np.asarray(img.convert("RGB"), np.int16)
    M = top_redesign.tokens()["mosaic"]
    px0, px1 = int(M["pad"]["l"]), 1080 - int(M["pad"]["r"])
    rule_y = _rule_row(a, px0, px1, 1350 // 2)
    assert rule_y is not None, "footer rule not painted"
    # grid ink = anything lit in the columns' x-range above the rule
    gx0 = int(min(M["grid"]["cols_x"]))
    gx1 = int(max(M["grid"]["cols_x"]) + M["grid"]["cover"])
    lit = a[:rule_y, gx0:gx1].max(2) > 60
    content_rows = [r for r in range(rule_y) if lit[r].any()]
    assert content_rows, "grid not painted"
    assert content_rows[-1] < rule_y - 1, (content_rows[-1], rule_y)


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
