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


def test_per_page_clamped_and_empty(monkeypatch):
    """Out-of-range `per_page` never crashes and never loses a release;
    no items → no pages.

    Property asserted now (rewrite 2026-08-18): for per_page 0 and 99 the
    set still comes out with ≥1 non-empty page and the pages, concatenated
    in order, are exactly the input items (every release appears once);
    the clamp bounds themselves (1/8) are not pinned."""
    setmana = datetime.date(2026, 6, 22)
    chunks: list[list[dict]] = []
    real = renderer._story_novetats

    def spy(setmana_, chunk, **kw):
        chunks.append(list(chunk))
        return real(setmana_, chunk, **kw)

    monkeypatch.setattr(renderer, "_story_novetats", spy)
    for n, per_page in ((3, 0), (9, 99), (5, -4)):
        chunks.clear()
        items = _items(n)
        paths = renderer.render_stories_novetats(setmana, items, per_page=per_page)
        assert paths and len(paths) == len(chunks), (n, per_page)
        assert all(chunks), (n, per_page)  # no empty page
        assert [it for c in chunks for it in c] == items, (n, per_page)
    # no items → no pages.
    assert renderer.render_stories_novetats(setmana, [], per_page=4) == []
