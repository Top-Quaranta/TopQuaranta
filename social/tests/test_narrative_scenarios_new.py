"""ADR-0008 — Four new narrative detectors and IG-feed tertiary slot.

The detectors that hit the DB are exercised only smoke-tested here
via direct Scenario assembly (no fixtures); the real coverage of
the SQL path comes from the broader smoke at FASE F."""

from __future__ import annotations

import datetime
import random

import pytest

from social.narrative import scenarios as scen
from social.narrative.banks.hero import HERO
from social.narrative.composers import instagram_feed as c_ig


def test_hero_bank_contains_four_new_scenarios():
    """ADR-0008: the bank must register a9, a10, a11, a12."""
    new_codes = {
        "a9_debut_anywhere",
        "a10_artista_first_ever",
        "a11_top5_drop_generic",
        "a12_artista_emerging",
    }
    assert new_codes.issubset(HERO.keys())


def test_no_hashtag_position_in_any_hero_template():
    """ADR-0006 invariant carries to the new banks: no `#N` where
    N is a digit. The regex ` #\\d` catches mid-sentence forms; the
    leading-`#` case is only legitimate when followed by a letter
    (a hashtag like `#topquaranta`)."""
    import re

    bad = re.compile(r" #\d")
    for code, by_length in HERO.items():
        for length, entries in by_length.items():
            for i, tpl in enumerate(entries):
                assert not bad.search(tpl), f"{code}/{length}[{i}] has `#N`: {tpl!r}"


def _entries(n=40):
    return [
        {
            "posicio": i + 1,
            "canco_nom": f"Cançó {i + 1}",
            "artista_nom": f"Artista {i + 1}",
            "artista_instagram_url": "",
        }
        for i in range(n)
    ]


def _scenario(code, severity, **data):
    base = {
        "artista": "Maria Jaume",
        "de_artista": "de Maria Jaume",
        "per_a_artista": "per a Maria Jaume",
        "per_artista": "per Maria Jaume",
        "canco": "Sant Domingo Forever",
        "posicio": 3,
        "posicio_ordinal": "3r",
        "posicio_anterior": 2,
        "posicio_anterior_ordinal": "2n",
        "posicio_anterior_str": "fora del top",
        "posicio_nova_str": "al 7è",
        "streak": 2,
        "n_cancons": 3,
        "dies": 10,
        "mesos": 6,
        "pujada": 12,
        "territori_label": "Global",
    }
    base.update(data)
    return scen.Scenario(code=code, severity=severity, data=base)


@pytest.mark.django_db
def test_instagram_feed_uses_tertiary_when_three_scenarios_given():
    """ADR-0008: IG feed composer surfaces a third scene (short tier)
    when scenarios[2] exists. The tertiary canço appears in the body
    even when the secondary already used a different canço."""
    hero = _scenario("a2_streak", 5, canco="Headline Song")
    secondary = _scenario("a4_debut_alt", 7, canco="Second Song", posicio=3)
    tertiary = _scenario(
        "a9_debut_anywhere", 3, canco="Third Song", posicio=10, posicio_ordinal="10è"
    )
    out = c_ig.compose(
        [hero, secondary, tertiary],
        _entries(),
        territori="PPCC",
        setmana=datetime.date(2026, 5, 18),
        rng=random.Random(0),
    )
    assert "Third Song" in out["text"]
    assert len(out["phrase_ids"]) == 3


@pytest.mark.django_db
def test_instagram_feed_works_without_tertiary_scenario():
    """No regression when only hero + secondary are given (back-compat)."""
    hero = _scenario("a2_streak", 5, canco="Headline Song")
    secondary = _scenario("a4_debut_alt", 7, canco="Second Song", posicio=3)
    out = c_ig.compose(
        [hero, secondary],
        _entries(),
        territori="PPCC",
        setmana=datetime.date(2026, 5, 18),
        rng=random.Random(0),
    )
    assert "Headline Song" in out["text"] or "Maria Jaume" in out["text"]
    # phrase_ids may be 1-2 depending on bank registry state.
    assert len(out["phrase_ids"]) <= 2
