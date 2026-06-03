"""PR α: cross-slot subject dedup + a13 bank + novetats hashtags.

Pure-stdlib (no Django). Run in isolation with
    python3 -m pytest social/tests/test_narrative_alpha.py -q -c /dev/null
"""

from __future__ import annotations

from social.captions import HASHTAGS_NOVETATS
from social.narrative.banks.hashtags import TERRITORY_HASHTAGS
from social.narrative.banks.hero import HERO
from social.narrative.scenarios import Scenario, _scenario_subject, select_slots
from social.narrative.utils import territori_label, territori_ordinal


def _S(code, sev, cid, aid):
    return Scenario(code, sev, {"canco_id": cid, "artista_id": aid})


# ── select_slots / _scenario_subject ─────────────────────────────────


def test_scenario_subject_tuple():
    assert _scenario_subject(_S("a6", 6, 100, 1)) == (100, 1)
    assert _scenario_subject(_S("a5", 5, None, 1)) == (None, 1)
    assert _scenario_subject(Scenario("fallback_no_event", 0, {})) == (None, None)


def test_select_slots_drops_same_song():
    # [0] and [1] share canco_id 100 → [1] dropped; [2] and [3] distinct.
    scs = [
        _S("a10", 8, 100, 1),
        _S("a6", 6, 100, 1),
        _S("a1", 5, 200, 2),
        _S("a4", 4, 300, 3),
    ]
    assert [s.code for s in select_slots(scs, 3)] == ["a10", "a1", "a4"]


def test_select_slots_drops_same_artist():
    # a5 (artist 1, no song) conflicts with a10 (artist 1) → dropped.
    scs = [
        _S("a10", 8, 100, 1),
        _S("a6", 6, 100, 1),
        _S("a5", 5, None, 1),
        _S("a1", 4, 200, 2),
    ]
    assert [s.code for s in select_slots(scs, 3)] == ["a10", "a1"]


def test_select_slots_only_two_distinct_no_forced_tertiary():
    # 4 scenarios but only 2 distinct subjects → caption ends at 2 slots.
    scs = [
        _S("a10", 8, 100, 1),
        _S("a6", 6, 100, 1),
        _S("a8", 5, 200, 2),
        _S("a9", 4, 200, 2),
    ]
    assert len(select_slots(scs, 3)) == 2


def test_select_slots_degenerate_single_subject():
    scs = [_S("a10", 8, 100, 1), _S("a6", 6, 100, 1)]
    assert [s.code for s in select_slots(scs, 3)] == ["a10"]


def test_select_slots_empty():
    assert select_slots([], 3) == []


def test_select_slots_none_ids_never_conflict():
    # Two generic scenarios (both None,None) must NOT dedup each other.
    scs = [
        Scenario("fallback_no_event", 0, {}),
        Scenario("fallback_no_event", 0, {}),
    ]
    assert len(select_slots(scs, 2)) == 2


# ── novetats hashtags TitleCase ──────────────────────────────────────


def test_novetats_hashtags_titlecase():
    assert HASHTAGS_NOVETATS == ["#TopQuaranta", "#MúsicaEnCatalà", "#Novetats"]
    # Consistent with the tops' bank: same #TopQuaranta token, TitleCase.
    assert "#TopQuaranta" in TERRITORY_HASHTAGS["PPCC"]
    for t in HASHTAGS_NOVETATS:
        assert t[1].isupper(), t  # first letter after '#' is uppercase
        assert " " not in t


# ── a13 bank renders without KeyError ────────────────────────────────


def test_a13_bank_registered_and_renders():
    assert "a13_top1_return" in HERO
    data = {
        "artista": "Rosalía",
        "de_artista": "de Rosalía",
        "per_a_artista": "per a Rosalía",
        "per_artista": "per Rosalía",
        "canco": "Divinize",
        "gap_setmanes": 5,
        "gap_setmanes_str": "5 setmanes",
    }
    bad = (
        " de de ",
        " a de ",
        " del de ",
        " de del ",
        " a del ",
        " al del ",
        " al de ",
    )
    for terr in ("PPCC", "CAT", "VAL", "BAL"):
        d = {
            **data,
            "territori_label": territori_label(terr),
            "territori_ordinal": territori_ordinal(terr),
        }
        for tier in ("short", "medium", "long"):
            for tpl in HERO["a13_top1_return"][tier]:
                out = tpl.format(**d)  # must not KeyError
                low = f" {out.lower()} "
                for b in bad:
                    assert b not in low, f"double prep in {tpl!r}"


def test_a13_short_tier_under_120():
    data = {
        "artista": "Maria Jaume",
        "de_artista": "de Maria Jaume",
        "canco": "Sant Domingo Forever",
        "gap_setmanes": 5,
        "gap_setmanes_str": "5 setmanes",
        "territori_label": "Global",
        "territori_ordinal": "del top general",
    }
    for tpl in HERO["a13_top1_return"]["short"]:
        assert len(tpl.format(**data)) <= 120, tpl
