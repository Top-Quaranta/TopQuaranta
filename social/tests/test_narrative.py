"""Narrative engine tests (Fase 4 PR 1, 2026-05-18).

Covers the three detectors, phrase-bank invariants, composer
channel-budget contracts and the anti-repetition registry cycle.
"""

from __future__ import annotations

import datetime
import random

import pytest

from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal
from social.models import NarrativePhraseUsage
from social.narrative import scenarios as scen
from social.narrative.composers import bluesky as c_bluesky
from social.narrative.composers import instagram_feed as c_ig_feed
from social.narrative.composers import instagram_story as c_ig_story
from social.narrative.composers import mastodon as c_mastodon
from social.narrative.composers import newsletter as c_newsletter
from social.narrative.composers import telegram as c_telegram
from social.narrative.phrases import PHRASES, TERRITORY_HASHTAGS, phrase_id
from social.narrative.registry import filter_unused, mark_used, pick_phrase

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def territory():
    return "PPCC"


def _monday(year, month, day):
    return datetime.date(year, month, day)


def _make_canco(nom, artista, album, slug_suffix):
    return Canco.objects.create(
        nom=nom,
        slug=f"c-{slug_suffix}",
        artista=artista,
        album=album,
        verificada=True,
        activa=True,
    )


def _seed_top_row(canco, territori, setmana, posicio):
    return TopSetmanal.objects.create(
        canco=canco,
        territori=territori,
        setmana=setmana,
        posicio=posicio,
        score_setmanal=float(100 - posicio),
    )


# ── A. Scenarios ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_detect_a2_streak_with_four_weeks(territory):
    """La Fúmiga case: same canco at #1 four consecutive weeks."""
    a = Artista.objects.create(nom="La Fúmiga", slug="la-fumiga", aprovat=True)
    al = Album.objects.create(nom="A", slug="a", artista=a, descartat=False)
    c = _make_canco("La Gent de la Mediterrània", a, al, "lgm")
    weeks = [
        _monday(2026, 4, 20),
        _monday(2026, 4, 27),
        _monday(2026, 5, 4),
        _monday(2026, 5, 11),
    ]
    for w in weeks:
        _seed_top_row(c, territory, w, 1)

    s = scen.detect_a2_streak(territory, weeks[-1])
    assert s is not None
    assert s.code == "a2_streak"
    assert s.severity == 4
    assert s.data["streak"] == 4
    assert s.data["artista"] == "La Fúmiga"
    assert s.data["canco"] == "La Gent de la Mediterrània"
    assert s.data["territori_label"] == "Global"


@pytest.mark.django_db
def test_detect_a2_streak_returns_none_for_single_week(territory):
    """A streak of length 1 is just "new at #1", not a streak."""
    a = Artista.objects.create(nom="One Week", slug="ow", aprovat=True)
    al = Album.objects.create(nom="A", slug="ow-a", artista=a, descartat=False)
    c = _make_canco("Just Now", a, al, "ow-c")
    _seed_top_row(c, territory, _monday(2026, 5, 11), 1)
    assert scen.detect_a2_streak(territory, _monday(2026, 5, 11)) is None


@pytest.mark.django_db
def test_detect_a4_debut_alt_at_position_two(territory):
    """A canco absent last week, debuting at #2 this week."""
    a = Artista.objects.create(nom="Suc i Sopes", slug="ss", aprovat=True)
    al = Album.objects.create(nom="A", slug="ss-a", artista=a, descartat=False)
    debut_c = _make_canco("Alba", a, al, "ss-alba")
    last_week_c = _make_canco("Algun Èxit", a, al, "ss-other")

    last = _monday(2026, 4, 13)
    this = _monday(2026, 4, 20)
    # Last week had `last_week_c` at #2 (so absence of `debut_c` is real).
    _seed_top_row(last_week_c, territory, last, 2)
    # This week: debut_c at #2, last_week_c still at #5 (irrelevant).
    _seed_top_row(debut_c, territory, this, 2)
    _seed_top_row(last_week_c, territory, this, 5)

    s = scen.detect_a4_debut_alt(territory, this)
    assert s is not None
    assert s.code == "a4_debut_alt"
    assert s.severity == 8  # 10 - 2
    assert s.data["posicio"] == 2
    assert s.data["canco"] == "Alba"


@pytest.mark.django_db
def test_detect_a5_artista_multiple_with_five_cancons():
    """Maria Jaume BAL case (scaled down to 5)."""
    a = Artista.objects.create(nom="Maria Jaume", slug="mj", aprovat=True)
    al = Album.objects.create(nom="A", slug="mj-a", artista=a, descartat=False)
    other = Artista.objects.create(nom="Una Altra", slug="ua", aprovat=True)
    other_al = Album.objects.create(
        nom="B", slug="ua-b", artista=other, descartat=False
    )
    setmana = _monday(2026, 5, 11)

    for i in range(5):
        c = _make_canco(f"Cançó {i}", a, al, f"mj-{i}")
        _seed_top_row(c, "BAL", setmana, i + 1)
    # noise from another artist — must not be counted.
    other_c = _make_canco("D'altres", other, other_al, "ua-c")
    _seed_top_row(other_c, "BAL", setmana, 6)

    s = scen.detect_a5_artista_multiple("BAL", setmana)
    assert s is not None
    assert s.code == "a5_artista_multiple"
    assert s.severity == 5
    assert s.data["n_cancons"] == 5
    assert s.data["artista"] == "Maria Jaume"
    assert s.data["posicions"] == [1, 2, 3, 4, 5]


@pytest.mark.django_db
def test_detect_all_sorts_by_severity_desc(territory):
    """detect_all returns scenarios ordered by severity desc — a 4-
    week streak (sev=4) ranks below a #1 debut (sev=9) and below a
    5-track artist (sev=5)."""
    a = Artista.objects.create(nom="X", slug="x", aprovat=True)
    al = Album.objects.create(nom="A", slug="x-a", artista=a, descartat=False)
    debut = _make_canco("New", a, al, "x-new")
    streak_c = _make_canco("Streak", a, al, "x-streak")

    setmana = _monday(2026, 5, 11)
    # Streak (sev=2). Need at least 2 weeks of same #1; pin a
    # different canco at #1 last week so a2_streak doesn't fire.
    # We'll seed an alternative #1 for both weeks to force A2.
    streak_artist = Artista.objects.create(nom="Streak Band", slug="sb", aprovat=True)
    streak_al = Album.objects.create(
        nom="B", slug="sb-b", artista=streak_artist, descartat=False
    )
    streak_real = _make_canco("Persistent", streak_artist, streak_al, "sb-p")
    _seed_top_row(streak_real, territory, _monday(2026, 5, 4), 1)
    _seed_top_row(streak_real, territory, setmana, 1)
    # Debut at #2 — last week's row required for "absent" check.
    # We only put streak_real at last week's top, so `debut` is
    # absent → A4 fires at #2 → sev=8.
    _seed_top_row(debut, territory, setmana, 2)

    out = scen.detect_all(territory, setmana)
    codes = [s.code for s in out]
    assert "a4_debut_alt" in codes
    assert "a2_streak" in codes
    # A4 debut at #2 has sev=8; A2 streak of 2 has sev=2.
    assert out[0].code == "a4_debut_alt"


# ── B. Phrases ────────────────────────────────────────────────────


def test_phrases_have_three_lengths():
    """Every phrase entry has short, medium, long."""
    for code, bank in PHRASES.items():
        assert len(bank) == 15, f"{code} bank has {len(bank)} entries, expected 15"
        for i, entry in enumerate(bank):
            for length in ("short", "medium", "long"):
                assert length in entry, f"{code}[{i}] missing {length}"
                assert entry[length], f"{code}[{i}] {length} is empty"


def test_phrases_short_under_80_chars():
    """`short` is for Bluesky (300-char budget with rows + link).
    Each opener fits comfortably under 80 chars BEFORE interpolation
    — interpolation can grow it slightly, but composer enforces the
    hard 300 limit downstream."""
    for code, bank in PHRASES.items():
        for i, entry in enumerate(bank):
            assert (
                len(entry["short"]) <= 80
            ), f"{code}[{i}].short is {len(entry['short'])} chars"


def test_phrases_interpolate_without_keyerror():
    """Every phrase must accept the canonical scenario.data shape
    for its code without raising KeyError on .format()."""
    fake_data_by_code = {
        "a2_streak": {
            "artista": "Artist",
            "canco": "Song",
            "streak": 4,
            "territori_label": "Global",
        },
        "a4_debut_alt": {
            "artista": "Artist",
            "canco": "Song",
            "posicio": 2,
            "territori_label": "Catalunya",
        },
        "a5_artista_multiple": {
            "artista": "Artist",
            "n_cancons": 5,
            "territori_label": "Illes Balears",
            "posicions": [1, 2, 3, 4, 5],
        },
    }
    for code, bank in PHRASES.items():
        data = fake_data_by_code[code]
        for i, entry in enumerate(bank):
            for length in ("short", "medium", "long"):
                try:
                    entry[length].format(**data)
                except KeyError as exc:
                    raise AssertionError(
                        f"{code}[{i}].{length} references unknown var: {exc}"
                    )


def test_phrases_interpolate_with_diverse_artist_names():
    """Grammatical-neutrality contract (Fase 4 PR 1.5):
    every template must produce a clean, non-empty string for a
    representative set of artist-name shapes — singular feminine,
    singular masculine, singular-conventional band, plural-marked
    band, articled band. We can't test grammar mechanically, but
    we can guarantee that interpolation never leaves dangling
    placeholders or empties for any of these shapes."""
    artist_names = [
        "Maria Jaume",  # singular feminine person
        "Lluís Llach",  # singular masculine person
        "Manel",  # singular-conventional band name
        "Els Catarres",  # plural-marked band
        "La Fúmiga",  # articled feminine band
    ]
    fake_data_by_code = {
        "a2_streak": {"canco": "Cançó", "streak": 4, "territori_label": "Global"},
        "a4_debut_alt": {
            "canco": "Cançó",
            "posicio": 2,
            "territori_label": "Catalunya",
        },
        "a5_artista_multiple": {
            "n_cancons": 5,
            "territori_label": "Illes Balears",
            "posicions": [1, 2, 3, 4, 5],
        },
    }
    for code, bank in PHRASES.items():
        base = fake_data_by_code[code]
        for i, entry in enumerate(bank):
            for length in ("short", "medium", "long"):
                for name in artist_names:
                    out = entry[length].format(artista=name, **base)
                    assert out.strip(), f"{code}[{i}].{length} empty for {name}"
                    assert (
                        "{" not in out
                    ), f"{code}[{i}].{length} has unfilled var for {name}"
                    # No accidental apostrophe-elision of `de`.
                    assert (
                        "d'" + name not in out
                    ), f"{code}[{i}].{length} elided `de` before {name}"


def test_territory_hashtags_exposed():
    """The composers rely on TERRITORY_HASHTAGS having entries for
    the four populated territoris."""
    for code in ("PPCC", "CAT", "VAL", "BAL"):
        assert code in TERRITORY_HASHTAGS
        assert "#TopQuaranta" in TERRITORY_HASHTAGS[code]


# ── C. Composers — channel budgets ────────────────────────────────


def _fake_entries(n=40):
    return [
        {
            "posicio": i + 1,
            "canco_nom": f"Cançó número {i + 1}",
            "artista_nom": f"Artista {i + 1}",
            "artista_instagram_url": (
                f"https://www.instagram.com/artista{i + 1}/" if i % 2 == 0 else ""
            ),
        }
        for i in range(n)
    ]


def _hero_scenario():
    return scen.Scenario(
        code="a2_streak",
        severity=4,
        data={
            "artista": "La Fúmiga",
            "canco": "La Gent de la Mediterrània",
            "streak": 4,
            "territori_label": "Global",
        },
    )


@pytest.mark.django_db
def test_composer_bluesky_respects_300_chars():
    rng = random.Random(0)
    out = c_bluesky.compose(
        [_hero_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=rng,
    )
    assert len(out["text"]) <= 300, out["text"]
    assert out["text"], "empty bluesky output"


@pytest.mark.django_db
def test_composer_mastodon_respects_500_chars():
    rng = random.Random(0)
    out = c_mastodon.compose(
        [_hero_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=rng,
    )
    assert len(out["text"]) <= 500, out["text"]


@pytest.mark.django_db
def test_composer_telegram_respects_1024_chars():
    rng = random.Random(0)
    out = c_telegram.compose(
        [_hero_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=rng,
    )
    assert len(out["text"]) <= 1024


@pytest.mark.django_db
def test_composer_instagram_feed_uses_handles():
    rng = random.Random(0)
    out = c_ig_feed.compose(
        [_hero_scenario()],
        _fake_entries(5),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=rng,
    )
    # Entries with instagram_url get an `@handle` mention; entries
    # without fall back to the plain name. At least one mention
    # must be present.
    assert "@artista1" in out["text"]


@pytest.mark.django_db
def test_composer_mastodon_uses_plain_names():
    rng = random.Random(0)
    out = c_mastodon.compose(
        [_hero_scenario()],
        _fake_entries(5),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=rng,
    )
    # Mastodon must NOT carry `@artistaN` Instagram-style mentions
    # in the row list; the plain name "Artista N" is what we want.
    assert "Artista 1" in out["text"]
    assert "@artista1" not in out["text"]


@pytest.mark.django_db
def test_composer_newsletter_has_full_top():
    rng = random.Random(0)
    entries = _fake_entries(40)
    out = c_newsletter.compose(
        [_hero_scenario()],
        entries,
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=rng,
    )
    # Newsletter has no hard cap and we want every row visible.
    assert "Cançó número 40" in out["text"]


@pytest.mark.django_db
def test_composer_instagram_story_returns_short_overlay():
    rng = random.Random(0)
    out = c_ig_story.compose(
        [_hero_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=rng,
    )
    assert out["text"], "empty story overlay"
    assert out["hashtags"] == []
    # The short phrase tier caps at 80 chars before interpolation.
    assert len(out["text"]) <= 160  # generous after interpolation


# ── D. Registry cycle ─────────────────────────────────────────────


@pytest.mark.django_db
def test_registry_marks_and_filters():
    """Marking a phrase as used removes it from the unused pool for
    the same (channel, territori) within the lookback window."""
    setmana = _monday(2026, 5, 11)
    bank_size = len(PHRASES["a2_streak"])
    fresh_before = filter_unused("a2_streak", "long", "PPCC", "mastodon")
    assert len(fresh_before) == bank_size

    # Use phrase #0 of the long tier.
    pid = phrase_id("a2_streak", 0, "long")
    mark_used(pid, "PPCC", setmana, "mastodon")

    fresh_after = filter_unused("a2_streak", "long", "PPCC", "mastodon")
    used_idxs = {idx for idx, _ in fresh_after}
    assert 0 not in used_idxs
    assert len(fresh_after) == bank_size - 1


@pytest.mark.django_db
def test_registry_isolation_across_channels_and_territoris():
    """A phrase used on Mastodon PPCC must still be available on
    Mastodon CAT and on Bluesky PPCC."""
    setmana = _monday(2026, 5, 11)
    pid = phrase_id("a2_streak", 0, "long")
    mark_used(pid, "PPCC", setmana, "mastodon")

    # Same channel, different territori → unused.
    cat_fresh = filter_unused("a2_streak", "long", "CAT", "mastodon")
    assert 0 in {idx for idx, _ in cat_fresh}
    # Same territori, different channel → unused.
    bsky_fresh = filter_unused("a2_streak", "long", "PPCC", "bluesky")
    assert 0 in {idx for idx, _ in bsky_fresh}


@pytest.mark.django_db
def test_registry_returns_all_when_exhausted():
    """When every phrase has been used in the window, the filter
    returns the full bank (the post must go out)."""
    setmana = _monday(2026, 5, 11)
    bank_size = len(PHRASES["a2_streak"])
    for i in range(bank_size):
        mark_used(phrase_id("a2_streak", i, "long"), "PPCC", setmana, "mastodon")
    fresh = filter_unused("a2_streak", "long", "PPCC", "mastodon")
    assert len(fresh) == bank_size, "should fall back to full bank"


@pytest.mark.django_db
def test_pick_phrase_is_deterministic_with_rng():
    """Tests pin a Random(seed) so output is reproducible."""
    rng = random.Random(42)
    pid, text = pick_phrase(_hero_scenario(), "long", "PPCC", "mastodon", rng=rng)
    assert pid.startswith("a2_streak_")
    assert "La Fúmiga" in text
    assert "{" not in text  # template fully interpolated


@pytest.mark.django_db
def test_pick_phrase_returns_empty_on_unknown_code():
    """Unknown scenario code → empty sentinel so composer can fall
    back without raising."""
    s = scen.Scenario(code="does_not_exist", severity=1, data={})
    pid, text = pick_phrase(s, "long", "PPCC", "mastodon", rng=random.Random(0))
    assert pid == ""
    assert text == ""
