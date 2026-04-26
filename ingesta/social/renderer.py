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
from PIL import Image, ImageDraw, ImageFilter

from . import colors, fonts
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


def _logo_block(draw: ImageDraw.ImageDraw, x: int, y: int, *, size: int = 36) -> int:
    """Renders 'Top' (yellow) + 'Quaranta' (white). Returns the x of
    the right edge so callers can lay things out next to it."""
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


def _feed_cover_with_overlay(url: str | None) -> Image.Image:
    """4:5 background using the artist cover, blurred + dark overlay."""
    if url:
        img = fetch_cover(url)
        if img is not None:
            img = img.resize((FEED_W, FEED_W), Image.LANCZOS)
            img = img.filter(ImageFilter.GaussianBlur(8))
            # Crop centre to fit 1350 height by stretching vertically
            img = img.resize((FEED_W, FEED_H), Image.LANCZOS)
            overlay = Image.new("RGB", img.size, colors.COLOR_BG)
            return Image.blend(img, overlay, 0.6)
    # Fallback: solid ink
    return _feed_canvas()


def _feed_portada(territori: str, setmana, hero_cover_url: str | None) -> Image.Image:
    """Cover slide for the feed carousel."""
    if territori and territori != "PPCC" and hero_cover_url:
        img = _feed_cover_with_overlay(hero_cover_url)
    else:
        img = _feed_canvas()
    d = ImageDraw.Draw(img)

    # Logo top-left
    _logo_block(d, 60, 60, size=44)

    # Territori pill top-right (only for non-PPCC)
    if territori and territori != "PPCC":
        from .captions import TERRITORI_NOM

        text = TERRITORI_NOM.get(territori, territori)
        f = fonts.sans_bold(28)
        tw = d.textlength(text, font=f)
        pad_x, pad_y = 22, 12
        x1, y1 = FEED_W - 60 - tw - pad_x * 2, 60
        d.rounded_rectangle(
            (x1, y1, x1 + tw + pad_x * 2, y1 + 28 + pad_y * 2),
            radius=18,
            fill=colors.COLOR_CARD,
        )
        d.text((x1 + pad_x, y1 + pad_y - 4), text, font=f, fill=colors.COLOR_WHITE)

    # Centred TOP / TOP 40 number
    if territori == "PPCC":
        big = "TOP 40"
        f = fonts.display_bold(180)
        tw = d.textlength(big, font=f)
        d.text(
            ((FEED_W - tw) // 2, FEED_H // 2 - 120),
            big,
            font=f,
            fill=colors.COLOR_YELLOW,
        )
        sub = "Global"
        f2 = fonts.display_regular(60)
        tw2 = d.textlength(sub, font=f2)
        d.text(
            ((FEED_W - tw2) // 2, FEED_H // 2 + 60),
            sub,
            font=f2,
            fill=colors.COLOR_WHITE,
        )
    else:
        from .captions import TERRITORI_NOM

        nom = TERRITORI_NOM.get(territori, territori)
        f = fonts.display_bold(110)
        tw = d.textlength(nom, font=f)
        if tw > FEED_W - 120:
            f = fonts.display_bold(80)
            tw = d.textlength(nom, font=f)
        d.text(((FEED_W - tw) // 2, FEED_H - 360), nom, font=f, fill=colors.COLOR_WHITE)

    # Setmana pill bottom
    from .captions import _setmana_label

    label_text = f"Setmana del {_setmana_label(setmana)}"
    f3 = fonts.sans_bold(28)
    tw3 = d.textlength(label_text, font=f3)
    pad_x, pad_y = 28, 14
    x1 = (FEED_W - tw3 - pad_x * 2) // 2
    y1 = FEED_H - 220
    d.rounded_rectangle(
        (x1, y1, x1 + tw3 + pad_x * 2, y1 + 28 + pad_y * 2),
        radius=22,
        fill=colors.COLOR_WHITE,
    )
    d.text((x1 + pad_x, y1 + pad_y - 4), label_text, font=f3, fill=colors.COLOR_BG)

    _footer(d, FEED_W, FEED_H)
    return img


def _feed_list_slide(
    territori: str, entries: list[dict], start_pos: int, page: int, total_pages: int
) -> Image.Image:
    """One feed slide listing up to 10 entries from the top."""
    img = _feed_canvas()
    d = ImageDraw.Draw(img)

    # Header — logo + territori + page indicator
    _logo_block(d, 60, 50, size=32)
    from .captions import TERRITORI_NOM

    nom = TERRITORI_NOM.get(territori, territori)
    f_h = fonts.sans_bold(22)
    nom_text = f"Top {nom}"
    nom_tw = d.textlength(nom_text, font=f_h)
    d.text((FEED_W - 60 - nom_tw, 56), nom_text, font=f_h, fill=colors.COLOR_TEXT_MUTED)

    # Layout
    row_h = 100
    list_top = 150
    n = len(entries)
    f_pos = fonts.display_bold(38)
    f_song = fonts.display_bold(28)
    f_artist = fonts.sans_regular(22)
    pos_w = 70

    for i, e in enumerate(entries[:10]):
        y = list_top + i * row_h
        pos = e["posicio"]

        # Position number in a yellow square
        d.rounded_rectangle(
            (60, y, 60 + pos_w, y + pos_w), radius=12, fill=colors.COLOR_YELLOW
        )
        pos_text = str(pos)
        ptw = d.textlength(pos_text, font=f_pos)
        d.text(
            (60 + (pos_w - ptw) // 2, y + 10),
            pos_text,
            font=f_pos,
            fill=colors.COLOR_BG,
        )

        # Trend indicator
        _trend_glyph(d, 145, y + 22, pos, e.get("posicio_anterior"))

        # Cover thumbnail right side
        cover = _cover(
            e.get("cover_url"), 80, fallback_letter=e.get("canco_nom", "?")[:1]
        )
        cover_r = _rounded(cover, 12)
        img.paste(cover_r, (FEED_W - 60 - 80, y), cover_r)

        # Song + artist text block
        text_x = 195
        text_w = (FEED_W - 60 - 80 - 20) - text_x
        song = _truncate(d, e["canco_nom"], f_song, text_w)
        artist = _truncate(d, e["artista_nom"], f_artist, text_w)
        d.text((text_x, y + 8), song, font=f_song, fill=colors.COLOR_WHITE)
        d.text((text_x, y + 50), artist, font=f_artist, fill=colors.COLOR_TEXT_MUTED)

    # Page indicator
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
    img = _feed_canvas()
    d = ImageDraw.Draw(img)
    _logo_block(d, 60, 60, size=44)
    title = "Nous àlbums" if tipus == "nous_albums" else "Nous singles"
    f = fonts.display_bold(120)
    tw = d.textlength(title, font=f)
    if tw > FEED_W - 120:
        f = fonts.display_bold(90)
        tw = d.textlength(title, font=f)
    d.text(
        ((FEED_W - tw) // 2, FEED_H // 2 - 80), title, font=f, fill=colors.COLOR_YELLOW
    )

    from .captions import _setmana_label

    sub = f"Setmana del {_setmana_label(setmana)}"
    f2 = fonts.sans_bold(36)
    tw2 = d.textlength(sub, font=f2)
    d.text(
        ((FEED_W - tw2) // 2, FEED_H // 2 + 80), sub, font=f2, fill=colors.COLOR_WHITE
    )
    _footer(d, FEED_W, FEED_H)
    return img


def _feed_album_slide(item: dict) -> Image.Image:
    """One album per slide — the legacy treatment."""
    img = _feed_canvas()
    d = ImageDraw.Draw(img)
    _logo_block(d, 60, 50, size=32)

    # Big cover centred
    cover = _cover(item.get("cover_url"), 800, fallback_letter=item.get("nom", "?")[:1])
    cover_r = _rounded(cover, 24)
    img.paste(cover_r, ((FEED_W - 800) // 2, 160), cover_r)

    # Title + artist underneath
    f_t = fonts.display_bold(54)
    f_a = fonts.sans_regular(36)
    title = _truncate(d, item["nom"], f_t, FEED_W - 120)
    artist = _truncate(d, item["artista_nom"], f_a, FEED_W - 120)
    d.text(
        ((FEED_W - d.textlength(title, font=f_t)) // 2, 1010),
        title,
        font=f_t,
        fill=colors.COLOR_WHITE,
    )
    d.text(
        ((FEED_W - d.textlength(artist, font=f_a)) // 2, 1080),
        artist,
        font=f_a,
        fill=colors.COLOR_TEXT_MUTED,
    )

    _footer(d, FEED_W, FEED_H)
    return img


def _feed_singles_slide(items: list[dict], page: int, total_pages: int) -> Image.Image:
    """Up to 10 singles in a list — same shape as the top list slide
    but without position numbers (singles aren't ranked here)."""
    img = _feed_canvas()
    d = ImageDraw.Draw(img)
    _logo_block(d, 60, 50, size=32)

    f_h = fonts.sans_bold(22)
    h = "Nous singles"
    htw = d.textlength(h, font=f_h)
    d.text((FEED_W - 60 - htw, 56), h, font=f_h, fill=colors.COLOR_TEXT_MUTED)

    row_h = 100
    list_top = 150
    f_song = fonts.display_bold(28)
    f_artist = fonts.sans_regular(22)

    for i, e in enumerate(items[:10]):
        y = list_top + i * row_h
        cover = _cover(e.get("cover_url"), 80, fallback_letter=e.get("nom", "?")[:1])
        cover_r = _rounded(cover, 12)
        img.paste(cover_r, (60, y), cover_r)

        text_x = 175
        text_w = (FEED_W - 60) - text_x
        song = _truncate(d, e["nom"], f_song, text_w)
        artist = _truncate(d, e["artista_nom"], f_artist, text_w)
        d.text((text_x, y + 8), song, font=f_song, fill=colors.COLOR_WHITE)
        d.text((text_x, y + 50), artist, font=f_artist, fill=colors.COLOR_TEXT_MUTED)

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
        # singles: list of 10 per slide
        pages = max(1, (len(items) + 9) // 10)
        for page in range(1, pages + 1):
            chunk = items[(page - 1) * 10 : page * 10]
            if not chunk:
                break
            p = _path(tipus, "", setmana, page)
            _feed_singles_slide(chunk, page, pages).save(p, "PNG")
            out.append(p)
    return out[:10]


# ── STORIES ──────────────────────────────────────────────────────────


def _story_canvas() -> Image.Image:
    return Image.new("RGB", (STORY_W, STORY_H), colors.COLOR_BG)


def _story_intro(territori: str, setmana, *, label_top: str) -> Image.Image:
    img = _story_canvas()
    d = ImageDraw.Draw(img)

    card_w, card_h = 880, 700
    cx, cy = (STORY_W - card_w) // 2, (STORY_H - card_h) // 2
    d.rounded_rectangle(
        (cx, cy, cx + card_w, cy + card_h), radius=32, fill=colors.COLOR_CARD
    )

    # "TOP 40" / "TOP 5"
    f_big = fonts.display_bold(120)
    tw = d.textlength(label_top, font=f_big)
    d.text(
        (cx + (card_w - tw) // 2, cy + 90),
        label_top,
        font=f_big,
        fill=colors.COLOR_YELLOW if territori == "PPCC" else colors.COLOR_YELLOW_DEEP,
    )

    # Territori name
    from .captions import TERRITORI_NOM, _setmana_label

    nom = TERRITORI_NOM.get(territori, territori)
    f_nom = fonts.display_bold(64)
    nom_tw = d.textlength(nom, font=f_nom)
    d.text(
        (cx + (card_w - nom_tw) // 2, cy + 280),
        nom,
        font=f_nom,
        fill=colors.COLOR_WHITE,
    )

    # Setmana
    label = f"Setmana del {_setmana_label(setmana)}"
    f_sub = fonts.sans_regular(36)
    sub_tw = d.textlength(label, font=f_sub)
    d.text(
        (cx + (card_w - sub_tw) // 2, cy + 450),
        label,
        font=f_sub,
        fill=colors.COLOR_TEXT_MUTED,
    )

    return img


def _story_canco(territori: str, e: dict) -> Image.Image:
    img = _story_canvas()
    d = ImageDraw.Draw(img)

    # Territori header
    from .captions import TERRITORI_NOM

    nom = TERRITORI_NOM.get(territori, territori)
    f_h = fonts.sans_bold(36)
    htw = d.textlength(nom, font=f_h)
    d.text(((STORY_W - htw) // 2, 100), nom, font=f_h, fill=colors.COLOR_WHITE)

    # Card
    card_w, card_h = 920, 1300
    cx, cy = (STORY_W - card_w) // 2, 220
    d.rounded_rectangle(
        (cx, cy, cx + card_w, cy + card_h), radius=32, fill=colors.COLOR_CARD
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

    # Cançó name (yellow, up to 2 lines)
    f_song = fonts.display_bold(44)
    lines = _wrap_two_lines(d, e["canco_nom"], f_song, card_w - 80)
    for i, line in enumerate(lines[:2]):
        line_tw = d.textlength(line, font=f_song)
        d.text(
            (cx + (card_w - line_tw) // 2, cy + 940 + i * 60),
            line,
            font=f_song,
            fill=colors.COLOR_YELLOW,
        )

    # Artista
    f_a = fonts.sans_regular(34)
    artist = _truncate(d, e["artista_nom"], f_a, card_w - 80)
    a_tw = d.textlength(artist, font=f_a)
    d.text(
        (cx + (card_w - a_tw) // 2, cy + 1180),
        artist,
        font=f_a,
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

    f1 = fonts.display_bold(56)
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
