"""Dynamic Open Graph image generator (1200×630 PNG).

Each entity type renders its own card. Cards get aggressively cached
on disk under `/var/cache/topquaranta/og/<entity>/<slug>.png` keyed
by `updated_at` — when the entity's `updated_at` advances, the next
render replaces the old PNG.

Reuses the same fonts and palette as the social renderer
(`social/renderer.py`) so brand consistency is automatic.
"""

from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path

from django.http import FileResponse, Http404
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from music.models import Album, Artista, Canco
from social import fonts as social_fonts

logger = logging.getLogger(__name__)

# 1200×630 = the Open Graph standard for high-resolution social
# previews. Twitter, Mastodon, FB, WhatsApp all crop sensibly from
# this aspect.
OG_W = 1200
OG_H = 630

CACHE_DIR = Path("/var/cache/topquaranta/og")

# Palette mirrors mm-design / social/colors.py.
COLOR_INK = (10, 10, 10)
COLOR_YELLOW = (250, 204, 21)
COLOR_WHITE = (255, 255, 255)
COLOR_MUTED = (156, 163, 175)


def _ensure_cache_dir(subdir: str) -> Path:
    p = CACHE_DIR / subdir
    p.mkdir(parents=True, exist_ok=True)
    return p


def _font(family: str, size: int) -> ImageFont.FreeTypeFont:
    """Wrapper around social.fonts to keep the import surface narrow.
    Falls back to PIL's default font if the family file isn't on disk
    (fresh deploy without fonts vendored)."""
    try:
        return social_fonts.font(family, size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    """Greedy word-wrapping. Returns the lines that fit within max_w."""
    words = text.split()
    lines: list[str] = []
    line = ""
    for w in words:
        test = (line + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def _bg_with_cover(cover_url: str | None) -> Image.Image:
    """Build the base 1200×630 image. If we have an album cover URL,
    use a blurred-blown-up version as background; otherwise a flat
    ink rectangle."""
    img = Image.new("RGB", (OG_W, OG_H), COLOR_INK)
    if cover_url:
        try:
            from io import BytesIO

            import requests

            r = requests.get(cover_url, timeout=5)
            if r.ok:
                cover = Image.open(BytesIO(r.content)).convert("RGB")
                # Cover-fit to OG and blur as decorative background.
                bg = cover.resize((OG_W, OG_H), Image.LANCZOS).filter(
                    ImageFilter.GaussianBlur(radius=24)
                )
                # Darken so foreground text stays readable (60% alpha
                # ink overlay).
                overlay = Image.new("RGB", (OG_W, OG_H), COLOR_INK)
                img = Image.blend(bg, overlay, 0.55)
        except Exception:
            logger.exception("og: cover fetch failed for %s", cover_url)
    return img


def _draw_brand(draw: ImageDraw.ImageDraw) -> None:
    """Top-left brand mark — small enough to not steal attention."""
    f = _font("display", 26)
    draw.text((48, 38), "TopQuaranta", fill=COLOR_YELLOW, font=f)


def _draw_footer(draw: ImageDraw.ImageDraw, text: str = "topquaranta.cat") -> None:
    f = _font("sans", 22)
    draw.text((48, OG_H - 48 - 22), text, fill=COLOR_MUTED, font=f)


# ── Per-entity composers ────────────────────────────────────────────


def _compose_homepage() -> Image.Image:
    img = _bg_with_cover(None)
    draw = ImageDraw.Draw(img)
    _draw_brand(draw)

    f_title = _font("display", 96)
    f_sub = _font("sans", 36)
    draw.text((48, 220), "TopQuaranta", fill=COLOR_YELLOW, font=f_title)
    sub_lines = [
        "El rànquing setmanal",
        "de música en català",
    ]
    y = 340
    for ln in sub_lines:
        draw.text((48, y), ln, fill=COLOR_WHITE, font=f_sub)
        y += 50
    _draw_footer(draw)
    return img


def _compose_top(territori_codi: str, territori_nom: str) -> Image.Image:
    img = _bg_with_cover(None)
    draw = ImageDraw.Draw(img)
    _draw_brand(draw)

    f_eyebrow = _font("sans", 28)
    f_big = _font("display", 96)
    draw.text((48, 220), "TOP", fill=COLOR_MUTED, font=f_eyebrow)
    draw.text((48, 256), territori_nom, fill=COLOR_YELLOW, font=f_big)

    f_sub = _font("sans", 28)
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sub = f"Setmana del {monday.strftime('%d/%m/%Y')} · TopQuaranta"
    draw.text((48, 380), sub, fill=COLOR_WHITE, font=f_sub)

    _draw_footer(draw)
    return img


def _compose_artista(a: Artista) -> Image.Image:
    # Try to use the latest album cover as background motif
    latest_album = (
        Album.objects.filter(artista=a, descartat=False, imatge_url__gt="")
        .order_by("-data_llancament")
        .first()
    )
    cover = latest_album.imatge_url if latest_album else None
    img = _bg_with_cover(cover)
    draw = ImageDraw.Draw(img)
    _draw_brand(draw)

    # Headline = artist name, large. Wrap if needed.
    f_eyebrow = _font("sans", 28)
    draw.text((48, 220), "ARTISTA", fill=COLOR_MUTED, font=f_eyebrow)

    f_name = _font("display", 96)
    name_lines = _wrap(draw, a.nom, f_name, OG_W - 96)
    y = 256
    for ln in name_lines[:2]:  # at most 2 lines
        draw.text((48, y), ln, fill=COLOR_YELLOW, font=f_name)
        y += 100

    # Sub: territori + n_cançons
    n = Canco.objects.filter(artista=a, verificada=True, activa=True).count()
    locs = a.localitats.select_related("municipi__territori").all()
    territori_nom = ""
    if locs:
        codes = sorted({ll.municipi.territori_id for ll in locs if ll.municipi})
        if codes:
            from .meta import TERRITORI_NOMS

            territori_nom = ", ".join(TERRITORI_NOMS.get(c, c) for c in codes)
    sub_parts = []
    if territori_nom:
        sub_parts.append(territori_nom)
    if n:
        sub_parts.append(f"{n} cançons al catàleg")
    if sub_parts:
        f_sub = _font("sans", 28)
        draw.text((48, OG_H - 100), " · ".join(sub_parts), fill=COLOR_WHITE, font=f_sub)
    _draw_footer(draw, "topquaranta.cat/artista/" + a.slug)
    return img


def _compose_album(al: Album) -> Image.Image:
    img = _bg_with_cover(al.imatge_url)
    draw = ImageDraw.Draw(img)
    _draw_brand(draw)

    # Inset the actual cover at the right side as a thumbnail
    if al.imatge_url:
        try:
            from io import BytesIO

            import requests

            r = requests.get(al.imatge_url, timeout=5)
            if r.ok:
                cover = Image.open(BytesIO(r.content)).convert("RGB")
                cover = cover.resize((400, 400), Image.LANCZOS)
                img.paste(cover, (OG_W - 400 - 48, 115))
        except Exception:
            logger.exception("og: album cover paste failed for %s", al.slug)

    f_eyebrow = _font("sans", 28)
    draw.text((48, 220), "ÀLBUM", fill=COLOR_MUTED, font=f_eyebrow)

    f_name = _font("display", 72)
    name_lines = _wrap(draw, al.nom, f_name, OG_W - 96 - 460)
    y = 256
    for ln in name_lines[:3]:
        draw.text((48, y), ln, fill=COLOR_YELLOW, font=f_name)
        y += 80

    f_artist = _font("sans", 36)
    draw.text((48, y + 16), al.artista.nom, fill=COLOR_WHITE, font=f_artist)
    if al.data_llancament:
        f_date = _font("sans", 28)
        draw.text(
            (48, y + 16 + 50),
            str(al.data_llancament.year),
            fill=COLOR_MUTED,
            font=f_date,
        )
    _draw_footer(draw)
    return img


def _compose_canco(c: Canco) -> Image.Image:
    cover_url = c.album.imatge_url if c.album_id else None
    img = _bg_with_cover(cover_url)
    draw = ImageDraw.Draw(img)
    _draw_brand(draw)

    if cover_url:
        try:
            from io import BytesIO

            import requests

            r = requests.get(cover_url, timeout=5)
            if r.ok:
                cover = Image.open(BytesIO(r.content)).convert("RGB")
                cover = cover.resize((400, 400), Image.LANCZOS)
                img.paste(cover, (OG_W - 400 - 48, 115))
        except Exception:
            logger.exception("og: canco cover paste failed for %s", c.slug)

    f_eyebrow = _font("sans", 28)
    draw.text((48, 220), "CANÇÓ", fill=COLOR_MUTED, font=f_eyebrow)

    f_name = _font("display", 72)
    name_lines = _wrap(draw, c.nom, f_name, OG_W - 96 - 460)
    y = 256
    for ln in name_lines[:3]:
        draw.text((48, y), ln, fill=COLOR_YELLOW, font=f_name)
        y += 80

    f_artist = _font("sans", 36)
    draw.text((48, y + 16), c.artista.nom, fill=COLOR_WHITE, font=f_artist)
    _draw_footer(draw)
    return img


# ── Public entry point + caching ────────────────────────────────────


def _cached_render(subdir: str, slug: str, lastmod, builder) -> Path:
    """Render to PNG, caching on disk keyed by `lastmod` so we
    invalidate when the entity changes. Returns the cached path."""
    cache_dir = _ensure_cache_dir(subdir)
    # Filename includes the lastmod timestamp so the file's name
    # changes when the entity does — Caddy / browsers will pull the
    # fresh one because the URL itself differs.
    stamp = (
        lastmod.strftime("%Y%m%d%H%M%S")
        if isinstance(lastmod, datetime.datetime)
        else "0"
    )
    fname = f"{slug or 'home'}-{stamp}.png"
    out = cache_dir / fname
    if out.exists():
        return out
    # Wipe stale variants for this slug (cheap; subdir holds <few>
    # files per entity at most).
    for old in cache_dir.glob(f"{slug or 'home'}-*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    img = builder()
    img.save(out, format="PNG", optimize=True)
    return out


def serve_og(request, kind: str, slug: str = "") -> FileResponse:
    """View handler for `/og/<kind>/[<slug>].png`."""
    if kind == "home":
        path = _cached_render("home", "home", None, _compose_homepage)
    elif kind == "top":
        from .meta import TERRITORI_NOMS

        codi = slug.upper().replace(".PNG", "") if slug else "PPCC"
        if codi not in TERRITORI_NOMS:
            raise Http404
        path = _cached_render(
            "top",
            codi,
            None,
            lambda: _compose_top(codi, TERRITORI_NOMS[codi]),
        )
    elif kind == "artista":
        slug = slug.removesuffix(".png")
        a = Artista.objects.filter(slug=slug, aprovat=True).first()
        if not a:
            raise Http404
        path = _cached_render(
            "artista", slug, a.updated_at, lambda: _compose_artista(a)
        )
    elif kind == "album":
        slug = slug.removesuffix(".png")
        al = (
            Album.objects.filter(slug=slug, descartat=False, artista__aprovat=True)
            .select_related("artista")
            .first()
        )
        if not al:
            raise Http404
        path = _cached_render("album", slug, al.updated_at, lambda: _compose_album(al))
    elif kind == "canco":
        slug = slug.removesuffix(".png")
        c = (
            Canco.objects.filter(slug=slug, verificada=True, activa=True)
            .select_related("artista", "album")
            .first()
        )
        if not c:
            raise Http404
        path = _cached_render("canco", slug, c.updated_at, lambda: _compose_canco(c))
    elif kind == "default":
        path = _cached_render("home", "default", None, _compose_homepage)
    else:
        raise Http404
    resp = FileResponse(path.open("rb"), content_type="image/png")
    resp["Cache-Control"] = "public, max-age=86400"
    return resp
