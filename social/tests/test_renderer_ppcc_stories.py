"""Renderer Step 3b redesign: the 7-slide editorial PPCC story set.

Renders real slides (needs Django for settings/fonts/svg_assets) and
pins the structure + the redesign: JPG output, reasonable weight, the
new display fonts, the #1 hero Playfair climax, the 40→11 mosaic, and
the yellow outro without the legacy slate card.
"""

from __future__ import annotations

import datetime

import pytest
from PIL import Image

from social import colors, fonts, renderer
from social.narrative.story_synth import synthesize_hero

WK = datetime.date(2026, 5, 25)


def _entries(n=40):
    return [
        {
            "posicio": i + 1,
            "canco_nom": f"Cançó {i + 1}",
            "artista_nom": f"Artista {i + 1}",
            "artistes_noms": [f"Artista {i + 1}"],
            "cover_url": None,  # no network in tests → placeholder
            "album_deezer_id": None,
        }
        for i in range(n)
    ]


def _novetats(n=3):
    return [
        {
            "nom": f"Novetat {i + 1}",
            "slug": f"novetat-{i + 1}",
            "artista_nom": f"Banda {i + 1}",
            "cover_url": None,
            "album_deezer_id": None,
            "dies": i,
        }
        for i in range(n)
    ]


class _Scn:
    def __init__(self, code, data):
        self.code = code
        self.data = data


def _count_yellow(img: Image.Image) -> int:
    """Full-resolution yellow-pixel count over the whole slide. The hero
    Playfair title + kickers are yellow on ink, so a healthy count proves
    the headline painted. Native res — a downscale blends the strokes."""
    rgb = img.convert("RGB")
    return sum(1 for r, g, b in rgb.getdata() if r > 200 and g > 160 and b < 130)


# ── Full set ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_ppcc_story_set_outputs_7_jpeg_slides():
    paths = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=_novetats(3), hero_headline="DEBUT AL CIM"
    )
    assert len(paths) == 7, [p.name for p in paths]
    for p in paths:
        assert p.suffix == ".jpg", p.name
        assert p.is_file()
        with Image.open(p) as im:
            assert im.format == "JPEG"
            assert im.size == (renderer.STORY_W, renderer.STORY_H)
        assert p.stat().st_size < 500_000, (p.name, p.stat().st_size)


@pytest.mark.django_db
def test_ppcc_story_set_skips_novetats_when_empty():
    paths = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=[], hero_headline="NOU #1"
    )
    assert len(paths) == 6, [p.name for p in paths]


@pytest.mark.django_db
def test_ppcc_story_set_skips_novetats_when_items_falsy():
    """A list of falsy entries (None / empty dict) must also be treated as
    'no novetats' — the slide is neither generated nor returned."""
    paths = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=[None, {}], hero_headline="NOU #1"
    )
    assert len(paths) == 6, [p.name for p in paths]


@pytest.mark.django_db
def test_ppcc_story_set_handles_short_top():
    """Only 5 ranked entries (the test fixture's size): no crash, the
    11-40 mosaic and 4-10 grid simply render empty, slides still produce."""
    paths = renderer.render_stories_ppcc(
        WK, _entries(5), novetats_items=[], hero_headline=""
    )
    assert len(paths) == 6
    for p in paths:
        with Image.open(p) as im:
            assert im.format == "JPEG"


# ── #1 hero headline wiring ─────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "code,data",
    [
        ("a1_outside_to_top1", {}),
        ("a2_streak", {"streak": 5}),
        ("a13_top1_return", {"gap_setmanes_str": "5 setmanes"}),
        ("fallback_no_event", {}),
    ],
)
def test_hero_slide_receives_scenario_synthesis(code, data):
    import random

    headline = synthesize_hero(_Scn(code, data), random.Random(0))
    assert headline and headline == headline.upper()
    img = renderer._story_hero(_entries(1)[0], headline)
    assert img.size == (renderer.STORY_W, renderer.STORY_H)
    # The slide carries appreciable yellow (Playfair title + kickers) on ink.
    assert _count_yellow(img) > 1000, _count_yellow(img)


@pytest.mark.django_db
def test_hero_slide_empty_headline_falls_back():
    """An empty headline must not crash and must still paint a headline
    (the generic fallback line)."""
    img = renderer._story_hero(_entries(1)[0], "")
    assert _count_yellow(img) > 1000, _count_yellow(img)


# ── Top 11-40 mosaic ────────────────────────────────────────────────


@pytest.mark.django_db
def test_mosaic_renders_30_covers_with_fallback():
    """30 covers, some pointing at a (failing) Deezer URL so the
    placeholder path is exercised. Must render without error."""
    entries = _entries(40)[10:40]
    for i, e in enumerate(entries):
        if i % 2 == 0:
            e["cover_url"] = (
                "https://e-cdns-images.dzcdn.net/images/cover/zzz/250x250.jpg"
            )
    img = renderer._story_top_mosaic(WK, entries)
    assert img.size == (renderer.STORY_W, renderer.STORY_H)


# ── Top 10-4 grid — dynamic row height ──────────────────────────────


@pytest.mark.django_db
def test_grid_long_titles_do_not_reach_footer():
    """Every title forced to 2 lines: dynamic row heights + the #4 clamp
    keep the last (centred) cover out of the footer band."""
    entries = []
    for i in range(7):
        e = _entries(1)[0].copy()
        e["posicio"] = i + 4
        e["canco_nom"] = "On T'has Ficat Aquesta Nit Que No Et Trobo Enlloc"
        e["artistes_noms"] = ["Una Banda De Nom Ben Llarg"]
        entries.append(e)
    img = renderer._story_top_grid(WK, entries).convert("RGB")
    assert img.size == (renderer.STORY_W, renderer.STORY_H)
    # Placeholder covers paint COLOR_CARD; none may appear in the 30 px
    # strip just above the footer (proves no cover overflowed downward).
    cr = colors._hex_to_rgb(colors.COLOR_CARD)
    band = img.crop(
        (0, renderer.STORY_H - 122, renderer.STORY_W, renderer.STORY_H - 96)
    )
    card = sum(
        1
        for r, g, b in band.getdata()
        if abs(r - cr[0]) < 20 and abs(g - cr[1]) < 20 and abs(b - cr[2]) < 20
    )
    assert card == 0, f"a cover bled into the footer band ({card} px)"


# ── Outro ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_outro_is_yellow_without_slate_card():
    img = renderer._story_outro_ppcc(WK).convert("RGB")
    small = img.resize((108, 192))
    pixels = list(small.getdata())

    def _near(px, hex_str, tol=24):
        r, g, b = px
        h = hex_str.lstrip("#")
        tr, tg, tb = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return abs(r - tr) < tol and abs(g - tg) < tol and abs(b - tb) < tol

    yellow = sum(1 for px in pixels if _near(px, colors.COLOR_YELLOW))
    slate = sum(1 for px in pixels if _near(px, colors.COLOR_CARD))
    assert yellow > len(pixels) * 0.5, yellow  # yellow dominates
    assert slate == 0, f"slate COLOR_CARD must be gone, found {slate}"


# ── Redesign: fonts + intro ─────────────────────────────────────────


def test_redesign_fonts_load_real_families():
    """The four bundled display families resolve to the vendored TTFs
    (not the DejaVu fallback) — guards the OFL bundle being present."""
    for loader in (
        fonts.anton,
        fonts.bricolage_xbold,
        fonts.instrument_italic,
        fonts.display_xbold,
    ):
        f = loader(48)
        assert f.getbbox("Test")[2] > 0
    # Resolved path must be the vendored file, not a DejaVu fallback.
    assert "PlayfairDisplay-ExtraBold" in fonts._resolve("display_xbold")
    assert "Anton" in fonts._resolve("anton")
    assert "Bricolage" in fonts._resolve("bricolage_xbold")
    assert "InstrumentSerif" in fonts._resolve("instrument_italic")


@pytest.mark.django_db
def test_intro_is_green_with_big_yellow_forty():
    """Slide 1 is the green field carrying the big yellow '40'."""
    img = renderer._story_intro_ppcc(WK).convert("RGB")
    small = img.resize((108, 192))
    px = list(small.getdata())

    def _near(p, hexs, tol=30):
        h = hexs.lstrip("#")
        t = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        return all(abs(p[i] - t[i]) < tol for i in range(3))

    green = sum(1 for p in px if _near(p, colors.terr_color("PPCC"), 40))
    assert green > len(px) * 0.4, green  # green dominates
    assert _count_yellow(img) > 1000  # the big "40" + pill


# ── Territorial regression ──────────────────────────────────────────


@pytest.mark.django_db
def test_territorial_stories_still_use_cta_path():
    """render_stories_top (territorial) is untouched: intro + N + CTA."""
    paths = renderer.render_stories_top(
        "top_territorial", "CAT", WK, _entries(5), max_cancons=5
    )
    assert len(paths) == 7  # intro + 5 cançons + CTA
    for p in paths:
        with Image.open(p) as im:
            assert im.format == "JPEG"
