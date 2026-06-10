"""Editorial "Sèrie 7" PIL redesign of the three novetats feed slides.

# Spec: social/feed_design/FEED-PIL-SPEC.md

Additive and **gated** by `ConfiguracioGlobal.feed_redisseny_actiu` (default
False). The renderer delegates here only when the flag is on; otherwise the
legacy builders in `renderer.py` run byte-for-byte.

Scope is strictly the *maquetació* of:
  • the carousel cover (`build_cover`),
  • the single-album slide (`build_album`),
  • the singles grid (`build_singles`).

It does NOT touch album selection, singles bin-packing, per-channel gating,
idempotency, or where covers come from: covers are fetched with the exact same
`cover_cache.fetch(url)` Deezer path the legacy code uses; only the *visual* of
the cover-missing tile changes (per the spec's fallback rule).

Every numeric/colour value is read from `feed_design/feed-tokens.json`, the
measured source of truth. Rendering is deterministic (fixed grain seed) so the
output is stable for tests and review renders.

Truth hierarchy: the Claude Design reference PNGs
(`social/feed_design/samples/` mirror them) win over `feed-tokens.json`,
which was an approximate measurement; the JSON is still the default source
for values the PNGs don't pin. Bricolage Grotesque is vendored at all three
spec weights (500 Medium / 700 Bold / 800 ExtraBold).
"""

from __future__ import annotations

import datetime
import functools
import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from social import cover_cache, fonts, svg_assets

logger = logging.getLogger(__name__)

_DESIGN_DIR = Path(__file__).resolve().parent / "feed_design"
_TOKENS_PATH = _DESIGN_DIR / "feed-tokens.json"

CANVAS_W, CANVAS_H = 1080, 1350

# Deterministic grain so renders are reproducible across runs/tests.
_GRAIN_SEED = 7


@functools.lru_cache(maxsize=1)
def tokens() -> dict:
    """The measured token table (`feed-tokens.json`), cached."""
    with open(_TOKENS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ── colour helpers ───────────────────────────────────────────────────


def _rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgba(hex_or_rgb, alpha: float) -> tuple[int, int, int, int]:
    if isinstance(hex_or_rgb, str):
        r, g, b = _rgb(hex_or_rgb)
    else:
        r, g, b = hex_or_rgb
    return (r, g, b, int(round(alpha * 255)))


# DB territory code → spec territory key. The JSON uses `nor` for Catalunya
# Nord (DB code `CNO`); everything else matches the abbr. Aggregate/unknown
# codes (PPCC, ALT, CAR, …) fall back to the PPCC green anchors.
_CODE_TO_KEY = {
    "CAT": "pri",
    "VAL": "val",
    "BAL": "bal",
    "CNO": "nor",
    "NOR": "nor",
    "FRA": "fra",
    "AND": "and",
    "ALG": "alg",
}


def territori(code: str | None) -> dict:
    """Resolve a DB territory code to `{deep, accent, abbr, short, name}`.

    Unknown / aggregate codes fall back to the PPCC green anchors so the
    function is total (it never raises on a future code)."""
    t = tokens()
    key = _CODE_TO_KEY.get((code or "").upper())
    if key and key in t["territories"]:
        return t["territories"][key]
    a = t["brand_anchors"]
    return {
        "name": "Països Catalans",
        "short": "Global",
        "abbr": (code or "PPCC").upper()[:4],
        "deep": a["green_deep"],
        "accent": a["green_light"],
    }


# ── font helpers ─────────────────────────────────────────────────────


def _font(role: str, size: int, weight: int = 800):
    """Map a spec font role to a vendored loader. `bricolage` honours the
    spec weight (500 Medium / 700 Bold / 800 ExtraBold) — the three OFL
    statics are vendored at `social/fonts/`."""
    if role == "anton":
        return fonts.anton(size)
    if role == "playfair":
        return fonts.display_xbold(size)
    if role == "instrument":
        return fonts.instrument_italic(size)
    if role == "bricolage":
        if weight <= 500:
            return fonts.bricolage_medium(size)
        if weight <= 700:
            return fonts.bricolage_bold(size)
        return fonts.bricolage_xbold(size)
    raise ValueError(f"unknown font role {role!r}")


def _text(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font,
    fill,
    *,
    align: str = "left",
    tracking: float = 0.0,
):
    """Draw a single line whose top-left box corner is `(x, y)` for
    `align="left"`. For `center`, `x` is the centre; for `right`, `x` is the
    right edge. `tracking` (letter-spacing, px) is honoured by drawing glyph
    by glyph. `y` is the top of the cap box (PIL anchor "a")."""
    if not text:
        return
    advances = [draw.textlength(ch, font=font) for ch in text]
    total = sum(advances) + tracking * max(0, len(text) - 1)
    if align == "center":
        cx = x - total / 2
    elif align == "right":
        cx = x - total
    else:
        cx = x
    if tracking == 0:
        draw.text((cx, y), text, font=font, fill=fill, anchor="la")
        return
    for ch, adv in zip(text, advances):
        draw.text((cx, y), ch, font=font, fill=fill, anchor="la")
        cx += adv + tracking


# ── texture helpers ──────────────────────────────────────────────────


def _grain(w: int, h: int, opacity: float) -> Image.Image:
    """Deterministic monochrome grain as an RGBA overlay. A subtle linear
    blend toward grey noise — a pragmatic stand-in for the SVG soft-light/
    overlay filter (close enough at these low opacities)."""
    rng = np.random.default_rng(_GRAIN_SEED)
    noise = rng.normal(128, 38, size=(h, w)).clip(0, 255).astype(np.uint8)
    a = np.full((h, w), int(round(opacity * 255)), dtype=np.uint8)
    arr = np.dstack([noise, noise, noise, a])
    return Image.fromarray(arr, "RGBA")


def _apply_grain(img: Image.Image, opacity: float) -> None:
    g = _grain(img.width, img.height, opacity)
    img.alpha_composite(g)


def _radial_green(w: int, h: int, inner: str, outer: str) -> Image.Image:
    """`radial-gradient(130% 80% at 50% 0%, inner → outer)`."""
    cx, cy = w / 2.0, 0.0
    # Tighter core so the top-centre glow reads and the edges fall to deep
    # green (the JSON's 1.30×/0.80× was too gradual → looked flat).
    rx, ry = 1.05 * w, 0.72 * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    d = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    t = np.clip(d, 0.0, 1.0)[..., None]
    a = np.array(_rgb(inner), dtype=np.float64)
    b = np.array(_rgb(outer), dtype=np.float64)
    arr = (a * (1 - t) + b * t).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


# ── cover / fallback tile ────────────────────────────────────────────


def _cover_or_tile(cover_url: str | None, size: int, title: str, terr: dict):
    """Square cover at `size`. Uses the SAME Deezer fetch as the legacy path
    (`cover_cache.fetch`); on miss, renders the spec fallback tile. Returns
    (RGBA image, used_fallback)."""
    img = cover_cache.fetch(cover_url) if cover_url else None
    if img is not None:
        return img.convert("RGBA").resize((size, size), Image.LANCZOS), False
    return _fallback_tile(size, title, terr), True


def _fallback_tile(size: int, title: str, terr: dict) -> Image.Image:
    """Spec fallback (cover == null): deep-fill tile, big initial in accent,
    inner keyline, TOPQUARANTA footer."""
    img = Image.new("RGBA", (size, size), _rgb(terr["deep"]) + (255,))
    d = ImageDraw.Draw(img)
    initial = (title or "?").strip()[:1].upper() or "?"
    f_init = _font("anton", int(size * 0.5))
    d.text((size / 2, size / 2), initial, font=f_init, fill=terr["accent"], anchor="mm")
    inset = int(round(size * 0.06))
    d.rounded_rectangle(
        (inset, inset, size - inset, size - inset),
        radius=0,
        outline=_rgba(terr["accent"], 0.4),
        width=2,
    )
    f_foot = _font("anton", max(8, int(size * 0.04)))
    _text(
        d,
        size / 2,
        size - int(round(size * 0.07)),
        "TOPQUARANTA",
        f_foot,
        _rgba("#ffffff", 0.5),
        align="center",
        tracking=4,
    )
    return img


def _paste_logo(img: Image.Image, *, height: int, x, y: int, align: str = "left"):
    """White wordmark at the given height. `x` is left/centre/right per align;
    `align="right"` treats `x` as the right edge."""
    width = int(round(height * svg_assets.LOGO_ASPECT))
    logo = svg_assets.logo_image_mono(width, "#ffffff")
    if logo is None:
        return
    if align == "center":
        lx = int(round(x - logo.width / 2))
    elif align == "right":
        lx = int(round(x - logo.width))
    else:
        lx = int(round(x))
    img.alpha_composite(logo.convert("RGBA"), (lx, y))


def _finish(img: Image.Image) -> Image.Image:
    """Flatten RGBA → RGB on ink so JPEG save matches the legacy contract."""
    bg = Image.new("RGB", img.size, _rgb(tokens()["brand_anchors"]["ink"]))
    bg.paste(img, (0, 0), img)
    return bg


def _ellipsize(draw, text: str, font, max_w: float) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return (text + ell) if text else ell


def _wrap_two(draw, text: str, font, max_w: float) -> tuple[str, str]:
    """Greedy break into (line1, line2). Line2 may still overflow (caller
    ellipsizes it). Keeps as many words on line1 as fit."""
    words = text.split()
    line1: list[str] = []
    for i, w in enumerate(words):
        trial = " ".join(line1 + [w])
        if line1 and draw.textlength(trial, font=font) > max_w:
            return " ".join(line1), " ".join(words[i:])
        line1.append(w)
    return " ".join(line1), ""


# ── slide 1 · carousel cover ─────────────────────────────────────────


def build_cover(tipus: str, setmana: datetime.date) -> Image.Image:
    """Camp verd. `tipus` ∈ {nous_albums, nous_singles}."""
    from .captions import _setmana_label

    t = tokens()
    anchors = t["brand_anchors"]
    is_albums = tipus == "nous_albums"
    etiqueta_txt = "ÀLBUMS" if is_albums else "SINGLES"
    cadencia_txt = "cada dimarts" if is_albums else "cada divendres"

    # Brighter highlight at top-centre than the flat #427c42→#2f5a2f the
    # JSON measured: the reference cover has a clear radial glow. We lift the
    # inner toward a lighter green and keep the brand-green deep edge.
    img = _radial_green(CANVAS_W, CANVAS_H, "#4f9450", anchors["green_deep"])
    _apply_grain(img, t["grain"]["layers"]["cover"]["opacity"])
    d = ImageDraw.Draw(img)

    _paste_logo(img, height=48, x=CANVAS_W / 2, y=88, align="center")
    d = ImageDraw.Draw(img)
    _text(
        d,
        CANVAS_W / 2,
        166,
        "aquesta setmana presenta",
        _font("instrument", 48),
        anchors["cream"],
        align="center",
    )
    # ── Overlapping NOVETATS / ÀLBUMS block ──────────────────────────
    # The big word fills the width at ~250 px (shrink only if it would
    # overflow); NOVETATS sits smaller, above and nudged right, overlapping
    # the top of the yellow word. Drop shadow on the big word (0, +8,
    # rgba(0,0,0,0.16)) for the embossed feel of the reference.
    margin = 70
    max_w = CANVAS_W - 2 * margin
    big_track = 1.25
    big_size = 250

    def _big_w(sz: int) -> float:
        fn = _font("anton", sz)
        return sum(d.textlength(c, font=fn) for c in etiqueta_txt) + big_track * (
            len(etiqueta_txt) - 1
        )

    while _big_w(big_size) > max_w and big_size > 180:
        big_size -= 4
    f_big = _font("anton", big_size)
    big_top = 392
    _text(
        d,
        CANVAS_W / 2,
        big_top + 8,
        etiqueta_txt,
        f_big,
        _rgba("#000000", 0.16),
        align="center",
        tracking=big_track,
    )
    _text(
        d,
        CANVAS_W / 2,
        big_top,
        etiqueta_txt,
        f_big,
        anchors["yellow"],
        align="center",
        tracking=big_track,
    )
    # NOVETATS overlaps the big word's top by ~50 px and is nudged right.
    _text(
        d,
        CANVAS_W / 2 + 36,
        big_top - 30,
        "NOVETATS",
        _font("anton", 116),
        "#ffffff",
        align="center",
    )

    # Star + flanking rules.
    star_y = 1139
    f_star = _font("anton", 24)
    _text(d, CANVAS_W / 2, star_y, "★", f_star, anchors["yellow"], align="center")
    sw = d.textlength("★", font=f_star)
    rule_col = _rgba("#ffffff", 0.34)
    gap = 18
    for sign in (-1, 1):
        x0 = CANVAS_W / 2 + sign * (sw / 2 + gap)
        x1 = x0 + sign * 150
        d.line(
            [(min(x0, x1), star_y + 14), (max(x0, x1), star_y + 14)],
            fill=rule_col,
            width=2,
        )

    # Bottom row: SETMANA pill (yellow, ink, real project-week number) +
    # cadència whisper, centred together with gap 22.
    setmana_txt = _setmana_label(setmana).upper()
    f_pill = _font("anton", 38)
    pad_x, pad_y = 20, 7
    pill_tw = sum(d.textlength(c, font=f_pill) for c in setmana_txt) + 2 * (
        len(setmana_txt) - 1
    )
    pill_w = pill_tw + 2 * pad_x
    pill_h = 38 + 2 * pad_y
    f_cad = _font("instrument", 40)
    cad_w = d.textlength(cadencia_txt, font=f_cad)
    gap = 22
    group_w = pill_w + gap + cad_w
    gx = CANVAS_W / 2 - group_w / 2
    py = 1206
    d.rounded_rectangle(
        (gx, py, gx + pill_w, py + pill_h), radius=8, fill=anchors["yellow"]
    )
    _text(d, gx + pad_x, py + pad_y, setmana_txt, f_pill, anchors["ink"], tracking=2)
    _text(d, gx + pill_w + gap, py + (pill_h - 40) / 2, cadencia_txt, f_cad, "#ffffff")

    return _finish(img)


# ── slide 2 · single album ───────────────────────────────────────────


def build_album(item: dict) -> Image.Image:
    t = tokens()
    sl = t["slides"]["2_album"]
    anchors = t["brand_anchors"]
    terr = territori(item.get("artista_territori"))

    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), _rgb(anchors["ink"]) + (255,))
    _apply_grain(img, t["grain"]["layers"]["album_page"]["opacity"])

    # Hero cover 660, centred horizontally, per the measured y.
    size = sl["cover"]["size"]
    cover, _fb = _cover_or_tile(item.get("cover_url"), size, item.get("nom", "?"), terr)
    cx = (CANVAS_W - size) // 2
    cy = sl["cover"]["y"]
    # Soft drop shadow.
    shadow = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rectangle((cx, cy + 24, cx + size, cy + size + 24), fill=(0, 0, 0, 115))
    shadow = shadow.filter(ImageFilter.GaussianBlur(30))
    img.alpha_composite(shadow)
    img.alpha_composite(cover, (cx, cy))
    # Inset keyline on the cover.
    ImageDraw.Draw(img).rectangle(
        (cx, cy, cx + size - 1, cy + size - 1), outline=_rgba("#ffffff", 0.07), width=1
    )

    # Territory band along the bottom.
    band = sl["band"]
    by = band["y"]
    band_img = Image.new(
        "RGBA", (CANVAS_W, band["height"]), _rgb(terr["deep"]) + (255,)
    )
    _apply_grain(band_img, t["grain"]["layers"]["album_band"]["opacity"])
    img.alpha_composite(band_img, (0, by))

    d = ImageDraw.Draw(img)
    _paste_logo(img, height=42, x=80, y=70)
    d = ImageDraw.Draw(img)
    _text(
        d,
        1000,
        73,
        "NOU ÀLBUM",
        _font("anton", 24),
        terr["accent"],
        align="right",
        tracking=5,
    )

    # Title (Playfair) + artist (Bricolage) inside the band. One line at 76;
    # if it overflows, wrap to two lines at 60 (raised) like the reference.
    budget = CANVAS_W - 80 - 320
    f_title = _font("playfair", 76)
    if d.textlength(item["nom"], font=f_title) <= budget:
        _text(d, 80, 1162, item["nom"], f_title, "#ffffff")
    else:
        f2 = _font("playfair", 60)
        l1, l2 = _wrap_two(d, item["nom"], f2, budget)
        _text(d, 80, 1133, l1, f2, "#ffffff")
        _text(d, 80, 1196, _ellipsize(d, l2, f2, budget), f2, "#ffffff")
    _text(
        d,
        80,
        1246,
        item.get("artista_nom", "—"),
        _font("bricolage", 38, 700),
        _rgba("#ffffff", 0.85),
    )

    # Territory abbr + FULL name, right-aligned in the band.
    _text(
        d,
        1000,
        1228,
        terr["abbr"],
        _font("anton", 22),
        terr["accent"],
        align="right",
        tracking=2,
    )
    _text(
        d,
        1000,
        1261,
        terr["name"],
        _font("bricolage", 26, 700),
        "#ffffff",
        align="right",
    )

    return _finish(img)


# ── slide 3 · singles grid ───────────────────────────────────────────


def build_singles(
    items: list[dict], page: int, total_pages: int, setmana=None
) -> Image.Image:
    """Up to 10 rows. `page`/`total_pages` come from the caller's bin-packing
    (unchanged); this only lays the rows out. `setmana` (ISO Monday) feeds the
    week number in the subtitle. PPCC is never rendered as a row territory —
    aggregate-only items are skipped (blinded)."""
    t = tokens()
    sl = t["slides"]["3_singles"]
    anchors = t["brand_anchors"]

    # Blind PPCC: it is the global aggregate, never a real row territory.
    items = [e for e in items if (e.get("artista_territori") or "").upper() != "PPCC"]

    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), _rgb(anchors["ink"]) + (255,))
    _apply_grain(img, t["grain"]["layers"]["singles_page"]["opacity"])
    d = ImageDraw.Draw(img)

    # Header.
    _text(d, 70, 43, "NOVETATS", _font("anton", 76), "#ffffff", tracking=0.76)
    _text(d, 70, 111, "SINGLES", _font("anton", 76), anchors["yellow"])
    subtitol = "estrenes de la setmana"
    if setmana is not None:
        from music.dates import project_week_number

        subtitol = "estrenes de la setmana %d" % project_week_number(
            setmana + datetime.timedelta(days=5)
        )
    _text(d, 70, 211, subtitol, _font("instrument", 34), _rgba("#ffffff", 0.62))
    _paste_logo(img, height=42, x=1010, y=70, align="right")
    d = ImageDraw.Draw(img)

    rows = sl["rows"]
    y_starts = rows["row_y_starts"]
    row_h = rows["row_height"]
    cells = rows["cells"]
    for i, e in enumerate(items[: rows["count_max"]]):
        y = y_starts[i]
        terr = territori(e.get("artista_territori"))

        # Row background card + keyline.
        d.rounded_rectangle(
            (
                rows["container"]["x"],
                y,
                rows["container"]["x"] + rows["container"]["width"],
                y + row_h,
            ),
            radius=10,
            fill=_rgba("#ffffff", 0.035),
            outline=_rgba("#ffffff", 0.06),
            width=1,
        )

        # Territory chip (deep) with abbr (accent).
        ch = cells["terr_chip"]
        d.rounded_rectangle(
            (ch["x"], y, ch["x"] + ch["width"], y + row_h),
            radius=10,
            fill=_rgb(terr["deep"]),
        )
        _text(
            d,
            ch["x"] + ch["width"] / 2,
            y + row_h / 2 - 13,
            terr["abbr"],
            _font("anton", ch["abbr"]["size"]),
            terr["accent"],
            align="center",
        )

        # Thumb 72, vertically centred.
        thumb = cells["thumb"]
        tsize = thumb["size"]
        cover, _fb = _cover_or_tile(e.get("cover_url"), tsize, e.get("nom", "?"), terr)
        ty = y + (row_h - tsize) // 2
        img.alpha_composite(cover, (thumb["x"], ty))

        # Title + artist.
        tx = cells["titol"]["x"]
        right_label_x = 1010 - cells["terr_short"]["padding_right"]
        text_w = right_label_x - tx - 16
        f_title = _font("bricolage", cells["titol"]["size"], 800)
        f_artist = _font("bricolage", cells["artista"]["size"], 500)
        title = _ellipsize(d, e["nom"], f_title, text_w)
        artist = _ellipsize(d, e.get("artista_nom", "—"), f_artist, text_w)
        _text(d, tx, y + 14, title, f_title, "#ffffff")
        _text(d, tx, y + 50, artist, f_artist, _rgba("#ffffff", 0.66))

        # Territory short name (Instrument italic), right.
        _text(
            d,
            1010,
            y + row_h / 2 - 13,
            terr["short"],
            _font("instrument", cells["terr_short"]["size"]),
            _rgba("#ffffff", 0.5),
            align="right",
        )

    # Footer: url + page indicator (only when multi-page).
    foot = sl["footer"]
    _text(
        d,
        foot["left"]["x"],
        foot["y"],
        "topquaranta.cat",
        _font("instrument", foot["left"]["size"]),
        _rgba("#ffffff", 0.55),
    )
    if total_pages > 1:
        _draw_page_indicator(d, page, total_pages, foot)

    return _finish(img)


def _draw_page_indicator(d, page: int, total: int, foot: dict) -> None:
    pi = foot["page_indicator"]
    dots = pi["dots"]
    label = f"{page:02d} / {total:02d}"
    f_lab = _font("bricolage", pi["label"]["size"], 700)
    lab_w = sum(d.textlength(c, font=f_lab) for c in label) + (len(label) - 1) * 1
    right = 1010
    lab_x = right - lab_w
    _text(d, lab_x, foot["y"], label, f_lab, _rgba("#ffffff", 0.6), tracking=1)

    # Dots to the left of the label.
    x = lab_x - pi["gap_to_label"]
    dot_y = foot["y"] + 6
    for i in range(total - 1, -1, -1):
        active = i == (page - 1)
        w = dots["active_width"] if active else dots["inactive_width"]
        col = dots["active_color"] if active else dots["inactive_color"]
        col = col if isinstance(col, str) else col
        x0 = x - w
        fill = _rgb(dots["active_color"]) if active else _rgba("#ffffff", 0.25)
        d.rounded_rectangle(
            (x0, dot_y, x, dot_y + dots["height"]), radius=dots["radius"], fill=fill
        )
        x = x0 - dots["gap"]
