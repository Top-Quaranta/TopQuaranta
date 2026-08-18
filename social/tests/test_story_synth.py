"""#1 story-hero headline synthesis (Step 3a). Pure-stdlib.

python3 -m pytest social/tests/test_story_synth.py -q -c /dev/null
"""

from __future__ import annotations

import random

import pytest

from social.narrative.story_synth import _STORY_HERO, synthesize_hero


class _Scn:
    def __init__(self, code, data):
        self.code = code
        self.data = data


@pytest.mark.parametrize("code", list(_STORY_HERO))
def test_every_code_synthesises(code):
    s = _Scn(code, {"streak": 5, "gap_setmanes_str": "5 setmanes"})
    out = synthesize_hero(s, random.Random(0))
    assert out and out == out.upper()  # uppercased
    assert len(out) <= 50
    assert "{" not in out  # no unresolved placeholder


def test_a2_streak_uses_data():
    # Force the streak-numbered template.
    s = _Scn("a2_streak", {"streak": 5})
    seen = {synthesize_hero(s, random.Random(i)) for i in range(20)}
    # Property: the streak count reaches the headline in at least one
    # variant (the exact template copy is not pinned).
    assert any("5" in x for x in seen), seen
    assert all("{" not in x for x in seen)


def test_a13_can_mention_gap():
    s = _Scn("a13_top1_return", {"gap_setmanes_str": "5 setmanes"})
    seen = {synthesize_hero(s, random.Random(i)) for i in range(20)}
    # Property: the gap value reaches the headline in at least one
    # variant (the exact "TORNA … DESPRÉS DE" copy is not pinned).
    assert any("5 SETMANES" in x for x in seen), seen
    assert all("{" not in x for x in seen)


def test_unknown_code_falls_back():
    out = synthesize_hero(_Scn("zzz_unknown", {}), random.Random(0))
    assert out in [t.upper() for t in _STORY_HERO["fallback_no_event"]]


def test_missing_placeholder_falls_back():
    # a2 template needs {streak}; absent → fallback, no crash.
    out = synthesize_hero(_Scn("a2_streak", {}), random.Random(0))
    assert out == out.upper() and "{" not in out
