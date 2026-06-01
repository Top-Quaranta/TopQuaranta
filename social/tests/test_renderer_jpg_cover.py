"""Renderer Step 3a: JPG output + editorial PPCC feed cover.

Renders real slides (needs Django for settings/fonts/svg_assets) and
asserts the format switch + the new cover. The story-set rewrite lands
in 3b/3c; here we only pin the format + the feed cover.
"""

from __future__ import annotations

import datetime

import pytest
from PIL import Image

from social import renderer


def _entries(n=12):
    return [
        {
            "posicio": i + 1,
            "posicio_anterior": i + 2,
            "canco_nom": f"Cançó {i + 1}",
            "artista_nom": f"Artista {i + 1}",
            "artistes_noms": [f"Artista {i + 1}"],
            "cover_url": None,  # no network in tests → ink/placeholder
            "album_deezer_id": None,
        }
        for i in range(n)
    ]


WK = datetime.date(2026, 5, 25)


@pytest.mark.django_db
def test_feed_top_outputs_jpeg():
    paths = renderer.render_feed_top("top_ppcc", "PPCC", WK, _entries(12))
    assert paths, "no slides rendered"
    for p in paths:
        assert p.suffix == ".jpg", p.name
        assert p.is_file()
        with Image.open(p) as im:
            assert im.format == "JPEG"
        assert p.stat().st_size < 500_000, (p.name, p.stat().st_size)


@pytest.mark.django_db
def test_ppcc_cover_is_editorial_not_empty():
    """The PPCC cover (slide 0) is now the editorial cover. Proxy for
    'not ~85% empty ink': it carries appreciably more non-background
    ink than a bare logo+pill would (text fills the canvas)."""
    img = renderer._feed_portada_ppcc(
        WK, ["Rosalía", "Max Navarro", "SX3"], renderer.colors.terr_color("PPCC")
    )
    assert img.size == (renderer.FEED_W, renderer.FEED_H)
    # Count non-near-black pixels: the editorial cover paints a big
    # yellow headline + 3 names, so well above a near-empty cover.
    small = img.resize((108, 135)).convert("L")
    lit = sum(1 for px in small.getdata() if px > 40)
    assert lit > 600, lit  # generously above an ~empty ink canvas


@pytest.mark.django_db
def test_feed_list_slides_still_render():
    """List slides 1-4 are untouched; just confirm they still produce."""
    paths = renderer.render_feed_top("top_ppcc", "PPCC", WK, _entries(25))
    assert len(paths) >= 2  # cover + at least one list page
    for p in paths[1:]:
        with Image.open(p) as im:
            assert im.format == "JPEG"
