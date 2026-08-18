"""Narrative engine tests (Fase 4 reset, 2026-05-18).

Covers the eight scenario detectors, the utils, the phrase bank
invariants, the composer channel-budget contracts, the
anti-repetition registry cycle, and the apostrof-de contract for
diverse artist names."""

from __future__ import annotations

import datetime
import random
import re

import pytest

from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal
from social.narrative import scenarios as scen
from social.narrative.banks import phrase_id
from social.narrative.banks.hero import HERO
from social.narrative.composers import bluesky as c_bluesky
from social.narrative.composers import instagram_feed as c_ig_feed
from social.narrative.composers import instagram_story as c_ig_story
from social.narrative.composers import mastodon as c_mastodon
from social.narrative.composers import newsletter as c_newsletter
from social.narrative.composers import telegram as c_telegram
from social.narrative.registry import filter_unused, mark_used, pick_phrase
from social.narrative.utils import apostrof_de, llista_amb_i, territori_label

# ── A. utils ───────────────────────────────────────────────────────


def test_apostrof_de_basic_cases():
    assert apostrof_de("Anna") == "d'Anna"  # vowel
    assert apostrof_de("OBESES") == "d'OBESES"  # vowel caps
    assert apostrof_de("Helena") == "d'Helena"  # h muda
    assert apostrof_de("Manel") == "de Manel"  # consonant
    assert apostrof_de("Lluís Llach") == "de Lluís Llach"  # ll
    assert apostrof_de("Iván") == "de Iván"  # i no elideix
    assert apostrof_de("Úrsula") == "de Úrsula"  # u no elideix
    assert apostrof_de("") == "de "  # safe on empty


def test_llista_amb_i():
    assert llista_amb_i([]) == ""
    assert llista_amb_i(["X"]) == "X"
    assert llista_amb_i(["X", "Y"]) == "X i Y"
    assert llista_amb_i(["X", "Y", "Z"]) == "X, Y i Z"
    assert llista_amb_i(["A", "B", "C", "D"]) == "A, B, C i D"


def test_territori_label():
    # `territori_label` returns the GENITIVE form (2026-05-31 refactor):
    # the `{territori_label}` placeholder follows "Top …"/"al Nè …", so it
    # must carry the preposition + article. PPCC stays "Global" (no prep).
    assert territori_label("PPCC") == "Global"
    assert territori_label("CAT") == "de Catalunya"
    # Unknown/omitted codes now raise (no silent passthrough) so an
    # erroneous call surfaces instead of leaking a raw slug (e.g. "ALT").
    with pytest.raises(KeyError):
        territori_label("UNKNOWN")


# ── B. scenarios ───────────────────────────────────────────────────


def _monday(y, m, d):
    return datetime.date(y, m, d)


def _recent_monday():
    """A Monday inside the registry recency window.

    `registry.filter_unused` keeps usages with `setmana >= today - 4
    weeks`. Registry tests that `mark_used` then assert the phrase is
    filtered MUST use a date inside that window — a fixed past date
    silently falls out of the window as real time advances (the
    2026-06-09 time-bomb where `_monday(2026, 5, 11)` crossed the
    4-week cutoff and the assertion flipped). Relative-to-today keeps
    them robust."""
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _make_canco(nom, artista, album, slug, data_llancament=None):
    return Canco.objects.create(
        nom=nom,
        slug=slug,
        artista=artista,
        album=album,
        verificada=True,
        activa=True,
        data_llancament=data_llancament,
    )


def _seed(canco, territori, setmana, posicio):
    return TopSetmanal.objects.create(
        canco=canco,
        territori=territori,
        setmana=setmana,
        posicio=posicio,
        score_setmanal=float(100 - posicio),
    )


@pytest.mark.django_db
def test_detect_a1_outside_to_top1():
    """Cançó al #1 aquesta setmana que la setmana anterior estava
    fora del top → severity 10."""
    a = Artista.objects.create(nom="X", slug="x", aprovat=True)
    al = Album.objects.create(nom="A", slug="x-a", artista=a, descartat=False)
    c = _make_canco("Nou cim", a, al, "x-c")
    other = _make_canco("Vell cim", a, al, "x-o")
    # Last week: other at #1, c not in top
    _seed(other, "PPCC", _monday(2026, 5, 4), 1)
    # This week: c at #1
    _seed(c, "PPCC", _monday(2026, 5, 11), 1)
    s = scen.detect_a1_outside_to_top1("PPCC", _monday(2026, 5, 11))
    assert s and s.code == "a1_outside_to_top1"
    assert s.severity == 10
    assert s.data["posicio_anterior_str"] == "fora del top"


@pytest.mark.django_db
def test_detect_a2_streak_with_four_weeks():
    a = Artista.objects.create(nom="La Fúmiga", slug="lf", aprovat=True)
    al = Album.objects.create(nom="A", slug="lf-a", artista=a, descartat=False)
    c = _make_canco("Cim", a, al, "lf-c")
    for w in (
        _monday(2026, 4, 20),
        _monday(2026, 4, 27),
        _monday(2026, 5, 4),
        _monday(2026, 5, 11),
    ):
        _seed(c, "PPCC", w, 1)
    s = scen.detect_a2_streak("PPCC", _monday(2026, 5, 11))
    assert s and s.data["streak"] == 4
    # Tasca C (2026-05-18): article-stripping → "de la Fúmiga"
    # (lowercase article post-contraction).
    assert s.data["de_artista"] == "de la Fúmiga"


@pytest.mark.django_db
def test_detect_a3_fall_from_top1():
    a = Artista.objects.create(nom="A", slug="a", aprovat=True)
    al = Album.objects.create(nom="A", slug="a-a", artista=a, descartat=False)
    c = _make_canco("X", a, al, "a-c")
    _seed(c, "PPCC", _monday(2026, 5, 4), 1)  # was #1 last week
    _seed(c, "PPCC", _monday(2026, 5, 11), 5)  # now #5
    s = scen.detect_a3_fall_from_top1("PPCC", _monday(2026, 5, 11))
    assert s and s.severity == 4
    assert "5è" in s.data["posicio_nova_str"]


@pytest.mark.django_db
def test_detect_a4_debut_alt_at_top3():
    a = Artista.objects.create(nom="X", slug="x", aprovat=True)
    al = Album.objects.create(nom="A", slug="x-a", artista=a, descartat=False)
    existing = _make_canco("Vell", a, al, "x-v")
    new = _make_canco("Debut", a, al, "x-d")
    _seed(existing, "PPCC", _monday(2026, 5, 4), 2)
    _seed(new, "PPCC", _monday(2026, 5, 11), 2)
    s = scen.detect_a4_debut_alt("PPCC", _monday(2026, 5, 11))
    assert s and s.data["posicio"] == 2
    assert s.data["canco"] == "Debut"


@pytest.mark.django_db
def test_cold_start_suppresses_freshness_detectors():
    """First ranking week of a territori (no previous week seeded) must
    not fire a1/a4/a9/a10 — with no baseline every entry is trivially
    "new" and every artist trivially "first ever", so the "debut" /
    "fora del top" / "estrena absoluta" framing would be false
    freshness."""
    a = Artista.objects.create(nom="Z", slug="z", aprovat=True)
    al = Album.objects.create(nom="A", slug="z-a", artista=a, descartat=False)
    c1 = _make_canco("Cim", a, al, "z-1")
    c2 = _make_canco("Segon", a, al, "z-2")
    c3 = _make_canco("Sise", a, al, "z-3")
    W = _monday(2026, 4, 13)  # nothing seeded for the week before it
    _seed(c1, "VAL", W, 1)
    _seed(c2, "VAL", W, 2)
    _seed(c3, "VAL", W, 6)
    assert scen.detect_a1_outside_to_top1("VAL", W) is None
    assert scen.detect_a4_debut_alt("VAL", W) is None
    assert scen.detect_a9_debut_anywhere("VAL", W) is None
    assert scen.detect_a10_artista_first_ever("VAL", W) is None
    # Seed a real baseline week with a DIFFERENT artist. Now there is a
    # baseline, so the same fixtures legitimately fire: a4 (c1 jumped in
    # from outside an existing top) and a10 (artist `a` is genuinely
    # first-ever, absent from the baseline week).
    other = Artista.objects.create(nom="Q", slug="q", aprovat=True)
    other_al = Album.objects.create(nom="B", slug="q-b", artista=other)
    _seed(
        _make_canco("Baseline", other, other_al, "q-b"), "VAL", _monday(2026, 4, 6), 1
    )
    s4 = scen.detect_a4_debut_alt("VAL", W)
    assert s4 and s4.code == "a4_debut_alt" and s4.data["posicio"] == 1
    s10 = scen.detect_a10_artista_first_ever("VAL", W)
    assert s10 and s10.code == "a10_artista_first_ever"


def _seed_filler(territori, setmana, start_pos, count):
    """Seed `count` cançons from distinct one-off artists so a focal
    artist's share of the top can be controlled in a5 tests."""
    for j in range(count):
        fa = Artista.objects.create(nom=f"Filler{j}", slug=f"f{j}", aprovat=True)
        fal = Album.objects.create(nom="F", slug=f"f{j}-a", artista=fa)
        fc = _make_canco(f"Fill{j}", fa, fal, f"f{j}-c")
        _seed(fc, territori, setmana, start_pos + j)


@pytest.mark.django_db
def test_detect_a5_artista_multiple_good_week_fires():
    """4 cançons among a 24-row top (share 0.17, n<5) is a good week,
    not domination: a5 fires and celebrates."""
    a = Artista.objects.create(nom="Maria Jaume", slug="mj", aprovat=True)
    al = Album.objects.create(nom="A", slug="mj-a", artista=a, descartat=False)
    setmana = _monday(2026, 5, 11)
    for i in range(4):
        c = _make_canco(f"C{i}", a, al, f"mj-{i}")
        _seed(c, "BAL", setmana, i + 1)
    _seed_filler("BAL", setmana, 5, 20)  # top_size = 24, share = 4/24 ≈ 0.17
    s = scen.detect_a5_artista_multiple("BAL", setmana)
    assert s and s.data["n_cancons"] == 4
    assert s.data["de_artista"] == "de Maria Jaume"


@pytest.mark.django_db
def test_detect_a5_domination_is_suppressed_by_count():
    """5+ cançons from one artist is domination: a5 is suppressed so a
    movement/position scenario can headline instead of celebrating."""
    a = Artista.objects.create(nom="Maria Jaume", slug="mj", aprovat=True)
    al = Album.objects.create(nom="A", slug="mj-a", artista=a, descartat=False)
    setmana = _monday(2026, 5, 11)
    for i in range(6):
        c = _make_canco(f"C{i}", a, al, f"mj-{i}")
        _seed(c, "BAL", setmana, i + 1)
    _seed_filler("BAL", setmana, 7, 30)  # n=6 ≥ 5 → domination regardless of share
    assert scen.detect_a5_artista_multiple("BAL", setmana) is None


@pytest.mark.django_db
def test_detect_a5_domination_is_suppressed_by_share():
    """A small top where one artist holds ≥25 % is also domination,
    even with fewer than 5 cançons."""
    a = Artista.objects.create(nom="Maria Jaume", slug="mj", aprovat=True)
    al = Album.objects.create(nom="A", slug="mj-a", artista=a, descartat=False)
    setmana = _monday(2026, 5, 11)
    for i in range(3):
        c = _make_canco(f"C{i}", a, al, f"mj-{i}")
        _seed(c, "ALT", setmana, i + 1)
    _seed_filler("ALT", setmana, 4, 6)  # top_size 9, share 3/9 ≈ 0.33 ≥ 0.25
    assert scen.detect_a5_artista_multiple("ALT", setmana) is None


@pytest.mark.django_db
def test_detect_a6_canco_recent():
    a = Artista.objects.create(nom="X", slug="x", aprovat=True)
    al = Album.objects.create(nom="A", slug="x-a", artista=a, descartat=False)
    setmana = _monday(2026, 5, 11)
    c = _make_canco(
        "Nova",
        a,
        al,
        "x-c",
        data_llancament=setmana - datetime.timedelta(days=10),
    )
    _seed(c, "PPCC", setmana, 3)
    s = scen.detect_a6_canco_recent("PPCC", setmana)
    assert s and s.data["dies"] == 10 and s.data["posicio"] == 3


@pytest.mark.django_db
def test_detect_a6_suppressed_for_reissue_by_deceased_artist():
    """A reissue whose data_llancament looks recent but whose artist
    died before it (Pau Riba pattern): a6 must NOT fire — the recency is
    the artifact, so it never claims 'just publicada'."""
    a = Artista.objects.create(
        nom="Pau Riba",
        slug="pr",
        aprovat=True,
        mb_end_date=datetime.date(2022, 3, 6),
    )
    al = Album.objects.create(nom="A", slug="pr-a", artista=a, descartat=False)
    setmana = _monday(2026, 5, 18)
    c = _make_canco(
        "Noia de Porcellana",
        a,
        al,
        "pr-c",
        data_llancament=datetime.date(2026, 4, 24),  # reissue date, < 30 d
    )
    _seed(c, "BAL", setmana, 1)
    assert scen.detect_a6_canco_recent("BAL", setmana) is None


@pytest.mark.django_db
def test_detect_a6_suppressed_for_version_marker_title():
    """A 'recent' live/remaster cut is not a genuine new release: a6
    suppressed."""
    a = Artista.objects.create(nom="Y", slug="y", aprovat=True)
    al = Album.objects.create(nom="A", slug="y-a", artista=a, descartat=False)
    setmana = _monday(2026, 5, 11)
    c = _make_canco(
        "Camins (En Directe)",
        a,
        al,
        "y-c",
        data_llancament=setmana - datetime.timedelta(days=5),
    )
    _seed(c, "CAT", setmana, 2)
    assert scen.detect_a6_canco_recent("CAT", setmana) is None


@pytest.mark.django_db
def test_detect_a4_freshness_blocked_for_reissue():
    """a4 still fires for a reissue debut ('debuta al N' is chart-true)
    but flags freshness_blocked so the composer drops the first-week
    touch. A genuine recent debut does not set the flag."""
    a = Artista.objects.create(
        nom="Pau Riba", slug="pr", aprovat=True, mb_end_date=datetime.date(2022, 3, 6)
    )
    al = Album.objects.create(nom="A", slug="pr-a", artista=a, descartat=False)
    other = _make_canco("Vell", a, al, "pr-v")
    new = _make_canco(
        "Noia de Porcellana", a, al, "pr-d", data_llancament=datetime.date(2026, 4, 24)
    )
    _seed(other, "BAL", _monday(2026, 5, 4), 2)
    _seed(new, "BAL", _monday(2026, 5, 11), 1)
    s = scen.detect_a4_debut_alt("BAL", _monday(2026, 5, 11))
    assert s and s.data.get("freshness_blocked") is True

    # Genuine recent debut: flag absent.
    b = Artista.objects.create(nom="SX3", slug="sx3", aprovat=True)
    bal = Album.objects.create(nom="B", slug="sx3-a", artista=b)
    gb = _make_canco(
        "Tots Som Súpers", b, bal, "sx3-d", data_llancament=_monday(2026, 5, 10)
    )
    _seed(_make_canco("Prev", b, bal, "sx3-p"), "CAT", _monday(2026, 5, 4), 2)
    _seed(gb, "CAT", _monday(2026, 5, 11), 1)
    s2 = scen.detect_a4_debut_alt("CAT", _monday(2026, 5, 11))
    assert s2 and "freshness_blocked" not in s2.data


@pytest.mark.django_db
def test_detect_a7_long_runner():
    a = Artista.objects.create(nom="X", slug="x", aprovat=True)
    al = Album.objects.create(nom="A", slug="x-a", artista=a, descartat=False)
    setmana = _monday(2026, 5, 11)
    c = _make_canco(
        "Vella",
        a,
        al,
        "x-c",
        data_llancament=setmana - datetime.timedelta(days=400),
    )
    _seed(c, "PPCC", setmana, 5)
    s = scen.detect_a7_long_runner("PPCC", setmana)
    assert s and s.data["mesos_estrena"] >= 12


@pytest.mark.django_db
def test_detect_a8_pujada_forta():
    a = Artista.objects.create(nom="X", slug="x", aprovat=True)
    al = Album.objects.create(nom="A", slug="x-a", artista=a, descartat=False)
    c = _make_canco("Puja", a, al, "x-c")
    _seed(c, "PPCC", _monday(2026, 5, 4), 25)  # was #25
    _seed(c, "PPCC", _monday(2026, 5, 11), 5)  # now #5 → climb 20
    s = scen.detect_a8_pujada_forta("PPCC", _monday(2026, 5, 11))
    assert s and s.data["pujada"] == 20 and s.data["posicio"] == 5


@pytest.mark.django_db
def test_detect_all_sorts_by_severity():
    a = Artista.objects.create(nom="A", slug="a", aprovat=True)
    al = Album.objects.create(nom="A", slug="a-a", artista=a, descartat=False)
    # Seed a strong A1 (sev=10) AND a 2-week A2 (sev=2)
    streak_c = _make_canco("Streak", a, al, "s-c")
    new_c = _make_canco("New", a, al, "n-c")
    _seed(streak_c, "PPCC", _monday(2026, 5, 4), 5)  # was #5
    _seed(new_c, "PPCC", _monday(2026, 5, 11), 1)  # debuts at #1 → A1 sev=10
    out = scen.detect_all("PPCC", _monday(2026, 5, 11))
    assert out
    assert out[0].code == "a1_outside_to_top1"


@pytest.mark.django_db
def test_detect_a13_top1_return_with_gap_5():
    """top1 W, pos3 W-1, top1 W-5 → a13 fires, severity 8 (gap 5 weeks)."""
    a = Artista.objects.create(nom="R", slug="r", aprovat=True)
    al = Album.objects.create(nom="A", slug="r-a", artista=a, descartat=False)
    c = _make_canco("Divinize", a, al, "r-c")
    other = _make_canco("Vell", a, al, "r-o")
    W = _monday(2026, 5, 18)
    _seed(c, "PPCC", W, 1)  # this week #1
    _seed(c, "PPCC", _monday(2026, 5, 11), 3)  # W-1 at #3 (not #1)
    _seed(other, "PPCC", _monday(2026, 5, 11), 1)  # someone else #1 at W-1
    _seed(c, "PPCC", _monday(2026, 4, 13), 1)  # W-5 was #1
    s = scen.detect_a13_top1_return("PPCC", W)
    assert s and s.code == "a13_top1_return"
    assert s.severity == 8
    assert s.data["gap_setmanes"] == 5
    assert s.data["gap_setmanes_str"] == "5 setmanes"


@pytest.mark.django_db
def test_detect_a13_top1_return_with_gap_2():
    """top1 W, pos2 W-1, top1 W-2 → a13 fires, severity 5 (gap 2 weeks)."""
    a = Artista.objects.create(nom="R", slug="r", aprovat=True)
    al = Album.objects.create(nom="A", slug="r-a", artista=a, descartat=False)
    c = _make_canco("X", a, al, "r-c")
    other = _make_canco("Vell", a, al, "r-o")
    W = _monday(2026, 5, 18)
    _seed(c, "PPCC", W, 1)
    _seed(c, "PPCC", _monday(2026, 5, 11), 2)  # W-1 at #2
    _seed(other, "PPCC", _monday(2026, 5, 11), 1)
    _seed(c, "PPCC", _monday(2026, 5, 4), 1)  # W-2 was #1
    s = scen.detect_a13_top1_return("PPCC", W)
    assert s and s.severity == 5
    assert s.data["gap_setmanes"] == 2


@pytest.mark.django_db
def test_detect_a13_does_not_fire_on_streak():
    """top1 W and top1 W-1 → a13 is NOT a return (a2_streak owns it)."""
    a = Artista.objects.create(nom="R", slug="r", aprovat=True)
    al = Album.objects.create(nom="A", slug="r-a", artista=a, descartat=False)
    c = _make_canco("X", a, al, "r-c")
    W = _monday(2026, 5, 18)
    _seed(c, "PPCC", W, 1)
    _seed(c, "PPCC", _monday(2026, 5, 11), 1)  # #1 last week too
    assert scen.detect_a13_top1_return("PPCC", W) is None
    assert scen.detect_a2_streak("PPCC", W) is not None


@pytest.mark.django_db
def test_detect_a13_does_not_fire_without_prior_top1():
    """top1 W, never #1 before → a13 NO (a1_outside_to_top1 owns it).

    A baseline week is seeded (with a different #1) so a1 can fire for
    the right reason — the song genuinely jumped from outside the top.
    Without that baseline a1 is now suppressed too (cold-start guard)."""
    a = Artista.objects.create(nom="R", slug="r", aprovat=True)
    al = Album.objects.create(nom="A", slug="r-a", artista=a, descartat=False)
    c = _make_canco("X", a, al, "r-c")
    other = _make_canco("Vell", a, al, "r-o")
    W = _monday(2026, 5, 18)
    _seed(other, "PPCC", _monday(2026, 5, 11), 1)  # baseline week, c absent
    _seed(c, "PPCC", W, 1)  # first #1 for c
    assert scen.detect_a13_top1_return("PPCC", W) is None
    assert scen.detect_a1_outside_to_top1("PPCC", W) is not None


@pytest.mark.django_db
def test_detect_a13_subject_ids_present():
    """a13's Scenario.data carries canco_id + artista_id for dedup."""
    a = Artista.objects.create(nom="R", slug="r", aprovat=True)
    al = Album.objects.create(nom="A", slug="r-a", artista=a, descartat=False)
    c = _make_canco("X", a, al, "r-c")
    other = _make_canco("Vell", a, al, "r-o")
    W = _monday(2026, 5, 18)
    _seed(c, "PPCC", W, 1)
    _seed(other, "PPCC", _monday(2026, 5, 11), 1)
    _seed(c, "PPCC", _monday(2026, 5, 4), 1)
    s = scen.detect_a13_top1_return("PPCC", W)
    assert s.data["canco_id"] == c.pk
    assert s.data["artista_id"] == a.pk


@pytest.mark.django_db
def test_fallback_when_no_scenario():
    """Empty top → detect_all returns [] and composer should fall
    back to fallback_no_event."""
    out = scen.detect_all("PPCC", _monday(2026, 5, 11))
    assert out == []
    f = scen.fallback_scenario("PPCC")
    assert f.code == "fallback_no_event"
    assert f.data["territori_label"] == "Global"


# ── C. bank invariants ─────────────────────────────────────────────


def test_hero_has_nine_codes_three_lengths_fifteen_entries_each():
    expected_codes = {
        "a1_outside_to_top1",
        "a2_streak",
        "a3_fall_from_top1",
        "a4_debut_alt",
        "a5_artista_multiple",
        "a6_canco_recent",
        "a7_long_runner",
        "a8_pujada_forta",
        "a9_debut_anywhere",
        "a10_artista_first_ever",
        "a11_top5_drop_generic",
        "a12_artista_emerging",
        "a13_top1_return",
        "fallback_no_event",
    }
    assert set(HERO.keys()) == expected_codes
    for code, by_length in HERO.items():
        for length in ("short", "medium", "long"):
            assert length in by_length, f"{code} missing {length}"
            # The original 12 detectors + fallback ship 15 variants/tier;
            # a13 (2026-06-01) ships 6 (its trigger is rarer). Either way
            # at least 4 so anti-repeat has room.
            minimum = 6 if code == "a13_top1_return" else 15
            assert (
                len(by_length[length]) >= minimum
            ), f"{code}/{length} has {len(by_length[length])} entries"


def test_short_phrases_fit_under_120_chars():
    """`short` tier is for Bluesky / stories. ≤120 chars after
    interpolation with realistic data."""
    sample = {
        "artista": "Maria Jaume",
        "de_artista": "de Maria Jaume",
        "per_a_artista": "per a Maria Jaume",
        "per_artista": "per Maria Jaume",
        "canco": "Sant Domingo Forever",
        "streak": 4,
        "posicio": 3,
        "posicio_ordinal": "3r",
        "posicio_anterior_str": "fora del top",
        "posicio_anterior_de": "de fora del top",
        "posicio_anterior": 3,
        "posicio_anterior_ordinal": "3r",
        "posicio_nova_str": "al 5è",
        "n_cancons": 4,
        "dies": 18,
        "dies_str": "18 dies",
        "mesos_estrena": 8,
        "pujada": 15,
        "gap_setmanes": 5,
        "gap_setmanes_str": "5 setmanes",
        "territori_label": "Global",
        "territori_ordinal": "del top general",
    }
    for code, by_length in HERO.items():
        for i, tpl in enumerate(by_length["short"]):
            try:
                out = tpl.format(**sample)
            except KeyError:
                pytest.fail(f"{code}/short[{i}] missing var: {tpl!r}")
            assert len(out) <= 120, f"{code}/short[{i}] = {len(out)} chars"


def test_phrases_interpolate_with_diverse_artist_names():
    """Templates must produce non-empty output for diverse name
    shapes. Apostrof-de is precomputed via {de_artista} so
    `de Els Catarres` doesn't appear naked anywhere."""
    # Tasca C (2026-05-18): templates now interpolate three
    # pre-rendered preposition variants. We compute them from the
    # canonical helper so the test stays in sync with the rules.
    from social.narrative.utils import with_preposition

    artist_names = [
        "Maria Jaume",
        "Lluís Llach",
        "Manel",
        "OBESES",
        "La Fúmiga",
        "Els Catarres",
        "Anna",
    ]
    artists = [
        (
            nom,
            with_preposition(nom, "de"),
            with_preposition(nom, "per_a"),
            with_preposition(nom, "per"),
        )
        for nom in artist_names
    ]
    base = {
        "canco": "Cançó",
        "streak": 4,
        "posicio": 3,
        "posicio_ordinal": "3r",
        "posicio_anterior_str": "fora del top",
        "posicio_anterior_de": "de fora del top",
        "posicio_anterior": 3,
        "posicio_anterior_ordinal": "3r",
        "posicio_nova_str": "al 5è",
        "n_cancons": 4,
        "dies": 18,
        "dies_str": "18 dies",
        "mesos_estrena": 8,
        "pujada": 15,
        "gap_setmanes": 5,
        "gap_setmanes_str": "5 setmanes",
        "territori_label": "Global",
        "territori_ordinal": "del top general",
    }
    for code, by_length in HERO.items():
        for length in ("short", "medium", "long"):
            for i, tpl in enumerate(by_length[length]):
                for nom, de_nom, per_a_nom, per_nom in artists:
                    out = tpl.format(
                        artista=nom,
                        de_artista=de_nom,
                        per_a_artista=per_a_nom,
                        per_artista=per_nom,
                        **base,
                    )
                    assert out.strip()
                    assert "{" not in out


def test_no_emoji_repeats_more_than_twice_per_bank():
    """Within a single scenario bank (all 3 length tiers combined),
    no emoji appears more than twice per length tier across entries."""
    emoji_re = re.compile(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
    )
    for code, by_length in HERO.items():
        for length, entries in by_length.items():
            counts: dict[str, int] = {}
            for tpl in entries:
                for em in set(emoji_re.findall(tpl)):
                    counts[em] = counts.get(em, 0) + 1
            for em, n in counts.items():
                assert n <= 2, f"{code}/{length}: emoji {em} repeats {n} times"


# ── D. composers ──────────────────────────────────────────────────


def _fake_entries(n=40):
    return [
        {
            "posicio": i + 1,
            "canco_nom": f"Cançó {i + 1}",
            "artista_nom": f"Artista {i + 1}",
            "artista_instagram_url": "",
        }
        for i in range(n)
    ]


def _fake_scenario():
    return scen.Scenario(
        code="a4_debut_alt",
        severity=7,
        data={
            "artista": "OBESES",
            "de_artista": "d'OBESES",
            "canco": "Amor Artificial",
            "posicio": 3,
            "posicio_ordinal": "3r",
            "territori_label": "Global",
            "territori_ordinal": "del top general",
        },
    )


def _full_scenario(code, sev, canco_id, artista_id, canco, artista):
    """A scenario with complete data + distinct subject ids so
    select_slots keeps it and every tier renders."""
    return scen.Scenario(
        code=code,
        severity=sev,
        data={
            "artista": artista,
            "de_artista": f"de {artista}",
            "per_a_artista": f"per a {artista}",
            "per_artista": f"per {artista}",
            "canco": canco,
            "streak": 4,
            "posicio": 3,
            "posicio_ordinal": "3r",
            "posicio_anterior_str": "fora del top",
            "posicio_anterior_de": "de fora del top",
            "posicio_anterior": 3,
            "posicio_anterior_ordinal": "3r",
            "posicio_nova_str": "al 5è",
            "n_cancons": 4,
            "dies": 12,
            "dies_str": "12 dies",
            "mesos_estrena": 8,
            "pujada": 15,
            "gap_setmanes": 5,
            "gap_setmanes_str": "5 setmanes",
            "territori_label": "Global",
            "territori_ordinal": "del top general",
            "canco_id": canco_id,
            "artista_id": artista_id,
        },
    )


def _three_distinct_scenarios():
    return [
        _full_scenario("a6_canco_recent", 9, 101, 11, "Cançó U", "Artista U"),
        _full_scenario("a8_pujada_forta", 7, 102, 12, "Cançó D", "Artista D"),
        _full_scenario("a7_long_runner", 5, 103, 13, "Cançó T", "Artista T"),
    ]


@pytest.mark.django_db
def test_ig_density_floor_upgrades_increase_density(caplog):
    """The density floor is a best-effort target: the composer upgrades
    tiers to get closer to it without ever exceeding 2200 and WITHOUT
    synthesising filler (spec allows sub-density). We verify the
    mechanism — three distinct subjects produce a denser caption than a
    single one, the result fits the ceiling, and a thin caption WARNs."""
    caplog.set_level(30, logger="social.narrative.composers.instagram_feed")  # WARNING
    setmana = _monday(2026, 5, 11)
    three = c_ig_feed.compose(
        _three_distinct_scenarios(),
        _fake_entries(40),
        territori="PPCC",
        setmana=setmana,
        rng=random.Random(0),
    )
    one = c_ig_feed.compose(
        _three_distinct_scenarios()[:1],
        _fake_entries(40),
        territori="PPCC",
        setmana=setmana,
        rng=random.Random(0),
    )
    assert len(three["text"]) <= c_ig_feed.MAX_CHARS
    # More distinct subjects + tier upgrades → a denser caption.
    assert len(three["text"]) > len(one["text"])
    # A genuinely thin (single-slot) caption that stays under the floor
    # must surface a WARN rather than be padded.
    if len(one["text"]) < c_ig_feed.MIN_CHARS:
        assert any("under density floor" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_newsletter_three_paragraphs_with_three_subjects():
    """Newsletter now carries hero + secondary + tertiary (3 paragraphs)
    when the detectors supply 3 distinct subjects."""
    out = c_newsletter.compose(
        _three_distinct_scenarios(),
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=random.Random(0),
    )
    paras = [p for p in out["narrative_part"].split("\n\n") if p.strip()]
    # hero + secondary + tertiary + top5 detail = 4 blocks.
    assert len(paras) >= 3
    assert len(out["phrase_ids"]) == 3


@pytest.mark.django_db
def test_ig_dedup_no_repeated_subject_in_slots():
    """Two scenarios sharing an artist → only one slot for that artist."""
    scs = [
        _full_scenario("a6_canco_recent", 9, 201, 21, "Cançó A", "Mateix"),
        _full_scenario("a8_pujada_forta", 8, 202, 21, "Cançó B", "Mateix"),
        _full_scenario("a7_long_runner", 5, 203, 23, "Cançó C", "Altre"),
    ]
    out = c_ig_feed.compose(
        scs,
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=random.Random(0),
    )
    # 2 distinct artists kept → at most 2 narrative slots.
    assert len(out["phrase_ids"]) <= 2


@pytest.mark.django_db
def test_build_novetats_enriches_flags_and_composes_narrative():
    """nous_albums with 1 known (in-top) artist + 1 brand-new artist:
    build_novetats sets the flags and compose_for_channel produces a
    narrative caption (not the legacy skeleton)."""
    from social import captions, payload

    pub = _monday(2026, 5, 25)
    known = Artista.objects.create(nom="Coneguda", slug="coneguda", aprovat=True)
    nova = Artista.objects.create(nom="Nova", slug="nova", aprovat=True)
    al_k = Album.objects.create(
        nom="Disc Conegut",
        slug="disc-k",
        artista=known,
        descartat=False,
        tipus="album",
        data_llancament=pub - datetime.timedelta(days=2),
    )
    al_n = Album.objects.create(
        nom="Debut",
        slug="debut",
        artista=nova,
        descartat=False,
        tipus="album",
        data_llancament=pub - datetime.timedelta(days=1),
    )
    _make_canco("T1", known, al_k, "t1")
    _make_canco("T2", nova, al_n, "t2")
    # `known` has a recent top appearance; `nova` does not.
    top_canco = _make_canco("Hit", known, al_k, "hit")
    _seed(top_canco, "PPCC", pub, 1)

    data = payload.build_novetats("nous_albums", pub, publish_date=pub)
    assert data and len(data["items"]) == 2
    by_artist = {it["artista_nom"]: it for it in data["items"]}
    assert by_artist["Coneguda"]["artista_en_top"] is True
    assert by_artist["Nova"]["primer_release"] is True

    res = captions.compose_for_channel(
        "instagram_feed", "nous_albums", "", pub, data["items"], rng=random.Random(0)
    )
    txt = res["text"]
    assert txt and "Setmana" not in txt.split("\n")[0]  # not the skeleton header
    assert res["hashtags"] == ["#TopQuaranta", "#MúsicaEnCatalà", "#Novetats"]


@pytest.mark.django_db
def test_composer_mastodon_respects_500_chars():
    out = c_mastodon.compose(
        [_fake_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=random.Random(0),
    )
    assert len(out["text"]) <= 500, out["text"]


@pytest.mark.django_db
def test_bluesky_never_exceeds_300_with_long_artist_names():
    """Stress test (Fase 4 ajust 2): a hero with a real-life-long
    artist name and a streak of 10 weeks must still produce a
    body that fits under Bluesky's 300-char ceiling."""
    hero = scen.Scenario(
        code="a2_streak",
        severity=10,
        data={
            "artista": "Sopa de Cabra En Directe a Cap Roig",
            "de_artista": "de Sopa de Cabra En Directe a Cap Roig",
            "canco": "Camins (En Directe a Cap Roig, Agost 2025)",
            "streak": 10,
            "territori_label": "Global",
            "territori_ordinal": "del top general",
        },
    )
    out = c_bluesky.compose(
        [hero],
        [
            {
                "posicio": 1,
                "canco_nom": "Camins (En Directe a Cap Roig, Agost 2025)",
                "artista_nom": "Sopa de Cabra En Directe a Cap Roig",
            },
            {
                "posicio": 2,
                "canco_nom": "Una Cançó Llarguíssima Per a Estressar el Budget",
                "artista_nom": "Algun Artista Amb Nom Llarg",
            },
        ],
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=random.Random(0),
    )
    assert (
        len(out["text"]) <= 300
    ), f"bluesky body is {len(out['text'])} chars (>300):\n{out['text']}"


@pytest.mark.django_db
def test_composer_telegram_respects_1024_chars():
    out = c_telegram.compose(
        [_fake_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=random.Random(0),
    )
    assert len(out["text"]) <= 1024


@pytest.mark.django_db
def test_composer_instagram_feed_no_bullet_list_at_body():
    """The post BODY is narrative, never a numbered listing. The
    only place where `1. X\n2. Y` is acceptable is the newsletter
    list_part."""
    out = c_ig_feed.compose(
        [_fake_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=random.Random(0),
    )
    text = out["text"]
    # No "1. X\n2. Y" enumerated pair at the start of consecutive lines.
    assert not re.search(r"^\s*1\.\s.+\n\s*2\.\s", text, re.MULTILINE), text


@pytest.mark.django_db
def test_composer_newsletter_separates_narrative_and_list():
    out = c_newsletter.compose(
        [_fake_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=random.Random(0),
    )
    assert out["narrative_part"]
    assert out["list_part"]
    # narrative_part must NOT contain the enumerated listing.
    assert not re.search(r"^\s*1\.\s", out["narrative_part"], re.MULTILINE)
    # list_part must contain all 40 entries.
    assert "40. Cançó 40" in out["list_part"]
    assert "1. Cançó 1" in out["list_part"]


@pytest.mark.django_db
def test_composer_instagram_story_returns_short_overlay():
    out = c_ig_story.compose(
        [_fake_scenario()],
        _fake_entries(40),
        territori="PPCC",
        setmana=_monday(2026, 5, 11),
        rng=random.Random(0),
    )
    assert out["text"]
    assert out["hashtags"] == []
    assert len(out["text"]) <= 160


# ── E. registry cycle ─────────────────────────────────────────────


@pytest.mark.django_db
def test_registry_marks_and_filters():
    setmana = _recent_monday()  # inside the 4-week recency window
    bank_size = len(HERO["a2_streak"]["long"])
    fresh_before = filter_unused("a2_streak", "long", "PPCC", "mastodon")
    assert len(fresh_before) == bank_size

    pid = phrase_id("hero", "a2_streak", 0, "long")
    mark_used(pid, "PPCC", setmana, "mastodon")

    fresh_after = filter_unused("a2_streak", "long", "PPCC", "mastodon")
    used_idxs = {idx for idx, _ in fresh_after}
    assert 0 not in used_idxs
    assert len(fresh_after) == bank_size - 1


@pytest.mark.django_db
def test_registry_isolation_across_channels_and_territoris():
    setmana = _recent_monday()  # inside the 4-week recency window
    pid = phrase_id("hero", "a2_streak", 0, "long")
    mark_used(pid, "PPCC", setmana, "mastodon")
    # Same channel, different territori → unused.
    fresh = filter_unused("a2_streak", "long", "CAT", "mastodon")
    assert 0 in {idx for idx, _ in fresh}
    # Same territori, different channel → unused.
    fresh = filter_unused("a2_streak", "long", "PPCC", "bluesky")
    assert 0 in {idx for idx, _ in fresh}


@pytest.mark.django_db
def test_pick_phrase_is_deterministic_with_rng():
    scenario = scen.Scenario(
        code="a2_streak",
        severity=4,
        data={
            "artista": "La Fúmiga",
            "de_artista": "de La Fúmiga",
            "canco": "Cim",
            "streak": 4,
            "territori_label": "Global",
            "territori_ordinal": "del top general",
        },
    )
    rng = random.Random(42)
    pid, text = pick_phrase(scenario, "long", "PPCC", "mastodon", rng=rng)
    assert pid.startswith("hero_a2_streak_")
    assert "La Fúmiga" in text
    assert "{" not in text


@pytest.mark.django_db
def test_pick_phrase_drops_freshness_variants_when_blocked():
    """When a4 carries freshness_blocked, pick_phrase must never return a
    template with the 'primera setmana' touch, while the bank does carry
    such variants (so the filter is meaningful)."""
    from social.narrative.banks.hero import A4_DEBUT_ALT

    data = {
        "artista": "Pau Riba",
        "de_artista": "de Pau Riba",
        "canco": "Noia de Porcellana",
        "posicio": 1,
        "posicio_ordinal": "1r",
        "territori_label": "de les Illes Balears",
        "territori_ordinal": "de les Illes Balears",
    }
    # Sanity: the short bank really does contain a 'primera setmana' phrase.
    assert any("primera setmana" in t.lower() for t in A4_DEBUT_ALT["short"])

    blocked = scen.Scenario("a4_debut_alt", 9, {**data, "freshness_blocked": True})
    for seed in range(60):
        _, text = pick_phrase(
            blocked, "short", "BAL", "mastodon", rng=random.Random(seed)
        )
        assert "primera setmana" not in text.lower()

    # Without the flag the touch is reachable (not asserting it appears
    # every time, just that the filter is what removes it).
    plain = scen.Scenario("a4_debut_alt", 9, dict(data))
    seen_fresh = any(
        "primera setmana"
        in pick_phrase(plain, "short", "BAL", "mastodon", rng=random.Random(s))[
            1
        ].lower()
        for s in range(60)
    )
    assert seen_fresh


# ── Release-novelty gate: exhaustive anti-regression (PAS 3) ─────────

_GATED_CODES = [
    "a4_debut_alt",
    "a9_debut_anywhere",
    "a10_artista_first_ever",
    "a12_artista_emerging",
]


def test_gated_banks_have_neutral_variant_in_every_tier():
    """Future-proof: every gated detector must keep at least one
    non-release-novelty phrase in EVERY tier. If a future phrase set
    breaks this, the gate would have to suppress the scenario — that is
    the STOP signal, and this test is where it surfaces."""
    from social.narrative.banks.hero import HERO
    from social.narrative.freshness import phrase_asserts_release_novelty

    for code in _GATED_CODES:
        for tier, phrases in HERO[code].items():
            neutral = [p for p in phrases if not phrase_asserts_release_novelty(p)]
            assert neutral, f"{code}/{tier} has no neutral variant"
        # The filter must also be meaningful (the bank carries novelty).
        assert any(
            phrase_asserts_release_novelty(p)
            for phrases in HERO[code].values()
            for p in phrases
        ), f"{code} carries no novelty phrase (gate would be a no-op)"


@pytest.mark.django_db
def test_pick_phrase_blocked_never_yields_release_novelty():
    """For a freshness_blocked scenario, no rng pick of any gated
    detector, in any tier, may return release-novelty lexicon."""
    from social.narrative.freshness import phrase_asserts_release_novelty

    data = {
        "artista": "Pau Riba",
        "de_artista": "de Pau Riba",
        "per_a_artista": "per a Pau Riba",
        "per_artista": "per Pau Riba",
        "canco": "Noia de Porcellana",
        "posicio": 3,
        "posicio_ordinal": "3r",
        "territori_label": "de les Illes Balears",
        "territori_ordinal": "de les Illes Balears",
        "freshness_blocked": True,
    }
    for code in _GATED_CODES:
        sc = scen.Scenario(code, 5, dict(data))
        for tier in ("short", "medium", "long"):
            for seed in range(40):
                _, text = pick_phrase(
                    sc, tier, "BAL", "mastodon", rng=random.Random(seed)
                )
                if not text:
                    continue
                assert not phrase_asserts_release_novelty(
                    text
                ), f"{code}/{tier} seed {seed}: {text}"


@pytest.mark.django_db
def test_detect_a10_reissue_keeps_chart_neutral_phrasing():
    """a10 for a reissue (deceased artist) still fires (first-ever in the
    top is a chart fact) but flags freshness_blocked, so 'estrena
    absoluta' is dropped and a neutral 'primera vegada al top' variant is
    used."""
    a = Artista.objects.create(
        nom="Pau Riba", slug="pr", aprovat=True, mb_end_date=datetime.date(2022, 3, 6)
    )
    al = Album.objects.create(nom="A", slug="pr-a", artista=a, descartat=False)
    # Prior week exists (baseline) so the cold-start guard does not fire,
    # with a different artist so Pau Riba is genuinely first-ever.
    other = Artista.objects.create(nom="Q", slug="q", aprovat=True)
    other_al = Album.objects.create(nom="B", slug="q-b", artista=other)
    _seed(_make_canco("Prev", other, other_al, "q-p"), "BAL", _monday(2026, 5, 11), 1)
    c = _make_canco(
        "Noia de Porcellana", a, al, "pr-c", data_llancament=datetime.date(2026, 4, 24)
    )
    _seed(c, "BAL", _monday(2026, 5, 18), 5)
    s = scen.detect_a10_artista_first_ever("BAL", _monday(2026, 5, 18))
    assert s and s.code == "a10_artista_first_ever"
    assert s.data.get("freshness_blocked") is True


@pytest.mark.django_db
def test_detect_a9_flags_reissue():
    """a9 (debut at 4-40) flags a reissue so its novelty phrasing is
    dropped. (a10/a12's gate is covered by the exhaustive tests above.)"""
    a = Artista.objects.create(
        nom="Pau Riba", slug="pr", aprovat=True, mb_end_date=datetime.date(2022, 3, 6)
    )
    al = Album.objects.create(nom="A", slug="pr-a", artista=a, descartat=False)
    # a9: prior week baseline + a fresh-looking-but-reissue entry at #8.
    _seed(_make_canco("Base", a, al, "pr-b"), "BAL", _monday(2026, 5, 11), 1)
    c = _make_canco(
        "Noia de Porcellana", a, al, "pr-9", data_llancament=datetime.date(2026, 4, 24)
    )
    _seed(c, "BAL", _monday(2026, 5, 18), 8)
    s9 = scen.detect_a9_debut_anywhere("BAL", _monday(2026, 5, 18))
    assert s9 and s9.data.get("freshness_blocked") is True
