"""ADR-0007 — Instagram composer rewrites artista_nom to @handle
when the artist has an `instagram_url` stored. The other 4 channels
keep the plain name (different mention syntax per platform)."""

from __future__ import annotations

import datetime
import random

import pytest

from social.narrative import scenarios as scen
from social.narrative.composers import bluesky as c_bsky
from social.narrative.composers import instagram_feed as c_ig
from social.narrative.composers import mastodon as c_mastodon


def _monday():
    return datetime.date(2026, 5, 18)


def _entries():
    """Top-5 entries with the #2 artist having an Instagram URL."""
    return [
        {
            "posicio": i + 1,
            "canco_nom": f"Cançó {i + 1}",
            "artista_nom": f"Artista {i + 1}",
            "artista_instagram_url": (
                "https://instagram.com/artista2_handle" if i + 1 == 2 else ""
            ),
        }
        for i in range(40)
    ]


def _hero_scenario_for_artist2():
    """Hero scenario whose artist matches `Artista 2` (the one with
    an Instagram URL in `_entries()`)."""
    return scen.Scenario(
        code="a4_debut_alt",
        severity=7,
        data={
            "artista": "Artista 2",
            "de_artista": "d'Artista 2",
            "per_a_artista": "per a Artista 2",
            "per_artista": "per Artista 2",
            "canco": "Cançó 2",
            "posicio": 2,
            "posicio_ordinal": "2n",
            "territori_label": "Global",
        },
    )


@pytest.mark.django_db
def test_instagram_feed_substitutes_handle_when_available():
    out = c_ig.compose(
        [_hero_scenario_for_artist2()],
        _entries(),
        territori="PPCC",
        setmana=_monday(),
        rng=random.Random(0),
    )
    assert "@artista2_handle" in out["text"]


@pytest.mark.django_db
def test_instagram_feed_falls_back_to_plain_name_without_handle():
    entries = [
        {
            **e,
            "artista_instagram_url": "",  # nobody has a handle
        }
        for e in _entries()
    ]
    out = c_ig.compose(
        [_hero_scenario_for_artist2()],
        entries,
        territori="PPCC",
        setmana=_monday(),
        rng=random.Random(0),
    )
    # No @-mentions, but plain name is still there.
    assert "Artista 2" in out["text"]
    assert "@" not in out["text"].split("#")[0]  # no @ in body (hashtags excluded)


@pytest.mark.django_db
def test_mastodon_never_uses_at_handle():
    """ADR-0007: only Instagram autolinks `@handle`. Other channels
    keep the plain name to avoid showing broken literal text."""
    out = c_mastodon.compose(
        [_hero_scenario_for_artist2()],
        _entries(),
        territori="PPCC",
        setmana=_monday(),
        rng=random.Random(0),
    )
    body = out["text"].split("#")[0]  # strip hashtags block
    assert "@artista2_handle" not in body
    assert "Artista 2" in body


@pytest.mark.django_db
def test_bluesky_never_uses_at_handle():
    out = c_bsky.compose(
        [_hero_scenario_for_artist2()],
        _entries(),
        territori="PPCC",
        setmana=_monday(),
        rng=random.Random(0),
    )
    body = out["text"].split("#")[0]
    assert "@artista2_handle" not in body
