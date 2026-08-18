"""Newsletter HTML rework (Step 2) + helper coverage.

Anchors the 2026-05-09 lesson (Django `{# #}` is single-line only; a
multi-line comment leaked into every recipient's email) and the new
chrome: podi, hybrid top 4-10, territorial/novetats mini-cards, share
buttons, trend indicators, UTM on every body link, dark mode.
"""

from __future__ import annotations

import re

import pytest
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from comptes.newsletter_meta import derive_subject, trend_indicator
from comptes.newsletter_utm import build_newsletter_url


def _row(pos, canco, artista, *, anterior=None):
    return {
        "posicio": pos,
        "canco_nom": canco,
        "canco_slug": canco.lower().replace(" ", "-"),
        "artistes_display": artista,
        "cover": "https://www.topquaranta.cat/portades/album/1-250.jpg",
        "trend": trend_indicator(pos, anterior),
        "url": build_newsletter_url(
            f"https://www.topquaranta.cat/canco/{canco.lower()}", f"top_{pos}", 39
        ),
    }


def _context():
    podi = [
        _row(1, "Divinize", "Rosalía", anterior=4),  # ↑3
        _row(2, "Estrelles", "Max Navarro", anterior=2),  # →
        _row(3, "Nous", "Ouineta", anterior=None),  # DEBUT
    ]
    resta = [_row(p, f"Cançó {p}", f"Artista {p}", anterior=p) for p in range(4, 11)]
    return {
        "subject": "Setmana 39 · Divinize entra al #1",
        "site_url": "https://www.topquaranta.cat",
        "territori_nom": "Global",
        "project_week": 39,
        "podi": podi,
        "resta": resta,
        "narrative_html": "<p>Un paràgraf editorial de prova.</p>",
        "territorials": [
            {
                "territori": "CAT",
                "territori_nom": "Catalunya",
                "canco_nom": "Tema CAT",
                "artistes_display": "Banda CAT",
                "cover": "https://www.topquaranta.cat/portades/album/2-250.jpg",
                "url": build_newsletter_url(
                    "https://www.topquaranta.cat/top?territori=CAT",
                    "territorial_cat",
                    39,
                ),
            }
        ],
        "novetats": [
            {
                "nom": "Disc Nou",
                "artista_nom": "Banda X",
                "cover": "https://www.topquaranta.cat/portades/album/3-250.jpg",
                "url": build_newsletter_url(
                    "https://www.topquaranta.cat/artista/banda-x", "novetat_1", 39
                ),
            }
        ],
        "share_links": [
            {
                "canal": "telegram",
                "url": build_newsletter_url(
                    "https://t.me/topquaranta", "compartir_telegram", 39
                ),
            }
        ],
        "browser_url": build_newsletter_url(
            "https://www.topquaranta.cat/top", "veure_navegador", 39
        ),
        "cta_url": build_newsletter_url(
            "https://www.topquaranta.cat/top", "cta_top", 39
        ),
        "unsub_url": "https://www.topquaranta.cat/api/v1/compte/baixa-newsletter/?token=x",
    }


def _render():
    return render_to_string("comptes/email_newsletter_top.html", _context())


# ── structural helpers (property oracles, no pixel/hex pins) ─────────


def _style_css(html):
    m = re.search(r"<style[^>]*>(.*?)</style>", html, flags=re.S)
    return m.group(1) if m else ""


def _split_media(css):
    """→ (top_level_css, [(query, body), ...]) with brace matching."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # prose may say "@media"
    top, media, i = [], [], 0
    while i < len(css):
        m = re.compile(r"@media\s*([^{]+)\{").search(css, i)
        if not m:
            top.append(css[i:])
            break
        top.append(css[i : m.start()])
        depth, j = 1, m.end()
        while j < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        media.append((m.group(1).strip(), css[m.end() : j - 1]))
        i = j
    return "".join(top), media


def _rules(css):
    """[(selector, declarations)] for a flat CSS body (comments removed).
    Comma-separated selector lists are expanded one row per selector."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for one in sel.split(","):
            out.append((one.strip(), body.strip()))
    return out


def _decl(css_body, prop):
    m = re.search(r"(?:^|;)\s*%s\s*:\s*([^;]+)" % re.escape(prop), css_body)
    return m.group(1).replace("!important", "").strip() if m else None


def _no_mso(html):
    """The HTML with every MSO conditional-comment segment removed."""
    return re.sub(r"<!--\[if mso\]>.*?<!\[endif\]-->", "", html, flags=re.S)


def _tags(html, name):
    """[(attrs_str, attrs_dict)] for every <name ...> opening tag."""
    out = []
    for attrs in re.findall(r"<%s\b([^>]*)>" % name, html, flags=re.S):
        out.append((attrs, dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))))
    return out


def _column_classes(html):
    """Column classes are the SOURCE OF TRUTH of the hybrid layout: any
    class that (a) gets a `max-width` cap in the top-level <style> rules
    and (b) is used on a <div>. Derived, never listed by hand."""
    top, _ = _split_media(_style_css(html))
    capped = {
        sel.lstrip(".")
        for sel, body in _rules(top)
        if sel.startswith(".") and _decl(body, "max-width")
    }
    used_on_div = {d.get("class") for _, d in _tags(html, "div")}
    return capped & used_on_div


# ── template render ──────────────────────────────────────────────────


def test_renders_titles_and_blocks():
    html = _render()
    for s in ("Divinize", "Estrelles", "Cançó 4", "Tema CAT", "Disc Nou", "Telegram"):
        assert s in html, s
    assert "Un paràgraf editorial" in html


def test_all_images_have_alt():
    html = _render()
    for img in re.findall(r"<img\b[^>]*>", html):
        assert re.search(r'\balt="[^"]+"', img), img  # non-empty alt


def test_body_content_links_carry_utm():
    html = _render()
    # Every link to a /canco, /top, /artista or share target must be
    # UTM-tagged; the unsub link is the only deliberately-bare one.
    for m in re.finditer(r'href="([^"]+)"', html):
        url = m.group(1)
        if "baixa-newsletter" in url:
            continue
        if any(p in url for p in ("/canco/", "/top", "/artista/", "t.me/")):
            assert "utm_source=newsletter" in url, url
            assert "utm_content=" in url, url


def test_trend_indicators_render():
    html = _render()
    assert "DEBUT" in html  # podi #3 has no previous position
    assert "↑3" in html  # #1 climbed from 4
    assert "→" in html  # #2 stable


def test_no_template_comment_leaks():
    html = _render()
    for marker in ("{#", "#}", "{ #", "Fase 4", "Django's", "endcomment"):
        assert marker not in html, marker
    text = strip_tags(html)
    assert "{#" not in text and "endcomment" not in text


def test_dark_mode_and_responsive_present():
    """Property asserted: the <style> block has a dark-scheme media query
    with at least one rule and a mobile (`max-width`) media query with
    at least one rule — breakpoint value not pinned."""
    html = _render()
    _, media = _split_media(_style_css(html))
    dark = [b for q, b in media if "prefers-color-scheme" in q and "dark" in q]
    mobile = [b for q, b in media if re.search(r"max-width\s*:\s*\d+px", q)]
    assert dark and _rules(dark[0]), media
    assert mobile and _rules(mobile[0]), media


# ── Gmail compatibility (2026-07-05 refactor) ────────────────────────


def test_gmail_meta_color_scheme_dark():
    """Gmail auto-inverts ambiguous emails; the meta pins dark-only."""
    html = _render()
    assert '<meta name="color-scheme" content="dark">' in html
    assert '<meta name="supported-color-schemes" content="dark">' in html


def test_gmail_redundant_bgcolor_attributes():
    """Every surface element pins its dark background explicitly, so
    Gmail keeps the dark surfaces even when it strips or ignores CSS
    (dark-mode inversion, clipped <style>). Structural cells use the
    `bgcolor` attribute; the card surfaces are <div>s (2026-08-01), where
    `bgcolor` does not exist, so they carry the inline background-color.
    Property asserted: <body>, every section cell (`td.px`) and every
    `.card` div carry an INLINE background (attribute and/or style, and
    when both, the same value); no surface relies on the <style> block.
    Hex values and counts are not pinned."""
    html = _render()
    ((_body_attrs, body),) = _tags(html, "body")
    assert body.get("bgcolor") and _decl(body.get("style", ""), "background-color")
    sections = [d for _, d in _tags(html, "td") if "px" in d.get("class", "").split()]
    assert sections
    for d in sections:
        inline = _decl(d.get("style", ""), "background-color")
        assert d.get("bgcolor") and inline, d
        assert d["bgcolor"].lower() == inline.lower(), d
    cards = [d for _, d in _tags(html, "div") if "card" in d.get("class", "").split()]
    assert cards
    for d in cards:
        assert _decl(d.get("style", ""), "background-color"), d


def test_gmail_no_rgba_and_no_anchor_wrapped_tables():
    """rgba() borders were replaced by solid hex equivalents and no <a>
    wraps a <table> (Gmail reflows block anchors)."""
    html = _render()
    assert "rgba(" not in html
    assert not re.search(r"<a\b[^>]*>\s*<table", html)


def test_gmail_hybrid_container():
    """Fluid-hybrid wrapper: width=100% + inline max-width + MSO ghost
    table, instead of a fixed pixel width attribute.
    Property asserted: outside the MSO conditionals no <table> carries a
    fixed pixel `width` attribute; the outer wrapper is width=100% with
    an inline pixel max-width; an MSO ghost exists. 640 not pinned."""
    html = _render()
    assert "[if mso]" in html
    plain = _no_mso(html)
    fixed = [
        a for a, d in _tags(plain, "table") if re.fullmatch(r"\d+", d.get("width", ""))
    ]
    assert not fixed, fixed
    wraps = [d for _, d in _tags(plain, "table") if d.get("class") == "wrap"]
    assert len(wraps) == 1
    w = wraps[0]
    assert w.get("width") == "100%"
    assert re.fullmatch(r"\d+px", _decl(w.get("style", ""), "max-width") or ""), w
    # …and the MSO ghost is the only place a pixel width appears on a table.
    assert re.search(r"<!--\[if mso\]><table[^>]*width=\"\d+\"", html)


# ── Gmail mobile: hybrid columns (2026-08-01) ────────────────────────
#
# The 2026-07-05 pass stacked the multi-column groups with
# `.gridcell { display:block; width:100% }` from the <style> block over
# <td>s that carried an inline percentage width. Gmail applied the
# `display:block` but not the matching `width:100%`, so every card fell
# back to its content width: ragged top 4-10 rows, half-width podi cards,
# territorial cards shrunk to the 64 px cover. Replaced by the fluid
# hybrid pattern: a column is a <div> that is full-width by DEFAULT, and
# the <style> block only adds the max-width caps that turn the stack into
# a row on wide viewports.


def _col_divs(html):
    """[(class, inline style)] for every column div — classes derived
    from the <style> caps (see `_column_classes`)."""
    classes = _column_classes(html)
    return [
        (d["class"], d.get("style", ""))
        for _, d in _tags(html, "div")
        if d.get("class") in classes
    ]


def test_gmail_columns_are_full_width_divs_by_default():
    """Layout must survive the <style> block being dropped entirely: no
    <td> is stacked via CSS, and every column div is width:100% inline so
    the no-CSS fallback is a clean single column.
    Property asserted: column classes are derived from the <style> caps;
    every div using one is inline `display:inline-block; width:100%` with
    no inline max-width; no @media rule stacks anything with
    `display:block`. No class names or counts pinned."""
    html = _render()
    classes = _column_classes(html)
    assert len(classes) >= 2, classes  # a real multi-column layout
    cols = _col_divs(html)
    assert cols
    for _cls, style in cols:
        assert _decl(style, "display") == "inline-block", style
        assert _decl(style, "width") == "100%", style
        assert _decl(style, "max-width") is None, style  # the cap is class-only
    _, media = _split_media(_style_css(html))
    for _q, body in media:
        for sel, decl in _rules(body):
            assert _decl(decl, "display") != "block", (sel, decl)


def test_gmail_column_caps_live_in_the_style_block_and_reset_on_mobile():
    """The max-width caps are class rules, and the @media block resets
    them to 100% — class-on-class, so it wins on source order even if a
    client strips `!important`.
    Property asserted: for every column class, the top-level cap is a
    pixel value and the mobile @media block has a rule for that class
    setting max-width to 100%. Pixel caps not pinned."""
    html = _render()
    top, media = _split_media(_style_css(html))
    classes = _column_classes(html)
    assert classes
    mobile = [b for q, b in media if re.search(r"max-width\s*:\s*\d+px", q)]
    assert mobile
    mobile_rules = _rules(mobile[0])
    for cls in classes:
        caps = [_decl(b, "max-width") for sel, b in _rules(top) if sel == "." + cls]
        assert any(re.fullmatch(r"\d+px", c or "") for c in caps), (cls, caps)
        resets = [_decl(b, "max-width") for sel, b in mobile_rules if sel == "." + cls]
        assert any(r and r.startswith("100%") for r in resets), (cls, resets)


def test_gmail_columns_never_add_padding_to_a_100pc_box():
    """Measured 2026-08-01: `width:100%` plus inline padding on the same
    element made the email 410 px wide in a 393 px viewport. Padding goes
    on an inner div, never on the element that carries width:100%."""
    html = _render()
    for _cls, style in _col_divs(html):
        assert "padding" not in style, style


def test_gmail_cards_own_their_width_not_a_nested_table():
    """Nested tables are shrink-to-fit in Gmail, so the card surface
    (background + border + radius) sits on a block-level <div>; any table
    inside it is layout-only.
    Property asserted: no `.card` is a <table>/<td>; there is at least
    one card div per top 4-10 entry; every card div carries its own
    inline background-color AND border. Hex/radius/count not pinned."""
    html = _render()
    for tag in ("table", "td", "tr"):
        assert not [
            d for _, d in _tags(html, tag) if "card" in d.get("class", "").split()
        ]
    cards = [d for _, d in _tags(html, "div") if "card" in d.get("class", "").split()]
    assert len(cards) >= len(_context()["resta"])
    for d in cards:
        style = d.get("style", "")
        assert _decl(style, "background-color"), d
        assert _decl(style, "border"), d


def test_gmail_mso_ghost_columns_for_outlook():
    """Outlook ignores inline-block widths, so each column group is
    bracketed by an MSO ghost table with pixel widths.
    Property asserted: MSO conditionals are balanced, and every column
    div is immediately preceded by an MSO segment that opens a ghost
    `<td width="<px>">`. Ghost pixel widths not pinned."""
    html = _render()
    assert html.count("<!--[if mso]>") == html.count("<![endif]-->") > 0
    classes = _column_classes(html)
    assert classes
    seg_re = re.compile(r"<!--\[if mso\]>(.*?)<!\[endif\]-->", re.S)
    n = 0
    for m in re.finditer(
        r'<div class="(%s)"' % "|".join(map(re.escape, classes)), html
    ):
        before = html[: m.start()]
        segs = seg_re.findall(before)
        assert segs, m.group(0)
        assert re.search(r'<td\s[^>]*width="\d+"', segs[-1]), (m.group(1), segs[-1])
        n += 1
    assert n >= 2


# ── no top 1-40 section + management block ───────────────────────────


def test_management_block_absent_without_gestio_url():
    """The subscriber copy (no gestio_url) must NOT carry the admin block."""
    html = _render()
    assert "Còpia de gestió" not in html
    assert "/staff/social/esborrany" not in html


def test_management_block_present_with_gestio_url():
    """The admin/preview copy carries the block + the staff editor link."""
    link = "https://www.topquaranta.cat/staff/social/esborrany?setmana=2026-06-08"
    ctx = _context()
    ctx["gestio_url"] = link
    html = render_to_string("comptes/email_newsletter_top.html", ctx)
    assert "Còpia de gestió" in html
    assert link in html


# ── UTM helper ───────────────────────────────────────────────────────


def test_utm_helper_four_params():
    url = build_newsletter_url("https://www.topquaranta.cat/top", "cta_top", 39)
    for p in (
        "utm_source=newsletter",
        "utm_medium=email",
        "utm_campaign=top_39_global",
        "utm_content=cta_top",
    ):
        assert p in url, p


def test_utm_helper_bare_host_separator():
    url = build_newsletter_url("https://t.me/topquaranta", "compartir_telegram", 39)
    assert "?utm_source=newsletter" in url  # path present → '?'


# ── subject derivation ───────────────────────────────────────────────


class _Scn:
    def __init__(self, code, data):
        self.code = code
        self.data = data


@pytest.mark.parametrize(
    "code",
    [
        "a1_outside_to_top1",
        "a2_streak",
        "a13_top1_return",
        "a4_debut_alt",
        "fallback_no_event",
    ],
)
def test_subject_every_code_renders(code):
    import random

    s = _Scn(code, {"artista": "Rosalía", "canco": "Divinize"})
    subj = derive_subject(s, 39, random.Random(0))
    assert subj.startswith("Setmana 39 · ")
    assert len(subj) <= 60
    assert "{" not in subj  # no unresolved placeholder


def test_subject_fallback_on_missing_placeholder():
    import random

    s = _Scn("a1_outside_to_top1", {})  # no {artista}
    subj = derive_subject(s, 39, random.Random(0))
    assert subj.startswith("Setmana 39 · ")
    assert "{" not in subj


# ── cover helper ─────────────────────────────────────────────────────


def test_cover_placeholder_when_absent(monkeypatch):
    from comptes import newsletter_covers as nc
    from ingesta.portades import manager

    # Force "not on disk" → placeholder.
    monkeypatch.setattr(
        manager, "path_for", lambda *a, **k: __import__("pathlib").Path("/nope/x.jpg")
    )
    url = nc.album_cover_url(123, 500)
    assert url == nc.placeholder_url()
    assert url.endswith("/static/web/img/newsletter/cover_placeholder.png")


def test_cover_none_id_is_placeholder():
    from comptes import newsletter_covers as nc

    assert nc.album_cover_url(None, 250) == nc.placeholder_url()


def test_cover_local_url_when_present(monkeypatch, tmp_path):
    from comptes import newsletter_covers as nc
    from ingesta.portades import manager

    real = tmp_path / "456-500.jpg"
    real.write_bytes(b"x")
    monkeypatch.setattr(manager, "path_for", lambda *a, **k: real)
    url = nc.album_cover_url(456, 500)
    assert url.endswith("/portades/album/456-500.jpg")
    assert "utm" not in url  # covers are not UTM-tagged


# ── trend indicator ──────────────────────────────────────────────────


def test_trend_classification():
    assert trend_indicator(1, 4)["text"] == "↑3"
    assert trend_indicator(4, 1)["text"] == "↓3"
    assert trend_indicator(2, 2)["text"] == "→"
    assert trend_indicator(5, None)["text"] == "DEBUT"
    assert trend_indicator(1, 8, is_return=True)["text"] == "TORNA"
    # TORNA wins over a DEBUT-looking None.
    assert trend_indicator(1, None, is_return=True)["text"] == "TORNA"
