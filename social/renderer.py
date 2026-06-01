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
from io import BytesIO
from pathlib import Path

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


# ── STORIES · PPCC editorial set (Step 3b) ───────────────────────────
#
# Seven slides, ordered to build toward the #1 climax:
#   1. intro       — green PPCC senyera + logo + Setmana pill
#   2. top 11-40   — 5×6 cover mosaic with a position badge per cell
#   3. top 4-10    — 2-column cover grid, last one centred
#   4. podi #2-3   — two 350 px covers stacked, title + artist each
#   5. #1 hero     — big cover + synthesised Playfair headline (climax)
#   6. novetats    — 2-3 recent releases with covers
#   7. outro       — yellow-accent CTA (no slate card)
#
# Typography: Playfair Display is used ONLY on the #1 hero headline;
# every other text on the seven slides is Roboto (sans). No trend cues.

GREEN_PPCC = colors.terr_color("PPCC")


def _story_footer_caption(d: ImageDraw.ImageDraw, text: str):
    """Centred muted footer line (the slide 'peu')."""
    f = fonts.sans_bold(30)
    tw = d.textlength(text, font=f)
    d.text(
        ((STORY_W - tw) // 2, STORY_H - 96),
        text,
        font=f,
        fill=colors.COLOR_TEXT_MUTED,
    )


def _pos_badge(
    img: Image.Image,
    x: int,
    y: int,
    pos,
    *,
    size: int = 48,
    fill: str = GREEN_PPCC,
    font_size: int = 26,
):
    """Small rounded position badge (green, white number) anchored at
    the top-left of a cover thumbnail."""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((x, y, x + size, y + size), radius=12, fill=fill)
    f = fonts.sans_bold(font_size)
    t = str(pos)
    tw = d.textlength(t, font=f)
    bbox = f.getbbox(t)
    th = bbox[3] - bbox[1]
    d.text(
        (x + (size - tw) // 2, y + (size - th) // 2 - bbox[1]),
        t,
        font=f,
        fill=colors.COLOR_WHITE,
    )


def _story_kicker(d: ImageDraw.ImageDraw, text: str, y: int, *, fill: str = GREEN_PPCC):
    """Centred green section kicker (Roboto bold)."""
    f = fonts.sans_bold(56)
    tw = d.textlength(text, font=f)
    d.text(((STORY_W - tw) // 2, y), text, font=f, fill=fill)


def _story_top_mosaic(setmana, entries: list[dict]) -> Image.Image:
    """Slide 2 — positions 11-40 as a 5×6 mosaic of cover thumbnails,
    each with a position badge. Peu: 'Top 11-40 · Setmana N'."""
    from .captions import _setmana_label

    img = _story_canvas()
    d = ImageDraw.Draw(img)
    _story_kicker(d, "TOP 11–40", 150)

    cols, rows = 5, 6
    margin_x, gap = 60, 16
    cell = (STORY_W - 2 * margin_x - (cols - 1) * gap) // cols  # ≈179
    grid_top = 300
    for idx, e in enumerate(entries[: cols * rows]):
        r, c = divmod(idx, cols)
        x = margin_x + c * (cell + gap)
        y = grid_top + r * (cell + gap)
        cover = _story_cover(
            e.get("album_deezer_id"),
            e.get("cover_url"),
            cell,
            fallback_letter=(e.get("canco_nom") or "?")[:1],
        )
        img.paste(_rounded(cover, 12), (x, y), _rounded(cover, 12))
        _pos_badge(img, x + 6, y + 6, e.get("posicio", idx + 11), size=44, font_size=24)

    _story_footer_caption(d, f"Top 11–40 · {_setmana_label(setmana)}")
    return img


def _story_top_grid(setmana, entries: list[dict]) -> Image.Image:
    """Slide 3 — positions 4-10 as a 2-column cover grid (last centred),
    each cover with a position badge. Mirrors the newsletter D1a 'top
    4-10' block, adapted to a 9:16 story."""
    from .captions import _setmana_label

    img = _story_canvas()
    d = ImageDraw.Draw(img)
    _story_kicker(d, "TOP 4–10", 150)

    items = entries[:7]
    cover = 300
    gap = 48
    col_x = [
        (STORY_W - 2 * cover - gap) // 2,
        (STORY_W - 2 * cover - gap) // 2 + cover + gap,
    ]
    grid_top = 320
    row_h = cover + gap
    n = len(items)
    for idx, e in enumerate(items):
        is_last_odd = idx == n - 1 and n % 2 == 1
        r = idx // 2
        if is_last_odd:
            x = (STORY_W - cover) // 2
        else:
            x = col_x[idx % 2]
        y = grid_top + r * row_h
        cov = _story_cover(
            e.get("album_deezer_id"),
            e.get("cover_url"),
            cover,
            fallback_letter=(e.get("canco_nom") or "?")[:1],
        )
        img.paste(_rounded(cov, 20), (x, y), _rounded(cov, 20))
        _pos_badge(
            img, x + 14, y + 14, e.get("posicio", idx + 4), size=64, font_size=34
        )

    _story_footer_caption(d, _setmana_label(setmana))
    return img


def _story_podi(entries: list[dict]) -> Image.Image:
    """Slide 4 — positions 2 & 3 stacked: a 350 px cover each with the
    song title (Roboto bold) and artist (Roboto regular) alongside.

    Note: the Step-3 brief sketched Playfair for these titles, but the
    project invariant reserves Playfair for the #1 hero headline only;
    the podi titles are Roboto to honour it."""
    img = _story_canvas()
    d = ImageDraw.Draw(img)
    _story_kicker(d, "EL PODI", 150)

    cover = 350
    cover_x = 80
    text_x = cover_x + cover + 50
    text_w = STORY_W - text_x - 60
    f_pos = fonts.sans_bold(120)
    f_song = fonts.sans_bold(54)
    f_artist = fonts.sans_regular(38)
    top0 = 360
    row_h = cover + 110
    for idx, e in enumerate(entries[:2]):
        y = top0 + idx * row_h
        cov = _story_cover(
            e.get("album_deezer_id"),
            e.get("cover_url"),
            cover,
            fallback_letter=(e.get("canco_nom") or "?")[:1],
        )
        img.paste(_rounded(cov, 24), (cover_x, y), _rounded(cov, 24))

        pos = str(e.get("posicio", idx + 2))
        d.text((text_x, y - 6), pos, font=f_pos, fill=GREEN_PPCC)
        # Song title (up to 2 lines) + artist under the big number.
        title_lines = _wrap_two_lines(d, e.get("canco_nom") or "—", f_song, text_w)[:2]
        ty = y + 150
        for line in title_lines:
            d.text((text_x, ty), line, font=f_song, fill=colors.COLOR_WHITE)
            ty += 62
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        artist = _join_artists(d, names, f_artist, text_w)
        d.text((text_x, ty + 8), artist, font=f_artist, fill=colors.COLOR_TEXT_MUTED)

    return img


def _story_hero(entry: dict, headline: str | None) -> Image.Image:
    """Slide 5 — the #1 climax. A synthesised Playfair headline on top,
    a large (720 px) cover centred, the song name + artist (Roboto)
    underneath. `headline` comes from `story_synth.synthesize_hero`;
    an empty value falls back to a generic line."""
    img = _story_canvas()
    d = ImageDraw.Draw(img)

    # "#1" eyebrow.
    f_eyebrow = fonts.sans_bold(40)
    eb = "#1 DE LA SETMANA"
    d.text(
        ((STORY_W - d.textlength(eb, font=f_eyebrow)) // 2, 110),
        eb,
        font=f_eyebrow,
        fill=GREEN_PPCC,
    )

    # Synthesised headline — the ONLY Playfair text in the set.
    text = (headline or "AL CIM AQUESTA SETMANA").strip() or "AL CIM AQUESTA SETMANA"
    f_head = fonts.display_bold(72)
    head_lines = _wrap_two_lines(d, text, f_head, STORY_W - 120)[:2]
    hy = 200
    for line in head_lines:
        lw = d.textlength(line, font=f_head)
        d.text(((STORY_W - lw) // 2, hy), line, font=f_head, fill=colors.COLOR_YELLOW)
        hy += 92

    # Big cover, centred, with a green frame so it pops on ink.
    cover = 720
    cy = max(hy + 40, 460)
    cx = (STORY_W - cover) // 2
    d.rounded_rectangle(
        (cx - 16, cy - 16, cx + cover + 16, cy + cover + 16),
        radius=40,
        fill=GREEN_PPCC,
    )
    cov = _story_cover(
        entry.get("album_deezer_id"),
        entry.get("cover_url"),
        cover,
        fallback_letter=(entry.get("canco_nom") or "?")[:1],
    )
    img.paste(_rounded(cov, 28), (cx, cy), _rounded(cov, 28))

    # Song + artist (Roboto) under the cover.
    f_song = fonts.sans_bold(60)
    f_artist = fonts.sans_regular(44)
    song = _truncate(d, entry.get("canco_nom") or "—", f_song, STORY_W - 120)
    ty = cy + cover + 60
    d.text(
        ((STORY_W - d.textlength(song, font=f_song)) // 2, ty),
        song,
        font=f_song,
        fill=colors.COLOR_WHITE,
    )
    names = entry.get("artistes_noms") or [entry.get("artista_nom") or "—"]
    artist_raw = _join_artists(d, names, f_artist, STORY_W - 120, max_lines=2)
    ay = ty + 78
    for line in artist_raw.split("\n"):
        d.text(
            ((STORY_W - d.textlength(line, font=f_artist)) // 2, ay),
            line,
            font=f_artist,
            fill=colors.COLOR_TEXT_MUTED,
        )
        ay += 54
    return img


def _story_novetats(setmana, items: list[dict]) -> Image.Image:
    """Slide 6 — 2-3 recent releases, each as a cover + title + artist
    row. Same visual family as the newsletter novetats block."""
    img = _story_canvas()
    d = ImageDraw.Draw(img)
    _story_kicker(d, "NOVETATS", 150)
    f_sub = fonts.sans_regular(36)
    sub = "Estrenes d'aquesta setmana"
    d.text(
        ((STORY_W - d.textlength(sub, font=f_sub)) // 2, 230),
        sub,
        font=f_sub,
        fill=colors.COLOR_TEXT_MUTED,
    )

    cover = 240
    row_x = 80
    text_x = row_x + cover + 44
    text_w = STORY_W - text_x - 60
    f_title = fonts.sans_bold(50)
    f_artist = fonts.sans_regular(40)
    top0 = 380
    row_h = cover + 80
    for idx, it in enumerate(items[:3]):
        y = top0 + idx * row_h
        cov = _story_cover(
            it.get("album_deezer_id"),
            it.get("cover_url"),
            cover,
            fallback_letter=(it.get("nom") or "?")[:1],
        )
        img.paste(_rounded(cov, 20), (row_x, y), _rounded(cov, 20))
        title_lines = _wrap_two_lines(d, it.get("nom") or "—", f_title, text_w)[:2]
        ty = y + 40
        for line in title_lines:
            d.text((text_x, ty), line, font=f_title, fill=colors.COLOR_WHITE)
            ty += 58
        artist = _truncate(d, it.get("artista_nom") or "—", f_artist, text_w)
        d.text((text_x, ty + 6), artist, font=f_artist, fill=GREEN_PPCC)

    _story_footer_caption(d, "topquaranta.cat")
    return img


def _story_outro_ppcc() -> Image.Image:
    """Slide 7 — yellow-accent outro: ink text on a yellow field, the
    mono brand logo, and an informative (non-clickable) URL line. No
    slate `COLOR_CARD` card (that primitive stays in use by the
    territorial `_story_cta`)."""
    img = Image.new("RGB", (STORY_W, STORY_H), colors.COLOR_YELLOW)
    d = ImageDraw.Draw(img)

    # Mono ink logo, centred upper third (the tri-colour logo's yellow
    # marks would vanish on the yellow field).
    logo_w = 560
    logo = svg_assets.logo_image_mono(logo_w, colors.COLOR_BG)
    if logo is not None:
        img.paste(logo, ((STORY_W - logo.size[0]) // 2, 620), logo)

    f1 = fonts.sans_bold(64)
    line1 = "Top complet a"
    d.text(
        ((STORY_W - d.textlength(line1, font=f1)) // 2, 940),
        line1,
        font=f1,
        fill=colors.COLOR_BG,
    )
    f2 = fonts.sans_bold(88)
    line2 = "topquaranta.cat"
    d.text(
        ((STORY_W - d.textlength(line2, font=f2)) // 2, 1030),
        line2,
        font=f2,
        fill=colors.COLOR_BG,
    )
    f3 = fonts.sans_regular(34)
    line3 = "El rànquing setmanal de música en català"
    d.text(
        ((STORY_W - d.textlength(line3, font=f3)) // 2, 1180),
        line3,
        font=f3,
        fill=colors.COLOR_BG,
    )
    return img


def render_stories_ppcc(
    setmana,
    entries: list[dict],
    *,
    novetats_items: list[dict] | None = None,
    hero_headline: str | None = None,
) -> list[Path]:
    """Render the 7-slide editorial PPCC story set (Step 3b).

    Replaces the legacy intro + N-cançó + CTA sequence for PPCC. The
    novetats slide is skipped when no recent releases are available, so
    the set is 6 or 7 slides. Territorial stories keep
    `render_stories_top`."""
    out: list[Path] = []
    novetats_items = novetats_items or []

    def _emit(img: Image.Image):
        p = _path("top_ppcc", "PPCC", setmana, len(out), story=True)
        img.save(p, "JPEG", quality=90)
        out.append(p)

    _emit(_story_intro("PPCC", setmana, label_top="TOP 40"))
    _emit(_story_top_mosaic(setmana, entries[10:40]))
    _emit(_story_top_grid(setmana, entries[3:10]))
    _emit(_story_podi(entries[1:3]))
    _emit(_story_hero(entries[0] if entries else {}, hero_headline))
    if novetats_items:
        _emit(_story_novetats(setmana, novetats_items[:3]))
    _emit(_story_outro_ppcc())
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
