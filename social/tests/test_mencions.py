"""The mention contract, in one place (ADR-0007).

One rule, stated once:

    Only `instagram_feed` rewrites an artist's name to `@handle`.
    Every other channel emits the plain name. An artist with no stored
    Instagram URL always gets the plain name, everywhere.

Instagram is the only network that autolinks an `@handle`; on the others
the syntax differs (`@user@instance`, `@user.bsky.social`) and we store
no per-network handles, so an IG-style handle renders as broken literal
text.

**Why this file exists.** Before 2026-08-16 that single rule was asserted
by eleven test instances spread over four files — `test_captions.py`,
`test_instagram_handles.py`, `test_smoke_cycle_may23.py` and
`test_multi_channel.py`. Seven of them fell to one mutation of one line.
That is not seven safeguards, it is one safeguard billed seven times: it
slows the suite, and when the rule changes there are four files to find.

Consolidating is only honest if detection survives, so it was verified by
mutation before and after. Both mutations that the eleven caught are
still caught here:

* the engine stops emitting `@handle` (`instagram_feed::_ig_label`),
* a non-Instagram channel starts emitting one (`_artist_label`).

Covered on both axes that matter — channel × handle-present — and through
both routes into the text: the narrative composers, and the public
`caption_*` helpers that `publicar_social` / `publicar_canal` call.
"""

from __future__ import annotations

import datetime
import random

import pytest

from social.captions import caption_novetats, caption_short, caption_top
from social.narrative import scenarios as scen
from social.narrative.composers import bluesky as c_bsky
from social.narrative.composers import instagram_feed as c_ig
from social.narrative.composers import mastodon as c_mastodon
from social.narrative.composers import newsletter as c_newsletter
from social.narrative.composers import telegram as c_telegram

SETMANA = datetime.date(2026, 5, 18)
HANDLE = "@artista2_handle"
NOM_PLA = "Artista 2"

# The composer per channel, and whether it is the one allowed to mention.
CANALS = [
    ("instagram_feed", c_ig, True),
    ("mastodon", c_mastodon, False),
    ("bluesky", c_bsky, False),
    ("telegram", c_telegram, False),
    ("newsletter", c_newsletter, False),
]


def _entries(*, amb_handle=True):
    """Top-40 slice where artist #2 has (or hasn't) an Instagram URL."""
    return [
        {
            "posicio": i + 1,
            "canco_nom": f"Cançó {i + 1}",
            "artista_nom": f"Artista {i + 1}",
            "artista_instagram_url": (
                "https://instagram.com/artista2_handle"
                if (i + 1 == 2 and amb_handle)
                else ""
            ),
        }
        for i in range(40)
    ]


def _hero_artista2():
    """A hero scenario about artist #2, so the mention has to be rendered
    somewhere a composer can reach it."""
    return scen.Scenario(
        code="a4_debut_alt",
        severity=7,
        data={
            "artista": NOM_PLA,
            "de_artista": "d'Artista 2",
            "per_a_artista": "per a Artista 2",
            "per_artista": "per Artista 2",
            "canco": "Cançó 2",
            "posicio": 2,
            "posicio_ordinal": "2n",
            "territori_label": "Global",
        },
    )


def _text(out) -> str:
    return out.get("text") or out.get("html") or ""


# ── The narrative composers ────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("canal,mod,pot_mencionar", CANALS)
def test_only_instagram_rewrites_a_name_into_a_handle(canal, mod, pot_mencionar):
    """Parametrised by CHANNEL and nothing else. The rule never reads the
    territori, so sweeping three of them would triple the case count and
    buy nothing — the smoke this replaces did, which is part of why one
    rule cost eleven cases."""
    text = _text(
        mod.compose(
            [_hero_artista2()],
            _entries(),
            territori="PPCC",
            setmana=SETMANA,
            rng=random.Random(0),
        )
    )
    if pot_mencionar:
        assert HANDLE in text, f"{canal} no menciona: {text!r}"
    else:
        assert HANDLE not in text, f"{canal} filtra el handle: {text!r}"
        # …and the artist is still named. Otherwise "drops the artist
        # entirely" would pass as "doesn't use the handle".
        assert NOM_PLA in text, f"{canal} no anomena l'artista"


@pytest.mark.django_db
def test_an_artist_without_a_stored_url_is_never_mentioned():
    """Instagram only: it is the one channel that can invent a handle, so
    it is the only one where "no URL stored" is a risk worth a case."""
    text = _text(
        c_ig.compose(
            [_hero_artista2()],
            _entries(amb_handle=False),
            territori="PPCC",
            setmana=SETMANA,
            rng=random.Random(0),
        )
    )
    assert HANDLE not in text
    assert NOM_PLA in text


# ── The public caption helpers ─────────────────────────────────────


TOP_ENTRIES = [
    {
        "posicio": 1,
        "canco_nom": "Divinize",
        "artista_nom": "Rosalía",
        "artista_instagram_url": "https://www.instagram.com/rosalia.vt/",
    },
    {
        "posicio": 2,
        "canco_nom": "Sense",
        "artista_nom": "Sense Insta",
        "artista_instagram_url": "",
    },
]


@pytest.mark.django_db
def test_the_public_caption_helpers_follow_the_rule():
    """`django_db` is load-bearing: `compose_for_channel` swallows any
    engine error and returns the legacy caption, so a test without DB
    access silently measures the one path production never takes. That
    is why the 2026-05-20 mention regression went undetected."""
    # Instagram: the handle, and never one invented for the artist
    # that has no URL stored.
    text = caption_top("top_ppcc", "PPCC", SETMANA, TOP_ENTRIES)
    assert "@rosalia.vt" in text
    assert "Sense Insta" in text and "@Sense Insta" not in text

    assert "@manel.cat" in caption_novetats(
        "nous_albums",
        SETMANA,
        [
            {
                "nom": "Disc",
                "artista_nom": "Manel",
                "artista_instagram_url": "https://www.instagram.com/manel.cat/",
            }
        ],
    )

    # `caption_short` is what `publicar_canal` feeds the other four. One
    # case with a loop, not four cases: the assertion message says which
    # channel failed, which is all the extra cases were buying.
    for canal in ("mastodon", "bluesky", "telegram", "newsletter"):
        curt = caption_short(
            "top_ppcc", "PPCC", SETMANA, TOP_ENTRIES, max_chars=2000, n=5, channel=canal
        )
        assert "@rosalia.vt" not in curt, f"{canal} filtra el handle"
        assert "Rosalía" in curt, f"{canal} no anomena l'artista"


# ── The fallback path ──────────────────────────────────────────────
#
# `compose_for_channel` catches anything the engine raises and returns
# the legacy caption instead. That path is not a curiosity: it is what
# actually ships whenever the engine breaks, and the mention rule has to
# hold there too. The two tests this file replaces covered it **by
# accident** — they had no `django_db` mark, so they tripped Django's
# database guard and landed on the fallback without saying so. Here it
# is deliberate: the engine is made to fail on purpose.


@pytest.fixture
def motor_avariat(monkeypatch):
    def _peta(*a, **k):
        raise RuntimeError("motor avariat a posta")

    monkeypatch.setattr(
        "social.narrative.composers.instagram_feed.compose", _peta, raising=False
    )
    for canal in ("mastodon", "bluesky", "telegram", "newsletter"):
        monkeypatch.setattr(
            f"social.narrative.composers.{canal}.compose", _peta, raising=False
        )


@pytest.mark.django_db
def test_the_rule_holds_when_the_engine_is_down(motor_avariat):
    """Both halves of the rule, on the fallback path."""
    assert "@rosalia.vt" in caption_top("top_ppcc", "PPCC", SETMANA, TOP_ENTRIES)
    for canal in ("mastodon", "bluesky", "telegram", "newsletter"):
        curt = caption_short(
            "top_ppcc", "PPCC", SETMANA, TOP_ENTRIES, max_chars=2000, n=5, channel=canal
        )
        assert "@rosalia.vt" not in curt, f"{canal} filtra el handle en reserva"
        assert "Rosalía" in curt, f"{canal} no anomena l'artista en reserva"
