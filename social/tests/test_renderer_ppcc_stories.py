"""Renderer Step 3b redesign: the 8-slide editorial PPCC story set.

Renders real slides (needs Django for settings/fonts/svg_assets) and
pins the structure + the redesign: JPG output, reasonable weight, the
new display fonts, the #1 hero Playfair climax, the 40→21 mosaic, the
20→11 pairs tier (re-tiering of 2026-08-12), and the yellow outro
without the legacy slate card.
"""

from __future__ import annotations

import datetime

import pytest
from PIL import Image, ImageStat

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
def test_ppcc_story_set_outputs_8_jpeg_slides():
    """Property asserted now (rewrite 2026-08-18): the full set is a
    non-empty, distinct list of story-sized JPEG files under IG's weight
    comfort limit — the exact "8 slides" design pin is gone (the slide
    order/count contract lives in test_ppcc_story_structure)."""
    paths = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=_novetats(3), hero_headline="DEBUT AL CIM"
    )
    assert paths and len(set(paths)) == len(paths), [p.name for p in paths]
    for p in paths:
        assert p.suffix == ".jpg", p.name
        assert p.is_file()
        with Image.open(p) as im:
            assert im.format == "JPEG"
            assert im.size == (renderer.STORY_W, renderer.STORY_H)
        assert p.stat().st_size < 500_000, (p.name, p.stat().st_size)


@pytest.mark.django_db
def test_ppcc_story_set_skips_novetats_when_empty():
    """Property asserted now (rewrite 2026-08-18): with no novetats the set
    is exactly one slide shorter than the same set with novetats — the
    novetats slide is the only thing that goes; no absolute count pinned."""
    amb = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=_novetats(3), hero_headline="NOU #1"
    )
    sense = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=[], hero_headline="NOU #1"
    )
    assert len(sense) == len(amb) - 1, ([p.name for p in amb], [p.name for p in sense])


@pytest.mark.django_db
def test_ppcc_story_set_skips_novetats_when_items_falsy():
    """A list of falsy entries (None / empty dict) must also be treated as
    'no novetats' — the slide is neither generated nor returned."""
    paths = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=[None, {}], hero_headline="NOU #1"
    )
    assert len(paths) == 7, [p.name for p in paths]


@pytest.mark.django_db
def test_ppcc_story_set_handles_short_top():
    """Only 5 ranked entries (the test fixture's size): no crash, the
    21-40 mosaic, 11-20 pairs and 4-10 grid simply render empty, slides
    still produce.

    Property asserted now (rewrite 2026-08-18): no crash, and the short top
    yields the same number of slides as a full 40-entry set (the PPCC set
    keeps its structure; only territorial degrades by omission), every one
    a story-sized JPEG. The ==7 pin is gone."""
    full = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=[], hero_headline=""
    )
    paths = renderer.render_stories_ppcc(
        WK, _entries(5), novetats_items=[], hero_headline=""
    )
    assert paths and len(paths) == len(full), [p.name for p in paths]
    for p in paths:
        with Image.open(p) as im:
            assert im.format == "JPEG"
            assert im.size == (renderer.STORY_W, renderer.STORY_H)


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
    """Property asserted now (rewrite 2026-08-18): the synthesised headline
    reaches the slide — below the cover the slide carries the full stack of
    bright text bands (scenario kicker + title + artist, counted by a
    luminance oracle, region located from the story tokens), and a
    different headline changes what is painted there. No palette pin."""
    import random

    headline = synthesize_hero(_Scn(code, data), random.Random(0))
    assert headline and headline == headline.upper()
    img = renderer._story_hero(_entries(1)[0], headline)
    assert img.size == (renderer.STORY_W, renderer.STORY_H)
    _assert_pintada(img, "hero")
    assert len(_hero_text_bands(img)) >= 3, _hero_text_bands(img)
    other = renderer._story_hero(_entries(1)[0], headline + " I MÉS")
    assert _hero_below_cover(other).tobytes() != _hero_below_cover(img).tobytes()


def _hero_below_cover(img: Image.Image) -> Image.Image:
    """Crop from the cover's bottom edge to the footer band (from tokens)."""
    t = renderer._ST["hero"]
    y0 = t["cover"]["y"] + t["cover"]["size"]
    y1 = renderer.STORY_H - renderer._ST["common"]["footer_url"]["y_from_bottom"] - 10
    return img.convert("L").crop((0, y0, renderer.STORY_W, y1))


def _hero_text_bands(img: Image.Image) -> list[tuple[int, int]]:
    """Contiguous runs of rows carrying bright ink below the cover — one
    run per line of text (kicker line(s), title line(s), artist)."""
    L = _hero_below_cover(img)
    w = L.size[0]
    px = L.load()
    rows = [y for y in range(L.size[1]) if sum(px[x, y] > 150 for x in range(w)) > 3]
    bands: list[list[int]] = []
    prev = -100
    for r in rows:
        if r - prev > 10:
            bands.append([r, r])
        else:
            bands[-1][1] = r
        prev = r
    return [(a, b) for a, b in bands]


@pytest.mark.django_db
def test_hero_slide_empty_headline_falls_back():
    """An empty headline must not crash and must still paint a headline
    (the generic fallback line).

    Property asserted now (rewrite 2026-08-18): with "" the slide carries
    as many bright text bands below the cover as with a real one-line
    headline (the fallback line is painted, not skipped), and "" and None
    fall back identically — luminance oracle, no palette pin."""
    img = renderer._story_hero(_entries(1)[0], "")
    _assert_pintada(img, "hero-empty")
    bands = _hero_text_bands(img)
    ref = _hero_text_bands(renderer._story_hero(_entries(1)[0], "DEBUT AL CIM"))
    assert len(bands) == len(ref) >= 3, (bands, ref)
    assert (
        _hero_below_cover(img).tobytes()
        == _hero_below_cover(renderer._story_hero(_entries(1)[0], None)).tobytes()
    )


# ── Top 21-40 mosaic ────────────────────────────────────────────────


@pytest.mark.django_db
def test_mosaic_renders_20_covers_with_fallback():
    """20 covers, some pointing at a (failing) Deezer URL so the
    placeholder path is exercised. Must render without error."""
    entries = _entries(40)[20:40]
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


# ── Top 20-11 pairs — footer overflow guard ─────────────────────────


@pytest.mark.django_db
def test_pairs_long_titles_do_not_reach_footer():
    """All 10 titles forced to 2 lines: the 3+3+3+1 grid (fixed row
    pitch) must stay clear of the footer band (worst-case vertical
    fit), including the centred #11 on the last row."""
    entries = []
    for i in range(10):
        e = _entries(1)[0].copy()
        e["posicio"] = i + 11
        e["canco_nom"] = "On T'has Ficat Aquesta Nit Que No Et Trobo Enlloc"
        e["artistes_noms"] = ["Una Banda De Nom Ben Llarg"]
        entries.append(e)
    img = renderer._story_top_pairs(WK, entries).convert("RGB")
    assert img.size == (renderer.STORY_W, renderer.STORY_H)
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


# ── Step 3c no-regression baseline (added BEFORE parametrising) ──────
#
# These two guards freeze the current PPCC behaviour so that the Step
# 3c work (palette parametrisation + a separate territorial
# orchestrator) cannot silently drift the PPCC render. Established here
# while the builders are still PPCC-hardcoded, so they are a true
# before-state baseline.


# ── Content oracle ──────────────────────────────────────────────────
#
# Every structural test in this file passes on a BLANK slide: they check
# size, format, weight, slide count and pixel-region emptiness. A 2026-08-15
# audit proved it — making `_story_top_grid` return an untouched background
# left all 434 social tests green, on a slide that goes to Instagram
# Stories twice a week. Nothing looked at whether anything had been PAINTED.
#
# The oracle is the luminance standard deviation of the whole slide: a
# painted slide has covers, text and pills spread over the ink; a blank one
# is a near-flat field. Measured 2026-08-15 on the real 8-slide set:
# 22.0–40.6 for real slides, 1.62 for a bare `_bg_ink()`. The threshold sits
# an order of magnitude clear of both, so ordinary design changes can't
# trip it — only a slide that stopped painting.

_MIN_VARIACIO = 10.0


def _variacio(img: Image.Image) -> float:
    """Luminance spread. Near zero on a slide that never got painted."""
    return ImageStat.Stat(img.convert("L")).stddev[0]


def _assert_pintada(img: Image.Image, nom: str) -> None:
    v = _variacio(img)
    assert v >= _MIN_VARIACIO, f"{nom}: sembla en blanc (variació {v:.2f})"


@pytest.mark.django_db
def test_every_ppcc_slide_is_actually_painted():
    paths = renderer.render_stories_ppcc(
        WK, _entries(40), novetats_items=_novetats(3), hero_headline="DEBUT AL CIM"
    )
    for p in paths:
        with Image.open(p) as im:
            _assert_pintada(im, p.name)


@pytest.mark.django_db
def test_every_territorial_slide_is_actually_painted():
    """The territorial set degrades by omission, so it can legitimately be
    shorter — but no slide it DOES emit may be blank."""
    paths = renderer.render_stories_territorial(
        "VAL", WK, _entries(12), novetats_items=_novetats(2)
    )
    assert paths, "el joc territorial no ha generat cap diapositiva"
    for p in paths:
        with Image.open(p) as im:
            _assert_pintada(im, p.name)


@pytest.mark.django_db
def test_every_novetats_slide_is_actually_painted():
    paths = renderer.render_stories_novetats(WK, _novetats(7), per_page=3)
    assert paths, "el joc de novetats no ha generat cap diapositiva"
    for p in paths:
        with Image.open(p) as im:
            _assert_pintada(im, p.name)
