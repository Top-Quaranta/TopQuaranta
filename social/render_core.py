"""Shared PIL render primitives — the single engine behind the social slides.

# Spec: docs/architecture/social.md

DRY consolidation (2026-06): the primitives below used to live twice — once in
`feed_redesign.py` (feed novetats) and once, in a slightly different shape, in
`renderer.py` (the editorial stories). They are written ONCE here, parameterised
so each call site reproduces its previous output **pixel-for-pixel**:

  * `draw_text` covers both anchoring modes (em-box / cap-top / ink-top), both
    compositing modes (transparent-layer vs direct draw) and both glyph modes
    (whole-string when un-tracked vs glyph-by-glyph) — the feed used the former,
    the stories the latter.
  * `radial_bg` covers the feed gradient (clip the distance, float64) and the
    story gradient (divide by an outer stop, float32) via `stop`/`dtype`.
  * `star` covers the feed star (inner radius from tokens) and the story star
    (inner = 0.42·outer), composite or direct.

Geometry stays with each caller (feed: `feed-tokens.json`; stories: inline for
now). Already-shared, tested helpers (`cover_cache`, `svg_assets`,
`fonts`, `colors`) are CONSUMED, never reimplemented.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from social import fonts, svg_assets

# ── colour parsing ───────────────────────────────────────────────────

_RGB_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)"
)


def col(s: str) -> tuple[int, int, int, int]:
    """Parse an exact CSS `rgb()/rgba()` string OR a `#hex` to an RGBA tuple."""
    m = _RGB_RE.match(s.strip())
    if not m:
        h = s.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    r, g, b, a = m.groups()
    return (int(r), int(g), int(b), int(round(float(a) * 255)) if a else 255)


# ── text ─────────────────────────────────────────────────────────────


def layer(size) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def cap_offset(font) -> float:
    """Offset from a 'la'-anchored draw point to the cap-top ink (capital H)."""
    return font.getbbox("H", anchor="la")[1]


def tracked_width(d: ImageDraw.ImageDraw, text: str, font, tracking: float) -> float:
    """Advance width with `tracking` px added after every glyph but the last."""
    if not text:
        return 0.0
    return sum(d.textlength(ch, font=font) for ch in text) + tracking * (len(text) - 1)


def draw_text(
    canvas,
    x,
    y,
    text,
    font,
    fill,
    *,
    align="left",
    tracking=0.0,
    cap_top=None,
    ink_top=False,
    ink_center=None,
    glyphwise=None,
    composite=True,
) -> float:
    """Draw one line; return its advance width.

    Anchoring of `y`:
      * `cap_top` given → the glyph CAP-TOP ink (capital H) lands at `cap_top`.
      * `ink_center` given → this text's INK is vertically centred on `ink_center`
        (the ink bbox midpoint lands there — for numerals/pills inside a box).
      * `ink_top=True` → this text's bbox-top ink lands at `y`.
      * otherwise → `y` is the em-box top ('la').
    `align`: x is the left / centre / right edge. `tracking`: px after each glyph.
    `glyphwise`: None → auto (glyph-by-glyph iff tracking≠0). True forces it.
    `composite`: True → draw on a transparent layer then alpha-composite onto the
    `canvas` Image (alpha-correct). False → draw directly (canvas may be an Image
    or an ImageDraw).
    """
    if not text:
        return 0.0
    # advance metrics (font-only; any ImageDraw gives the same numbers)
    probe = ImageDraw.Draw(layer((1, 1)))
    advs = [probe.textlength(ch, font=font) for ch in text]
    total = sum(advs) + tracking * max(0, len(text) - 1)
    if align == "center":
        left = x - total / 2
    elif align == "right":
        left = x - total
    else:
        left = x
    if cap_top is not None:
        draw_y = cap_top - cap_offset(font)
    elif ink_center is not None:
        b = probe.textbbox((0, 0), text, font=font)
        draw_y = ink_center - (b[1] + b[3]) / 2
    elif ink_top:
        draw_y = y - probe.textbbox((0, 0), text, font=font)[1]
    else:
        draw_y = y

    if composite:
        lay = layer(canvas.size)
        d = ImageDraw.Draw(lay)
    else:
        d = (
            canvas
            if isinstance(canvas, ImageDraw.ImageDraw)
            else ImageDraw.Draw(canvas)
        )

    gw = (tracking != 0) if glyphwise is None else glyphwise
    if gw:
        cx = left
        for ch, adv in zip(text, advs):
            d.text((cx, draw_y), ch, font=font, fill=fill, anchor="la")
            cx += adv + tracking
    else:
        d.text((left, draw_y), text, font=font, fill=fill, anchor="la")

    if composite:
        canvas.alpha_composite(lay)
    return total


# ── shapes ───────────────────────────────────────────────────────────


def rect(img, box, *, fill=None, radius=0, outline=None, width=1):
    """Rounded rectangle, alpha-composited onto an RGBA `img`."""
    lay = layer(img.size)
    ImageDraw.Draw(lay).rounded_rectangle(
        box, radius=radius, fill=fill, outline=outline, width=width
    )
    img.alpha_composite(lay)


def star(canvas, cx, cy, r_out, fill, *, inner_ratio=0.42, points=5, composite=False):
    """Five-point star polygon. `inner_ratio` = inner/outer radius. Composite onto
    an RGBA Image, or draw directly (canvas = Image/ImageDraw)."""
    pts = []
    for i in range(points * 2):
        r = r_out if i % 2 == 0 else r_out * inner_ratio
        ang = -math.pi / 2 + i * math.pi / points
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    if composite:
        lay = layer(canvas.size)
        ImageDraw.Draw(lay).polygon(pts, fill=fill)
        canvas.alpha_composite(lay)
    else:
        d = (
            canvas
            if isinstance(canvas, ImageDraw.ImageDraw)
            else ImageDraw.Draw(canvas)
        )
        d.polygon(pts, fill=fill)


# ── texture / gradient ───────────────────────────────────────────────


def apply_grain(img, opacity, *, seed, round_alpha=True):
    """Deterministic gaussian grey noise at `opacity`, alpha-composited over the
    whole `img`. `round_alpha`: round the 0-255 alpha (cover/page) vs truncate
    (the album band) — kept as a flag so both historical call sites stay exact."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(128, 38, (img.height, img.width)).clip(0, 255).astype(np.uint8)
    a255 = int(round(opacity * 255)) if round_alpha else int(opacity * 255)
    a = np.full((img.height, img.width), a255, np.uint8)
    img.alpha_composite(Image.fromarray(np.dstack([noise, noise, noise, a]), "RGBA"))


def radial_bg(
    size, inner_hex, outer_hex, center, radii, *, stop=1.0, dtype="float64", mode="RGBA"
):
    """Elliptical radial gradient (`inner_hex` centre → `outer_hex`). `center`
    and `radii` are fractions of `size`. `t = clip(dist/stop, 0, 1)`. `dtype`
    selects float32 (story) or float64 (feed) so each caller stays exact."""
    w, h = size
    (fx, fy), (rx_f, ry_f) = center, radii
    cx, cy, rx, ry = fx * w, fy * h, rx_f * w, ry_f * h
    yy, xx = np.mgrid[0:h, 0:w].astype(dtype)
    dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    t = np.clip(dist / stop, 0.0, 1.0)[..., None]
    a = np.array(col(inner_hex)[:3], dtype)
    b = np.array(col(outer_hex)[:3], dtype)
    arr = (a * (1 - t) + b * t).astype(np.uint8)
    out = Image.fromarray(arr, "RGB")
    return out.convert("RGBA") if mode == "RGBA" else out


# ── logo (mono) ──────────────────────────────────────────────────────


def logo_mono(width: int, hex_color: str):
    """Monochrome brand wordmark at `width`, recoloured to `hex_color`."""
    return svg_assets.logo_image_mono(width, hex_color)


def paste_logo(img, *, h, x, y, align="left", hex_color="#ffffff"):
    """Place the mono logo of height `h` at (x, y); `align` left/center/right."""
    width = int(round(h * svg_assets.LOGO_ASPECT))
    logo = logo_mono(width, hex_color)
    if logo is None:
        return
    lx = {"center": x - logo.width / 2, "right": x - logo.width}.get(align, x)
    img.alpha_composite(logo.convert("RGBA"), (int(round(lx)), int(round(y))))


# ── territory code resolution (palette values stay with each caller) ──

# DB territory code → editorial design key. ALT/CAR included; CAT resolves to
# `pri` (the SENYERA silhouette), never the cross.
CODE_TO_KEY = {
    "CAT": "pri",
    "VAL": "val",
    "BAL": "bal",
    "CNO": "nor",
    "NOR": "nor",
    "FRA": "fra",
    "AND": "and",
    "ALG": "alg",
    "ALT": "alt",
    "CAR": "car",
}


def terr_key(code: str | None, *, fallback="pri") -> str:
    """Design key (pri/val/…) for a DB territory code; `fallback` if unknown."""
    return CODE_TO_KEY.get((code or "").upper(), fallback)


# ── territorial silhouette (singles chip) ─────────────────────────────


@lru_cache(maxsize=16)
def _silhouette_base(path: str):
    return Image.open(path).convert("RGBA")


def silhouette(png_path, accent, w: int, h: int):
    """Territory silhouette PNG recoloured to `accent` (alpha = shape), resized
    to (w, h)."""
    base = _silhouette_base(str(png_path))
    silh = Image.new("RGBA", base.size, tuple(accent))
    silh.putalpha(base.getchannel("A"))
    return silh.resize((max(1, w), max(1, h)), Image.LANCZOS)


# ── fallback tile ────────────────────────────────────────────────────


def tile(
    size,
    deep,
    accent,
    initial,
    *,
    initial_frac=0.5,
    simple=False,
    keyline=None,
    footer=None,
):
    """Square fallback tile: `deep` bg, big `initial` (at `initial_frac`·size) in
    `accent`. When not `simple`, draws an `accent` keyline + a footer wordmark.
    `keyline`/`footer` are token dicts. Pure: colours are RGBA tuples, geometry
    is fractions of `size`."""
    img = Image.new("RGBA", (size, size), deep)
    f = fonts.anton(int(round(size * initial_frac)))
    ImageDraw.Draw(img).text(
        (size / 2, size / 2), initial, font=f, fill=accent, anchor="mm"
    )
    if simple:
        return img
    if keyline:
        inset = int(round(size * keyline["inset_frac"]))
        ar, ag, ab = accent[:3]
        ImageDraw.Draw(img).rectangle(
            (inset, inset, size - inset, size - inset),
            outline=(ar, ag, ab, int(keyline["alpha"] * 255)),
            width=keyline["width"],
        )
    if footer:
        lay = layer((size, size))
        d = ImageDraw.Draw(lay)
        f2 = fonts.anton(max(8, int(round(size * footer["size_frac"]))))
        txt = footer["text"]
        advs = [d.textlength(c, font=f2) for c in txt]
        tw = sum(advs) + footer["ls"] * (len(txt) - 1)
        cx = size / 2 - tw / 2
        fy = size * footer["y_off_frac"]
        for c, adv in zip(txt, advs):
            d.text((cx, fy), c, font=f2, fill=footer["color"], anchor="la")
            cx += adv + footer["ls"]
        img.alpha_composite(lay)
    return img


# ── text wrap ────────────────────────────────────────────────────────


def wrap(d, text, font, budget):
    """Greedy word-wrap to `budget` px width. Returns the list of lines."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and d.textlength(trial, font=font) > budget:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


# ── movement indicator (TOP) ──────────────────────────────────────────

# Semantic, palette-independent movement colours (read at a glance, never
# recoloured per territory). From the Claude Design top-kit.
MOVE_COLORS = {
    "up": (123, 191, 123, 255),  # green — climbs
    "down": (221, 120, 130, 255),  # soft red — drops
    "new": (250, 204, 21, 255),  # yellow — new entry
    "re": (232, 164, 77, 255),  # amber — re-entry
    "eq": (255, 255, 255, 102),  # neutral — same position (alpha .40)
}


def parse_move(posicio, posicio_anterior, *, reentry=False):
    """Classify a chart movement from real data.

    `posicio_anterior is None` ⇒ the track was NOT in last week's top → a new
    entry ("new") unless the caller proves it's a re-entry (`reentry=True`,
    derived from older history). Otherwise the delta drives up/down/eq.
    Returns `(kind, n)` with kind ∈ {up, down, new, re, eq}."""
    if posicio_anterior is None:
        return ("re", 0) if reentry else ("new", 0)
    delta = int(posicio_anterior) - int(posicio)
    if delta > 0:
        return ("up", delta)
    if delta < 0:
        return ("down", -delta)
    return ("eq", 0)


def draw_move(img, right_x, cy, kind, n, *, size=24, variant="full"):
    """Draw a movement indicator right-aligned ending at `right_x`, vertically
    centred on `cy`. `variant`: 'full' shows the delta number after the arrow,
    'compact' the arrow/symbol only. One primitive for poster + list."""
    col_ = MOVE_COLORS[kind]
    d = ImageDraw.Draw(img)
    if kind in ("up", "down"):
        tri_h = size * 0.62
        tri_w = tri_h * 0.86
        gap = size * 0.26
        num_fs = size * 0.92
        num = str(n) if variant == "full" else ""
        f = fonts.bricolage_xbold(int(round(num_fs))) if num else None
        num_w = tracked_width(d, num, f, 0) if num else 0.0
        total = tri_w + (gap + num_w if num else 0)
        x0 = right_x - total
        # triangle (apex up for 'up', down for 'down')
        cxk = x0 + tri_w / 2
        top, bot = cy - tri_h / 2, cy + tri_h / 2
        if kind == "up":
            pts = [(cxk, top), (x0, bot), (x0 + tri_w, bot)]
        else:
            pts = [(x0, top), (x0 + tri_w, top), (cxk, bot)]
        d.polygon(pts, fill=col_)
        if num:
            # number ink-centred vertically on cy
            bbox = f.getbbox(num, anchor="la")
            draw_text(
                img,
                x0 + tri_w + gap,
                cy - (bbox[3] - bbox[1]) / 2 - bbox[1],
                num,
                f,
                col_,
                ink_top=False,
                composite=False,
            )
        return
    if kind in ("new", "re"):
        txt = "NOU" if kind == "new" else "RE"
        fs = size * (0.86 if kind == "new" else 0.78)
        ls = size * (0.04 if kind == "new" else 0.03)
        f = fonts.anton(int(round(fs)))
        w = tracked_width(d, txt, f, ls)
        bbox = f.getbbox(txt, anchor="la")
        draw_text(
            img,
            right_x,
            cy - (bbox[3] - bbox[1]) / 2 - bbox[1],
            txt,
            f,
            col_,
            align="right",
            tracking=ls,
            glyphwise=True,
            composite=False,
        )
        return
    # eq — short neutral bar
    bar_w, bar_h = size * 0.66, max(2, size * 0.12)
    d.rounded_rectangle(
        (right_x - bar_w, cy - bar_h / 2, right_x, cy + bar_h / 2), radius=1, fill=col_
    )
