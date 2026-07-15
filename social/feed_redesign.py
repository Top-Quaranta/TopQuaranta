"""Editorial "Sèrie 7" PIL redesign of the three novetats feed slides.

# Spec: social/feed_design/FEED-PIL-SPEC.md

This is the **only** novetats feed renderer (since 2026-06-11): `renderer.py`'s
`render_feed_novetats` delegates the three pieces (cover, single-album, singles
grid) straight to `build_cover` / `build_album` / `build_singles`. The earlier
`ConfiguracioGlobal.feed_redisseny_actiu` gate and the legacy PIL layout were
removed once the redesign was approved.

**Source of truth: `social/feed_design/feed-tokens.json`** — EXACT computed
values (getComputedStyle + getBoundingClientRect) extracted from the curated
Claude Design export (`feed1.html`) rendered headless at 1080×1350. Every
position, size, colour, letter-spacing, shadow offset and gradient stop here
comes from that extraction, not from a verbal description. Effects without a
1:1 mapping use their known PIL equivalent: grain = deterministic gaussian
grey noise at the JSON opacity; text-shadow = an offset draw; CSS gradient =
a PIL gradient.

Scope is layout only: album selection, singles bin-packing, per-channel
gating, idempotency, and the Deezer cover sourcing/fallback contract
(`cover_cache.fetch`) are untouched — only the cover-missing tile's visual.

Content rules: album title NEVER ellipsised (wrap to 2 lines, then shrink);
full territory name on the album, short name on singles; PPCC is never a row
territory; Bricolage 500/700/800 are real vendored statics.
"""

from __future__ import annotations

import datetime
import functools
import json
import logging
from pathlib import Path

from PIL import Image, ImageDraw

from social import cover_cache, fonts, render_core, svg_assets

logger = logging.getLogger(__name__)

_DESIGN_DIR = Path(__file__).resolve().parent / "feed_design"
_TOKENS_PATH = _DESIGN_DIR / "feed-tokens.json"
_LOGO_DIR = _DESIGN_DIR / "territory_logos"
CANVAS_W, CANVAS_H = 1080, 1350
_GRAIN_SEED = 7


@functools.lru_cache(maxsize=1)
def tokens() -> dict:
    """The exact extracted token table, cached."""
    with open(_TOKENS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# Primitives live once in `render_core`; these thin aliases keep the build_*
# call sites unchanged. Token-bound wrappers (territori, _terr_logo, _tile,
# _font) stay here because their geometry/palette comes from `feed-tokens.json`.
_col = render_core.col
_CODE_TO_KEY = render_core.CODE_TO_KEY
_terr_key = render_core.terr_key


def _terr_logo(key: str, accent):
    """Territory silhouette recoloured to `accent`, optically sized for the chip
    (width = optH*aspect capped at maxW, then height scales). Geometry from the
    tokens; the recolour/resize is `render_core.silhouette`. None if no spec."""
    spec = tokens()["territory_logos"]
    pt = spec["per_territory"].get(key)
    if pt is None:
        return None
    opt_h, aspect, max_w = pt["optH"], pt["aspect"], spec["maxW"]
    w, h = opt_h * aspect, float(opt_h)
    if w > max_w:
        w, h = float(max_w), max_w / aspect
    return render_core.silhouette(_LOGO_DIR / f"{key}.png", accent, round(w), round(h))


def territori(code: str | None) -> dict:
    """DB territory code → `{deep, accent, abbr, short, name}` (exact rgb
    strings). Aggregate/unknown → a green fallback so the fn is total."""
    t = tokens()["territories"]
    key = _CODE_TO_KEY.get((code or "").upper())
    if key and key in t:
        return t[key]
    return {
        "name": "Països Catalans",
        "short": "Global",
        "abbr": (code or "PPCC").upper()[:4],
        "deep": "rgb(47, 90, 47)",
        "accent": "rgb(123, 191, 123)",
    }


# ── fonts ────────────────────────────────────────────────────────────


def _artist_credit(item: dict) -> str:
    """Per-release credit: principal + collaborators, comma-joined
    (mirrors `top_redesign._artist_credit` and the story slides, which
    show every artist via `artistes_noms`). Falls back to the legacy
    single `artista_nom`. Callers wrap it in `_ellipsize` to fit."""
    names = item.get("artistes_noms") or [item.get("artista_nom") or ""]
    return ", ".join(n for n in names if n) or "—"


def _font(role: str, size, weight: int = 800):
    size = int(round(size))
    if role == "anton":
        return fonts.anton(size)
    if role == "playfair":
        return fonts.display_xbold(size)
    if role == "instrument":
        return fonts.instrument_italic(size)
    if role == "bricolage":
        if weight <= 500:
            return fonts.bricolage_medium(size)
        if weight <= 700:
            return fonts.bricolage_bold(size)
        return fonts.bricolage_xbold(size)
    raise ValueError(f"unknown font role {role!r}")


# ── primitive draw helpers (alpha-correct via overlay composite) ─────


def _layer():
    return render_core.layer((CANVAS_W, CANVAS_H))


_cap_offset = render_core.cap_offset


def _text(img, x, y, text, font, fill, *, align="left", tracking=0.0, cap_top=None):
    """Feed one-line text (transparent-layer composite, cap-top/em-box anchor)."""
    render_core.draw_text(
        img,
        x,
        y,
        text,
        font,
        fill,
        align=align,
        tracking=tracking,
        cap_top=cap_top,
        composite=True,
    )


_rect = render_core.rect
_wrap = render_core.wrap


def _apply_grain(img, opacity):
    render_core.apply_grain(img, opacity, seed=_GRAIN_SEED)


def _radial(spec) -> Image.Image:
    """CSS radial-gradient(extent at pos, stops) → RGBA. Feed semantics: the
    distance is clipped to 1 (stop=1.0), float64."""
    return render_core.radial_bg(
        (CANVAS_W, CANVAS_H),
        spec["stops"][0][1],
        spec["stops"][1][1],
        spec["at"],
        spec["extent"],
        stop=1.0,
        dtype="float64",
        mode="RGBA",
    )


# ── cover slot / fallback tile ───────────────────────────────────────


def _cover_or_tile(cover_url, size, title, terr, *, simple=False):
    img = cover_cache.fetch(cover_url) if cover_url else None
    if img is not None:
        return img.convert("RGBA").resize((size, size), Image.LANCZOS)
    return _tile(size, title, terr, simple=simple)


def _tile(size, title, terr, *, simple=False) -> Image.Image:
    """Feed fallback tile — geometry from `fallback_tile` tokens, drawn by
    `render_core.tile`."""
    fb = tokens()["fallback_tile"]
    initial = (title or "?").strip()[:1].upper() or "?"
    footer = {**fb["footer"], "color": _col(fb["footer"]["color"])}
    return render_core.tile(
        size,
        _col(terr["deep"]),
        _col(terr["accent"]),
        initial,
        initial_frac=fb["initial"]["size_frac"],
        simple=simple,
        keyline=fb["keyline"],
        footer=footer,
    )


def _paste_logo(img, *, h, x, y, align="left"):
    render_core.paste_logo(img, h=h, x=x, y=y, align=align, hex_color="#ffffff")


def _finish(img) -> Image.Image:
    bg = Image.new("RGB", img.size, _col(tokens()["brand"]["ink"])[:3])
    bg.paste(img, (0, 0), img)
    return bg


def _star(img, s):
    """Five-point star from the cover token spec (absolute inner radius)."""
    render_core.star(
        img,
        s["cx"],
        s["cy"],
        s["outer"],
        _col(s["color"]),
        inner_ratio=s["inner"] / s["outer"],
        points=s["points"],
        composite=True,
    )


# ── slide 1 · cover ──────────────────────────────────────────────────


def build_cover(tipus: str, setmana, *, covers: list | None = None) -> Image.Image:
    """Novetats cover. `covers` (raw cover images, ≥2) switches the
    background to the duotone mosaic (2026-07, gated by
    `feed_artwork_actiu`); the novetats palette (yellow accent, green
    field hue) comes from the tokens. None → byte-identical typographic
    cover. The caller guarantees ≥2 covers (fewer falls back to None)."""
    from .captions import _setmana_label

    C = tokens()["cover"]
    is_alb = tipus == "nous_albums"
    if covers:
        from . import duotone

        img = duotone.duotone_mosaic(
            covers,
            C["etiqueta"]["color"],  # yellow accent
            C["gradient"]["stops"][0][1],  # green field top = edition hue
            (CANVAS_W, CANVAS_H),
        )
    else:
        img = _radial(C["gradient"])
        _apply_grain(img, tokens()["grain"]["cover"])

    _paste_logo(
        img, h=C["logo"]["h"], x=C["logo"]["cx"], y=C["logo"]["y"], align="center"
    )

    p = C["presenta"]
    _text(
        img,
        540,
        p["y"],
        p["text"],
        _font("instrument", p["size"]),
        _col(p["color"]),
        align="center",
    )

    # NOVETATS (white) and ÀLBUMS/SINGLES (yellow) are ink-anchored by
    # cap-top so the white overlaps the yellow exactly like the reference.
    n = C["novetats"]
    _text(
        img,
        540,
        0,
        n["text"],
        _font("anton", n["size"]),
        _col(n["color"]),
        align="center",
        cap_top=n["cap_top"],
    )

    e = C["etiqueta"]
    et = e["albums"] if is_alb else e["singles"]
    f_e = _font("anton", e["size"])
    sh = e["shadow"]
    _text(
        img,
        540 + sh["dx"],
        0,
        et,
        f_e,
        _col(sh["color"]),
        align="center",
        tracking=e["ls"],
        cap_top=e["cap_top"] + sh["dy"],
    )
    _text(
        img,
        540,
        0,
        et,
        f_e,
        _col(e["color"]),
        align="center",
        tracking=e["ls"],
        cap_top=e["cap_top"],
    )

    r = C["rule"]
    _rect(
        img,
        (r["left"][0], r["y"], r["left"][1], r["y"] + r["h"]),
        fill=_col(r["color"]),
    )
    _rect(
        img,
        (r["right"][0], r["y"], r["right"][1], r["y"] + r["h"]),
        fill=_col(r["color"]),
    )
    _star(img, C["star"])

    # Bottom row: SETMANA pill (left) + cadència italic (right), group centred.
    pill, cad, grp = C["pill"], C["cadencia"], C["bottom_group"]
    setmana_txt = _setmana_label(setmana).upper()
    f_pill = _font("anton", pill["size"])
    lay = ImageDraw.Draw(_layer())
    ptw = sum(lay.textlength(c, font=f_pill) for c in setmana_txt) + pill["ls"] * (
        len(setmana_txt) - 1
    )
    pill_w = ptw + 2 * pill["pad_x"]
    cad_txt = cad["albums"] if is_alb else cad["singles"]
    f_cad = _font("instrument", cad["size"])
    cad_w = lay.textlength(cad_txt, font=f_cad)
    group_w = pill_w + grp["gap"] + cad_w
    gx = grp["center"] - group_w / 2
    py = pill["y"]
    _rect(
        img,
        (gx, py, gx + pill_w, py + pill["h"]),
        fill=_col(pill["bg"]),
        radius=pill["radius"],
    )
    _text(
        img,
        gx + pill["pad_x"],
        py + (pill["h"] - pill["size"]) / 2 - 2,
        setmana_txt,
        f_pill,
        _col(pill["color"]),
        tracking=pill["ls"],
    )
    _text(img, gx + pill_w + grp["gap"], cad["y"], cad_txt, f_cad, _col(cad["color"]))

    return _finish(img)


# ── slide 2 · album ──────────────────────────────────────────────────


def build_album(item: dict) -> Image.Image:
    A = tokens()["album"]
    terr = territori(item.get("artista_territori"))
    accent = _col(terr["accent"])

    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), _col(tokens()["brand"]["ink"]))
    _apply_grain(img, tokens()["grain"]["page"])

    # Title wrap: never ellipsise — wrap to ≤2 lines, shrink if still wider.
    tcfg = A["title"]
    budget = tcfg["wrap_budget"]
    size = tcfg["size"]
    probe = ImageDraw.Draw(_layer())
    while True:
        f_title = _font("playfair", size, tcfg["weight"])
        lines = _wrap(probe, item["nom"], f_title, budget)
        if len(lines) <= 2 or size <= tcfg["min_size"]:
            break
        size -= 4
    lines = lines[:2]
    nlines = len(lines)

    band = A["band"]
    band_h = band["h1"] + band["per_line"] * (nlines - 1)
    band_top = band["bottom"] - band_h
    cov = A["cover"]
    cover_y = cov["header_bottom"] + (band_top - cov["header_bottom"] - cov["size"]) / 2
    cx = (CANVAS_W - cov["size"]) // 2

    # Hero cover (or fallback tile).
    tile = _cover_or_tile(
        item.get("cover_url"), cov["size"], item.get("nom", "?"), terr
    )
    img.alpha_composite(tile, (cx, int(round(cover_y))))

    # Territory band (deep) + grain within the band (truncated alpha — exact).
    band_img = Image.new("RGBA", (CANVAS_W, band_h), _col(terr["deep"]))
    render_core.apply_grain(
        band_img, band["grain"], seed=_GRAIN_SEED, round_alpha=False
    )
    img.alpha_composite(band_img, (0, int(round(band_top))))

    _paste_logo(img, h=A["logo"]["h"], x=A["logo"]["x"], y=A["logo"]["y"])
    na = A["nou_album"]
    _text(
        img,
        na["right"],
        na["y"],
        na["text"],
        _font("anton", na["size"]),
        accent,
        align="right",
        tracking=na["ls"],
    )

    title_y = band_top + tcfg["y_off_band"]
    for i, ln in enumerate(lines):
        _text(
            img,
            tcfg["x"],
            title_y + i * tcfg["line_h"],
            ln,
            f_title,
            _col(tcfg["color"]),
        )
    ar = A["artist"]
    f_ar = _font("bricolage", ar["size"], ar["weight"])
    # Ellipsise the credit so a long principal+collab list can't collide
    # with the right-aligned territory block (abbr/name end at x=1000).
    _text(
        img,
        ar["x"],
        ar["y"],
        _ellipsize(img, _artist_credit(item), f_ar, A["title"]["wrap_budget"] - 60),
        f_ar,
        _col(ar["color"]),
    )
    ab = A["abbr"]
    _text(
        img,
        ab["right"],
        ab["y"],
        terr["abbr"],
        _font("anton", ab["size"]),
        accent,
        align="right",
        tracking=ab["ls"],
    )
    nm = A["name"]
    _text(
        img,
        nm["right"],
        nm["y"],
        terr["name"],
        _font("bricolage", nm["size"], nm["weight"]),
        _col(nm["color"]),
        align="right",
    )

    return _finish(img)


# ── slide 3 · singles ────────────────────────────────────────────────


def build_singles(
    items: list[dict], page: int, total_pages: int, setmana=None
) -> Image.Image:
    S = tokens()["singles"]
    # Blind PPCC — never a row territory.
    items = [e for e in items if (e.get("artista_territori") or "").upper() != "PPCC"]

    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), _col(tokens()["brand"]["ink"]))
    _apply_grain(img, tokens()["grain"]["page"])

    H = S["header"]
    for key in ("novetats", "singles"):
        e = H[key]
        _text(
            img,
            e["x"],
            e["y"],
            e["text"],
            _font("anton", e["size"]),
            _col(e["color"]),
            tracking=e["ls"],
        )
    sub = H["subtitle"]
    txt = sub["prefix"]
    if setmana is not None:
        from music.dates import project_week_number

        txt = "%s %d" % (
            sub["prefix"],
            project_week_number(setmana + datetime.timedelta(days=5)),
        )
    _text(
        img,
        sub["x"],
        sub["y"],
        txt,
        _font("instrument", sub["size"]),
        _col(sub["color"]),
    )
    _paste_logo(
        img, h=H["logo"]["h"], x=H["logo"]["right"], y=H["logo"]["y"], align="right"
    )

    R = S["rows"]
    for i, e in enumerate(items[: R["count"]]):
        y = R["y0"] + i * R["pitch"]
        terr = territori(e.get("artista_territori"))
        _rect(
            img,
            (R["x"], y, R["x"] + R["w"], y + R["h"]),
            fill=_col(R["card_bg"]),
            radius=R["card_radius"],
        )
        ch = R["chip"]
        _rect(
            img,
            (ch["x"], y, ch["x"] + ch["w"], y + R["h"]),
            fill=_col(terr["deep"]),
            radius=R["card_radius"],
        )
        # Territory silhouette (replaces the old abbr text), centred in the chip.
        if ch.get("logo"):
            logo = _terr_logo(
                _terr_key(e.get("artista_territori")), _col(terr["accent"])
            )
            if logo is not None:
                lx = ch["x"] + (ch["w"] - logo.width) / 2
                ly = y + (R["h"] - logo.height) / 2
                img.alpha_composite(logo, (int(round(lx)), int(round(ly))))
        elif ch.get("abbr"):  # legacy fallback
            ab = ch["abbr"]
            _text(
                img,
                ch["x"] + ch["w"] / 2,
                y + ab["y_off"],
                terr["abbr"],
                _font("anton", ab["size"]),
                _col(terr["accent"]),
                align="center",
            )
        th = R["thumb"]
        tile = _cover_or_tile(
            e.get("cover_url"), th["size"], e.get("nom", "?"), terr, simple=True
        )
        if th["radius"]:
            mask = Image.new("L", (th["size"], th["size"]), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, th["size"], th["size"]), radius=th["radius"], fill=255
            )
            img.paste(tile.convert("RGB"), (th["x"], int(round(y + th["y_off"]))), mask)
        else:
            img.alpha_composite(tile, (th["x"], int(round(y + th["y_off"]))))
        ti, ar, sh = R["title"], R["artist"], R["short"]
        text_w = (sh["right"] - 16) - ti["x"]
        f_ti = _font("bricolage", ti["size"], ti["weight"])
        f_ar = _font("bricolage", ar["size"], ar["weight"])
        _text(
            img,
            ti["x"],
            y + ti["y_off"],
            _ellipsize(img, e["nom"], f_ti, text_w),
            f_ti,
            _col(ti["color"]),
        )
        _text(
            img,
            ar["x"],
            y + ar["y_off"],
            _ellipsize(img, _artist_credit(e), f_ar, text_w),
            f_ar,
            _col(ar["color"]),
        )
        _text(
            img,
            sh["right"],
            y + sh["y_off"],
            terr["short"],
            _font("instrument", sh["size"]),
            _col(sh["color"]),
            align="right",
        )

    F = S["footer"]
    u = F["url"]
    _text(
        img, u["x"], u["y"], u["text"], _font("instrument", u["size"]), _col(u["color"])
    )
    if total_pages > 1:
        _page_indicator(img, page, total_pages, F["page"])

    return _finish(img)


def _ellipsize(img, text, font, max_w):
    d = ImageDraw.Draw(_layer())
    if d.textlength(text, font=font) <= max_w:
        return text
    while text and d.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return (text + "…") if text else "…"


def _page_indicator(img, page, total, P):
    lab = P["label"]
    label = f"{page:02d} / {total:02d}"
    f = _font("bricolage", lab["size"], lab["weight"])
    d = ImageDraw.Draw(_layer())
    lw = sum(d.textlength(c, font=f) for c in label) + lab["ls"] * (len(label) - 1)
    _text(
        img,
        lab["right"],
        lab["y"],
        label,
        f,
        _col(lab["color"]),
        align="right",
        tracking=lab["ls"],
    )
    dots = P["dots"]
    x = lab["right"] - lw - dots["gap_to_label"]
    for i in range(total - 1, -1, -1):
        w = dots["active_w"] if i == (page - 1) else dots["inactive_w"]
        c = _col(dots["active"]) if i == (page - 1) else _col(dots["inactive"])
        _rect(
            img,
            (x - w, dots["y"], x, dots["y"] + dots["h"]),
            fill=c,
            radius=dots["h"] / 2,
        )
        x -= w + dots["gap"]
