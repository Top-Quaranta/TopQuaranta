"""Font loader for the social renderer.

Tries vendored TTFs at `social/fonts/` first; falls back to
DejaVu (always present on Debian/Ubuntu) so renders never crash even
on a fresh dev machine. Each helper takes a size in pixels and
caches the resulting `ImageFont.FreeTypeFont` keyed by (path, size).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

logger = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).resolve().parent / "fonts"

_VENDORED = {
    "display_bold": FONTS_DIR / "PlayfairDisplay-Bold.ttf",
    "display_regular": FONTS_DIR / "PlayfairDisplay-Regular.ttf",
    "sans_bold": FONTS_DIR / "Roboto-Bold.ttf",
    "sans_regular": FONTS_DIR / "Roboto-Regular.ttf",
    # Step 3b PPCC story redesign families.
    "display_xbold": FONTS_DIR / "PlayfairDisplay-ExtraBold.ttf",
    "anton": FONTS_DIR / "Anton-Regular.ttf",
    "bricolage_medium": FONTS_DIR / "BricolageGrotesque-Medium.ttf",
    "bricolage_bold": FONTS_DIR / "BricolageGrotesque-Bold.ttf",
    "bricolage_xbold": FONTS_DIR / "BricolageGrotesque-ExtraBold.ttf",
    "instrument_italic": FONTS_DIR / "InstrumentSerif-Italic.ttf",
}

# Fallbacks present on Debian/Ubuntu base images.
_FALLBACK = {
    "display_bold": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "display_regular": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "sans_bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "sans_regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # Best-effort fallbacks for the new display families — only hit on a
    # dev box missing the vendored TTFs; production ships them.
    "display_xbold": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "anton": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "bricolage_medium": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "bricolage_bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "bricolage_xbold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "instrument_italic": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
}


@lru_cache(maxsize=64)
def _load(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _resolve(slot: str) -> str:
    p = _VENDORED.get(slot)
    if p and p.exists():
        return str(p)
    fb = _FALLBACK.get(slot)
    if fb and Path(fb).exists():
        logger.warning(
            "Vendored font %s not found at %s; falling back to %s",
            slot,
            p,
            fb,
        )
        return fb
    raise RuntimeError(f"No font available for slot {slot}")


def display_bold(size: int) -> ImageFont.FreeTypeFont:
    return _load(_resolve("display_bold"), size)


def display_regular(size: int) -> ImageFont.FreeTypeFont:
    return _load(_resolve("display_regular"), size)


def sans_bold(size: int) -> ImageFont.FreeTypeFont:
    return _load(_resolve("sans_bold"), size)


def sans_regular(size: int) -> ImageFont.FreeTypeFont:
    return _load(_resolve("sans_regular"), size)


# ── Step 3b PPCC story families ──────────────────────────────────────


def display_xbold(size: int) -> ImageFont.FreeTypeFont:
    """Playfair Display 800 — slide-5 hero song title only."""
    return _load(_resolve("display_xbold"), size)


def anton(size: int) -> ImageFont.FreeTypeFont:
    """Anton 400 — condensed display: headlines, numbers, badges, pills."""
    return _load(_resolve("anton"), size)


def bricolage_medium(size: int) -> ImageFont.FreeTypeFont:
    """Bricolage Grotesque 500 — artist subtitles / lighter metadata."""
    return _load(_resolve("bricolage_medium"), size)


def bricolage_bold(size: int) -> ImageFont.FreeTypeFont:
    """Bricolage Grotesque 700 — artists, page indicator, territory name."""
    return _load(_resolve("bricolage_bold"), size)


def bricolage_xbold(size: int) -> ImageFont.FreeTypeFont:
    """Bricolage Grotesque 800 — song titles on slides 2, 3, 4, 6."""
    return _load(_resolve("bricolage_xbold"), size)


def instrument_italic(size: int) -> ImageFont.FreeTypeFont:
    """Instrument Serif 400 italic — 'presenta' / 'tens el top sencer'."""
    return _load(_resolve("instrument_italic"), size)
