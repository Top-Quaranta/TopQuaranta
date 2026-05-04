"""Tests for the UTM-URL helper used by every social caption."""

from __future__ import annotations

import datetime

import pytest

from social.captions import caption_short, utm_url

# Sat 9 May 2026 = ISO Monday 4 May 2026; project_week_number(sat)
# resolves to 35 with the anchor week 34 = 25 Apr 2026.
SETMANA_LUNDI = datetime.date(2026, 5, 4)


def test_utm_url_top_ppcc():
    url = utm_url("mastodon", "top_ppcc", SETMANA_LUNDI)
    assert url.startswith("https://topquaranta.cat/?")
    assert "utm_source=mastodon" in url
    assert "utm_medium=social" in url
    assert "utm_campaign=top_ppcc-2026-w36" in url


def test_utm_url_territorial_appends_territory():
    url = utm_url("bluesky", "top_territorial", SETMANA_LUNDI, territori="CAT")
    # Territory suffix lower-cased so it matches the analytics dim.
    assert "utm_campaign=top_territorial-2026-w36-cat" in url


def test_utm_url_ppcc_territory_skipped():
    """`PPCC` is the global aggregate, not a real region — don't
    pollute the campaign name with it."""
    url = utm_url("telegram", "top_ppcc", SETMANA_LUNDI, territori="PPCC")
    assert "utm_campaign=top_ppcc-2026-w36" in url
    assert "-ppcc" not in url


def test_utm_url_newsletter_uses_email_medium():
    url = utm_url("newsletter", "nous_albums", SETMANA_LUNDI)
    assert "utm_medium=email" in url
    assert "utm_source=newsletter" in url


def test_utm_url_custom_base_preserved():
    url = utm_url(
        "newsletter",
        "top_territorial",
        SETMANA_LUNDI,
        base="https://www.topquaranta.cat/top",
        territori="VAL",
    )
    assert url.startswith("https://www.topquaranta.cat/top?")
    assert "utm_campaign=top_territorial-2026-w36-val" in url


def test_caption_short_with_channel_includes_utm_link():
    text = caption_short(
        "top_ppcc",
        "PPCC",
        SETMANA_LUNDI,
        [
            {"posicio": 1, "canco_nom": "Cançó A", "artista_nom": "Artista A"},
            {"posicio": 2, "canco_nom": "Cançó B", "artista_nom": "Artista B"},
        ],
        max_chars=2000,
        channel="mastodon",
    )
    assert "utm_source=mastodon" in text
    assert "utm_campaign=top_ppcc-2026-w36" in text


def test_caption_short_without_channel_falls_back_to_bare_url():
    """Backwards-compat: the IG flow still calls without `channel`."""
    text = caption_short(
        "top_ppcc",
        "PPCC",
        SETMANA_LUNDI,
        [{"posicio": 1, "canco_nom": "Cançó A", "artista_nom": "Artista A"}],
        max_chars=2000,
    )
    assert "https://topquaranta.cat" in text
    assert "utm_" not in text
