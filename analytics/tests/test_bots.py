"""Bot-marker parity + classification guards (Fase 2 Slice A).

The canonical marker list lives in `analytics/bots.py`. The reverse
proxy decision lives in `deploy/Caddyfile` (`@bot` matcher). These two
MUST stay equivalent: the dashboard's bot/human split is only honest if
the middleware classifies UAs the same way Caddy routes them.
"""

from __future__ import annotations

import re
from pathlib import Path

from analytics.bots import BOT_UA_MARKERS, classify_ua

# repo root: analytics/tests/test_bots.py -> parents[2]
_CADDYFILE = Path(__file__).resolve().parents[2] / "deploy" / "Caddyfile"


def _caddy_markers() -> set[str]:
    """Extract the @bot User-Agent alternation tokens from the Caddyfile
    and normalise them to the same form as BOT_UA_MARKERS (unescaped,
    lowercase).
    """
    text = _CADDYFILE.read_text(encoding="utf-8")
    m = re.search(r"header_regexp User-Agent \(\?i\)\(([^\n]*?)\)\s*$", text, re.M)
    assert m, "could not locate the @bot User-Agent regex in the Caddyfile"
    body = m.group(1)
    tokens = body.split("|")
    return {t.replace("\\.", ".").strip().lower() for t in tokens}


def test_python_markers_match_caddyfile_regex():
    assert set(BOT_UA_MARKERS) == _caddy_markers()


def test_no_duplicate_markers():
    assert len(BOT_UA_MARKERS) == len(set(BOT_UA_MARKERS))


def test_classify_known_bots():
    googlebot = (
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    )
    assert classify_ua(googlebot) == "bot"
    assert classify_ua("GPTBot/1.0") == "bot"
    assert classify_ua("facebookexternalhit/1.1") == "bot"


def test_classify_human_and_empty():
    chrome = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/148.0 Safari/537.36"
    )
    assert classify_ua(chrome) == "human"
    assert classify_ua("") == "human"
    assert classify_ua(None) == "human"


def test_sitemaps_are_not_pageviews():
    """A sitemap is a machine endpoint, never a visit. The skip list said
    `/sitemap.xml` — the index — but the real ones are `/sitemap-*.xml`,
    and a dot is not a dash. Combined with "unknown UA → human", they
    became the entire "top human pages" list of the weekly digest
    (2026-08-17)."""
    from analytics.middleware import _is_public_pageview

    class _Req:
        method = "GET"

        def __init__(self, path):
            self.path = path

    for path in (
        "/sitemap.xml",
        "/sitemap-artistes.xml",
        "/sitemap-cancons.xml",
        "/sitemap-albums.xml",
        "/sitemap-top_historic.xml",
        "/sitemap-territoris.xml",
        "/sitemap-generes.xml",
        "/sitemap-static.xml",
    ):
        assert not _is_public_pageview(_Req(path)), path

    # …and real pages still count.
    for path in ("/", "/top", "/artistes", "/canco/alguna-cosa"):
        assert _is_public_pageview(_Req(path)), path
