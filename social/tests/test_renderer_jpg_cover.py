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
    """The TOP carousel cover (slide 0) is the new editorial `build_top_cover`.
    Proxy for 'not ~empty': big EL TOP / 40 headline → plenty of lit pixels."""
    from social import top_redesign

    img = top_redesign.build_top_cover(WK, "ppcc")
    assert img.size == (renderer.FEED_W, renderer.FEED_H)
    small = img.resize((108, 135)).convert("L")
    lit = sum(1 for px in small.getdata() if px > 40)
    assert lit > 600, lit
