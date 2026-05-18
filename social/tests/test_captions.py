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


# ── Narrative-engine integration (Fase 4 PR #2) ─────────────────────


@pytest.mark.django_db
def test_caption_top_uses_narrative_engine():
    """With a real streak seeded into TopSetmanal, caption_top must
    contain the streak-scenario phrase from the narrative bank
    (one of `Top Global`, `{streak} setmanes`, `al #1`, …). We
    can't pin a specific phrase because the registry-bound pick
    is random; instead we assert that the hero block carries a
    streak-shaped token absent from the legacy template."""
    from music.models import Album, Artista, Canco
    from ranking.models import TopSetmanal

    artista = Artista.objects.create(nom="La Fúmiga", slug="la-fumiga", aprovat=True)
    album = Album.objects.create(nom="A", slug="a-lf", artista=artista, descartat=False)
    canco = Canco.objects.create(
        nom="La Gent de la Mediterrània",
        slug="lgm",
        artista=artista,
        album=album,
        verificada=True,
        activa=True,
    )
    for w in (
        datetime.date(2026, 4, 20),
        datetime.date(2026, 4, 27),
        datetime.date(2026, 5, 4),
        datetime.date(2026, 5, 11),
    ):
        TopSetmanal.objects.create(
            canco=canco, territori="PPCC", setmana=w, posicio=1, score_setmanal=99.0
        )

    entries = [
        {
            "posicio": 1,
            "canco_nom": "La Gent de la Mediterrània",
            "artista_nom": "La Fúmiga",
            "artista_instagram_url": "",
        }
    ]
    text = caption_top("top_ppcc", "PPCC", datetime.date(2026, 5, 11), entries)
    # Legacy header is "Top — Global\nSetmana N\n\n…". Engine prepends
    # a hero block referencing the artist and streak count. We can't
    # pin one phrase (random pick), but every A2_STREAK template
    # mentions either "{streak}" expanded (→ "4") AND "La Fúmiga".
    assert "La Fúmiga" in text
    # The legacy plain caption never carries the word "setmana" (it
    # uses "Setmana N" in the header). The engine bank uses lower-case
    # "setmana"/"setmanes" inside the hero. Quick signal that we're
    # on the engine path:
    assert any(tok in text for tok in (" setmana", "setmanes", "cim", "#1"))


@pytest.mark.django_db
def test_caption_short_mastodon_respects_500_char_limit():
    """No matter what hero the engine picks, the assembled Mastodon
    body must fit Mastodon's 500-char hard limit."""
    entries = [
        {"posicio": i, "canco_nom": f"Cançó {i}", "artista_nom": f"Artist {i}"}
        for i in range(1, 11)
    ]
    text = caption_short(
        "top_ppcc",
        "PPCC",
        SETMANA,
        entries,
        channel="mastodon",
    )
    assert len(text) <= 500, f"mastodon body is {len(text)} chars:\n{text}"


@pytest.mark.django_db
def test_caption_short_bluesky_respects_300_char_limit():
    """Bluesky's 300-char ceiling is the tightest budget; ensure the
    composer truncates row+hashtag+hero aggressively enough."""
    entries = [
        {"posicio": i, "canco_nom": f"Cançó {i}", "artista_nom": f"Artist {i}"}
        for i in range(1, 11)
    ]
    text = caption_short(
        "top_ppcc",
        "PPCC",
        SETMANA,
        entries,
        channel="bluesky",
    )
    assert len(text) <= 300, f"bluesky body is {len(text)} chars:\n{text}"


@pytest.mark.django_db
def test_caption_top_fallback_on_engine_error(monkeypatch, caplog):
    """If the engine raises ANY exception, `caption_top` must return
    the legacy plain-list shape and log the error. The publication
    must never go out empty because of an engine bug."""
    import logging

    from social.narrative import scenarios as scen

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic engine failure")

    monkeypatch.setattr(scen, "detect_all", _boom)

    entries = [
        {
            "posicio": 1,
            "canco_nom": "X",
            "artista_nom": "Y",
            "artista_instagram_url": "",
        }
    ]
    with caplog.at_level(logging.ERROR, logger="social.captions"):
        text = caption_top("top_ppcc", "PPCC", SETMANA, entries)

    # Legacy shape: "Top — Global\nSetmana N\n\n1. X · Y\n\n#…"
    assert text.startswith("Top — Global"), text[:60]
    assert "1. X · Y" in text
    # The exception was logged via logger.exception.
    assert any("narrative engine failed" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]
