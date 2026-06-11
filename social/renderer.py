"""PIL-based image generator for the Instagram payloads.

Render entry points:
  - `render_feed_top(tipus, territori, setmana, entries)` → list[Path]
  - `render_feed_novetats(tipus, setmana, items)`         → list[Path]
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

from . import colors, fonts, render_core, svg_assets
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


def _feed_canvas() -> Image.Image:
    return Image.new("RGB", (FEED_W, FEED_H), colors.COLOR_BG)


def _top_variant(territori: str) -> str:
    """Design variant for a top territori: 'ppcc' for the global top, else the
    DB territory code (its palette + name)."""
    return "ppcc" if (territori or "").upper() == "PPCC" else territori


def render_feed_top(
    tipus: str, territori: str, setmana, entries: list[dict]
) -> list[Path]:
    """Instagram TOP carousel (editorial redesign, 2026-06): cover + up to 4
    list slides of 10, COUNTING DOWN to #1 (40→31, 30→21, 20→11, 10→1) so the
    climax lands on the last slide. `entries` in chart order (posicio 1..N)."""
    from . import top_redesign as TR

    variant = _top_variant(territori)
    out: list[Path] = []
    p = _path(tipus, territori, setmana, 0)
    TR.build_top_cover(setmana, variant).save(p, "JPEG", quality=90)
    out.append(p)

    blocks = [(30, 40), (20, 30), (10, 20), (0, 10)]
    present = [b for b in blocks if entries[b[0] : b[1]]]
    total = len(present)
    for i, (lo, hi) in enumerate(present, start=1):
        rows = list(reversed(entries[lo:hi]))  # countdown within the slide
        slide = TR.build_top_list(
            rows, current=i, total=total, setmana=setmana, variant=variant
        )
        p = _path(tipus, territori, setmana, i)
        slide.save(p, "JPEG", quality=90)
        out.append(p)
    return out[:10]


def render_top_poster(tipus: str, territori: str, setmana, entries: list[dict]) -> Path:
    """The single-image TOP cartell (Telegram/Mastodon/Bluesky)."""
    from . import top_redesign as TR

    p = _path(tipus, territori, setmana, 0)
    TR.build_poster(entries, setmana, _top_variant(territori)).save(
        p, "JPEG", quality=90
    )
    return p


def render_albums_mosaic(setmana, items: list[dict]) -> Path:
    """The single-image new-albums mosaic (Telegram/Mastodon/Bluesky)."""
    from . import top_redesign as TR

    p = _path("nous_albums", "", setmana, 0)
    TR.build_albums_mosaic(items, setmana).save(p, "JPEG", quality=90)
    return p


# ── FEED · novetats (album/single carousel) ──────────────────────────


def render_feed_novetats(tipus: str, setmana, items: list[dict]) -> list[Path]:
    """The three novetats slides (cover, single-album, singles grid) via the
    editorial redesign in `social/feed_redesign.py` — the ONLY path since
    2026-06-11 (the gated legacy layout + `feed_redisseny_actiu` flag were
    removed). Selection, singles bin-packing, idempotency and the Deezer cover
    sourcing/fallback contract stay here; the editorial layout lives there.

    `tipus` is `nous_albums` (1 per slide) or `nous_singles` (≤10 per slide)."""
    from . import feed_redesign

    out: list[Path] = []
    p = _path(tipus, "", setmana, 0)
    feed_redesign.build_cover(tipus, setmana).save(p, "JPEG", quality=90)
    out.append(p)

    if tipus == "nous_albums":
        for i, item in enumerate(items[:9], start=1):
            p = _path(tipus, "", setmana, i)
            feed_redesign.build_album(item).save(p, "JPEG", quality=90)
            out.append(p)
    else:
        # Singles: dynamic bin-packing so we never end with a slide holding
        # 1-2 orphan rows. Up to 10 per slide is the hard cap. Within it we
        # split as evenly as possible (≤10→1, 11-20→2, 21-30→3, …).
        n = len(items)
        n_slides = max(1, (n + 9) // 10)
        per_slide = -(-n // n_slides)  # ceil-div
        pages = n_slides
        offset = 0
        for page in range(1, pages + 1):
            chunk_size = per_slide if (offset + per_slide) <= n else n - offset
            chunk = items[offset : offset + chunk_size]
            if not chunk:
                break
            p = _path(tipus, "", setmana, page)
            feed_redesign.build_singles(chunk, page, pages, setmana=setmana).save(
                p, "JPEG", quality=90
            )
            out.append(p)
            offset += chunk_size
    return out[:10]


# ── STORIES · PPCC editorial set (Step 3b redesign) ──────────────────
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
# Intro locative subtitle: non-PPCC names wider than this (at 100 pt) step
# down to 84 pt. 680 catches VAL (703) and BAL (816), not CAT (540).
_SUBTITLE_STEPDOWN_W = 680

# Story-intro watermark icon: which `territory_icon` art to draw per
# territori. CAT has no silhouette asset of its own (territory-cat.svg is
# a cross, shared with the web's TerritoriBadge), so the CAT story borrows
# the existing senyera art (the PPCC/global icon). This is a stories-only
# remap: it does NOT modify the vendor asset and does NOT touch the web
# (TerritoriBadge keeps the cross). VAL/BAL fall through to their own art.
_STORY_ICON_CODI = {"CAT": "PPCC"}


# ── low-level text + background helpers ──────────────────────────────


# Story text/star primitives live once in `render_core`; these adapters keep the
# `_story_*` call sites unchanged. Story semantics: ink-top anchor, glyph-by-glyph,
# direct draw (no compositing).
_tracked_width = render_core.tracked_width


def _draw_tracked(d, x, y_top, text, font, fill, *, tracking=0.0, center_w=None):
    """Single line with letter-spacing; ink-top anchored at `y_top`. When
    `center_w` is given, centred within `[0, center_w]`. Returns advance width."""
    if center_w is not None:
        return render_core.draw_text(
            d,
            center_w / 2,
            y_top,
            text,
            font,
            fill,
            align="center",
            tracking=tracking,
            ink_top=True,
            glyphwise=True,
            composite=False,
        )
    return render_core.draw_text(
        d,
        x,
        y_top,
        text,
        font,
        fill,
        tracking=tracking,
        ink_top=True,
        glyphwise=True,
        composite=False,
    )


def _draw_star(d, cx, cy, r_out, fill):
    """Five-point star polygon (inner = 0.42·outer), drawn directly."""
    render_core.star(d, cx, cy, r_out, fill, inner_ratio=0.42, composite=False)


def _radial_bg(
    inner_hex: str,
    outer_hex: str,
    center: tuple[float, float],
    radii: tuple[float, float],
    stop_outer: float,
) -> Image.Image:
    """Full-canvas RGB elliptical radial gradient (story semantics: divide the
    distance by `stop_outer`, float32). Delegates to `render_core.radial_bg`."""
    return render_core.radial_bg(
        (STORY_W, STORY_H),
        inner_hex,
        outer_hex,
        center,
        radii,
        stop=stop_outer,
        dtype="float32",
        mode="RGB",
    )


def _bg_ink(center=(0.5, 0.0), radii=(1.2, 0.6), stop=0.6) -> Image.Image:
    """Ink slides (2/3/4/6): #141210 centre → #0A0A0A."""
    return _radial_bg(colors.COLOR_INK_CENTRE, colors.COLOR_BG, center, radii, stop)


def _logo_white(width: int) -> Image.Image | None:
    return svg_assets.logo_image_mono(width, colors.COLOR_WHITE)


def _logo_ink(width: int) -> Image.Image | None:
    return svg_assets.logo_image_mono(width, colors.COLOR_BG)


def _header_pill(
    img: Image.Image, right_x: int, cy: int, label: str, fill: str, ink: str
):
    """Draw a header pill ending at `right_x`, centred on `cy`, filled with
    `fill` and `label` (Anton 26, ls 3) in `ink`. Returns the pill width so
    callers can stack pills horizontally. Distinct from the legacy `_pill`
    used by the old territorial CTA path."""
    d = ImageDraw.Draw(img)
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
    d.rectangle((x0, y0, x0 + pill_w, y0 + pill_h), fill=fill)
    _draw_tracked(d, x0 + pad_x, y0 + pad_y, label, f, ink, tracking=tracking)
    return pill_w


def _setmana_pill(img: Image.Image, right_x: int, cy: int, setmana) -> int:
    """Yellow SETMANA pill (ink text), right edge pinned at `right_x`."""
    from .captions import _setmana_label

    label = _setmana_label(setmana).upper()
    return _header_pill(img, right_x, cy, label, colors.COLOR_YELLOW, colors.COLOR_BG)


def _territori_pill(img: Image.Image, right_x: int, cy: int, territori: str) -> int:
    """Accent-tinted territory pill (short name, e.g. CATALUNYA) ending at
    `right_x`. Returns its width. PPCC callers skip this (no pill)."""
    from .narrative.utils import TERRITORI_SHORT

    pal = colors.story_palette(territori)
    label = (TERRITORI_SHORT.get(territori) or territori).upper()
    badge = pal["badge"]
    return _header_pill(img, right_x, cy, label, badge, colors.best_text_on(badge))


def _header_row(
    img: Image.Image,
    setmana,
    *,
    territori: str = "PPCC",
    logo_w: int = 217,
    logo_h: int = 44,
):
    """Slides 2/3/4/6 header: white logo left, SETMANA pill right, row
    height ≈53 vertically centred at the top padding. Territorial slides
    add an accent territory pill left of the SETMANA pill; PPCC has none
    (byte-identical)."""
    left = _PAD_STD[3]
    right = STORY_W - _PAD_STD[1]
    top = _PAD_STD[0]
    row_h = 53
    cy = top + row_h // 2
    logo = _logo_white(logo_w)
    if logo is not None:
        img.paste(logo, (left, cy - logo.size[1] // 2), logo)
    setmana_w = _setmana_pill(img, right, cy, setmana)
    if territori != "PPCC":
        _territori_pill(img, right - setmana_w - 16, cy, territori)
    return top + row_h


def _section_header(
    img: Image.Image,
    title: str,
    y_title_top: int,
    *,
    kicker: str | None = None,
    title_color: str = colors.COLOR_WHITE,
    rule_color: str = colors.COLOR_YELLOW,
    kicker_color: str = colors.COLOR_GREEN_LIGHT,
) -> int:
    """Optional kicker + Anton-96 title + accent rule. Centred. Returns
    the y just below the rule. `kicker_color` defaults to the PPCC green
    light; territorial builders pass their `story_palette` light tone."""
    d = ImageDraw.Draw(img)
    y = y_title_top
    if kicker:
        fk = fonts.sans_bold(25)
        _draw_tracked(d, 0, y, kicker, fk, kicker_color, tracking=7, center_w=STORY_W)
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


def _footer_url(img: Image.Image, *, light: str = colors.COLOR_GREEN_LIGHT) -> None:
    """`topquaranta.cat` — Anton 30, ls 4, centred, near the bottom edge
    (slides 2-6). `light` defaults to the PPCC green light; territorial
    builders pass their `story_palette` light tone."""
    d = ImageDraw.Draw(img)
    f = fonts.anton(30)
    _draw_tracked(
        d,
        0,
        STORY_H - 92,
        "topquaranta.cat",
        f,
        light,
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


def _story_intro_ppcc(setmana, *, territori: str = "PPCC") -> Image.Image:
    """Slide 1 — accent intro. Logo, "presenta", the big EL TOP / 40 /
    D'AQUESTA SETMANA stack, and the star-separated SETMANA pill row.
    The radial field uses the territory accent (PPCC → green, identical
    to before)."""
    from .captions import _setmana_label
    from .narrative.utils import TERRITORI_DE

    pal = colors.story_palette(territori)
    img = _radial_bg(pal["accent"], pal["deep"], (0.5, 0.0), (1.3, 0.8), 1.0)

    # Territorial intro: a large faint monochrome territory-icon watermark
    # in the lower-half empty band, behind the text. Aspect ratio is
    # preserved (territory_icon scales by width; height follows the
    # viewBox, so VAL/BAL stay wide, CAT square). White at low alpha
    # harmonises on any accent and never rivals the yellow "40". PPCC has
    # no icon (byte-identical). Copy before alpha-scaling: territory_icon
    # is lru_cached and the cached image must not be mutated.
    if territori != "PPCC":
        icon_codi = _STORY_ICON_CODI.get(territori, territori)
        icon = svg_assets.territory_icon(icon_codi, 540, colors.COLOR_WHITE)
        if icon is not None:
            icon = icon.copy()
            icon.putalpha(icon.getchannel("A").point(lambda v: int(v * 0.16)))
            iy = 1400 - icon.size[1] // 2
            img.paste(icon, ((STORY_W - icon.size[0]) // 2, iy), icon)

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
    # PPCC keeps the brand "D'AQUESTA SETMANA" at 100 pt (byte-identical).
    # Territorial stories localise the chart ("DE CATALUNYA" etc., via
    # TERRITORI_DE, uppercased). Long locative names ("DE LES ILLES
    # BALEARS" 816 px, "DEL PAÍS VALENCIÀ" 703 px at 100 pt) crowd the
    # margins under the "40", so non-PPCC subtitles step down one notch
    # to 84 pt when they exceed `_SUBTITLE_STEPDOWN_W`. The gate on
    # territori keeps PPCC untouched regardless of its width (780 px).
    f_setm = fonts.anton(100)
    if territori == "PPCC":
        subtitle = "D'AQUESTA SETMANA"
    else:
        subtitle = (TERRITORI_DE.get(territori) or "d'aquesta setmana").upper()
        if _tracked_width(d, subtitle, f_setm, 1) > _SUBTITLE_STEPDOWN_W:
            f_setm = fonts.anton(84)
    _draw_tracked(
        d,
        0,
        980,
        subtitle,
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
    line_col = colors.mix(pal["accent"], colors.COLOR_WHITE, 0.35)
    cxc = STORY_W / 2
    star_r, gap, sep_total = 16, 40, 920
    left0 = (STORY_W - sep_total) / 2
    d.rectangle((left0, sep_y, cxc - star_r - gap, sep_y + 2), fill=line_col)
    d.rectangle(
        (cxc + star_r + gap, sep_y, left0 + sep_total, sep_y + 2), fill=line_col
    )
    _draw_star(d, cxc, sep_y + 1, star_r, colors.COLOR_WHITE)
    return img


def _story_top_mosaic(
    setmana, entries: list[dict], *, territori: str = "PPCC"
) -> Image.Image:
    """Slide 2 — positions 40→11 as a 5×6 cover mosaic with yellow Anton
    number badges + Bricolage titles + Roboto artist subtitles."""
    pal = colors.story_palette(territori)
    img = _bg_ink()
    _header_row(img, setmana, territori=territori)
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
    _footer_url(img, light=pal["light"])
    return img


def _story_top_grid(
    setmana, entries: list[dict], *, territori: str = "PPCC"
) -> Image.Image:
    """Slide 3 — positions 10→4: 2-column cover grid (#10/#9, #8/#7,
    #6/#5) then #4 centred below.

    Row heights are dynamic: each grid row reserves space for the taller
    of its two titles (1 or 2 lines, ellipsised at 2) so a wrapped title
    never crowds the cover of the row below. The centred #4 is clamped so
    it can't slide under the footer when several rows run tall."""
    pal = colors.story_palette(territori)
    img = _bg_ink()
    _header_row(img, setmana, territori=territori)
    body_top = _section_header(img, "ENS ACOSTEM AL CIM", 200)

    d = ImageDraw.Draw(img)
    cover = 210
    col_gap, row_gap = 48, 40
    pair_w = 2 * cover + col_gap
    block_left = (STORY_W - pair_w) // 2
    col_x = [block_left, block_left + cover + col_gap]
    grid_top = body_top + 40
    title_lh, gap_above_title, gap_above_artist, artist_h = 34, 14, 4, 30
    f_badge = fonts.anton(46)
    f_title = fonts.bricolage_xbold(32)
    f_artist = fonts.sans_regular(25)
    subtle = colors.mix(colors.COLOR_BG, colors.COLOR_WHITE, 0.62)

    def _text_h(n_lines: int) -> int:
        """Height of the text block under a cover for `n_lines` title."""
        return gap_above_title + n_lines * title_lh + gap_above_artist + artist_h

    # Descending 10→4: grid holds #10/#9, #8/#7, #6/#5; #4 centred below.
    items = list(reversed(entries[:7]))
    # Pre-wrap every title (≤2 lines, ellipsised) so rows can be sized.
    wrapped = [
        _wrap_tracked(d, e.get("canco_nom") or "—", f_title, cover + 30, -0.32, 2)
        for e in items
    ]

    def _cell(e, lines, x, y, pos):
        _paste_cover(img, e, x, y, cover)
        _number_badge(img, x, y, str(pos), font=f_badge, pad_x=21, pad_y=9)
        ty = y + cover + gap_above_title
        for line in lines:
            _draw_tracked(d, x, ty, line, f_title, colors.COLOR_WHITE, tracking=-0.32)
            ty += title_lh
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        artist = _truncate(d, ", ".join(names), f_artist, cover + 30)
        _draw_tracked(d, x, ty + gap_above_artist, artist, f_artist, subtle)

    n = len(items)
    y = grid_top
    for r in range(3):
        i0, i1 = r * 2, r * 2 + 1
        if i0 >= n or i0 >= 6:
            break
        lines1 = wrapped[i1] if (i1 < n and i1 < 6) else None
        row_lines = max(len(wrapped[i0]), len(lines1) if lines1 else 1)
        _cell(
            items[i0], wrapped[i0], col_x[0], y, items[i0].get("posicio") or (10 - i0)
        )
        if lines1:
            _cell(items[i1], lines1, col_x[1], y, items[i1].get("posicio") or (10 - i1))
        y += cover + _text_h(row_lines) + row_gap
    # #4 centred below, clamped so its block never reaches the footer.
    if n >= 7:
        e = items[6]
        needed = cover + _text_h(len(wrapped[6]))
        max_y = STORY_H - 92 - 24 - needed  # 92 footer band + 24 margin
        _cell(
            e, wrapped[6], (STORY_W - cover) // 2, min(y, max_y), e.get("posicio") or 4
        )
    _footer_url(img, light=pal["light"])
    return img


def _story_podi(
    entries: list[dict], setmana, *, territori: str = "PPCC"
) -> Image.Image:
    """Slide 4 — #3 (top) and #2 (below): centred big covers with a big
    Anton number badge, Bricolage title and Roboto artist."""
    pal = colors.story_palette(territori)
    img = _radial_bg(
        colors.COLOR_INK_CENTRE, colors.COLOR_BG, (0.5, 0.04), (1.1, 0.55), 0.58
    )
    _header_row(img, setmana, territori=territori)
    _section_header(
        img, "EL PODI", 200, kicker="JA GAIREBÉ HI SOM", kicker_color=pal["light"]
    )

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
    _footer_url(img, light=pal["light"])
    return img


def _story_hero(
    entry: dict, headline: str | None, *, territori: str = "PPCC"
) -> Image.Image:
    """Slide 5 — the #1 climax. Inverted hierarchy: the editorial
    scenario is a subordinate yellow kicker; the SONG TITLE in Playfair
    Display 800 is the primary element. The yellow climax + ink field are
    brand-locked; only the territory pill (non-PPCC) and footer tint are
    territory-aware."""
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
    # Territory pill top-right (territorial only), aligned to the logo row.
    if territori != "PPCC":
        _territori_pill(img, STORY_W - _PAD_STD[1], _PAD_STD[0] + 22, territori)

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

    _footer_url(img, light=colors.story_palette(territori)["light"])
    return img


def _story_novetats(
    setmana, items: list[dict], *, territori: str = "PPCC"
) -> Image.Image:
    """Slide 6 — 2-3 recent releases stacked: centred cover + Bricolage
    title + Roboto artist, no number badge."""
    pal = colors.story_palette(territori)
    img = _bg_ink()
    _header_row(img, setmana)
    _section_header(
        img,
        "NOVETATS",
        200,
        kicker="FORA DEL TOP · ESTRENES",
        title_color=colors.COLOR_YELLOW,
        rule_color=pal["light"],
        kicker_color=pal["light"],
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
    _footer_url(img, light=pal["light"])
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
    """Render the 7-slide editorial PPCC story set (Step 3b — structure
    + visual redesign).

    The novetats slide is skipped when no recent releases are available,
    so the set is 6 or 7 slides."""
    out: list[Path] = []
    # Drop any falsy entries so a list of empty dicts can't slip through
    # and produce a blank novetats slide.
    novetats_items = [it for it in (novetats_items or []) if it]

    def _emit(img: Image.Image):
        p = _path("top_ppcc", "PPCC", setmana, len(out), story=True)
        img.save(p, "JPEG", quality=90)
        out.append(p)

    _emit(_story_intro_ppcc(setmana))
    _emit(_story_top_mosaic(setmana, entries[10:40]))
    _emit(_story_top_grid(setmana, entries[3:10]))
    _emit(_story_podi(entries[1:3], setmana))
    _emit(_story_hero(entries[0] if entries else {}, hero_headline))
    # Novetats slide is omitted entirely when there are no recent
    # releases — never generated, never uploaded (the set is then 6).
    if novetats_items:
        _emit(_story_novetats(setmana, novetats_items[:3]))
    _emit(_story_outro_ppcc(setmana))
    return out


def render_stories_territorial(
    territori: str,
    setmana,
    entries: list[dict],
    *,
    novetats_items: list[dict] | None = None,
    hero_headline: str | None = None,
) -> list[Path]:
    """Render the editorial territorial story set (Step 3c).

    Same grammar and inverted-toward-#1 slicing as the PPCC set, but
    recoloured per territory (`story_palette`) and degraded by omission:
    a tier slide is emitted only when its slice is non-empty, so a short
    top (N < 40) never yields a near-blank mosaic/grid/podi. Hero (#1)
    and outro stay brand yellow/ink. PPCC keeps `render_stories_ppcc`."""
    out: list[Path] = []
    novetats_items = [it for it in (novetats_items or []) if it]
    n = len(entries)
    if n < 11:
        # Not an error: graceful degradation. Surfaced so a future
        # volume collapse on a thin territory (BAL) is visible in logs.
        logger.warning(
            "territorial story has N=%d (<11) for %s setmana=%s; "
            "mosaic/grid/podi tiers may be omitted",
            n,
            territori,
            setmana,
        )

    def _emit(img: Image.Image):
        p = _path("top_territorial", territori, setmana, len(out), story=True)
        img.save(p, "JPEG", quality=90)
        out.append(p)

    _emit(_story_intro_ppcc(setmana, territori=territori))
    if n > 10:
        _emit(_story_top_mosaic(setmana, entries[10:40], territori=territori))
    if n > 3:
        _emit(_story_top_grid(setmana, entries[3:10], territori=territori))
    if n > 1:
        _emit(_story_podi(entries[1:3], setmana, territori=territori))
    if entries:
        _emit(_story_hero(entries[0], hero_headline, territori=territori))
    if novetats_items:
        _emit(_story_novetats(setmana, novetats_items[:3], territori=territori))
    _emit(_story_outro_ppcc(setmana))
    return out


def render_singles_single(setmana, items: list[dict]) -> tuple[Path, list[str]]:
    """Single-image new-singles render for one-image channels: the singles GRID
    (first page, ≤10) as one image, plus the titles of any overflow singles so
    the caller can append them to the post text. Design has no >10 single-image
    layout (decision pending) — first page + text, no compression."""
    from . import feed_redesign as F

    p = _path("nous_singles", "", setmana, 0)
    F.build_singles(items[:10], 1, 1, setmana=setmana).save(p, "JPEG", quality=90)
    overflow = [it.get("nom", "") for it in items[10:] if it.get("nom")]
    return p, overflow
