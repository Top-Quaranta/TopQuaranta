"""Editorial "Sèrie 7" PIL redesign of the three novetats feed slides.

# Spec: social/feed_design/FEED-PIL-SPEC.md

Additive and **gated** by `ConfiguracioGlobal.feed_redisseny_actiu` (default
False). `renderer.py` delegates here only when the flag is on; otherwise the
legacy builders run byte-for-byte.

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
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from social import cover_cache, fonts, svg_assets

logger = logging.getLogger(__name__)

_TOKENS_PATH = Path(__file__).resolve().parent / "feed_design" / "feed-tokens.json"
CANVAS_W, CANVAS_H = 1080, 1350
_GRAIN_SEED = 7


@functools.lru_cache(maxsize=1)
def tokens() -> dict:
    """The exact extracted token table, cached."""
    with open(_TOKENS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ── colour parsing ───────────────────────────────────────────────────

_RGB_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)"
)


def _col(s: str) -> tuple[int, int, int, int]:
    """Parse an exact CSS `rgb()/rgba()` string to an RGBA tuple."""
    m = _RGB_RE.match(s.strip())
    if not m:
        h = s.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    r, g, b, a = m.groups()
    return (int(r), int(g), int(b), int(round(float(a) * 255)) if a else 255)


# ── territory resolver ───────────────────────────────────────────────

_CODE_TO_KEY = {
    "CAT": "pri",
    "VAL": "val",
    "BAL": "bal",
    "CNO": "nor",
    "NOR": "nor",
    "FRA": "fra",
    "AND": "and",
    "ALG": "alg",
}


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
    return Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))


def _cap_offset(font) -> float:
    """Vertical offset from a 'la'-anchored draw point to the cap-top ink,
    using a plain capital. Lets us anchor by INK position (robust to the
    font's line-height) instead of the CSS box, which PIL places lower."""
    return font.getbbox("H", anchor="la")[1]


def _text(img, x, y, text, font, fill, *, align="left", tracking=0.0, cap_top=None):
    """Draw one line. `y` is the line-box top (anchor 'la'); if `cap_top` is
    given instead, the glyph CAP-TOP ink lands at `cap_top` (ink-anchored).
    `align`: x is left / centre / right edge. `tracking` = letter-spacing px.
    Alpha-correct: drawn on a transparent layer then composited."""
    if not text:
        return
    if cap_top is not None:
        y = cap_top - _cap_offset(font)
    lay = _layer()
    d = ImageDraw.Draw(lay)
    advances = [d.textlength(ch, font=font) for ch in text]
    total = sum(advances) + tracking * max(0, len(text) - 1)
    if align == "center":
        cx = x - total / 2
    elif align == "right":
        cx = x - total
    else:
        cx = x
    if tracking == 0:
        d.text((cx, y), text, font=font, fill=fill, anchor="la")
    else:
        for ch, adv in zip(text, advances):
            d.text((cx, y), ch, font=font, fill=fill, anchor="la")
            cx += adv + tracking
    img.alpha_composite(lay)


def _rect(img, box, *, fill=None, radius=0, outline=None, width=1):
    lay = _layer()
    ImageDraw.Draw(lay).rounded_rectangle(
        box, radius=radius, fill=fill, outline=outline, width=width
    )
    img.alpha_composite(lay)


# ── texture / gradient ───────────────────────────────────────────────


def _apply_grain(img, opacity):
    rng = np.random.default_rng(_GRAIN_SEED)
    noise = rng.normal(128, 38, (img.height, img.width)).clip(0, 255).astype(np.uint8)
    a = np.full((img.height, img.width), int(round(opacity * 255)), np.uint8)
    img.alpha_composite(Image.fromarray(np.dstack([noise, noise, noise, a]), "RGBA"))


def _radial(spec) -> Image.Image:
    """CSS radial-gradient(extent at pos, stops) → RGBA image. `extent` is
    (rx, ry) as fractions of (w, h); `at` is (fx, fy) fractions."""
    w, h = CANVAS_W, CANVAS_H
    (fx, fy), (ex, ey) = spec["at"], spec["extent"]
    cx, cy, rx, ry = fx * w, fy * h, ex * w, ey * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    t = np.clip(np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2), 0, 1)[..., None]
    s0, s1 = spec["stops"][0], spec["stops"][1]
    a = np.array(_col(s0[1])[:3], np.float64)
    b = np.array(_col(s1[1])[:3], np.float64)
    arr = (a * (1 - t) + b * t).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


# ── cover slot / fallback tile ───────────────────────────────────────


def _cover_or_tile(cover_url, size, title, terr, *, simple=False):
    img = cover_cache.fetch(cover_url) if cover_url else None
    if img is not None:
        return img.convert("RGBA").resize((size, size), Image.LANCZOS)
    return _tile(size, title, terr, simple=simple)


def _tile(size, title, terr, *, simple=False) -> Image.Image:
    fb = tokens()["fallback_tile"]
    tile = Image.new("RGBA", (size, size), _col(terr["deep"]))
    initial = (title or "?").strip()[:1].upper() or "?"
    f = _font("anton", size * fb["initial"]["size_frac"])
    ImageDraw.Draw(tile).text(
        (size / 2, size / 2), initial, font=f, fill=_col(terr["accent"]), anchor="mm"
    )
    if simple:
        return tile
    ky = fb["keyline"]
    inset = int(round(size * ky["inset_frac"]))
    ar, ag, ab, _a = _col(terr["accent"])
    ImageDraw.Draw(tile).rectangle(
        (inset, inset, size - inset, size - inset),
        outline=(ar, ag, ab, int(ky["alpha"] * 255)),
        width=ky["width"],
    )
    ff = fb["footer"]
    lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f2 = _font("anton", max(8, size * ff["size_frac"]))
    txt = ff["text"]
    advs = [d.textlength(c, font=f2) for c in txt]
    tw = sum(advs) + ff["ls"] * (len(txt) - 1)
    cx = size / 2 - tw / 2
    fy = size * ff["y_off_frac"]
    for c, adv in zip(txt, advs):
        d.text((cx, fy), c, font=f2, fill=_col(ff["color"]), anchor="la")
        cx += adv + ff["ls"]
    tile.alpha_composite(lay)
    return tile


def _paste_logo(img, *, h, x, y, align="left"):
    width = int(round(h * svg_assets.LOGO_ASPECT))
    logo = svg_assets.logo_image_mono(width, "#ffffff")
    if logo is None:
        return
    lx = {"center": x - logo.width / 2, "right": x - logo.width}.get(align, x)
    img.alpha_composite(logo.convert("RGBA"), (int(round(lx)), int(round(y))))


def _finish(img) -> Image.Image:
    bg = Image.new("RGB", img.size, _col(tokens()["brand"]["ink"])[:3])
    bg.paste(img, (0, 0), img)
    return bg


def _wrap(d, text, font, budget):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and d.textlength(trial, font=font) > budget:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _star(img, s):
    """Draw a 5-point star as a polygon (not a text glyph)."""
    import math

    cx, cy = s["cx"], s["cy"]
    R, r = s["outer"], s["inner"]
    pts = []
    for i in range(s["points"] * 2):
        rad = R if i % 2 == 0 else r
        ang = -math.pi / 2 + i * math.pi / s["points"]
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    lay = _layer()
    ImageDraw.Draw(lay).polygon(pts, fill=_col(s["color"]))
    img.alpha_composite(lay)


# ── slide 1 · cover ──────────────────────────────────────────────────


def build_cover(tipus: str, setmana) -> Image.Image:
    from .captions import _setmana_label

    C = tokens()["cover"]
    is_alb = tipus == "nous_albums"
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

    # Territory band (deep) + grain within the band.
    band_img = Image.new("RGBA", (CANVAS_W, band_h), _col(terr["deep"]))
    rng = np.random.default_rng(_GRAIN_SEED)
    noise = rng.normal(128, 38, (band_h, CANVAS_W)).clip(0, 255).astype(np.uint8)
    aa = np.full((band_h, CANVAS_W), int(band["grain"] * 255), np.uint8)
    band_img.alpha_composite(
        Image.fromarray(np.dstack([noise, noise, noise, aa]), "RGBA")
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
    _text(
        img,
        ar["x"],
        ar["y"],
        item.get("artista_nom", "—"),
        _font("bricolage", ar["size"], ar["weight"]),
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
            _ellipsize(img, e.get("artista_nom", "—"), f_ar, text_w),
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
