"""Duotone artwork treatment for feed cover slides (2026-07).

Normative layer spec transcribed from the approved mocks
(`preview-portades-ig.html` / `preview-dijous-i-fites.html`): the CSS
`.bg` stack, reproduced exactly in Pillow. Colours are NOT hardcoded
here — callers pass the edition's real palette (accent + hue) from
`feed_redesign.territori()` / the top-cover field. Only the treatment
(greyscale/contrast/brightness, multiply tint, hue veil opacity, the
readability gradient stops) is fixed, per the mock.

# Spec: docs/architecture/social.md

Layer order over the photo (mock `.bg`):
  1. photo   — cover-fit centred, greyscale, contrast 1.06, brightness 1.02
  2. tint    — accent colour, MULTIPLY blend, opacity 100%
  3. hue     — edition background colour, NORMAL blend, opacity 0.30
  4. veil    — vertical gradient of rgba(8,10,6) with alpha
               0.66@0% · 0.16@30% · 0.16@56% · 0.72@100%

The mosaic variant tiles N covers (2×2 for 4-5, 2×3 for 6+) with the
per-tile greyscale+contrast, then applies layers 2-4 once over the set.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageOps

# Readability veil (mock `.veil`): rgba(8,10,6) at these piecewise-linear
# alpha stops down the canvas height.
_VEIL_RGB = (8, 10, 6)
_VEIL_STOPS_POS = (0.0, 0.30, 0.56, 1.0)
_VEIL_STOPS_A = (0.66, 0.16, 0.16, 0.72)
_HUE_OPACITY = 0.30

# Per-tile photo treatment (mock `.ph` / `.mosaic .t`).
_CONTRAST = 1.06
_BRIGHTNESS = 1.02  # applied to the single-photo layer only (mock `.ph`)


def _as_rgb(color) -> tuple[int, int, int]:
    """Accept '#rrggbb', 'rgb(r, g, b)', or an (r,g,b[,a]) tuple."""
    if isinstance(color, (tuple, list)):
        return (int(color[0]), int(color[1]), int(color[2]))
    s = str(color).strip()
    if s.startswith("#"):
        h = s.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    if s.startswith("rgb"):
        nums = s[s.index("(") + 1 : s.index(")")].split(",")
        return (int(nums[0]), int(nums[1]), int(nums[2]))
    raise ValueError(f"unrecognised colour {color!r}")


def _greyscale(img: Image.Image, *, brightness: bool) -> Image.Image:
    """Layer 1: cover-fit already done by caller. Greyscale → contrast
    → (optional) brightness. Returns RGB."""
    g = ImageOps.grayscale(img).convert("RGB")
    g = ImageEnhance.Contrast(g).enhance(_CONTRAST)
    if brightness:
        g = ImageEnhance.Brightness(g).enhance(_BRIGHTNESS)
    return g


def _tint_and_hue(base_rgb: Image.Image, accent, hue) -> Image.Image:
    """Layers 2-3 over an RGB greyscale base. Multiply tint (accent,
    opacity 1.0), then normal hue layer (edition bg, opacity 0.30).
    Returns RGB."""
    w, h = base_rgb.size
    accent_solid = Image.new("RGB", (w, h), _as_rgb(accent))
    tinted = ImageChops.multiply(base_rgb, accent_solid)
    hue_solid = Image.new("RGB", (w, h), _as_rgb(hue))
    return Image.blend(tinted, hue_solid, _HUE_OPACITY)


def _veil(size: tuple[int, int]) -> Image.Image:
    """Layer 4: the vertical readability gradient as an RGBA overlay."""
    w, h = size
    ys = np.linspace(0.0, 1.0, h)
    alpha = np.interp(ys, _VEIL_STOPS_POS, _VEIL_STOPS_A)  # (h,)
    a = np.rint(np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    col = np.zeros((h, w, 4), dtype=np.uint8)
    col[..., 0], col[..., 1], col[..., 2] = _VEIL_RGB
    col[..., 3] = a[:, None]
    return Image.fromarray(col, "RGBA")


def _fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(
        img.convert("RGB"), size, method=Image.LANCZOS, centering=(0.5, 0.5)
    )


def duotone_photo(
    photo: Image.Image, accent, hue, size: tuple[int, int]
) -> Image.Image:
    """Single-photo duotone background (mock `.ph` + tint/hue/veil).
    Returns RGBA at `size`, ready to draw text on."""
    base = _greyscale(_fit(photo, size), brightness=True)
    treated = _tint_and_hue(base, accent, hue).convert("RGBA")
    treated.alpha_composite(_veil(size))
    return treated


def _grid_shape(n: int) -> tuple[int, int, int]:
    """(cols, rows, used) for n covers: 2×3 if ≥6 (use 6), else 2×2 (use 4).
    Callers guarantee n≥2 (fewer falls back to the typographic cover)."""
    if n >= 6:
        return 2, 3, 6
    return 2, 2, 4


def duotone_mosaic(
    photos: list[Image.Image], accent, hue, size: tuple[int, int]
) -> Image.Image:
    """Mosaic duotone background: greyscale+contrast per tile (no
    brightness, per mock `.mosaic .t`), gapless grid, then tint/hue/veil
    once over the whole. Requires len(photos) >= 2."""
    if len(photos) < 2:
        raise ValueError("duotone_mosaic needs >= 2 photos")
    cols, rows, used = _grid_shape(len(photos))
    photos = photos[:used]
    w, h = size
    cw, ch = w // cols, h // rows
    grid = Image.new("RGB", (w, h))
    for i, ph in enumerate(photos):
        r, c = divmod(i, cols)
        # Last col/row absorbs rounding so no seam is left uncovered.
        tw = w - c * cw if c == cols - 1 else cw
        th = h - r * ch if r == rows - 1 else ch
        tile = _greyscale(_fit(ph, (tw, th)), brightness=False)
        grid.paste(tile, (c * cw, r * ch))
    treated = _tint_and_hue(grid, accent, hue).convert("RGBA")
    treated.alpha_composite(_veil(size))
    return treated


if __name__ == "__main__":
    # Self-check: shapes/opacity invariants without needing real artwork.
    W, H = 1080, 1350
    dummy = Image.new("RGB", (600, 600), (180, 120, 90))
    out = duotone_photo(dummy, "rgb(250, 204, 21)", "#427c42", (W, H))
    assert out.size == (W, H) and out.mode == "RGBA"
    veil = _veil((W, H))
    top = veil.getpixel((W // 2, 0))[3]
    mid = veil.getpixel((W // 2, int(H * 0.43)))[3]
    bot = veil.getpixel((W // 2, H - 1))[3]
    assert abs(top - round(0.66 * 255)) <= 1, top
    assert abs(mid - round(0.16 * 255)) <= 1, mid
    assert abs(bot - round(0.72 * 255)) <= 1, bot
    m = duotone_mosaic([dummy] * 6, "rgb(250, 204, 21)", "#3a5a34", (W, H))
    assert m.size == (W, H)
    print("duotone self-check OK")
