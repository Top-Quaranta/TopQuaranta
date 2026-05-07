"""PIL-based image generator for the Instagram payloads.

Three render entry points:
  - `render_feed_top(tipus, territori, setmana, entries)` → list[Path]
  - `render_feed_novetats(tipus, setmana, items)`         → list[Path]
  - `render_stories_top(territori, setmana, entries)`     → list[Path]

All return PNG paths under `<SOCIAL_CACHE_DIR>/renders/`. Filename
is deterministic: `<tipus>_<territori>_<setmana>_<idx>.png`. Same
inputs → same path → idempotent re-renders.

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
    name = f"{suffix}_{tipus}_{ter}_{setmana.isoformat()}_{idx:02d}.png"
    return _renders_dir() / name


# ── Drawing helpers ───────────────────────────────────────────────────


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    """Single-line truncation with an ellipsis."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…" if text else "…"


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


def _feed_portada(territori: str, setmana, hero_cover_url: str | None) -> Image.Image:
    """Cover slide — legacy layout, modern palette.

    Layout (same for territorial + PPCC):
      • full-bleed cover (scale-to-cover, no black bands)
      • territory pill top-right (icon + name, white on territory colour)
      • brand-logo pill mid-bottom (~75% wide), filled with the
        territory colour; logo recoloured to whichever of white/ink
        contrasts best with that fill
      • small "Setmana N" pill bottom-left
    No URL pill — keeps the cover as visible as the legacy did.
    """
    from .captions import TERRITORI_NOM, _setmana_label

    accent = colors.terr_color(territori)
    is_ppcc = (territori or "") == "PPCC"

    # ── Background ───────────────────────────────────────────────
    # Territorial covers use the album cover of song #1; PPCC/Global
    # covers are solid ink — the brand-tri-colour logo (yellow + red
    # + blue) reads at maximum contrast on `tq-ink`, which is also
    # the SPA's body background. The PPCC accent (green) stays on
    # the rest of the global surfaces (stories, list squares).
    if is_ppcc:
        img = Image.new("RGB", (FEED_W, FEED_H), colors.COLOR_BG)
    else:
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
        artist = _truncate(d, e["artista_nom"], f_artist, text_w)
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

    p = _path(tipus, territori, setmana, 0)
    _feed_portada(territori, setmana, hero_cover).save(p, "PNG")
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
        slide.save(p, "PNG")
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
    _feed_novetats_portada(tipus, setmana).save(p, "PNG")
    out.append(p)

    if tipus == "nous_albums":
        for i, item in enumerate(items[:9], start=1):
            p = _path(tipus, "", setmana, i)
            _feed_album_slide(item).save(p, "PNG")
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
            _feed_singles_slide(chunk, page, pages).save(p, "PNG")
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

    # TOP N
    pos_text = f"TOP {e['posicio']}"
    f_pos = fonts.sans_bold(48)
    pos_tw = d.textlength(pos_text, font=f_pos)
    d.text(
        (cx + (card_w - pos_tw) // 2, cy + 850),
        pos_text,
        font=f_pos,
        fill=colors.COLOR_WHITE,
    )

    # Song title — white on the colour card, bold and large.
    # Bumped 44 → 58 → 68 → 80 in the May-2026 readability pass;
    # line-spacing 90 keeps the two-line layout from kissing.
    # TOP N number above stays at 48 (titles + artists only on stories).
    f_song = fonts.display_bold(80)
    lines = _wrap_two_lines(d, e["canco_nom"], f_song, card_w - 80)
    for i, line in enumerate(lines[:2]):
        line_tw = d.textlength(line, font=f_song)
        d.text(
            (cx + (card_w - line_tw) // 2, cy + 920 + i * 90),
            line,
            font=f_song,
            fill=colors.COLOR_WHITE,
        )

    # Artist — bumped 34 → 44; pushed down a bit so the wider
    # title block doesn't crash into it.
    f_a = fonts.sans_regular(44)
    artist = _truncate(d, e["artista_nom"], f_a, card_w - 80)
    a_tw = d.textlength(artist, font=f_a)
    d.text(
        (cx + (card_w - a_tw) // 2, cy + 1210),
        artist,
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


def render_stories_top(
    tipus: str, territori: str, setmana, entries: list[dict], *, max_cancons: int
) -> list[Path]:
    """Story sequence: intro + N cançó slides + CTA.

    `max_cancons` capped by ConfiguracioGlobal.story_max_cancons_ppcc
    for PPCC; territorial defaults to top 5."""
    out: list[Path] = []
    label = f"TOP {min(max_cancons, len(entries))}"

    p = _path(tipus, territori, setmana, 0, story=True)
    _story_intro(territori, setmana, label_top=label).save(p, "PNG")
    out.append(p)

    for i, e in enumerate(entries[:max_cancons], start=1):
        p = _path(tipus, territori, setmana, i, story=True)
        _story_canco(territori, e).save(p, "PNG")
        out.append(p)

    p = _path(tipus, territori, setmana, len(out), story=True)
    _story_cta().save(p, "PNG")
    out.append(p)
    return out
