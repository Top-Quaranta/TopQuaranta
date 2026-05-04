"""Rasterise SVG assets to PIL images for the Instagram renderer.

Two asset families:

  * `logo_image(width)` — the rectangular brand logo
    (`vendor/mm-design/icons/brand/logo-topquaranta-rect.svg`). Already
    coloured (yellow + ink + red); we only scale it.

  * `territory_icon(codi, size, fill)` — the per-territory icon
    (`vendor/mm-design/icons/territories/territory-<codi>.svg`). The
    SVG uses `fill="currentColor"`; we substitute `fill` so a single
    icon recolours per slide / per territory.

CairoSVG handles parsing + rasterisation. Everything is cached in
process memory keyed on (path, width, fill) — re-renders of the
same slide hit the cache.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)


def _vendor_root() -> Path:
    base = getattr(settings, "BASE_DIR", None)
    if base:
        return Path(base) / "vendor" / "mm-design" / "icons"
    return Path(__file__).resolve().parents[2] / "vendor" / "mm-design" / "icons"


LOGO_PATH = _vendor_root() / "brand" / "logo-topquaranta-rect.svg"
TERRITORY_DIR = _vendor_root() / "territories"

# Logo aspect ratio from its viewBox (1876.91 / 380.46 ≈ 4.93).
LOGO_ASPECT = 1876.9116 / 380.45602


def _rasterise(svg_bytes: bytes, width: int) -> Image.Image | None:
    try:
        import cairosvg  # local import — optional dep at module level
    except ImportError:
        logger.warning("cairosvg not installed; SVG asset skipped")
        return None
    try:
        png = cairosvg.svg2png(bytestring=svg_bytes, output_width=width)
    except Exception:  # noqa: BLE001 — never crash the renderer
        logger.exception("svg→png failed")
        return None
    return Image.open(BytesIO(png)).convert("RGBA")


@lru_cache(maxsize=32)
def logo_image(width: int) -> Image.Image | None:
    """Rectangular brand logo at `width` px; height auto from aspect."""
    if not LOGO_PATH.exists():
        logger.warning("logo SVG missing at %s", LOGO_PATH)
        return None
    return _rasterise(LOGO_PATH.read_bytes(), width)


# Brand colours baked into the rectangular logo SVG. Substituted in
# `logo_image_mono` when we need a single-colour logo on a coloured
# background (e.g. white-on-territory pill on the cover slide).
_LOGO_BRAND_COLOURS = ("#0047ba", "#cf3339", "#f1c22f")


@lru_cache(maxsize=32)
def logo_image_mono(width: int, fill: str) -> Image.Image | None:
    """Monochromatic version of the brand logo. All three baked-in
    fills (blue, red, yellow) are replaced with `fill`."""
    if not LOGO_PATH.exists():
        logger.warning("logo SVG missing at %s", LOGO_PATH)
        return None
    raw = LOGO_PATH.read_text(encoding="utf-8")
    for c in _LOGO_BRAND_COLOURS:
        raw = raw.replace(c, fill)
    return _rasterise(raw.encode("utf-8"), width)


def _patched_territory_svg(codi: str, fill: str) -> bytes | None:
    path = TERRITORY_DIR / f"territory-{codi.lower()}.svg"
    if not path.exists():
        logger.warning("territory icon missing for %s", codi)
        return None
    raw = path.read_text(encoding="utf-8")
    # The vendored SVGs use `fill="currentColor"` plus a stroke. Swap
    # both occurrences with the requested colour so cairosvg renders
    # the icon directly (it doesn't honour CSS currentColor).
    patched = re.sub(r'fill="currentColor"', f'fill="{fill}"', raw)
    return patched.encode("utf-8")


@lru_cache(maxsize=128)
def territory_icon(codi: str, size: int, fill: str) -> Image.Image | None:
    """Square monochrome territory icon, recoloured to `fill`."""
    if not codi:
        return None
    svg = _patched_territory_svg(codi, fill)
    if svg is None:
        return None
    return _rasterise(svg, size)
