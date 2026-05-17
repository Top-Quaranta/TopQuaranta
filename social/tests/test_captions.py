"""Caption text generation: per-channel artist labeling.

Locks in the 2026-05-16 decision: the long Instagram caption uses
`@handle` (autolink + notify), the short caption used by every other
channel (Mastodon, Bluesky, Telegram, Newsletter) falls back to plain
artist name because `@handle` is Instagram-specific and looks broken
on the other networks.
"""

from __future__ import annotations

import datetime

import pytest

from social.captions import caption_novetats, caption_short, caption_top

SETMANA = datetime.date(2026, 5, 11)  # Monday of TQ-week 37

TOP_ENTRIES = [
    {
        "posicio": 1,
        "canco_nom": "Una cançó",
        "artista_nom": "Rosalía",
        "artista_instagram_url": "https://www.instagram.com/rosalia.vt/",
    },
    {
        "posicio": 2,
        "canco_nom": "Una altra",
        "artista_nom": "Sense Insta",
        "artista_instagram_url": "",
    },
]

NOVETATS_ENTRIES = [
    {
        "nom": "Disc nou",
        "artista_nom": "Manel",
        "artista_instagram_url": "https://www.instagram.com/manel.cat/",
    }
]


def test_caption_top_uses_handle():
    text = caption_top("top_ppcc", "PPCC", SETMANA, TOP_ENTRIES)
    # Artist with handle renders the @username.
    assert "@rosalia.vt" in text
    # Artist without handle falls back to plain name.
    assert "Sense Insta" in text
    assert "@Sense Insta" not in text


def test_caption_novetats_uses_handle():
    text = caption_novetats("nous_albums", SETMANA, NOVETATS_ENTRIES)
    assert "@manel.cat" in text


def test_caption_short_strips_handle_for_non_instagram_channels():
    """The short caption is the one publicar_canal feeds to Mastodon,
    Bluesky, Telegram and Newsletter. None of them autolink Instagram
    handles, so we emit the plain artist name instead."""
    for channel in ("mastodon", "bluesky", "telegram", "newsletter"):
        text = caption_short(
            "top_ppcc",
            "PPCC",
            SETMANA,
            TOP_ENTRIES,
            max_chars=2000,
            n=5,
            channel=channel,
        )
        assert "@rosalia.vt" not in text, (
            f"channel={channel} body must not carry Instagram-style "
            f"@handle; got:\n{text}"
        )
        assert "Rosalía" in text, f"plain name missing for channel={channel}"
        assert "Sense Insta" in text


def test_caption_short_handles_missing_instagram_url():
    """An entry with no `artista_instagram_url` key should still emit
    the plain name without crashing."""
    entries = [
        {"posicio": 1, "canco_nom": "X", "artista_nom": "Only Name"},
    ]
    text = caption_short(
        "top_ppcc", "PPCC", SETMANA, entries, max_chars=2000, n=5, channel="mastodon"
    )
    assert "Only Name" in text
    assert "@" not in text.split("Tot el top")[0]  # no @ in the body
