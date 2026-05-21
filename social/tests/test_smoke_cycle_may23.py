"""FASE F — End-to-end smoke for the cycle of 23/05/2026.

Runs every channel composer × 3 territories with a deterministic
fake TopSetmanal slice and verifies the post-sprint invariants:

* ADR-0006: no `#N` (digit) in the body.
* ADR-0007: IG body contains `@handle` for entries with
  `artista_instagram_url`; no other channel does.
* ADR-0008: composers don't crash when 3 scenarios are provided.

The dataset is synthetic — the database-driven detector path is
covered by `test_narrative.py` and `test_narrative_scenarios_new.py`.
This smoke locks the rendering chain end-to-end without touching
the production DB.
"""

from __future__ import annotations

import datetime
import random
import re

import pytest

from social.narrative import scenarios as scen
from social.narrative.composers import bluesky as c_bsky
from social.narrative.composers import instagram_feed as c_ig
from social.narrative.composers import mastodon as c_mastodon
from social.narrative.composers import newsletter as c_newsletter
from social.narrative.composers import telegram as c_telegram

SETMANA = datetime.date(2026, 5, 18)  # Monday of cycle 23/05
TERRITORIS = ("PPCC", "CAT", "VAL")
HASHTAG_DIGIT = re.compile(r" #\d")


def _entries(n=40, with_handle_for=(2,)):
    return [
        {
            "posicio": i + 1,
            "canco_nom": f"Cançó {i + 1}",
            "artista_nom": f"Artista {i + 1}",
            "artista_instagram_url": (
                f"https://instagram.com/artista{i + 1}_handle"
                if (i + 1) in with_handle_for
                else ""
            ),
        }
        for i in range(n)
    ]


def _scenarios():
    """Three scenarios mimicking a "rich" cycle: streak hero, debut
    secondary, A9 tertiary. The IG composer is the only one that
    surfaces the tertiary slot (ADR-0008)."""
    hero = scen.Scenario(
        code="a2_streak",
        severity=5,
        data={
            "artista": "Artista 2",
            "de_artista": "d'Artista 2",
            "per_a_artista": "per a Artista 2",
            "per_artista": "per Artista 2",
            "canco": "Cançó 2",
            "streak": 4,
            "territori_label": "Global",
        },
    )
    secondary = scen.Scenario(
        code="a4_debut_alt",
        severity=7,
        data={
            "artista": "Artista 3",
            "de_artista": "d'Artista 3",
            "per_a_artista": "per a Artista 3",
            "per_artista": "per Artista 3",
            "canco": "Cançó 3",
            "posicio": 3,
            "posicio_ordinal": "3r",
            "territori_label": "Global",
        },
    )
    tertiary = scen.Scenario(
        code="a9_debut_anywhere",
        severity=3,
        data={
            "artista": "Artista 7",
            "de_artista": "d'Artista 7",
            "per_a_artista": "per a Artista 7",
            "per_artista": "per Artista 7",
            "canco": "Cançó 7",
            "posicio": 7,
            "posicio_ordinal": "7è",
            "territori_label": "Global",
        },
    )
    return [hero, secondary, tertiary]


@pytest.mark.django_db
@pytest.mark.parametrize("territori", TERRITORIS)
def test_smoke_no_hashtag_positions_across_channels(territori):
    """ADR-0006: the rendered text MUST NOT contain `#<digit>` in
    the body. The hashtag block (final lines) is allowed to have
    text hashtags like `#topquaranta` — the body itself must be
    digit-free."""
    entries = _entries()
    scenarios = _scenarios()

    channels = {
        "instagram_feed": c_ig,
        "mastodon": c_mastodon,
        "bluesky": c_bsky,
        "telegram": c_telegram,
        "newsletter": c_newsletter,
    }
    for name, mod in channels.items():
        out = mod.compose(
            scenarios,
            entries,
            territori=territori,
            setmana=SETMANA,
            rng=random.Random(0),
        )
        text = out.get("text") or out.get("html") or ""
        assert not HASHTAG_DIGIT.search(
            text
        ), f"{territori}/{name} body contains ` #<digit>`: {text!r}"


@pytest.mark.django_db
@pytest.mark.parametrize("territori", TERRITORIS)
def test_smoke_ig_substitutes_at_handle(territori):
    """ADR-0007: IG composer surfaces `@artista2_handle` for the
    hero artist (who has an IG URL stored in `_entries()`)."""
    out = c_ig.compose(
        _scenarios(),
        _entries(),
        territori=territori,
        setmana=SETMANA,
        rng=random.Random(0),
    )
    assert (
        "@artista2_handle" in out["text"]
    ), f"{territori}/instagram_feed missing @handle: {out['text']!r}"


@pytest.mark.django_db
def test_smoke_capture_textual_output_per_channel_and_territori():
    """FASE F report: emit one block per (territori, channel) so the
    sprint summary has real text. Writes the report to
    `/tmp/social-smoke-cycle-2026-05-23.txt`."""
    entries = _entries()
    scenarios = _scenarios()
    channels = {
        "IG-feed": c_ig,
        "Mastodon": c_mastodon,
        "Bluesky": c_bsky,
        "Telegram": c_telegram,
        "Newsletter": c_newsletter,
    }
    report = []
    for territori in TERRITORIS:
        for name, mod in channels.items():
            out = mod.compose(
                scenarios,
                entries,
                territori=territori,
                setmana=SETMANA,
                rng=random.Random(0),
            )
            text = out.get("text") or out.get("html") or ""
            report.append(f"\n=== {territori} / {name} ({len(text)} chars) ===")
            report.append(text)
    full = "\n".join(report)
    with open("/tmp/social-smoke-cycle-2026-05-23.txt", "w") as fh:
        fh.write(full)
    assert "=== PPCC / IG-feed" in full
    assert "=== VAL / Newsletter" in full


@pytest.mark.django_db
@pytest.mark.parametrize("territori", TERRITORIS)
def test_smoke_non_ig_channels_no_at_handle(territori):
    """ADR-0007: Mastodon, Bluesky, Telegram, Newsletter must NOT
    emit `@artista2_handle` — would render as broken literal text."""
    entries = _entries()
    scenarios = _scenarios()
    for name, mod in (
        ("mastodon", c_mastodon),
        ("bluesky", c_bsky),
        ("telegram", c_telegram),
        ("newsletter", c_newsletter),
    ):
        out = mod.compose(
            scenarios,
            entries,
            territori=territori,
            setmana=SETMANA,
            rng=random.Random(0),
        )
        text = out.get("text") or out.get("html") or ""
        assert (
            "@artista2_handle" not in text
        ), f"{territori}/{name} leaks @handle: {text!r}"
