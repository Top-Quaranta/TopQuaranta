"""Caption text generation: per-channel artist labeling.

Locks in the 2026-05-16 decision: the long Instagram caption uses
`@handle` (autolink + notify), the short caption used by every other
channel (Mastodon, Bluesky, Telegram, Newsletter) falls back to plain
artist name because `@handle` is Instagram-specific and looks broken
on the other networks.
"""

from __future__ import annotations

import datetime
import re

import pytest

from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal
from social.captions import (
    caption_novetats,
    caption_short,
    caption_top,
    compose_for_channel,
)

_NO_POSITIONAL_HASHTAG = re.compile(r"#\d")

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
    setmana = datetime.date(2026, 5, 11)
    text = caption_top("top_ppcc", "PPCC", setmana, entries)
    # Property asserted now (2026-08 rewrite): the caption is produced
    # by the ENGINE path — it differs from the legacy plain-list shape,
    # a hero phrase was actually emitted (compose_for_channel exposes
    # its phrase_ids), and the artist is named. We do not pin any copy
    # token: the phrase pick is random and the bank wording is free to
    # change. Tasca C (2026-05-18): article-stripping lowercases the
    # article in "de + La Fúmiga" → "de la Fúmiga", so accept either.
    from social.captions import _caption_top_legacy

    assert text.strip(), "caption must not be empty"
    assert text != _caption_top_legacy("top_ppcc", "PPCC", setmana, entries)
    assert "La Fúmiga" in text or "la Fúmiga" in text
    result = compose_for_channel("instagram_feed", "top_ppcc", "PPCC", setmana, entries)
    assert result["phrase_ids"], result
    assert result["text"].strip()


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

    # Property asserted now (2026-08 rewrite): the post never goes out
    # empty — the fallback is exactly the legacy caption for the same
    # inputs (derived, not a literal), it lists the entries, and the
    # failure was logged at ERROR with the traceback. No exact log
    # copy, no exact header copy.
    from social.captions import _caption_top_legacy

    assert text.strip(), "fallback caption must not be empty"
    assert text == _caption_top_legacy("top_ppcc", "PPCC", SETMANA, entries)
    assert "X" in text and "Y" in text
    assert any(r.levelno >= logging.ERROR and r.exc_info for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]


# ── Regression guard: 2026-05-20 narrative-engine collapse ──────────
#
# Post-mortem docs/archive/post-mortems/2026-05-20-narrative-engine-collapsed.md.
# Two defects landed silently when compose_for_channel started routing
# top_ppcc/top_territorial through the engine; fixed in #59 (55725dd,
# 2026-05-21) via ADR-0006 (Catalan ordinals, no positional "#N") and
# ADR-0007 (@handle restored on the Instagram-feed path only). These
# tests are the prevention net the post-mortem asked for: they fail if
# either defect is reintroduced.
#
# We exercise more than one hero scenario (A2 streak + A1
# outside-to-top1) so passing counts as real output verification, not
# just a negative grep. The asserts are invariant across the random
# phrase pick: every long-tier hero template names the artist (so the
# rewritten IG @handle always appears on the feed path), and no
# template in any tier emits "#<digit>".


def _mk_canco(nom, slug, artista):
    album = Album.objects.create(
        nom="A", slug=f"{slug}-al", artista=artista, descartat=False
    )
    return Canco.objects.create(
        nom=nom, slug=slug, artista=artista, album=album, verificada=True, activa=True
    )


def _seed_streak_top(territori, weeks):
    """Seed an A2-streak hero (La Fúmiga, #1 every week in `weeks`) and
    return the entries list with the hero carrying an instagram_url."""
    a = Artista.objects.create(nom="La Fúmiga", slug="lf-reg", aprovat=True)
    c = _mk_canco("La Gent de la Mediterrània", "lgm-reg", a)
    for w in weeks:
        TopSetmanal.objects.create(
            canco=c, territori=territori, setmana=w, posicio=1, score_setmanal=99.0
        )
    return [
        {
            "posicio": 1,
            "canco_nom": "La Gent de la Mediterrània",
            "artista_nom": "La Fúmiga",
            "artista_instagram_url": "https://www.instagram.com/lafumiga/",
        }
    ]


def _seed_outside_to_top1(territori, prev_week, this_week):
    """Seed an A1 hero (a song outside the top last week, #1 this week)
    and return entries with the hero carrying an instagram_url."""
    a = Artista.objects.create(nom="Figa Flawas", slug="ff-reg", aprovat=True)
    old = _mk_canco("Vell líder", "vl-reg", a)
    new = _mk_canco("Nou cim", "nc-reg", a)
    TopSetmanal.objects.create(
        canco=old,
        territori=territori,
        setmana=prev_week,
        posicio=1,
        score_setmanal=99.0,
    )
    TopSetmanal.objects.create(
        canco=new,
        territori=territori,
        setmana=this_week,
        posicio=1,
        score_setmanal=99.0,
    )
    return [
        {
            "posicio": 1,
            "canco_nom": "Nou cim",
            "artista_nom": "Figa Flawas",
            "artista_instagram_url": "https://www.instagram.com/figaflawas/",
        }
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "seeder, handle",
    [
        (
            lambda: _seed_streak_top(
                "PPCC",
                [
                    datetime.date(2026, 4, 20),
                    datetime.date(2026, 4, 27),
                    datetime.date(2026, 5, 4),
                    datetime.date(2026, 5, 11),
                ],
            ),
            "@lafumiga",
        ),
        (
            lambda: _seed_outside_to_top1(
                "PPCC", datetime.date(2026, 5, 4), datetime.date(2026, 5, 11)
            ),
            "@figaflawas",
        ),
    ],
    ids=["a2_streak", "a1_outside_to_top1"],
)
def test_no_positional_hashtag_in_any_channel(seeder, handle):
    """ADR-0006: no caption on any channel may contain a positional
    "#<digit>" (those autolink as hashtags on IG/Telegram and leak the
    audience out). Letter-led discovery hashtags (#TopQuaranta) are
    fine, so we match "#" only when directly followed by a digit."""
    entries = seeder()
    for channel in ("instagram_feed", "telegram", "bluesky", "mastodon", "newsletter"):
        res = compose_for_channel(
            channel, "top_ppcc", "PPCC", datetime.date(2026, 5, 11), entries
        )
        text = res["text"]
        assert not _NO_POSITIONAL_HASHTAG.search(
            text
        ), f"positional #N leaked into {channel} caption:\n{text}"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "seeder, handle",
    [
        (
            lambda: _seed_streak_top(
                "PPCC",
                [
                    datetime.date(2026, 4, 20),
                    datetime.date(2026, 4, 27),
                    datetime.date(2026, 5, 4),
                    datetime.date(2026, 5, 11),
                ],
            ),
            "@lafumiga",
        ),
        (
            lambda: _seed_outside_to_top1(
                "PPCC", datetime.date(2026, 5, 4), datetime.date(2026, 5, 11)
            ),
            "@figaflawas",
        ),
    ],
    ids=["a2_streak", "a1_outside_to_top1"],
)
def test_handle_only_on_instagram_feed(seeder, handle):
    """ADR-0007: an artist with a stored instagram_url surfaces as
    `@handle` on the Instagram-feed path (autolink + notify) and must
    NOT carry the literal `@handle` on the short channels, whose mention
    syntax differs (the IG-style `@handle` would render as broken text).

    We assert the @handle presence on IG and its absence on the four
    short channels. We do NOT assert the plain artist name is present on
    the short channels: the short-tier hero templates may reference only
    the song title, and Bluesky's 300-char truncation can drop both the
    top-5 listing and the hero down to a generic sentinel. So the plain
    name is not an invariant of those channels; the @handle contract is."""
    entries = seeder()
    week = datetime.date(2026, 5, 11)

    ig = compose_for_channel("instagram_feed", "top_ppcc", "PPCC", week, entries)[
        "text"
    ]
    assert handle in ig, f"@handle missing from IG feed caption:\n{ig}"

    for channel in ("telegram", "bluesky", "mastodon", "newsletter"):
        text = compose_for_channel(channel, "top_ppcc", "PPCC", week, entries)["text"]
        assert text, f"{channel} caption came back empty"
        assert (
            handle not in text
        ), f"@handle leaked into {channel} caption (should be plain name):\n{text}"
