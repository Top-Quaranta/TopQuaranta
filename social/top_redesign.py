"""TOP family — single-image renders (poster + albums mosaic) + carousel pieces.

# Spec: docs/architecture/social.md

Composes over `render_core` (primitives) + `feed_redesign` (territory palette,
fonts, cover/tile, finish) — no new primitive lives here. Geometry is data in
`social/top_design/top-tokens.json`. All boards are 1080×1350.

Hard rules: PPCC is never labelled (the global poster/cover carries no "PPCC"
text and no name); CAT resolves to the senyera silhouette; the logo is the real
asset; the poster is generated for the global top AND per territory (its palette).
"""

from __future__ import annotations

import datetime
import functools
import json
from pathlib import Path

from PIL import Image, ImageDraw

from social import feed_redesign as F
from social import render_core as R

_TOKENS_PATH = Path(__file__).resolve().parent / "top_design" / "top-tokens.json"
W, H = 1080, 1350


@functools.lru_cache(maxsize=1)
def tokens() -> dict:
    with open(_TOKENS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _ink():
    return Image.new("RGBA", (W, H), F._col(F.tokens()["brand"]["ink"]))


def _composite_over(over_rgba_str, base_rgba):
    """Effective solid colour of `over` (rgba string) composited on `base`."""
    r, g, b, a = F._col(over_rgba_str)
    af = a / 255.0
    br, bg, bb, _ = base_rgba
    return (
        int(round(r * af + br * (1 - af))),
        int(round(g * af + bg * (1 - af))),
        int(round(b * af + bb * (1 - af))),
        255,
    )


def _poster_palette(variant):
    """(accent_rgba, glow_inner_rgba, name) for the poster gradient/accents.
    PPCC → yellow accent, green glow over ink, NO name. Territory → its
    accent/deep + name."""
    ink = F._col(F.tokens()["brand"]["ink"])
    C = tokens()["cartell"]
    if variant in (None, "ppcc", "PPCC"):
        p = C["ppcc"]
        return F._col(p["accent"]), _composite_over(p["glow"], ink), None
    t = F.territori(variant)
    return F._col(t["accent"]), F._col(t["deep"]), t["name"]


def _move_for(e):
    """(kind, n) from real movement. Absent last week → RE if it charted before
    (`reentrada`), else NOU."""
    return R.parse_move(
        e.get("posicio"), e.get("posicio_anterior"), reentry=e.get("reentrada", False)
    )


def _thumb(e, size):
    return F._cover_or_tile(
        e.get("cover_url"),
        size,
        e.get("artista_nom") or e.get("canco_nom") or "?",
        F.territori(e.get("artista_territori")),
        simple=True,
    )


def _artist_credit(e: dict) -> str:
    """Per-song credit for a top row: principal + collaborators,
    comma-joined (mirrors the story slides, which already show every
    artist via `artistes_noms`). Falls back to the legacy single
    `artista_nom`. Callers wrap it in `F._ellipsize` to fit the slot,
    so a long credit truncates instead of overflowing."""
    names = e.get("artistes_noms") or [e.get("artista_nom") or ""]
    return ", ".join(n for n in names if n)


def build_poster(entries: list[dict], setmana, variant: str = "ppcc") -> Image.Image:
    """The TOP cartell (1080×1350, single image): top-10 rich + 11-40 dense,
    movement on every row. `variant` 'ppcc' (global, unlabelled) or a territory
    code (its palette + name)."""
    C = tokens()["cartell"]
    acc, glow_inner, name = _poster_palette(variant)
    white = (255, 255, 255, 255)

    g = C["gradient"]
    img = R.radial_bg(
        (W, H),
        "rgb(%d,%d,%d)" % glow_inner[:3],
        F.tokens()["brand"]["ink"],
        g["at"],
        g["extent"],
        stop=g["stop"],
        dtype="float64",
        mode="RGBA",
    )
    R.apply_grain(img, C["grain"], seed=F._GRAIN_SEED)
    R.rect(img, (0, 0, W, C["bar_h"]), fill=acc)  # top accent bar

    # ── header: logo + SETMANA pill ──
    hd = C["header"]
    F._paste_logo(img, h=hd["logo_h"], x=hd["logo_x"], y=hd["logo_y"])
    sm = hd["setmana"]
    from .captions import _setmana_label  # week label "SETMANA N"

    label = _setmana_label(setmana).upper()
    f_sm = F._font("anton", sm["size"])
    d = ImageDraw.Draw(img)
    tw = R.tracked_width(d, label, f_sm, sm["ls"])
    pill_w = tw + 2 * sm["pad_x"]
    px0 = sm["right"] - pill_w
    R.rect(img, (px0, sm["y"], sm["right"], sm["y"] + sm["h"]), fill=acc)
    R.draw_text(
        img,
        px0 + sm["pad_x"],
        0,
        label,
        f_sm,
        F._col(F.tokens()["brand"]["ink"]),
        tracking=sm["ls"],
        ink_center=sm["y"] + sm["h"] / 2,
        composite=True,
    )

    # ── EL TOP 40 (+ territory name) ──
    ti = C["title"]
    f_t = F._font("anton", ti["size"])
    el = "EL TOP "
    el_w = R.draw_text(img, ti["x"], 0, el, f_t, white, cap_top=ti["cap_top"])
    R.draw_text(img, ti["x"] + el_w, 0, "40", f_t, acc, cap_top=ti["cap_top"])
    if name:
        R.draw_text(
            img,
            ti["x"] + el_w + R.tracked_width(d, "40", f_t, 0) + ti["gap"],
            ti["cap_top"] + 40,
            name,
            F._font("instrument", ti["name_size"]),
            (255, 255, 255, 153),
        )

    items = entries[:40]  # the poster never prints a territory label → all rows render

    # ── rich top 10 (2 cols × 5) ──
    rc = C["rich"]
    for i, e in enumerate(items[:10]):
        col = i // 5
        cx = rc["cols_x"][col]
        y = rc["row_y0"] + (i % 5) * rc["row_pitch"]
        num = e.get("posicio", i + 1)
        f_n = F._font("anton", rc["numeral"]["size"])
        nb = f_n.getbbox(str(num), anchor="la")
        ncol = acc if num == 1 else white
        R.draw_text(
            img,
            cx + rc["numeral"]["w"],
            y,
            str(num),
            f_n,
            ncol,
            align="right",
            cap_top=None,
            composite=True,
        )
        th = _thumb(e, rc["thumb"]["size"])
        img.alpha_composite(th, (int(cx + rc["thumb"]["dx"]), int(y - 4)))
        tx = cx + rc["text_dx"]
        col_right = cx + 466  # rich column width
        tw_avail = col_right - tx - 40
        ft = F._font("bricolage", rc["title"]["size"], rc["title"]["weight"])
        fa = F._font("bricolage", rc["artist"]["size"], rc["artist"]["weight"])
        lh, art_size = rc["title"]["line_h"], rc["artist"]["size"]
        # title clamps to 2 lines (ellipsise the 2nd if it overflows); the artist
        # is ALWAYS its own line below — the title/artist block is vertically
        # centred on the row centre (thumb centre), so they never overlap.
        all_lines = R.wrap(d, e.get("canco_nom", ""), ft, tw_avail)
        lines = all_lines[:2]
        if len(all_lines) > 2 and lines:
            lines[-1] = F._ellipsize(img, lines[-1] + " " + all_lines[2], ft, tw_avail)
        row_center = y - 4 + rc["thumb"]["size"] / 2  # thumb centre
        block_h = len(lines) * lh + 6 + art_size
        top = row_center - block_h / 2
        for li, ln in enumerate(lines):
            R.draw_text(
                img, tx, top + li * lh, ln, ft, white, ink_top=True, composite=True
            )
        R.draw_text(
            img,
            tx,
            top + len(lines) * lh + 6,
            F._ellipsize(img, _artist_credit(e), fa, tw_avail),
            fa,
            (255, 255, 255, 153),
            ink_top=True,
            composite=True,
        )
        k, n = _move_for(e)
        R.draw_move(
            img,
            cx + 466,
            y + 20,
            k,
            n,
            size=rc["move"]["size"],
            variant=rc["move"]["variant"],
        )

    # ── dense 11-40 (2 cols × 15) ──
    de = C["dense"]
    for i, e in enumerate(items[10:40]):
        col = i // 15
        cx = de["cols_x"][col]
        y = de["row_y0"] + (i % 15) * de["row_pitch"]
        R.rect(
            img, (cx, y - 7, cx + de["col_w"], y - 6), fill=F._col(de["rule"]["color"])
        )
        num = e.get("posicio", i + 11)
        f_n = F._font("anton", de["numeral"]["size"])
        R.draw_text(
            img,
            cx + de["numeral"]["w"],
            y,
            str(num),
            f_n,
            F._col(de["numeral"]["color"]),
            align="right",
            composite=True,
        )
        tx = cx + de["text_dx"]
        tw_avail = de["col_w"] - de["text_dx"] - de["text_right_pad"]
        ft = F._font("bricolage", de["title"]["size"], de["title"]["weight"])
        fa = F._font("bricolage", de["artist"]["size"], de["artist"]["weight"])
        ty = y + de["title"]["dy"]
        gap = 8
        # Title + dimmed artist inline on one line. RESERVE room for the artist
        # so a long title ellipsises but the artist STAYS visible (deviates from
        # the design's whole-run ellipsis, which could drop the artist).
        artist = _artist_credit(e)
        art_w = min(d.textlength(artist, font=fa), tw_avail * 0.5)
        title = F._ellipsize(img, e.get("canco_nom", ""), ft, tw_avail - art_w - gap)
        title_w = R.draw_text(img, tx, ty, title, ft, white, composite=True)
        R.draw_text(
            img,
            tx + title_w + gap,
            ty,
            F._ellipsize(img, artist, fa, tw_avail - title_w - gap),
            fa,
            F._col(de["artist"]["color"]),
            composite=True,
        )
        k, n = _move_for(e)
        R.draw_move(
            img,
            cx + de["col_w"],
            y + 11,
            k,
            n,
            size=de["move"]["size"],
            variant=de["move"]["variant"],
        )

    # ── footer ──
    ft_ = C["footer"]
    R.rect(
        img,
        (C["pad"]["l"], ft_["rule_y"], W - C["pad"]["r"], ft_["rule_y"] + 2),
        fill=acc,
    )
    R.draw_text(
        img,
        ft_["url"]["x"],
        ft_["url"]["y"],
        "topquaranta.cat",
        F._font("instrument", ft_["url"]["size"]),
        F._col(ft_["url"]["color"]),
    )
    tg = ft_["tag"]
    R.draw_text(
        img,
        tg["right"],
        tg["y"],
        tg["text"],
        F._font("anton", tg["size"]),
        F._col(tg["color"]),
        align="right",
        tracking=tg["ls"],
    )
    return F._finish(img)


def build_albums_mosaic(albums: list[dict], setmana) -> Image.Image:
    """Mosaic of up to 9 new-album covers (single image, Tuesday)."""
    M = tokens()["mosaic"]
    white = (255, 255, 255, 255)
    g = M["gradient"]
    img = R.radial_bg(
        (W, H),
        g["inner"],
        g["outer"],
        g["at"],
        g["extent"],
        stop=g["stop"],
        dtype="float64",
        mode="RGBA",
    )
    R.apply_grain(img, M["grain"], seed=F._GRAIN_SEED)
    d = ImageDraw.Draw(img)

    hd = M["header"]
    f_h = F._font("anton", hd["nous"]["size"])
    R.draw_text(img, hd["nous"]["x"], hd["nous"]["y"], "NOUS", f_h, white)
    R.draw_text(
        img,
        hd["albums"]["x"],
        hd["albums"]["y"],
        "ÀLBUMS",
        f_h,
        F._col(hd["albums"]["color"]),
    )
    from .captions import _setmana_label

    wk = _setmana_label(setmana).split()[-1]
    R.draw_text(
        img,
        hd["subtitle"]["x"],
        hd["subtitle"]["y"],
        f"els àlbums de la setmana {wk}",
        F._font("instrument", hd["subtitle"]["size"]),
        F._col(hd["subtitle"]["color"]),
    )
    F._paste_logo(
        img, h=hd["logo_h"], x=hd["logo_right"], y=hd["logo_y"], align="right"
    )

    gr = M["grid"]
    cov, lh, dy = gr["cover"], gr["title"]["line_h"], gr["title"]["dy"]
    art_gap, art_h, row_gap = 4, 26, 18
    ft = F._font("bricolage", gr["title"]["size"], gr["title"]["weight"])
    fa = F._font("bricolage", gr["artist"]["size"], gr["artist"]["weight"])
    items = albums[:9]
    rows = [items[r * 3 : r * 3 + 3] for r in range((len(items) + 2) // 3)]
    # CSS-grid auto-rows + flex-centre: each row's height is content-driven (the
    # max title-line count in the row); the whole block is centred in the band
    # between the header and the footer rule (so row 3 never hits the footer).
    wrapped = {
        id(e): R.wrap(d, e.get("nom", ""), ft, cov)[: gr["title"]["max_lines"]]
        for e in items
    }
    row_h = [
        cov + dy + max(len(wrapped[id(e)]) for e in row) * lh + art_gap + art_h
        for row in rows
    ]
    block_h = sum(row_h) + row_gap * (len(rows) - 1)
    band_top, band_bot = 232.0, M["footer"]["rule_y"] - 16
    y = band_top + max(0, (band_bot - band_top - block_h) / 2)
    for ri, row in enumerate(rows):
        for ci, e in enumerate(row):
            cx = gr["cols_x"][ci]
            img.alpha_composite(_thumb(e, cov), (int(cx), int(y)))
            ty = y + cov + dy
            lines = wrapped[id(e)]
            for li, ln in enumerate(lines):
                R.draw_text(img, cx, ty + li * lh, ln, ft, white, composite=True)
            R.draw_text(
                img,
                cx,
                ty + len(lines) * lh + art_gap,
                F._ellipsize(img, _artist_credit(e), fa, cov),
                fa,
                F._col(gr["artist"]["color"]),
                composite=True,
            )
        y += row_h[ri] + row_gap

    fo = M["footer"]
    R.rect(
        img,
        (M["pad"]["l"], fo["rule_y"], W - M["pad"]["r"], fo["rule_y"] + 2),
        fill=F._col(fo["rule_color"]),
    )
    R.draw_text(
        img,
        fo["url"]["x"],
        fo["url"]["y"],
        "topquaranta.cat",
        F._font("instrument", fo["url"]["size"]),
        F._col(fo["url"]["color"]),
    )
    tg = fo["tag"]
    R.draw_text(
        img,
        tg["right"],
        tg["y"],
        tg["text"],
        F._font("anton", tg["size"]),
        F._col(tg["color"]),
        align="right",
        tracking=tg["ls"],
    )
    return F._finish(img)


def _shade(hex_str, amt):
    """Lighten (amt>0, toward white) or darken (amt<0, toward black) a #hex by
    |amt|. Mirrors the design's shade()."""
    h = hex_str.lstrip("#")
    rgb = [int(h[i : i + 2], 16) for i in (0, 2, 4)]
    t = 255 if amt > 0 else 0
    p = abs(amt)
    return tuple(int(round((t - c) * p + c)) for c in rgb) + (255,)


def _list_palette(variant):
    """(accent_rgba, accHi_rgba, chip, name, field_top_hex, field_bot_hex)."""
    yellow = F._col("rgb(250, 204, 21)")
    if variant in (None, "ppcc", "PPCC"):
        return yellow, yellow[:3] + (31,), True, None, "#427c42", "#2f5a2f"
    t = F.territori(variant)
    acc = F._col(t["accent"])
    deep = t["deep"].replace("rgb(", "").rstrip(")")
    dr, dg, db = (int(x) for x in deep.split(","))
    dhex = "#%02x%02x%02x" % (dr, dg, db)
    ft = "#%02x%02x%02x" % _shade(dhex, 0.14)[:3]
    fb = "#%02x%02x%02x" % _shade(dhex, -0.26)[:3]
    return acc, acc[:3] + (31,), False, t["name"], ft, fb


def build_top_cover(setmana, variant: str = "ppcc") -> Image.Image:
    """Carousel cover — green/territory field, EL TOP / 40, week pill."""
    C = tokens()["top_cover"]
    acc, _hi, _chip, name, ftop, fbot = _list_palette(variant)
    white = (255, 255, 255, 255)
    g = C["gradient"]
    img = R.radial_bg(
        (W, H),
        ftop,
        fbot,
        g["at"],
        g["extent"],
        stop=g["stop"],
        dtype="float64",
        mode="RGBA",
    )
    R.apply_grain(img, C["grain"], seed=F._GRAIN_SEED)
    d = ImageDraw.Draw(img)
    F._paste_logo(img, h=C["logo_h"], x=W / 2, y=C["logo_y"], align="center")
    sub = C["subtitle"]
    R.draw_text(
        img,
        W / 2,
        sub["y"],
        sub["text"],
        F._font("instrument", sub["size"]),
        F._col(sub["color"]),
        align="center",
    )
    et = C["el_top"]
    R.draw_text(
        img,
        W / 2,
        0,
        "EL TOP",
        F._font("anton", et["size"]),
        white,
        align="center",
        cap_top=et["cap_top"],
    )
    ft_ = C["forty"]
    R.draw_text(
        img,
        W / 2,
        0,
        "40",
        F._font("anton", ft_["size"]),
        acc,
        align="center",
        tracking=ft_["ls"],
        cap_top=ft_["cap_top"],
    )
    # divider rule + star
    ru = C["rule"]
    R.rect(
        img,
        (ru["left"][0], ru["y"], ru["left"][1], ru["y"] + 2),
        fill=F._col(ru["color"]),
    )
    R.rect(
        img,
        (ru["right"][0], ru["y"], ru["right"][1], ru["y"] + 2),
        fill=F._col(ru["color"]),
    )
    st = C["star"]
    R.star(
        img,
        st["cx"],
        st["cy"],
        st["outer"],
        acc,
        inner_ratio=st["inner_ratio"],
        composite=True,
    )
    # SETMANA pill + cadència (centred group)
    from .captions import _setmana_label

    pl = C["pill"]
    f_p = F._font("anton", pl["size"])
    label = _setmana_label(setmana).upper()
    pw = R.tracked_width(d, label, f_p, pl["ls"]) + 2 * pl["pad_x"]
    cad = C["cadencia"]
    cad_text = name if name else cad["ppcc_text"]
    f_c = F._font("instrument", cad["size"])
    cw = R.tracked_width(d, cad_text, f_c, 0)
    gap = 22
    total = pw + gap + cw
    x0 = (W - total) / 2
    py = pl["cy"] - pl["h"] / 2
    R.rect(img, (x0, py, x0 + pw, py + pl["h"]), fill=acc)
    R.draw_text(
        img,
        x0 + pl["pad_x"],
        0,
        label,
        f_p,
        F._col(F.tokens()["brand"]["ink"]),
        tracking=pl["ls"],
        ink_center=pl["cy"],
    )
    R.draw_text(
        img,
        x0 + pw + gap,
        0,
        cad_text,
        f_c,
        F._col(cad["color"]),
        ink_center=pl["cy"],
    )
    return F._finish(img)


def build_top_list(rows, current, total, setmana, variant: str = "ppcc") -> Image.Image:
    """Carousel list slide — up to 10 rows, chips (ppcc), #1 highlighted."""
    L = tokens()["top_list"]
    acc, hi, chip_on, name, _ft, _fb = _list_palette(variant)
    white = (255, 255, 255, 255)
    img = _ink()
    R.apply_grain(img, L["grain"], seed=F._GRAIN_SEED)
    d = ImageDraw.Draw(img)
    H_ = L["header"]
    rng = f"{rows[0]['posicio']} — {rows[-1]['posicio']}" if rows else ""
    et = H_["el_top"]
    f_h = F._font("anton", et["size"])
    elw = R.draw_text(img, et["x"], et["y"], "EL TOP ", f_h, white)
    R.draw_text(img, et["x"] + elw, et["y"], rng, f_h, acc)
    sub = H_["subtitle"]
    wk = _wk(setmana)
    sub_t = f"{name} · setmana {wk}" if name else f"el top de la setmana {wk}"
    R.draw_text(
        img,
        sub["x"],
        sub["y"],
        sub_t,
        F._font("instrument", sub["size"]),
        F._col(sub["color"]),
    )
    F._paste_logo(
        img, h=H_["logo_h"], x=H_["logo_right"], y=H_["logo_y"], align="right"
    )

    rw = L["rows"]
    for i, e in enumerate(rows[: rw["count"]]):
        y = rw["y0"] + i * rw["pitch"]
        terr = F.territori(e.get("artista_territori"))
        is1 = e.get("posicio") == 1
        R.rect(
            img,
            (rw["x"], y, rw["x"] + rw["w"], y + rw["h"]),
            fill=(hi if is1 else F._col(rw["card_bg"])),
        )
        if is1:
            R.rect(
                img, (rw["x"], y, rw["x"] + rw["w"], y + rw["h"]), outline=acc, width=2
            )
        nm = rw["numeral"]
        f_n = F._font("anton", nm["one_size"] if is1 else nm["size"])
        R.draw_text(
            img,
            nm["x"] + nm["w"] / 2,
            0,
            str(e.get("posicio", i + 1)),
            f_n,
            acc if is1 else white,
            align="center",
            ink_center=y + rw["h"] / 2,
            composite=True,
        )
        tx = rw["thumb"]["x"]
        if chip_on:
            ch = rw["chip"]
            R.rect(
                img,
                (ch["x"], y, ch["x"] + ch["w"], y + rw["h"]),
                fill=F._col(terr["deep"]),
            )
            logo = F._terr_logo(
                F._terr_key(e.get("artista_territori")), F._col(terr["accent"])
            )
            if logo is not None:
                img.alpha_composite(
                    logo,
                    (
                        int(ch["x"] + (ch["w"] - logo.width) / 2),
                        int(y + (rw["h"] - logo.height) / 2),
                    ),
                )
        else:
            tx = rw["chip"]["x"]  # reclaim chip space when no chip
        th = _thumb(e, rw["thumb"]["size"])
        img.alpha_composite(th, (int(tx), int(y + rw["thumb"]["dy"])))
        text_x = tx + rw["thumb"]["size"] + 16
        ti, ar = rw["title"], rw["artist"]
        avail = rw["move"]["right"] - 70 - text_x
        ft = F._font("bricolage", ti["size"], ti["weight"])
        fa = F._font("bricolage", ar["size"], ar["weight"])
        R.draw_text(
            img,
            text_x,
            y + ti["dy"],
            F._ellipsize(img, e.get("canco_nom", ""), ft, avail),
            ft,
            acc if is1 else white,
            composite=True,
        )
        R.draw_text(
            img,
            text_x,
            y + ar["dy"],
            F._ellipsize(img, _artist_credit(e), fa, avail),
            fa,
            F._col(ar["color"]),
            composite=True,
        )
        k, n = _move_for(e)
        R.draw_move(
            img,
            rw["move"]["right"],
            y + rw["h"] / 2,
            k,
            n,
            size=rw["move"]["size"],
            variant=rw["move"]["variant"],
        )

    fo = L["footer"]["url"]
    R.draw_text(
        img,
        fo["x"],
        fo["y"],
        "topquaranta.cat",
        F._font("instrument", fo["size"]),
        F._col(fo["color"]),
    )
    # page dots (active = accent, wider; inactive = white/0.25)
    dy, dh, aw, iw, gp, right = 1265, 10, 26, 10, 9, 1010
    widths = [aw if k + 1 == current else iw for k in range(total)]
    x = right - sum(widths) - gp * (total - 1)
    for k, w in enumerate(widths):
        c = acc if k + 1 == current else (255, 255, 255, 64)
        R.rect(img, (x, dy, x + w, dy + dh), radius=dh / 2, fill=c)
        x += w + gp
    return F._finish(img)


def _wk(setmana):
    from .captions import _setmana_label

    return _setmana_label(setmana).split()[-1]
