"""PIL-based image generator for the Instagram payloads.

Render entry points:
  - `render_feed_top(tipus, territori, setmana, entries)` → list[Path]
  - `render_feed_novetats(tipus, setmana, items)`         → list[Path]
  - `render_stories_top(territori, setmana, entries)`     → list[Path]
    (territorial story sequence: intro + N cançó slides + CTA)
  - `render_stories_ppcc(setmana, entries, …)`            → list[Path]
    (Step 3b editorial PPCC set: 7 slides built toward the #1 climax)

All return JPEG paths (quality 90) under `<SOCIAL_CACHE_DIR>/renders/`.
Filename is deterministic: `<tipus>_<territori>_<setmana>_<idx>.jpg`.
Same inputs → same path → idempotent re-renders. (Step 3: PNG → JPG
to cut file weight; Instagram's Graph API accepts JPEG.)

Layout reference (Sprint I prompt, lightly adapted to mm-design):
  - Feed dimensions: 1080×1350px (4:5 portrait, Instagram's max
    screen real estate without cropping).
  - Story dimensions: 1080×1920px (9:16).
  - Cover thumbnails inside list rows: 80×80, rounded.
  - Story cover: 750×750 inside a 920×1100 card.
"""

from __future__ import annotations

import logging
import math
from io import BytesIO
from pathlib import Path

import numpy as np
from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import colors, fonts, svg_assets
from .constants import LIST_ROW_HEIGHT, LIST_TOP_Y
from .cover_cache import fetch as fetch_cover

logger = logging.getLogger(__name__)

FEED_W, FEED_H = 1080, 1350
STORY_W, STORY_H = 1080, 1920


def _renders_dir() -> Path:
    base = Path(getattr(settings, "SOCIAL_CACHE_DIR", "/tmp/tq_social"))
    out = base / "renders"
    try:
        out.mkdir(parents=True, exist_ok=True)
        return out
    except OSError:
        out = Path("/tmp/tq_social/renders")
        out.mkdir(parents=True, exist_ok=True)
        return out


def _path(
    tipus: str, territori: str, setmana, idx: int, *, story: bool = False
) -> Path:
    suffix = "story" if story else "feed"
    ter = territori or "general"
    name = f"{suffix}_{tipus}_{ter}_{setmana.isoformat()}_{idx:02d}.jpg"
    return _renders_dir() / name


# ── Drawing helpers ───────────────────────────────────────────────────


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    """Single-line truncation with an ellipsis."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…" if text else "…"


def _pack_greedy_line(
    draw: ImageDraw.ImageDraw, names: list[str], font, max_width: int
) -> tuple[list[str], list[str]]:
    """Pack as many names as fit on a single line; return the
    packed prefix and the remaining tail.

    Incremental O(N): each candidate measure is one extra name
    on top of the previous packed list. Returns whole names only;
    callers handle ellipsis and pathological cases."""
    packed: list[str] = []
    remaining = list(names)
    while remaining:
        candidate = ", ".join(packed + [remaining[0]])
        if draw.textlength(candidate, font=font) <= max_width:
            packed.append(remaining.pop(0))
        else:
            break
    return packed, remaining


def _try_extend_line1_with_word_wrap(
    draw: ImageDraw.ImageDraw,
    line1_text: str,
    first_rest_name: str,
    font,
    max_width: int,
) -> tuple[str, str | None]:
    """Try to extend `line1_text` with leading words of
    `first_rest_name`. Returns `(extended_line1, line2_lead)` when
    a non-trivial prefix fits, or `(line1_text, None)` when the
    name is single-word or even its first word doesn't fit.

    Greedy on words: tries the longest word-prefix first, drops one
    word at a time. The remaining suffix becomes the lead of line 2
    (without a comma — the suffix continues the broken name, the
    comma comes after).

    Tasca B5 (2026-05-18): introduced to make line 1 fuller when the
    next whole name overflows by more than its first word costs.
    Example: La Gent's "Arde Bogotá" (260 px including ", ") doesn't
    fit line 1's 220-px tail, but ", Arde" (~115 px) does — we
    break the name, line 2 then leads with "Bogotá, …"."""
    words = first_rest_name.split(" ")
    if len(words) < 2:
        return line1_text, None
    for k in range(len(words) - 1, 0, -1):
        prefix = " ".join(words[:k])
        candidate = line1_text + ", " + prefix
        if draw.textlength(candidate, font=font) <= max_width:
            line2_lead = " ".join(words[k:])
            return candidate, line2_lead
    return line1_text, None


def _join_artists(
    draw: ImageDraw.ImageDraw,
    names: list[str],
    font,
    max_width: int,
    *,
    max_lines: int = 1,
) -> str:
    """Comma-join an artist list with whole-name truncation.

    Single-line (`max_lines=1`, default): tries the full list first;
    if it doesn't fit, drops names from the tail one at a time and
    appends `…` after the last name that does fit. Falls back to
    char-level truncation only when the main artist alone is wider
    than the slot.

    Multi-line (`max_lines=2`, story surface): same single-line
    attempt first — if the full list fits on one line we keep it
    that way (we don't force a split when there's room). Otherwise
    two greedy passes via `_pack_greedy_line`: line 1 holds as
    many names as fit, line 2 continues with the rest. If even
    line 2's whole-name pack still leaves a tail, drop names from
    line 2's tail and append `…`. Returns a string with one
    embedded `\\n`; the caller paints each line separately.

    The pathological "first name doesn't fit on any line" case
    falls through to `_truncate` (single line with char-level
    ellipsis) regardless of `max_lines` — splitting a single name
    across two lines is uglier than truncating it.

    Tasca B4 (2026-05-18): refactored to use `_pack_greedy_line`
    for O(N) instead of the prior O(N²) repeated-join measure.
    Visual behaviour is unchanged — the packing was already
    greedy-maximal; the empirical asymmetry between La Gent
    (31/30 chars) and Ai Mareta (43 chars on one line) comes from
    per-character width variance, not from a balancing pass that
    isn't there."""
    if not names:
        return "—"
    full = ", ".join(names)
    if draw.textlength(full, font=font) <= max_width:
        return full

    if max_lines <= 1:
        # Drop one name at a time from the end; append "…" after the
        # last fitting name. The ellipsis itself signals omission, so
        # no comma between the last name and the "…".
        for i in range(len(names) - 1, 0, -1):
            candidate = ", ".join(names[:i]) + "…"
            if draw.textlength(candidate, font=font) <= max_width:
                return candidate
        return _truncate(draw, names[0], font, max_width)

    # Two-line greedy pack.
    line1, rest = _pack_greedy_line(draw, names, font, max_width)
    if not rest:
        # All fit on line 1 — fast path. (We already covered the
        # full-list-fits case above; this is the defensive return.)
        return ", ".join(line1)
    if not line1:
        # First name alone is wider than the slot — single-line
        # char-truncate.
        return _truncate(draw, names[0], font, max_width)

    # Tasca B5: opportunistic word-wrap. If line 1 has room for
    # leading words of the first leftover name (multi-word names
    # only — "Arde Bogotá" splits, "OBESES" doesn't), break the
    # name so line 1 is fuller and line 2 leads with the remaining
    # words (no leading comma — the suffix continues the broken
    # name).
    #
    # Opportunistic, not forced: if the whole rest fits on line 2
    # without splitting anyone, don't word-wrap — clean whole-name
    # rendering is preferred when it's available.
    line1_text = ", ".join(line1)
    line2_lead = None
    rest_fits_whole = (
        draw.textlength(", ".join(rest), font=font) <= max_width if rest else True
    )
    if rest and not rest_fits_whole:
        line1_text, line2_lead = _try_extend_line1_with_word_wrap(
            draw, line1_text, rest[0], font, max_width
        )
        if line2_lead is not None:
            # First rest name was consumed (partially); shift to next.
            rest = rest[1:]

    # Line 2 greedy on the remaining whole names. If we have a
    # `line2_lead`, the available width for the rest of line 2 is
    # reduced by the lead's pixel cost (plus a ", " for the next
    # name's separator). We pack into the slot by pre-seeding
    # `packed` with the lead.
    if line2_lead is None:
        line2, tail = _pack_greedy_line(draw, rest, font, max_width)
        line2_joined = ", ".join(line2)
    else:
        # Pack greedily starting from `line2_lead`.
        line2 = [line2_lead]
        remaining = list(rest)
        while remaining:
            candidate = ", ".join(line2 + [remaining[0]])
            if draw.textlength(candidate, font=font) <= max_width:
                line2.append(remaining.pop(0))
            else:
                break
        tail = remaining
        line2_joined = ", ".join(line2)

    if not tail:
        return line1_text + "\n" + line2_joined
    # Line 2 has a tail — drop names from line 2 and append "…".
    for i in range(len(line2), 0, -1):
        candidate = ", ".join(line2[:i]) + "…"
        if draw.textlength(candidate, font=font) <= max_width:
            return line1_text + "\n" + candidate
    # Even line 2's first name doesn't fit with an ellipsis —
    # char-truncate that name on its own line.
    fallback_name = line2[0] if line2 else rest[0]
    return line1_text + "\n" + _truncate(draw, fallback_name, font, max_width)


def _wrap_two_lines(draw, text: str, font, max_width: int) -> list[str]:
    """Break into at most 2 lines; truncate the second with an ellipsis."""
    words = text.split()
    line1 = ""
    while (
        words
        and draw.textlength((line1 + " " + words[0]).strip(), font=font) <= max_width
    ):
        line1 = (line1 + " " + words.pop(0)).strip()
    if not words:
        return [line1] if line1 else [text]
    line2 = " ".join(words)
    return [line1, _truncate(draw, line2, font, max_width)]


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    """Return a copy with rounded corners (alpha mask)."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, img.size[0], img.size[1]), radius=radius, fill=255
    )
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def _placeholder_cover(size: int, text: str = "?") -> Image.Image:
    img = Image.new("RGB", (size, size), colors.COLOR_CARD)
    d = ImageDraw.Draw(img)
    f = fonts.display_bold(int(size * 0.45))
    bbox = d.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(
        ((size - tw) // 2 - bbox[0], (size - th) // 2 - bbox[1]),
        text,
        font=f,
        fill=colors.COLOR_TEXT_MUTED,
    )
    return img


def _cover(url: str | None, size: int, *, fallback_letter: str = "?") -> Image.Image:
    img = fetch_cover(url) if url else None
    if img is None:
        return _placeholder_cover(size, fallback_letter)
    return img.resize((size, size), Image.LANCZOS)


def _portada_local(deezer_id, mida: int) -> Image.Image | None:
    """Load a self-hosted portada JPG from the local store, or None.

    The renderer runs on the server where `PORTADES_ROOT` is populated
    (`ingesta.portades`, Caddy-served at `/portades/*`); on dev machines
    the file is absent and the caller falls through to the Deezer CDN."""
    if not deezer_id:
        return None
    try:
        from ingesta.portades import manager

        p = manager.path_for("album", int(deezer_id), mida, "jpg")
    except Exception:  # noqa: BLE001 — a bad id must never crash a render
        return None
    if not p.is_file():
        return None
    try:
        return Image.open(p).convert("RGB")
    except Exception:  # noqa: BLE001 — corrupted file → fall through
        logger.warning("portada decode failed for %s", p)
        return None


def _story_cover(
    deezer_id, url: str | None, size: int, *, fallback_letter: str = "?"
) -> Image.Image:
    """Cover for the PPCC story slides (Step 3b).

    Resolution order: local self-hosted portada first (the 250 px variant
    for small slots, the 500 px one for larger covers), then the live
    Deezer CDN URL, then a coloured placeholder tile. Unlike the
    newsletter, the placeholder is the last resort — the documented
    fallback is the Deezer URL, not the brand placeholder."""
    mida = 250 if size <= 250 else 500
    img = _portada_local(deezer_id, mida)
    if img is None and url:
        img = fetch_cover(url)
    if img is None:
        return _placeholder_cover(size, fallback_letter)
    return img.resize((size, size), Image.LANCZOS)


def _logo_block(
    img_or_draw,
    x: int,
    y: int,
    *,
    size: int = 36,
    width: int | None = None,
) -> int:
    """Paste the rectangular brand logo SVG. `size` is the *height*
    (kept as the legacy parameter name); width auto-scales from the
    logo's 4.93:1 aspect. Pass an explicit `width` to override.

    Accepts either a PIL.Image (preferred — needed to alpha-blit the
    SVG) or, for legacy callers, an ImageDraw object — in which case
    we fall back to the old text composition. Returns the x of the
    right edge so callers can lay things out next to it.
    """
    if width is None:
        width = int(round(size * svg_assets.LOGO_ASPECT))
    if isinstance(img_or_draw, Image.Image):
        logo = svg_assets.logo_image(width)
        if logo is not None:
            img_or_draw.paste(logo, (x, y), logo)
            return x + logo.size[0]
        # SVG missing → fall through to text fallback below
        draw = ImageDraw.Draw(img_or_draw)
    else:
        draw = img_or_draw

    # Text fallback (kept for safety if cairosvg/asset is unavailable).
    f = fonts.display_bold(size)
    draw.text((x, y), "Top", font=f, fill=colors.COLOR_YELLOW)
    w_top = draw.textlength("Top", font=f)
    draw.text((x + w_top + 6, y), "Quaranta", font=f, fill=colors.COLOR_WHITE)
    return int(x + w_top + 6 + draw.textlength("Quaranta", font=f))


def _footer(draw: ImageDraw.ImageDraw, w: int, h: int):
    f = fonts.sans_regular(20)
    text = "topquaranta.cat"
    tw = draw.textlength(text, font=f)
    draw.text(((w - tw) // 2, h - 40), text, font=f, fill=colors.COLOR_TEXT_SUBTLE)


def _measure_pill(
    *,
    text: str,
    font,
    pad_x: int = 22,
    pad_y: int = 12,
    icon_codi: str | None = None,
    icon_size: int = 36,
) -> tuple[int, int]:
    """Pill size without painting — useful when the caller needs to
    right-align or center the pill before drawing it.

    Returns (width, height). Mirrors `_pill`'s sizing exactly so a
    measure-then-paint flow lands at the same dimensions.
    """
    # We need a Draw to measure text; a 1×1 image is enough.
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = int(d.textlength(text, font=font)) if text else 0
    icon_w = icon_size if icon_codi else 0
    icon_gap = 10 if icon_codi else 0
    inner_w = icon_w + icon_gap + tw
    inner_h = max(icon_size if icon_codi else 0, _font_height(font))
    return inner_w + pad_x * 2, inner_h + pad_y * 2


def _pill(
    img: Image.Image,
    *,
    x: int,
    y: int,
    text: str,
    font,
    fill: str,
    text_fill: str = colors.COLOR_WHITE,
    pad_x: int = 22,
    pad_y: int = 12,
    radius: int = 22,
    icon_codi: str | None = None,
    icon_size: int = 36,
    icon_fill: str | None = None,
) -> tuple[int, int]:
    """Draw a rounded-rect pill with optional leading territory icon
    + text. Returns the pill's outer (width, height). The pill is
    pasted onto `img`; we use a one-off ImageDraw.

    Used everywhere we need readable text on top of a photo (covers)
    or to add a coloured tag (territory chip on slides)."""
    d = ImageDraw.Draw(img)
    tw = int(d.textlength(text, font=font)) if text else 0
    icon = None
    if icon_codi:
        icon = svg_assets.territory_icon(icon_codi, icon_size, icon_fill or text_fill)
    icon_gap = 10 if icon is not None else 0
    icon_w = icon.size[0] if icon is not None else 0
    inner_w = icon_w + icon_gap + tw
    inner_h = max(icon.size[1] if icon is not None else 0, _font_height(font))
    pill_w = inner_w + pad_x * 2
    pill_h = inner_h + pad_y * 2
    d.rounded_rectangle((x, y, x + pill_w, y + pill_h), radius=radius, fill=fill)
    cur_x = x + pad_x
    if icon is not None:
        icon_y = y + (pill_h - icon.size[1]) // 2
        img.paste(icon, (cur_x, icon_y), icon)
        cur_x += icon_w + icon_gap
    if text:
        # Vertical centring is approximate (PIL's textlength has no
        # bbox), so we drop a small fixed offset that looks right
        # across the fonts we ship.
        text_y = y + pad_y - 2
        d.text((cur_x, text_y), text, font=font, fill=text_fill)
    return pill_w, pill_h


def _font_height(font) -> int:
    """Best-effort font height for vertical pill sizing."""
    bbox = font.getbbox("Hg") if hasattr(font, "getbbox") else (0, 0, 0, 32)
    return max(bbox[3] - bbox[1], 24)


def _trend_glyph(
    draw, x: int, y: int, posicio: int, posicio_anterior, *, size: int = 22
):
    """Up arrow / down arrow / NEW badge / nothing if stable.
    Same vocabulary as the SPA's TrendCue."""
    if posicio_anterior is None:
        # NEW badge
        f = fonts.sans_bold(14)
        text = "NOU"
        tw = draw.textlength(text, font=f)
        pad_x, pad_y = 8, 4
        draw.rounded_rectangle(
            (x, y, x + tw + pad_x * 2, y + 16 + pad_y * 2),
            radius=10,
            fill=colors.COLOR_YELLOW,
        )
        draw.text((x + pad_x, y + pad_y - 2), text, font=f, fill=colors.COLOR_BG)
        return
    if posicio_anterior > posicio:
        # ▲ up
        col = colors.COLOR_SUCCESS
        draw.polygon(
            [(x + size // 2, y), (x, y + size), (x + size, y + size)], fill=col
        )
    elif posicio_anterior < posicio:
        col = colors.COLOR_DANGER
        draw.polygon([(x, y), (x + size, y), (x + size // 2, y + size)], fill=col)
    # equal → silent (matches public TopPage policy)


# ── FEED ─────────────────────────────────────────────────────────────


def _feed_canvas() -> Image.Image:
    return Image.new("RGB", (FEED_W, FEED_H), colors.COLOR_BG)


def _feed_cover_full(url: str | None) -> Image.Image:
    """Full-bleed 1080×1350 cover via `ImageOps.fit` — preserves
    proportions, centre-crops the overflow, no overlay or colour
    cast on top.
    """
    if url:
        img = fetch_cover(url)
        if img is not None:
            return ImageOps.fit(
                img.convert("RGB"),
                (FEED_W, FEED_H),
                method=Image.LANCZOS,
            )
    return _feed_canvas()


def _feed_portada_ppcc(setmana, featured: list[str], accent) -> Image.Image:
    """Editorial PPCC feed cover (Step 3): ink background, big
    "TOP 40 / SETMANA N" kicker, a teaser list of up to 5 featured
    artist names, and the brand logo. Replaces the ~85 %-empty legacy
    PPCC cover. Sans-only (Playfair is reserved for the #1 story hero)."""
    from .captions import _setmana_label

    img = Image.new("RGB", (FEED_W, FEED_H), colors.COLOR_BG)
    d = ImageDraw.Draw(img)

    # Brand logo, top-left.
    logo = svg_assets.logo_image(360)
    if logo is not None:
        img.paste(logo, (84, 90), logo)

    # "TOP 40" — the big yellow headline.
    f_top = fonts.sans_bold(210)
    d.text((84, 300), "TOP 40", font=f_top, fill=colors.COLOR_YELLOW)

    # "SETMANA N" under it.
    f_wk = fonts.sans_bold(64)
    d.text(
        (90, 560),
        _setmana_label(setmana).upper(),
        font=f_wk,
        fill=colors.COLOR_WHITE,
    )

    # Accent divider.
    d.rounded_rectangle((90, 680, 90 + 220, 690), radius=5, fill=accent)

    # Featured artists teaser.
    f_lead = fonts.sans_bold(34)
    d.text((90, 730), "AQUESTA SETMANA", font=f_lead, fill=accent)
    f_name = fonts.sans_bold(52)
    y = 800
    for nom in featured[:5]:
        name = _truncate(d, nom, f_name, FEED_W - 90 - 60)
        # Accent dot + name.
        d.ellipse((90, y + 22, 90 + 16, y + 38), fill=accent)
        d.text((124, y), name, font=f_name, fill=colors.COLOR_WHITE)
        y += 76

    # Footer URL.
    f_url = fonts.sans_regular(32)
    d.text(
        (90, FEED_H - 70), "topquaranta.cat", font=f_url, fill=colors.COLOR_TEXT_MUTED
    )
    return img


def _feed_portada(
    territori: str,
    setmana,
    hero_cover_url: str | None,
    *,
    featured: list[str] | None = None,
) -> Image.Image:
    """Cover slide.

    Territorial: full-bleed album cover + territory pill + logo pill +
    Setmana pill (unchanged).

    PPCC (Step 3, editorial rewrite): the old PPCC cover was ~85 % empty
    ink. Now an editorial cover on ink — big "TOP 40 / SETMANA N" kicker
    + a teaser list of `featured` artist names — plus the existing logo
    + Setmana pill at the bottom.
    """
    from .captions import _setmana_label

    accent = colors.terr_color(territori)
    is_ppcc = (territori or "") == "PPCC"

    if is_ppcc:
        return _feed_portada_ppcc(setmana, featured or [], accent)

    from .captions import TERRITORI_NOM

    img = _feed_cover_full(hero_cover_url)
    d = ImageDraw.Draw(img)

    # ── Territory pill, top-right (territorial only) ─────────────
    # PPCC has no chip — the green background already says "Global".
    nom = TERRITORI_NOM.get(territori, territori or "")
    if not is_ppcc:
        f_nom = fonts.sans_bold(34)
        chip_w, _ = _measure_pill(
            text=nom,
            font=f_nom,
            pad_x=20,
            pad_y=12,
            icon_codi=territori or "PPCC",
            icon_size=40,
        )
        _pill(
            img,
            x=int(FEED_W - 30 - chip_w),
            y=30,
            text=nom,
            font=f_nom,
            fill=accent,
            text_fill=colors.COLOR_WHITE,
            pad_x=20,
            pad_y=12,
            radius=12,  # mm-design `--mm-radius-lg`
            icon_codi=territori or "PPCC",
            icon_size=40,
            icon_fill=colors.COLOR_WHITE,
        )

    # ── Logo block, lower band ───────────────────────────────────
    # Width = 70% of canvas (756). Y shifted up 5% of canvas height
    # (≈68px) from the legacy 75% mark. Logo and Setmana pill 20%
    # larger than the earlier spec — logo h 106. Left-aligned to
    # match the Setmana text below. Container radius
    # `--mm-radius-lg` (12px).
    #
    # On territorial covers the logo sits inside an accent-coloured
    # pill so it stays legible over the photo. On PPCC the
    # background is already solid accent, so we drop the pill and
    # render the original tri-colour logo directly — the brand
    # marks (yellow/red/blue) pop on green.
    pill_w = int(FEED_W * 0.70)  # 756
    # Left margin bumped from 30 → 84 (+54 px = 5% of FEED_W) per the
    # May-2026 readability pass: same left-aligned stack, more
    # breathing room from the canvas edge.
    pill_x = 84
    pill_y = 944  # 1012 − 5% × 1350 ≈ 68
    logo_h = 106  # 88 × 1.20
    logo_w = int(round(logo_h * svg_assets.LOGO_ASPECT))
    pill_h = logo_h + 28  # 14px breathing each side
    if is_ppcc:
        # Original three-colour logo on the solid accent background —
        # no pill, but kept at the same x/y/size as the territorial
        # variant so the layout feels identical.
        logo = svg_assets.logo_image(logo_w)
    else:
        d.rounded_rectangle(
            (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
            radius=12,
            fill=accent,
        )
        logo = svg_assets.logo_image_mono(logo_w, colors.COLOR_WHITE)
    if logo is not None:
        img.paste(
            logo,
            (
                pill_x + 20,  # left-aligned
                pill_y + (pill_h - logo.size[1]) // 2,  # vertical centre
            ),
            logo,
        )

    # ── Setmana pill, 15px below the logo pill ───────────────────
    # Same width (756) so the two stack with a consistent column.
    # 20% taller (70 → 84) and the text scales the same.
    sm_x = 84  # mirrors pill_x — keeps the two-pill stack aligned
    sm_y = pill_y + pill_h + 15
    sm_w, sm_h = pill_w, 84  # 756×84
    d.rounded_rectangle(
        (sm_x, sm_y, sm_x + sm_w, sm_y + sm_h),
        radius=12,
        fill=colors.COLOR_WHITE,
    )
    f_sm = fonts.sans_bold(38)  # 32 × 1.20 ≈ 38
    label = _setmana_label(setmana)
    bbox = f_sm.getbbox(label)
    text_h = bbox[3] - bbox[1]
    d.text(
        (sm_x + 20, sm_y + (sm_h - text_h) // 2 - bbox[1]),
        label,
        font=f_sm,
        fill=colors.COLOR_BG,
    )
    return img


def _feed_list_slide(
    territori: str, entries: list[dict], start_pos: int, page: int, total_pages: int
) -> Image.Image:
    """One feed slide listing up to 10 entries from the top.

    Territory accent recolours: position squares, kicker bar, header
    chip, and the per-row territory icon (singles only — for top
    lists the territory is the same on every row, so we don't repeat
    it).
    """
    img = _feed_canvas()
    d = ImageDraw.Draw(img)
    accent = colors.terr_color(territori)
    from .captions import TERRITORI_NOM

    # Header — brand logo top-left, territory chip top-right.
    _logo_block(img, 60, 50, width=270)
    nom = TERRITORI_NOM.get(territori, territori)
    f_h = fonts.sans_bold(24)
    chip_w, _ = _measure_pill(
        text=nom,
        font=f_h,
        pad_x=20,
        pad_y=10,
        icon_codi=territori or "PPCC",
        icon_size=32,
    )
    _pill(
        img,
        x=int(FEED_W - 60 - chip_w),
        y=44,
        text=nom,
        font=f_h,
        fill=accent,
        text_fill=colors.COLOR_WHITE,
        pad_x=20,
        pad_y=10,
        radius=18,
        icon_codi=territori or "PPCC",
        icon_size=32,
        icon_fill=colors.COLOR_WHITE,
    )

    # Accent rule under the header.
    d.rounded_rectangle((60, 130, FEED_W - 60, 138), radius=4, fill=accent)

    # Layout — May-2026 readability pass v2. The pills + cards stay
    # the SAME size as the legacy spec (pos_w=76, LIST_ROW_HEIGHT=105,
    # LIST_TOP_Y=170 — both shared via social/constants.py with the
    # singles-novetats slide); the gain in apparent text size comes
    # from larger fonts + tighter vertical padding inside the cell.
    f_pos = fonts.display_bold(54)  # was 38 → 48 → 54
    f_song = fonts.display_bold(40)  # was 28 → 34 → 40
    f_artist = fonts.sans_regular(22)
    pos_w = 76

    for i, e in enumerate(entries[:10]):
        y = LIST_TOP_Y + i * LIST_ROW_HEIGHT
        pos = e["posicio"]

        # Tinted card behind each row — alternating depth so the eye
        # has somewhere to land beyond the flat ink background.
        card_fill = colors.darken(accent, 0.78 if i % 2 == 0 else 0.85)
        d.rounded_rectangle(
            (40, y - 6, FEED_W - 40, y + pos_w + 10),
            radius=18,
            fill=card_fill,
        )

        # Position number — territory accent square (yellow only on PPCC).
        d.rounded_rectangle((60, y, 60 + pos_w, y + pos_w), radius=14, fill=accent)
        pos_text = str(pos)
        ptw = d.textlength(pos_text, font=f_pos)
        # Very tight top padding (y+0) so the 54-pt glyph fills the
        # 76-pt square almost edge-to-edge.
        d.text(
            (60 + (pos_w - ptw) // 2, y),
            pos_text,
            font=f_pos,
            fill=colors.COLOR_WHITE,
        )

        # Trend indicator just to the right of the position square.
        _trend_glyph(d, 152, y + 26, pos, e.get("posicio_anterior"))

        # Cover thumbnail right side
        cover = _cover(
            e.get("cover_url"), 80, fallback_letter=e.get("canco_nom", "?")[:1]
        )
        cover_r = _rounded(cover, 12)
        img.paste(cover_r, (FEED_W - 60 - 80, y), cover_r)

        # Song + artist text block — leave room for the NOU pill that
        # `_trend_glyph` may render up to ~60px wide. text_x back to
        # the legacy 240 since pos_w is back to 76.
        text_x = 240
        text_w = (FEED_W - 60 - 80 - 20) - text_x
        song = _truncate(d, e["canco_nom"], f_song, text_w)
        # `artistes_noms` is the canonical list (main first +
        # collabs in insertion order). Fall back to the legacy
        # `artista_nom` single-string field for payload callers
        # that still build the old shape — keeps tests using
        # synthetic fixtures green.
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        artist = _join_artists(d, names, f_artist, text_w)
        # Tight top padding (y+0) for the 40-pt song title; artist
        # drops to y+54 so it doesn't kiss the title's descenders.
        d.text((text_x, y), song, font=f_song, fill=colors.COLOR_WHITE)
        d.text((text_x, y + 54), artist, font=f_artist, fill=colors.COLOR_TEXT_MUTED)

    # Page indicator — back to the legacy y so it doesn't get
    # squashed into the last row card.
    if total_pages > 1:
        f_p = fonts.sans_bold(22)
        text = f"{page}/{total_pages}"
        tw = d.textlength(text, font=f_p)
        d.text(
            ((FEED_W - tw) // 2, FEED_H - 80),
            text,
            font=f_p,
            fill=colors.COLOR_TEXT_MUTED,
        )

    _footer(d, FEED_W, FEED_H)
    return img


def render_feed_top(
    tipus: str, territori: str, setmana, entries: list[dict]
) -> list[Path]:
    """Render: portada + N pages of 10 entries.

    `entries[i]` keys: posicio, posicio_anterior, canco_nom,
    artista_nom, cover_url. Order matches the chart order.
    Returns the list of generated PNG paths in carousel order.
    """
    out: list[Path] = []
    hero_cover = entries[0].get("cover_url") if entries else None

    # Featured artists for the editorial PPCC cover (Step 3): the main
    # artist of each of the top-5 entries, de-duplicated preserving
    # chart order, capped at 5. Simple + robust; a scenario-weighted
    # heuristic is deferred until the story scenario is threaded.
    featured: list[str] = []
    for e in entries[:5]:
        nom = e.get("artista_nom") or ""
        if nom and nom not in featured:
            featured.append(nom)

    p = _path(tipus, territori, setmana, 0)
    _feed_portada(territori, setmana, hero_cover, featured=featured).save(
        p, "JPEG", quality=90
    )
    out.append(p)

    pages = max(1, (len(entries) + 9) // 10)
    for page in range(1, pages + 1):
        chunk = entries[(page - 1) * 10 : page * 10]
        if not chunk:
            break
        slide = _feed_list_slide(
            territori,
            chunk,
            start_pos=(page - 1) * 10 + 1,
            page=page,
            total_pages=pages,
        )
        p = _path(tipus, territori, setmana, page)
        slide.save(p, "JPEG", quality=90)
        out.append(p)

    # Instagram carousel cap is 10 — drop trailing slides if needed.
    return out[:10]


# ── FEED · novetats (album/single carousel) ──────────────────────────


def _feed_novetats_portada(tipus: str, setmana) -> Image.Image:
    """Cover slide for nous_albums / nous_singles.

    Mirrors the territorial cover layout exactly — same pill sizes,
    same vertical anchors, same fonts — with three substitutions:
      • Background: solid ink (no album cover at all — novetats
        aren't anchored to a single artist).
      • Top-right pill: tipus label ("Nous àlbums" / "Nous singles"),
        no leading icon. Fill = brand red (singles) or brand blue
        (àlbums).
      • Logo pill: same accent fill as the top-right chip, white
        monochrome logo.
    Setmana pill is identical to the territorial variant.
    """
    from .captions import _setmana_label

    accent = (
        colors.COLOR_NOVETATS_ALBUMS
        if tipus == "nous_albums"
        else colors.COLOR_NOVETATS_SINGLES
    )
    label = "Nous àlbums" if tipus == "nous_albums" else "Nous singles"

    img = Image.new("RGB", (FEED_W, FEED_H), colors.COLOR_BG)
    d = ImageDraw.Draw(img)

    # ── Top-right pill (no icon, just the tipus label) ───────────
    f_chip = fonts.sans_bold(34)
    chip_w, _ = _measure_pill(text=label, font=f_chip, pad_x=20, pad_y=12)
    _pill(
        img,
        x=int(FEED_W - 30 - chip_w),
        y=30,
        text=label,
        font=f_chip,
        fill=accent,
        text_fill=colors.COLOR_WHITE,
        pad_x=20,
        pad_y=12,
        radius=12,  # mm-design `--mm-radius-lg`
    )

    # ── Logo pill, lower band (geometry shared with territorial) ─
    pill_w = int(FEED_W * 0.70)  # 756
    # Left margin bumped from 30 → 84 (+54 px = 5% of FEED_W) per the
    # May-2026 readability pass: same left-aligned stack, more
    # breathing room from the canvas edge.
    pill_x = 84
    pill_y = 944  # 1012 − 5% × 1350 ≈ 68
    logo_h = 106  # 88 × 1.20
    logo_w = int(round(logo_h * svg_assets.LOGO_ASPECT))
    pill_h = logo_h + 28
    d.rounded_rectangle(
        (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
        radius=12,
        fill=accent,
    )
    logo = svg_assets.logo_image_mono(logo_w, colors.COLOR_WHITE)
    if logo is not None:
        img.paste(
            logo,
            (
                pill_x + 20,
                pill_y + (pill_h - logo.size[1]) // 2,
            ),
            logo,
        )

    # ── Setmana pill (identical to territorial) ──────────────────
    sm_x = 84  # mirrors pill_x — keeps the two-pill stack aligned
    sm_y = pill_y + pill_h + 15
    sm_w, sm_h = pill_w, 84
    d.rounded_rectangle(
        (sm_x, sm_y, sm_x + sm_w, sm_y + sm_h),
        radius=12,
        fill=colors.COLOR_WHITE,
    )
    f_sm = fonts.sans_bold(38)
    txt = _setmana_label(setmana)
    bbox = f_sm.getbbox(txt)
    text_h = bbox[3] - bbox[1]
    d.text(
        (sm_x + 20, sm_y + (sm_h - text_h) // 2 - bbox[1]),
        txt,
        font=f_sm,
        fill=colors.COLOR_BG,
    )
    return img


def _feed_album_slide(item: dict) -> Image.Image:
    """One album per slide.

    Top-left: brand logo.
    Top-right: territory icon-only pill in the artist's territory
    colour (no text — the icon is enough).
    Centre: big cover.
    Bottom: title + artist.
    """
    img = _feed_canvas()
    d = ImageDraw.Draw(img)
    _logo_block(img, 60, 50, width=270)

    # Territory icon-only pill, top-right.
    ter = item.get("artista_territori") or "PPCC"
    ter_color = colors.terr_color(ter)
    icon_pill_w, icon_pill_h = _measure_pill(
        text="",
        font=fonts.sans_bold(20),
        pad_x=20,
        pad_y=14,
        icon_codi=ter,
        icon_size=44,
    )
    _pill(
        img,
        x=int(FEED_W - 60 - icon_pill_w),
        y=44,
        text="",
        font=fonts.sans_bold(20),
        fill=ter_color,
        pad_x=20,
        pad_y=14,
        radius=22,
        icon_codi=ter,
        icon_size=44,
        icon_fill=colors.COLOR_WHITE,
    )

    # Big cover centred
    cover = _cover(item.get("cover_url"), 800, fallback_letter=item.get("nom", "?")[:1])
    cover_r = _rounded(cover, 24)
    img.paste(cover_r, ((FEED_W - 800) // 2, 160), cover_r)

    # Title + artist underneath. May-2026 readability v3: artist
    # bumped 36 → 44 (matches the story-canço pattern) and the
    # vertical anchors slide up 30 px so the block hugs the cover.
    # Cover is at y=160, h=800 → bottom at y=960; we want a small
    # ~20 px gutter, so title at y=980 and artist at y=1054 (line
    # height 74, room for the 44-pt body without descender clipping).
    f_t = fonts.display_bold(54)
    f_a = fonts.sans_regular(44)
    title = _truncate(d, item["nom"], f_t, FEED_W - 120)
    artist = _truncate(d, item["artista_nom"], f_a, FEED_W - 120)
    d.text(
        ((FEED_W - d.textlength(title, font=f_t)) // 2, 980),
        title,
        font=f_t,
        fill=colors.COLOR_WHITE,
    )
    d.text(
        ((FEED_W - d.textlength(artist, font=f_a)) // 2, 1054),
        artist,
        font=f_a,
        fill=colors.COLOR_TEXT_MUTED,
    )

    _footer(d, FEED_W, FEED_H)
    return img


def _feed_singles_slide(items: list[dict], page: int, total_pages: int) -> Image.Image:
    """Up to 10 singles in a list. Each row carries the artist's
    territory icon at the right edge so the slide stays colourful
    even when titles are short."""
    img = _feed_canvas()
    d = ImageDraw.Draw(img)
    _logo_block(img, 60, 50, width=270)

    # "Nous singles" pill top-right in brand red.
    f_h = fonts.sans_bold(24)
    chip_w, _ = _measure_pill(text="Nous singles", font=f_h, pad_x=20, pad_y=10)
    _pill(
        img,
        x=int(FEED_W - 60 - chip_w),
        y=44,
        text="Nous singles",
        font=f_h,
        fill=colors.COLOR_NOVETATS_SINGLES,
        text_fill=colors.COLOR_WHITE,
        pad_x=20,
        pad_y=10,
        radius=18,
    )

    # Accent rule under the header.
    d.rounded_rectangle(
        (60, 130, FEED_W - 60, 138),
        radius=4,
        fill=colors.COLOR_NOVETATS_SINGLES,
    )

    # May-2026 readability v3 pass — mirror `_feed_list_slide`. Same
    # row_h/list_top, but the song title gets bumped 28 → 40 pt and
    # both glyphs hug the top of the row (y+0 / y+54). Cover (80 px)
    # and territory icon (48 px) anchors are unchanged so the rest of
    # the layout stays put. Row geometry shared with `_feed_list_slide`
    # via social/constants.py.
    f_song = fonts.display_bold(40)  # was 28
    f_artist = fonts.sans_regular(22)
    icon_size = 48

    for i, e in enumerate(items[:10]):
        y = LIST_TOP_Y + i * LIST_ROW_HEIGHT
        ter = e.get("artista_territori") or "PPCC"
        ter_color = colors.terr_color(ter)

        # Tinted row card per territory so colour leaks through.
        card_fill = colors.darken(ter_color, 0.78 if i % 2 == 0 else 0.85)
        d.rounded_rectangle(
            (40, y - 6, FEED_W - 40, y + 80 + 10),
            radius=18,
            fill=card_fill,
        )

        # Cover thumbnail left.
        cover = _cover(e.get("cover_url"), 80, fallback_letter=e.get("nom", "?")[:1])
        cover_r = _rounded(cover, 12)
        img.paste(cover_r, (60, y), cover_r)

        # Territory icon at the right, in brand colour.
        t_icon = svg_assets.territory_icon(ter, icon_size, ter_color)
        if t_icon is not None:
            img.paste(
                t_icon,
                (FEED_W - 60 - icon_size, y + (80 - icon_size) // 2),
                t_icon,
            )

        text_x = 175
        text_w = (FEED_W - 60 - icon_size - 20) - text_x
        song = _truncate(d, e["nom"], f_song, text_w)
        artist = _truncate(d, e["artista_nom"], f_artist, text_w)
        # Tight top padding (y+0) for the 40-pt song; artist drops to
        # y+54 to clear the title's descenders.
        d.text((text_x, y), song, font=f_song, fill=colors.COLOR_WHITE)
        d.text((text_x, y + 54), artist, font=f_artist, fill=colors.COLOR_TEXT_MUTED)

    if total_pages > 1:
        f_p = fonts.sans_bold(22)
        text = f"{page}/{total_pages}"
        tw = d.textlength(text, font=f_p)
        d.text(
            ((FEED_W - tw) // 2, FEED_H - 80),
            text,
            font=f_p,
            fill=colors.COLOR_TEXT_MUTED,
        )

    _footer(d, FEED_W, FEED_H)
    return img


def render_feed_novetats(tipus: str, setmana, items: list[dict]) -> list[Path]:
    """`tipus` is `nous_albums` (1 per slide) or `nous_singles`
    (10 per slide, list-style)."""
    out: list[Path] = []
    p = _path(tipus, "", setmana, 0)
    _feed_novetats_portada(tipus, setmana).save(p, "JPEG", quality=90)
    out.append(p)

    if tipus == "nous_albums":
        for i, item in enumerate(items[:9], start=1):
            p = _path(tipus, "", setmana, i)
            _feed_album_slide(item).save(p, "JPEG", quality=90)
            out.append(p)
    else:
        # Singles: dynamic bin-packing so we never end with a slide
        # holding 1-2 orphan rows. Up to 10 per slide is the hard cap
        # (anything denser stops being legible). Within that cap we
        # split as evenly as possible:
        #   ≤10 → 1 slide
        #   11-20 → 2 slides (e.g. 11 → 6+5, 13 → 7+6, 20 → 10+10)
        #   21-30 → 3 slides, etc.
        n = len(items)
        n_slides = max(1, (n + 9) // 10)
        per_slide = -(-n // n_slides)  # ceil-div
        pages = n_slides
        offset = 0
        for page in range(1, pages + 1):
            # Last slide may end up smaller; that's intentional.
            chunk_size = per_slide if (offset + per_slide) <= n else n - offset
            chunk = items[offset : offset + chunk_size]
            if not chunk:
                break
            p = _path(tipus, "", setmana, page)
            _feed_singles_slide(chunk, page, pages).save(p, "JPEG", quality=90)
            out.append(p)
            offset += chunk_size
    return out[:10]


# ── STORIES ──────────────────────────────────────────────────────────


def _story_canvas() -> Image.Image:
    return Image.new("RGB", (STORY_W, STORY_H), colors.COLOR_BG)


def _story_intro(territori: str, setmana, *, label_top: str) -> Image.Image:
    """Story intro slide.

    PPCC: brand logo + the senyera icon (no card behind it) + a big
    "Setmana N" pill. No "TOP 40" or "Global" labels — the brand
    logo + icon already say it.

    Territorial: brand logo + territory icon (no card behind it) +
    "TOP N" + territory name + the Setmana pill anchored
    underneath the TOP+name block.
    """
    from .captions import TERRITORI_NOM, _setmana_label

    img = _story_canvas()
    d = ImageDraw.Draw(img)
    accent = colors.terr_color(territori)
    is_ppcc = (territori or "") == "PPCC"

    # Brand logo top, centred (tri-colour on solid ink).
    _logo_block(img, (STORY_W - 540) // 2, 200, width=540)

    # Territory icon directly on ink — no card behind.
    icon_size = 460
    icon = svg_assets.territory_icon(territori or "PPCC", icon_size, accent)
    icon_x = (STORY_W - icon_size) // 2
    icon_y = 460
    if icon is not None:
        img.paste(icon, (icon_x, icon_y), icon)

    if is_ppcc:
        # No "TOP 40", no "Global" — info already conveyed by logo +
        # senyera. Just a slightly bigger Setmana pill below the icon.
        f_sm = fonts.sans_bold(48)
        label = _setmana_label(setmana)
        pill_w, pill_h = _measure_pill(
            text=label,
            font=f_sm,
            pad_x=32,
            pad_y=18,
        )
        _pill(
            img,
            x=int((STORY_W - pill_w) // 2),
            y=icon_y + icon_size + 80,
            text=label,
            font=f_sm,
            fill=colors.COLOR_WHITE,
            text_fill=colors.COLOR_BG,
            pad_x=32,
            pad_y=18,
            radius=12,  # mm-design --mm-radius-lg
        )
    else:
        # Territorial intro: TOP N + territory name + Setmana pill.
        # Pill sits under the TOP+name block (not under the icon).
        f_big = fonts.display_bold(140)
        tw = int(d.textlength(label_top, font=f_big))
        top_y = icon_y + icon_size + 40
        d.text(
            ((STORY_W - tw) // 2, top_y),
            label_top,
            font=f_big,
            fill=colors.COLOR_YELLOW,
        )

        nom = TERRITORI_NOM.get(territori, territori)
        f_nom = fonts.display_bold(72)
        nom_tw = int(d.textlength(nom, font=f_nom))
        nom_y = top_y + 170
        d.text(
            ((STORY_W - nom_tw) // 2, nom_y),
            nom,
            font=f_nom,
            fill=colors.COLOR_WHITE,
        )

        f_sub = fonts.sans_bold(36)
        label = _setmana_label(setmana)
        pill_w, _ = _measure_pill(
            text=label,
            font=f_sub,
            pad_x=28,
            pad_y=14,
        )
        _pill(
            img,
            x=int((STORY_W - pill_w) // 2),
            y=nom_y + 130,
            text=label,
            font=f_sub,
            fill=colors.COLOR_WHITE,
            text_fill=colors.COLOR_BG,
            pad_x=28,
            pad_y=14,
            radius=12,
        )

    return img


def _story_canco(territori: str, e: dict) -> Image.Image:
    img = _story_canvas()
    d = ImageDraw.Draw(img)
    accent = colors.terr_color(territori)

    # Territori header — small icon + name in the accent colour.
    from .captions import TERRITORI_NOM

    nom = TERRITORI_NOM.get(territori, territori)
    f_h = fonts.sans_bold(36)
    htw = d.textlength(nom, font=f_h)
    icon = svg_assets.territory_icon(territori or "PPCC", 44, accent)
    icon_w = 44 + 12 if icon else 0
    total_w = htw + icon_w
    base_x = int((STORY_W - total_w) // 2)
    if icon is not None:
        img.paste(icon, (base_x, 100), icon)
    d.text((base_x + icon_w, 102), nom, font=f_h, fill=colors.COLOR_WHITE)

    # Card — full-strength territory accent (no darken). The cover
    # art fills the upper half so contrast is fine.
    card_w, card_h = 920, 1300
    cx, cy = (STORY_W - card_w) // 2, 220
    d.rounded_rectangle(
        (cx, cy, cx + card_w, cy + card_h),
        radius=32,
        fill=accent,
    )

    # Cover 750x750 centred at top of card
    cover = _cover(e.get("cover_url"), 750, fallback_letter=e.get("canco_nom", "?")[:1])
    cover_r = _rounded(cover, 24)
    img.paste(cover_r, (cx + (card_w - 750) // 2, cy + 60), cover_r)

    # ── Text block layout (Tasca B3) ───────────────────────────────
    # Pre-2026-05-18 the three text rows (TOP N, title, artist) were
    # painted at fixed cy-offsets (850 / 920 / 1210), which left a
    # ~210-px gap between the title and the artist for the common
    # single-line cases — the lower third of the green card looked
    # empty. Now the three rows are sized first, then the whole
    # block is centered vertically in the area between the cover
    # bottom (cy+810) and the card bottom (cy+1300), respecting
    # ~40-px top and ~60-px bottom paddings.
    #
    # Artist may now wrap to two lines via `_join_artists(..,
    # max_lines=2)` — applied only to stories, where vertical room
    # is generous. Feed-list rows keep their one-line constraint.

    f_pos = fonts.sans_bold(48)
    f_song = fonts.display_bold(80)
    f_a = fonts.sans_regular(44)

    # Resolve content for each row.
    pos_text = f"TOP {e['posicio']}"
    pos_tw = d.textlength(pos_text, font=f_pos)
    title_lines = _wrap_two_lines(d, e["canco_nom"], f_song, card_w - 80)[:2]
    names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
    artist_raw = _join_artists(d, names, f_a, card_w - 80, max_lines=2)
    artist_lines = artist_raw.split("\n")

    # Vertical metrics.
    TOPN_H = 48
    TITLE_LINE_SPACING = 90  # tight kerning that matches the 80-pt body
    TITLE_H = (len(title_lines) - 1) * TITLE_LINE_SPACING + 80
    ARTIST_LINE_SPACING = int(44 * 1.15)  # ~51 px, comfortable for Roboto
    ARTIST_H = (len(artist_lines) - 1) * ARTIST_LINE_SPACING + 44
    GAP_TOPN_TITLE = 22  # preserved from the legacy layout
    # Tasca B4: padding between the title's bottom and the artist
    # block is proportional to the title font size, not a fixed
    # number. With 1-line titles + 1-line artists the previous
    # constant (90 px) read tight; with 2-line titles it read
    # OK. 0.55 × 80 = 44 px puts both cases in the same visual
    # ballpark. Empirically: feels close to one body-line.
    GAP_TITLE_ARTIST = int(80 * 0.55)  # 44 px

    block_h = TOPN_H + GAP_TOPN_TITLE + TITLE_H + GAP_TITLE_ARTIST + ARTIST_H

    # Available area: cover bottom (cy + 60 + 750 = cy + 810) +
    # 40-px gutter at the top, card bottom (cy + card_h) − 60-px
    # padding at the bottom.
    available_top = cy + 60 + 750 + 40
    available_bottom = cy + card_h - 60
    available_h = max(0, available_bottom - available_top)
    # Clamp to the top of the available area if the block is taller
    # than the available room (only happens in the 2-line title +
    # 2-line artist case; still fits with ~35-px padding to the
    # card bottom).
    block_y0 = available_top + max(0, (available_h - block_h) // 2)

    # Paint TOP N.
    d.text(
        (cx + (card_w - pos_tw) // 2, block_y0),
        pos_text,
        font=f_pos,
        fill=colors.COLOR_WHITE,
    )

    # Paint title (1 or 2 lines, each centered).
    title_y0 = block_y0 + TOPN_H + GAP_TOPN_TITLE
    for i, line in enumerate(title_lines):
        line_tw = d.textlength(line, font=f_song)
        d.text(
            (cx + (card_w - line_tw) // 2, title_y0 + i * TITLE_LINE_SPACING),
            line,
            font=f_song,
            fill=colors.COLOR_WHITE,
        )

    # Paint artist (1 or 2 lines, each centered).
    artist_y0 = title_y0 + TITLE_H + GAP_TITLE_ARTIST
    for i, line in enumerate(artist_lines):
        line_tw = d.textlength(line, font=f_a)
        d.text(
            (cx + (card_w - line_tw) // 2, artist_y0 + i * ARTIST_LINE_SPACING),
            line,
            font=f_a,
            fill=colors.COLOR_WHITE,
        )

    # Footer "topquaranta.cat" on every cançó slide. Sits on the
    # ink background outside the card, so we use COLOR_TEXT_MUTED
    # (gray-400, 4.5:1 on COLOR_BG → AA-passing) — bright enough to
    # read, dim enough not to compete with the TOP N + title.
    f_footer = fonts.sans_bold(28)
    footer = "topquaranta.cat"
    fw = d.textlength(footer, font=f_footer)
    d.text(
        ((STORY_W - fw) // 2, STORY_H - 90),
        footer,
        font=f_footer,
        fill=colors.COLOR_TEXT_MUTED,
    )

    return img


def _story_cta() -> Image.Image:
    img = _story_canvas()
    d = ImageDraw.Draw(img)
    card_w, card_h = 880, 600
    cx, cy = (STORY_W - card_w) // 2, (STORY_H - card_h) // 2
    d.rounded_rectangle(
        (cx, cy, cx + card_w, cy + card_h), radius=32, fill=colors.COLOR_CARD
    )

    f1 = fonts.display_bold(64)
    line1 = "Top complet a"
    l1 = d.textlength(line1, font=f1)
    d.text((cx + (card_w - l1) // 2, cy + 180), line1, font=f1, fill=colors.COLOR_WHITE)
    f2 = fonts.display_bold(72)
    line2 = "topquaranta.cat"
    l2 = d.textlength(line2, font=f2)
    d.text(
        (cx + (card_w - l2) // 2, cy + 280), line2, font=f2, fill=colors.COLOR_YELLOW
    )
    f3 = fonts.sans_regular(28)
    line3 = "i a Spotify, Deezer, Apple Music, YouTube Music"
    l3 = d.textlength(line3, font=f3)
    d.text(
        (cx + (card_w - l3) // 2, cy + 420),
        line3,
        font=f3,
        fill=colors.COLOR_TEXT_MUTED,
    )
    return img


# ── STORIES · PPCC editorial set (Step 3c redesign) ──────────────────
#
# Seven slides, ordered to build toward the #1 climax. The visual
# language is the validated Claude Design canvas (1080×1920, pixel
# values measured from the reference PNGs):
#   1. intro     — green field, "EL TOP / 40 / D'AQUESTA SETMANA"
#   2. top 40-11 — 5×6 cover mosaic, yellow number badges
#   3. top 10-4  — 2-col cover grid (+ #4 centred below)
#   4. podi #3-2 — two big covers stacked, number + title + artist
#   5. #1 hero   — Playfair song title climax (inverted hierarchy)
#   6. novetats  — 2-3 recent releases
#   7. outro     — yellow field, "EL TOP 40", informative URL
#
# Typography: Anton (display/numbers), Bricolage Grotesque 800 (song
# titles on 2/3/4/6), Playfair Display 800 (slide-5 title ONLY),
# Instrument Serif italic (the two serif accents), Roboto (sans role:
# kickers, artist subtitles, hero scenario, CTA). No trend cues.

GREEN_PPCC = colors.terr_color("PPCC")  # #427C42

# Content-box padding (top, right, bottom, left).
_PAD_INTRO = (110, 80, 92, 80)  # usable width 920
_PAD_STD = (96, 90, 80, 90)  # usable width 900


# ── low-level text + background helpers ──────────────────────────────


def _tracked_width(d: ImageDraw.ImageDraw, text: str, font, tracking: float) -> float:
    """Advance width of `text` with `tracking` px added after each glyph
    except the last (PIL has no native letter-spacing)."""
    if not text:
        return 0.0
    w = sum(d.textlength(ch, font=font) for ch in text)
    return w + tracking * (len(text) - 1)


def _draw_tracked(
    d: ImageDraw.ImageDraw,
    x: float,
    y_top: float,
    text: str,
    font,
    fill,
    *,
    tracking: float = 0.0,
    center_w: int | None = None,
):
    """Draw a single line glyph-by-glyph with letter-spacing.

    `y_top` is the visual top of the inked glyphs (we offset by the
    line's bbox top so callers can stack lines by a chosen line-height
    instead of PIL's em-box top). When `center_w` is given, the line is
    horizontally centred within `[0, center_w]`."""
    w = _tracked_width(d, text, font, tracking)
    if center_w is not None:
        x = (center_w - w) / 2
    top_off = d.textbbox((0, 0), text, font=font)[1]
    cx = x
    for ch in text:
        d.text((cx, y_top - top_off), ch, font=font, fill=fill)
        cx += d.textlength(ch, font=font) + tracking
    return w


def _draw_star(d: ImageDraw.ImageDraw, cx: float, cy: float, r_out: float, fill):
    """Five-pointed star polygon (font-independent — none of the bundled
    display fonts carry U+2605)."""
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = r_out if i % 2 == 0 else r_out * 0.42
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    d.polygon(pts, fill=fill)


def _radial_bg(
    inner_hex: str,
    outer_hex: str,
    center: tuple[float, float],
    radii: tuple[float, float],
    stop_outer: float,
) -> Image.Image:
    """Full-canvas RGB background with a CSS-style elliptical radial
    gradient: `inner_hex` at the centre fading to `outer_hex` at
    `stop_outer` of the ellipse radius (clamped beyond)."""
    yy, xx = np.mgrid[0:STORY_H, 0:STORY_W].astype("float32")
    cx, cy = center[0] * STORY_W, center[1] * STORY_H
    rx, ry = radii[0] * STORY_W, radii[1] * STORY_H
    dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    t = np.clip(dist / stop_outer, 0.0, 1.0)[..., None]
    inner = np.array(colors._hex_to_rgb(inner_hex), dtype="float32")
    outer = np.array(colors._hex_to_rgb(outer_hex), dtype="float32")
    arr = inner * (1 - t) + outer * t
    return Image.fromarray(arr.astype("uint8"), "RGB")


def _bg_ink(center=(0.5, 0.0), radii=(1.2, 0.6), stop=0.6) -> Image.Image:
    """Ink slides (2/3/4/6): #141210 centre → #0A0A0A."""
    return _radial_bg(colors.COLOR_INK_CENTRE, colors.COLOR_BG, center, radii, stop)


def _logo_white(width: int) -> Image.Image | None:
    return svg_assets.logo_image_mono(width, colors.COLOR_WHITE)


def _logo_ink(width: int) -> Image.Image | None:
    return svg_assets.logo_image_mono(width, colors.COLOR_BG)


def _setmana_pill(img: Image.Image, right_x: int, cy: int, setmana) -> None:
    """Yellow SETMANA pill (Anton 26, ls 3, ink text), right edge pinned
    at `right_x`, vertically centred on `cy`."""
    from .captions import _setmana_label

    d = ImageDraw.Draw(img)
    label = _setmana_label(setmana).upper()
    f = fonts.anton(26)
    tracking = 3
    pad_x, pad_y = 18, 7
    tw = _tracked_width(d, label, f, tracking)
    bbox = d.textbbox((0, 0), label, font=f)
    th = bbox[3] - bbox[1]
    pill_w = tw + 2 * pad_x
    pill_h = th + 2 * pad_y
    x0 = right_x - pill_w
    y0 = cy - pill_h // 2
    d.rectangle((x0, y0, x0 + pill_w, y0 + pill_h), fill=colors.COLOR_YELLOW)
    _draw_tracked(
        d, x0 + pad_x, y0 + pad_y, label, f, colors.COLOR_BG, tracking=tracking
    )


def _header_row(img: Image.Image, setmana, *, logo_w: int = 217, logo_h: int = 44):
    """Slides 2/3/4/6 header: white logo left, SETMANA pill right, row
    height ≈53 vertically centred at the top padding."""
    left = _PAD_STD[3]
    right = STORY_W - _PAD_STD[1]
    top = _PAD_STD[0]
    row_h = 53
    cy = top + row_h // 2
    logo = _logo_white(logo_w)
    if logo is not None:
        img.paste(logo, (left, cy - logo.size[1] // 2), logo)
    _setmana_pill(img, right, cy, setmana)
    return top + row_h


def _section_header(
    img: Image.Image,
    title: str,
    y_title_top: int,
    *,
    kicker: str | None = None,
    title_color: str = colors.COLOR_WHITE,
    rule_color: str = colors.COLOR_YELLOW,
) -> int:
    """Optional green kicker + Anton-96 title + accent rule. Centred.
    Returns the y just below the rule."""
    d = ImageDraw.Draw(img)
    y = y_title_top
    if kicker:
        fk = fonts.sans_bold(25)
        _draw_tracked(
            d, 0, y, kicker, fk, colors.COLOR_GREEN_LIGHT, tracking=7, center_w=STORY_W
        )
        y += 25 + 12
    ft = fonts.anton(96)
    _draw_tracked(d, 0, y, title, ft, title_color, tracking=0.96, center_w=STORY_W)
    title_bbox = d.textbbox((0, 0), title, font=ft)
    y += (title_bbox[3] - title_bbox[1]) + 22
    rule_w = 130
    d.rectangle(
        ((STORY_W - rule_w) // 2, y, (STORY_W + rule_w) // 2, y + 7), fill=rule_color
    )
    return y + 7


def _footer_url(img: Image.Image) -> None:
    """`topquaranta.cat` — Anton 30, ls 4, green-light, centred, near the
    bottom edge (slides 2-6)."""
    d = ImageDraw.Draw(img)
    f = fonts.anton(30)
    _draw_tracked(
        d,
        0,
        STORY_H - 92,
        "topquaranta.cat",
        f,
        colors.COLOR_GREEN_LIGHT,
        tracking=4,
        center_w=STORY_W,
    )


def _number_badge(img: Image.Image, sx: int, sy: int, text: str, *, font, pad_x, pad_y):
    """Yellow-on-ink Anton number badge, top-left corner pinned at
    (sx, sy) (width auto so double digits grow rightward)."""
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    bw, bh = tw + 2 * pad_x, th + 2 * pad_y
    d.rectangle((sx, sy, sx + bw, sy + bh), fill=colors.COLOR_BG)
    d.text(
        (sx + pad_x - bbox[0], sy + pad_y - bbox[1]),
        text,
        font=font,
        fill=colors.COLOR_YELLOW,
    )


def _paste_cover(
    img: Image.Image, entry: dict, x: int, y: int, size: int, *, key="canco_nom"
):
    """Resolve + paste a square cover at (x, y). No rounding (the design
    uses flat squares)."""
    cov = _story_cover(
        entry.get("album_deezer_id"),
        entry.get("cover_url"),
        size,
        fallback_letter=(entry.get(key) or "?")[:1],
    )
    img.paste(cov, (x, y))


def _wrap_tracked(d, text, font, max_width, tracking, max_lines):
    """Greedy word-wrap into ≤ max_lines lines under `max_width` (with
    tracking), ellipsising the last line."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        if _tracked_width(d, cand, font, tracking) <= max_width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines and cur and (not lines or lines[-1] != cur):
        lines.append(cur)
    lines = lines[:max_lines]
    # Ellipsise the final line if content remains.
    if lines and _tracked_width(d, lines[-1], font, tracking) > max_width:
        s = lines[-1]
        while s and _tracked_width(d, s + "…", font, tracking) > max_width:
            s = s[:-1]
        lines[-1] = (s + "…") if s else "…"
    return lines


# ── slide builders ───────────────────────────────────────────────────


def _story_intro_ppcc(setmana) -> Image.Image:
    """Slide 1 — green intro. Logo, "presenta", the big EL TOP / 40 /
    D'AQUESTA SETMANA stack, and the star-separated SETMANA pill row."""
    from .captions import _setmana_label

    img = _radial_bg(GREEN_PPCC, colors.COLOR_GREEN_DEEP, (0.5, 0.0), (1.3, 0.8), 1.0)
    d = ImageDraw.Draw(img)

    # Logo white 340×69, centred at the top padding.
    logo = _logo_white(340)
    y = _PAD_INTRO[0]
    if logo is not None:
        img.paste(logo, ((STORY_W - logo.size[0]) // 2, y), logo)
        logo_bottom = y + logo.size[1]
    else:
        logo_bottom = y + 69

    # "presenta" — Instrument Serif italic 56, cream.
    fp = fonts.instrument_italic(56)
    _draw_tracked(
        d, 0, logo_bottom + 40, "presenta", fp, colors.COLOR_CREAM, center_w=STORY_W
    )

    # Central headline stack (tight, the 40 overflows its line box).
    f_top = fonts.anton(150)
    _draw_tracked(
        d, 0, 560, "EL TOP", f_top, colors.COLOR_WHITE, tracking=0.75, center_w=STORY_W
    )
    f_40 = fonts.anton(380)
    _draw_tracked(
        d, 0, 632, "40", f_40, colors.COLOR_YELLOW, tracking=-7.6, center_w=STORY_W
    )
    f_setm = fonts.anton(100)
    _draw_tracked(
        d,
        0,
        980,
        "D'AQUESTA SETMANA",
        f_setm,
        colors.COLOR_WHITE,
        tracking=1,
        center_w=STORY_W,
    )

    # Footer group anchored to the bottom padding.
    base = STORY_H - _PAD_INTRO[2]
    # Pill row: "SETMANA N" (yellow box) + "CADA DISSABTE" (white).
    f_pill = fonts.anton(46)
    setm_label = _setmana_label(setmana).upper()
    second = "CADA DISSABTE"
    pad_x, pad_y = 24, 8
    tr = 3
    w_setm = _tracked_width(d, setm_label, f_pill, tr)
    bbox = d.textbbox((0, 0), setm_label, font=f_pill)
    th = bbox[3] - bbox[1]
    pill_w = w_setm + 2 * pad_x
    pill_h = th + 2 * pad_y
    gap = 24
    w_second = _tracked_width(d, second, f_pill, tr)
    total_w = pill_w + gap + w_second
    row_x = (STORY_W - total_w) / 2
    pill_y = base - pill_h
    d.rectangle(
        (row_x, pill_y, row_x + pill_w, pill_y + pill_h), fill=colors.COLOR_YELLOW
    )
    _draw_tracked(
        d,
        row_x + pad_x,
        pill_y + pad_y,
        setm_label,
        f_pill,
        colors.COLOR_BG,
        tracking=tr,
    )
    _draw_tracked(
        d,
        row_x + pill_w + gap,
        pill_y + pad_y,
        second,
        f_pill,
        colors.COLOR_WHITE,
        tracking=tr,
    )

    # Star separator above the pill row.
    sep_y = pill_y - 37
    line_col = colors.mix(GREEN_PPCC, colors.COLOR_WHITE, 0.35)
    cxc = STORY_W / 2
    star_r, gap, sep_total = 16, 40, 920
    left0 = (STORY_W - sep_total) / 2
    d.rectangle((left0, sep_y, cxc - star_r - gap, sep_y + 2), fill=line_col)
    d.rectangle(
        (cxc + star_r + gap, sep_y, left0 + sep_total, sep_y + 2), fill=line_col
    )
    _draw_star(d, cxc, sep_y + 1, star_r, colors.COLOR_WHITE)
    return img


def _story_top_mosaic(setmana, entries: list[dict]) -> Image.Image:
    """Slide 2 — positions 40→11 as a 5×6 cover mosaic with yellow Anton
    number badges + Bricolage titles + Roboto artist subtitles."""
    img = _bg_ink()
    _header_row(img, setmana)
    body_top = _section_header(img, "EL RÀNQUING", 200)

    d = ImageDraw.Draw(img)
    cols, gap = 5, 18
    left = _PAD_STD[3]
    cover = 150
    cell_w = (STORY_W - _PAD_STD[1] - left - (cols - 1) * gap) // cols  # 165.6→165
    grid_top = body_top + 40
    f_badge = fonts.anton(33)
    f_title = fonts.bricolage_xbold(20)
    f_artist = fonts.sans_regular(17)
    # Descending 40→11 so the mosaic ends one rank above the top-10 reveal.
    items = list(reversed(entries[:30]))
    for idx, e in enumerate(items):
        r, c = divmod(idx, cols)
        x = left + c * (cell_w + gap)
        y = grid_top + r * (cell_w + 78)  # cover + title/artist block
        _paste_cover(img, e, x, y, cover)
        _number_badge(
            img,
            x,
            y,
            str(e.get("posicio") or (40 - idx)),
            font=f_badge,
            pad_x=15,
            pad_y=7,
        )
        ty = y + cover + 10
        for line in _wrap_tracked(
            d, e.get("canco_nom") or "—", f_title, cell_w, -0.2, 2
        ):
            _draw_tracked(d, x, ty, line, f_title, colors.COLOR_WHITE, tracking=-0.2)
            ty += 21
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        artist = _truncate(d, ", ".join(names), f_artist, cell_w)
        _draw_tracked(
            d,
            x,
            ty + 4,
            artist,
            f_artist,
            colors.mix(colors.COLOR_BG, colors.COLOR_WHITE, 0.62),
        )
    _footer_url(img)
    return img


def _story_top_grid(setmana, entries: list[dict]) -> Image.Image:
    """Slide 3 — positions 10→4: 2-column cover grid (#10/#9, #8/#7,
    #6/#5) then #4 centred below."""
    img = _bg_ink()
    _header_row(img, setmana)
    body_top = _section_header(img, "ENS ACOSTEM AL CIM", 200)

    d = ImageDraw.Draw(img)
    cover = 210
    col_gap, row_gap = 48, 40
    left = _PAD_STD[3]
    col_x = [left, left + cover + col_gap]
    # The two columns are left-aligned within the content box; centre the
    # pair block.
    pair_w = 2 * cover + col_gap
    block_left = (STORY_W - pair_w) // 2
    col_x = [block_left, block_left + cover + col_gap]
    grid_top = body_top + 40
    row_h = cover + 78 + row_gap
    f_badge = fonts.anton(46)
    f_title = fonts.bricolage_xbold(32)
    f_artist = fonts.sans_regular(25)
    subtle = colors.mix(colors.COLOR_BG, colors.COLOR_WHITE, 0.62)

    def _cell(e, x, y, pos):
        _paste_cover(img, e, x, y, cover)
        _number_badge(img, x, y, str(pos), font=f_badge, pad_x=21, pad_y=9)
        ty = y + cover + 14
        for line in _wrap_tracked(
            d, e.get("canco_nom") or "—", f_title, cover + 30, -0.32, 2
        ):
            _draw_tracked(d, x, ty, line, f_title, colors.COLOR_WHITE, tracking=-0.32)
            ty += 34
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        artist = _truncate(d, ", ".join(names), f_artist, cover + 30)
        _draw_tracked(d, x, ty + 4, artist, f_artist, subtle)

    # Descending 10→4: grid holds #10/#9, #8/#7, #6/#5; #4 centred below.
    items = list(reversed(entries[:7]))
    for idx, e in enumerate(items[:6]):
        r, c = divmod(idx, 2)
        x = col_x[c]
        y = grid_top + r * row_h
        _cell(e, x, y, e.get("posicio") or (10 - idx))
    # #4 centred below, in its own row.
    if len(items) >= 7:
        e = items[6]
        x = (STORY_W - cover) // 2
        y = grid_top + 3 * row_h
        _cell(e, x, y, e.get("posicio") or 4)
    _footer_url(img)
    return img


def _story_podi(entries: list[dict], setmana) -> Image.Image:
    """Slide 4 — #3 (top) and #2 (below): centred big covers with a big
    Anton number badge, Bricolage title and Roboto artist."""
    img = _radial_bg(
        colors.COLOR_INK_CENTRE, colors.COLOR_BG, (0.5, 0.04), (1.1, 0.55), 0.58
    )
    _header_row(img, setmana)
    _section_header(img, "EL PODI", 200, kicker="JA GAIREBÉ HI SOM")

    d = ImageDraw.Draw(img)
    cover = 300
    f_badge = fonts.anton(66)
    f_title = fonts.bricolage_xbold(60)
    f_artist = fonts.sans_regular(38)
    subtle = colors.mix(colors.COLOR_BG, colors.COLOR_WHITE, 0.66)
    entry_h = cover + 20 + 64 + 6 + 46  # cover + title block + artist
    top0 = 470
    gap = 120
    # entries arrive as [#2, #3]; show #3 on top then #2, building toward #1.
    ordered = list(entries[:2])[::-1]
    for idx, e in enumerate(ordered):
        y = top0 + idx * (entry_h + gap)
        x = (STORY_W - cover) // 2
        _paste_cover(img, e, x, y, cover)
        _number_badge(
            img, x, y, str(e.get("posicio", 3 - idx)), font=f_badge, pad_x=30, pad_y=13
        )
        ty = y + cover + 20
        title_lines = _wrap_tracked(
            d, e.get("canco_nom") or "—", f_title, STORY_W - 180, -1.2, 2
        )
        for line in title_lines:
            _draw_tracked(
                d,
                0,
                ty,
                line,
                f_title,
                colors.COLOR_WHITE,
                tracking=-1.2,
                center_w=STORY_W,
            )
            ty += 62
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        artist = _truncate(d, ", ".join(names), f_artist, STORY_W - 180)
        _draw_tracked(d, 0, ty + 6, artist, f_artist, subtle, center_w=STORY_W)
    _footer_url(img)
    return img


def _story_hero(entry: dict, headline: str | None) -> Image.Image:
    """Slide 5 — the #1 climax. Inverted hierarchy: the editorial
    scenario is a subordinate yellow kicker; the SONG TITLE in Playfair
    Display 800 is the primary element."""
    img = _radial_bg(
        colors.mix(colors.COLOR_BG, colors.COLOR_YELLOW, 0.16),
        colors.COLOR_BG,
        (0.5, 0.32),
        (0.8, 0.5),
        0.6,
    )
    d = ImageDraw.Draw(img)

    # Ghost "1" behind everything (white α0.04), clipped at the right.
    ghost = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(ghost)
    fg = fonts.anton(640)
    gd.text((842, 40), "1", font=fg, fill=(255, 255, 255, 10))
    img.paste(Image.alpha_composite(img.convert("RGBA"), ghost).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)

    # Logo white 217×44, top centred.
    logo = _logo_white(217)
    if logo is not None:
        img.paste(logo, ((STORY_W - logo.size[0]) // 2, _PAD_STD[0]), logo)

    # Kicker "EL NÚMERO 1".
    fk = fonts.anton(32)
    _draw_tracked(
        d, 0, 360, "EL NÚMERO 1", fk, colors.COLOR_YELLOW, tracking=10, center_w=STORY_W
    )

    # Cover 400×400 centred, hairline inset.
    cover = 400
    cx = (STORY_W - cover) // 2
    cy = 430
    _paste_cover(img, entry, cx, cy, cover)
    d.rectangle(
        (cx, cy, cx + cover - 1, cy + cover - 1),
        outline=colors.mix(colors.COLOR_BG, colors.COLOR_WHITE, 0.08),
        width=1,
    )

    # Editorial scenario (subordinate kicker).
    text = (headline or "AL CIM AQUESTA SETMANA").strip() or "AL CIM AQUESTA SETMANA"
    fsc = fonts.sans_bold(26)
    sy = cy + cover + 36
    sc_lines = _wrap_tracked(d, text, fsc, STORY_W - 180, 5, 2)
    for line in sc_lines:
        _draw_tracked(
            d, 0, sy, line, fsc, colors.COLOR_YELLOW, tracking=5, center_w=STORY_W
        )
        sy += 34

    # Song title — Playfair Display 800, the PRIMARY element.
    ft = fonts.display_xbold(108)
    title_lines = _wrap_two_lines(d, entry.get("canco_nom") or "—", ft, 880)[:2]
    ty = sy + 16
    for line in title_lines:
        _draw_tracked(d, 0, ty, line, ft, colors.COLOR_YELLOW, center_w=STORY_W)
        ty += 114

    # Artist — Roboto 700, white.
    fa = fonts.sans_bold(50)
    names = entry.get("artistes_noms") or [entry.get("artista_nom") or "—"]
    artist = _truncate(d, ", ".join(names), fa, STORY_W - 180)
    _draw_tracked(d, 0, ty + 30, artist, fa, colors.COLOR_WHITE, center_w=STORY_W)

    _footer_url(img)
    return img


def _story_novetats(setmana, items: list[dict]) -> Image.Image:
    """Slide 6 — 2-3 recent releases stacked: centred cover + Bricolage
    title + Roboto artist, no number badge."""
    img = _bg_ink()
    _header_row(img, setmana)
    _section_header(
        img,
        "NOVETATS",
        200,
        kicker="FORA DEL TOP · ESTRENES",
        title_color=colors.COLOR_YELLOW,
        rule_color=colors.COLOR_GREEN_LIGHT,
    )

    d = ImageDraw.Draw(img)
    cover = 210
    f_title = fonts.bricolage_xbold(50)
    f_artist = fonts.sans_regular(32)
    subtle = colors.mix(colors.COLOR_BG, colors.COLOR_WHITE, 0.66)
    items = items[:3]
    entry_h = cover + 16 + 52 + 6 + 32
    gap = 70
    block_h = len(items) * entry_h + (len(items) - 1) * gap if items else 0
    top0 = max(470, (STORY_H - block_h) // 2)
    for idx, it in enumerate(items):
        y = top0 + idx * (entry_h + gap)
        x = (STORY_W - cover) // 2
        _paste_cover(img, it, x, y, cover, key="nom")
        ty = y + cover + 16
        for line in _wrap_tracked(
            d, it.get("nom") or "—", f_title, STORY_W - 180, -1, 2
        ):
            _draw_tracked(
                d,
                0,
                ty,
                line,
                f_title,
                colors.COLOR_WHITE,
                tracking=-1,
                center_w=STORY_W,
            )
            ty += 52
        artist = _truncate(d, it.get("artista_nom") or "—", f_artist, STORY_W - 180)
        _draw_tracked(d, 0, ty + 6, artist, f_artist, subtle, center_w=STORY_W)
    _footer_url(img)
    return img


def _story_outro_ppcc(setmana) -> Image.Image:
    """Slide 7 — yellow outro. Ink logo, "tens el rànquing sencer" serif
    accent, big "EL TOP 40", star separator, CTA with an underlined
    domain, and a SETMANA footer. No slate card."""
    from .captions import _setmana_label

    img = Image.new("RGB", (STORY_W, STORY_H), colors.COLOR_YELLOW)
    d = ImageDraw.Draw(img)

    logo = _logo_ink(266)
    y = _PAD_STD[0]
    if logo is not None:
        img.paste(logo, ((STORY_W - logo.size[0]) // 2, y), logo)

    ink = colors.COLOR_BG
    # Serif accent.
    fa = fonts.instrument_italic(52)
    _draw_tracked(
        d,
        0,
        560,
        "tens el rànquing sencer",
        fa,
        colors.mix(colors.COLOR_YELLOW, ink, 0.72),
        center_w=STORY_W,
    )
    # "EL TOP 40".
    ft = fonts.anton(158)
    _draw_tracked(d, 0, 650, "EL TOP 40", ft, ink, tracking=0.79, center_w=STORY_W)

    # Star separator.
    sep_y = 960
    line_col = colors.mix(colors.COLOR_YELLOW, ink, 0.25)
    cxc = STORY_W / 2
    star_r, gap, sep_total = 15, 30, 520
    left0 = (STORY_W - sep_total) / 2
    d.rectangle((left0, sep_y, cxc - star_r - gap, sep_y + 3), fill=line_col)
    d.rectangle(
        (cxc + star_r + gap, sep_y, left0 + sep_total, sep_y + 3), fill=line_col
    )
    _draw_star(d, cxc, sep_y + 1, star_r, ink)

    # CTA with underlined domain.
    fc = fonts.sans_bold(42)
    cta_pre = "Cada dissabte a "
    cta_dom = "topquaranta.cat"
    tr = 1
    w_pre = _tracked_width(d, cta_pre, fc, tr)
    w_dom = _tracked_width(d, cta_dom, fc, tr)
    cta_y = 1060
    x0 = (STORY_W - (w_pre + w_dom)) / 2
    _draw_tracked(d, x0, cta_y, cta_pre, fc, ink, tracking=tr)
    _draw_tracked(d, x0 + w_pre, cta_y, cta_dom, fc, ink, tracking=tr)
    dom_bbox = d.textbbox((0, 0), cta_dom, font=fc)
    underline_y = cta_y + (dom_bbox[3] - dom_bbox[1]) + 10
    d.rectangle(
        (x0 + w_pre, underline_y, x0 + w_pre + w_dom, underline_y + 2), fill=ink
    )

    # SETMANA footer.
    ff = fonts.anton(40)
    _draw_tracked(
        d,
        0,
        STORY_H - _PAD_STD[2] - 40,
        _setmana_label(setmana).upper(),
        ff,
        ink,
        tracking=4,
        center_w=STORY_W,
    )
    return img


def render_stories_ppcc(
    setmana,
    entries: list[dict],
    *,
    novetats_items: list[dict] | None = None,
    hero_headline: str | None = None,
) -> list[Path]:
    """Render the 7-slide editorial PPCC story set (Step 3b structure,
    Step 3c visual redesign).

    The novetats slide is skipped when no recent releases are available,
    so the set is 6 or 7 slides. Territorial stories keep
    `render_stories_top`."""
    out: list[Path] = []
    novetats_items = novetats_items or []

    def _emit(img: Image.Image):
        p = _path("top_ppcc", "PPCC", setmana, len(out), story=True)
        img.save(p, "JPEG", quality=90)
        out.append(p)

    _emit(_story_intro_ppcc(setmana))
    _emit(_story_top_mosaic(setmana, entries[10:40]))
    _emit(_story_top_grid(setmana, entries[3:10]))
    _emit(_story_podi(entries[1:3], setmana))
    _emit(_story_hero(entries[0] if entries else {}, hero_headline))
    if novetats_items:
        _emit(_story_novetats(setmana, novetats_items[:3]))
    _emit(_story_outro_ppcc(setmana))
    return out


def render_stories_top(
    tipus: str, territori: str, setmana, entries: list[dict], *, max_cancons: int
) -> list[Path]:
    """Story sequence: intro + N cançó slides + CTA.

    `max_cancons` capped by ConfiguracioGlobal.story_max_cancons_ppcc
    for PPCC; territorial defaults to top 5."""
    out: list[Path] = []
    label = f"TOP {min(max_cancons, len(entries))}"

    p = _path(tipus, territori, setmana, 0, story=True)
    _story_intro(territori, setmana, label_top=label).save(p, "JPEG", quality=90)
    out.append(p)

    for i, e in enumerate(entries[:max_cancons], start=1):
        p = _path(tipus, territori, setmana, i, story=True)
        _story_canco(territori, e).save(p, "JPEG", quality=90)
        out.append(p)

    p = _path(tipus, territori, setmana, len(out), story=True)
    _story_cta().save(p, "JPEG", quality=90)
    out.append(p)
    return out
