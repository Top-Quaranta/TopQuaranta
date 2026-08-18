"""Paginated novetats story set (`render_stories_novetats`).

The novetats story used to be a single 3-item slide; it now paginates
so every release appears. Covers the chunking, the per-page indicator
plumbing, per_page clamping, and that the legacy single-page builder
stays unchanged for the weekly PPCC set.
"""

from __future__ import annotations

import datetime

from PIL import Image

from social import renderer


def _items(n):
    return [
        {
            "nom": f"Cançó {i}",
            "artistes_noms": [f"Artista {i}"],
            "artista_territori": "CAT",
            "cover_url": None,  # → placeholder tile, no network
            "album_deezer_id": None,
        }
        for i in range(n)
    ]


def test_pagination_splits_into_pages_of_per_page():
    setmana = datetime.date(2026, 6, 22)
    paths = renderer.render_stories_novetats(setmana, _items(11), per_page=4)
    # 11 → 4 + 4 + 3 = 3 pages.
    assert len(paths) == 3
    for p in paths:
        img = Image.open(p)
        assert img.size == (renderer.STORY_W, renderer.STORY_H)  # 1080×1920
        assert p.suffix == ".jpg"


def test_per_page_clamped_and_empty():
    setmana = datetime.date(2026, 6, 22)
    # per_page below 1 is clamped to 1 → one page per item.
    assert len(renderer.render_stories_novetats(setmana, _items(3), per_page=0)) == 3
    # above 8 is clamped to 8 → 9 items become 2 pages (8 + 1).
    assert len(renderer.render_stories_novetats(setmana, _items(9), per_page=99)) == 2
    # no items → no pages.
    assert renderer.render_stories_novetats(setmana, [], per_page=4) == []
