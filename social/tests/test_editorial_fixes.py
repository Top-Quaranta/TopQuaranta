"""Editorial fixes (2026-05-31): day-count agreement + top-5 dedup.

Bug 1 — "1 dies": the narrative banks hardcoded `{dies} dies`, so a
day-old debut read "1 dies". `utils.dies_str` now renders the
agreement-correct form and the banks use `{dies_str}`.

Bug 2 — duplicate artist in the "també al top 5" listing: an artist with
2+ songs in the top 5 was named once per song ("Max Navarro, Ouineta i
Max Navarro"). The SHORT register now dedups by artist (first occurrence).

Pure-stdlib (no Django): run in isolation with
    python3 -m pytest social/tests/test_editorial_fixes.py -q -c /dev/null
"""

from __future__ import annotations

import random

import social.narrative.banks.hero as hero_bank
from social.narrative.banks import top5 as top5_bank
from social.narrative.utils import dies_str


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def _hero_templates():
    out: list[str] = []
    for name, val in vars(hero_bank).items():
        if name.startswith("_"):
            continue
        out.extend(_strings(val))
    return out


# ── Bug 1: dies_str ──────────────────────────────────────────────────


def test_dies_str_agreement():
    assert dies_str(1) == "1 dia"
    assert dies_str(2) == "2 dies"
    assert dies_str(0) == "0 dies"  # plural in Catalan
    assert dies_str(7) == "7 dies"
    assert dies_str(30) == "30 dies"


def test_no_hardcoded_dies_plural_in_banks():
    # The `{dies} dies` pattern must be gone — every day count goes
    # through `{dies_str}` now.
    for tpl in _hero_templates():
        assert "{dies} dies" not in tpl, tpl
        assert "{dies}" not in tpl, tpl


def test_hero_templates_say_1_dia_not_1_dies():
    """Rendering every `{dies_str}` hero template with a 1-day-old debut
    must read '1 dia' and never '1 dies'."""
    sample = {
        "artista": "SX3",
        "de_artista": "de SX3",
        "canco": "Tots Som Súpers",
        "posicio": 2,
        "posicio_ordinal": "2n",
        "territori_label": "Global",
        "territori_ordinal": "del top general",
        "dies_str": dies_str(1),
    }
    rendered_any = False
    for tpl in _hero_templates():
        if "{dies_str}" not in tpl:
            continue
        out = tpl.format(**sample)
        rendered_any = True
        assert "1 dia" in out, tpl
        assert "1 dies" not in out, tpl
    assert rendered_any, "no {dies_str} templates found"


def test_hero_templates_plural_with_7_days():
    sample = {
        "artista": "SX3",
        "de_artista": "de SX3",
        "canco": "Tots Som Súpers",
        "posicio": 2,
        "posicio_ordinal": "2n",
        "territori_label": "Global",
        "territori_ordinal": "del top general",
        "dies_str": dies_str(7),
    }
    for tpl in _hero_templates():
        if "{dies_str}" not in tpl:
            continue
        out = tpl.format(**sample)
        assert "7 dies" in out, tpl


# ── Bug 2: top-5 artist dedup ────────────────────────────────────────


def _entry(pos, canco, artista):
    return {"posicio": pos, "canco_nom": canco, "artista_nom": artista}


def test_pick_short_dedups_repeated_artist():
    others = [
        _entry(1, "C1", "Max Navarro"),
        _entry(2, "C2", "Ouineta"),
        _entry(3, "C3", "Max Navarro"),
        _entry(4, "C4", "Rosalia"),
        _entry(5, "C5", "Julieta"),
    ]
    text = top5_bank.pick_short(others, leader=None, rng=random.Random(0))
    # Max Navarro mentioned exactly once.
    assert text.count("Max Navarro") == 1
    # Order by first occurrence, joined "X, Y, Z i W".
    assert "Max Navarro, Ouineta, Rosalia i Julieta" in text


def test_pick_short_with_leader_dedups():
    leader = _entry(1, "Lead", "Lider")
    others = [
        _entry(2, "C2", "Max Navarro"),
        _entry(3, "C3", "Max Navarro"),
        _entry(4, "C4", "Ouineta"),
    ]
    text = top5_bank.pick_short(others, leader=leader, rng=random.Random(0))
    assert text.count("Max Navarro") == 1
    assert "Max Navarro i Ouineta" in text


def test_pick_short_no_duplicates_unchanged():
    others = [
        _entry(2, "C2", "Ouineta"),
        _entry(3, "C3", "Rosalia"),
        _entry(4, "C4", "Julieta"),
    ]
    text = top5_bank.pick_short(others, leader=None, rng=random.Random(0))
    assert "Ouineta, Rosalia i Julieta" in text


def test_pick_long_keeps_distinct_songs_same_artist():
    """The LONG register lists distinct songs; the same artist legitimately
    recurs for different cançons — NOT deduped."""
    others = [
        _entry(2, "Inigualable", "Max Navarro"),
        _entry(3, "Estrelles", "Max Navarro"),
    ]
    text = top5_bank.pick_long(others, leader=None, rng=random.Random(0))
    assert text.count("Max Navarro") == 2
    assert "Inigualable" in text and "Estrelles" in text
