"""Pixel-measured fidelity pins for the editorial story slides.

Like the feed pins (`test_feed_redesign.py`), these MEASURE ink in a render and
assert against known milestones — no oracle images, only numbers well above the
noise floor. They guard the `render_core` engine refactor (2026-06): the stories
now compose over the shared primitives, and these pins catch any drift in the
ink-top text anchoring or the radial field. Deterministic (stories use no grain).
"""

from __future__ import annotations

import datetime

import numpy as np

from social import renderer

SET = datetime.date(2026, 6, 8)
TOL = 6


def _channels(img):
    a = np.asarray(img.convert("RGB"), np.int16)
    return a[:, :, 0], a[:, :, 1], a[:, :, 2]


def test_intro_text_ink_anchored_and_green_field():
    """The intro's big yellow '40' (drawn ink-top at the token y=632) and the
    white 'EL TOP' (y=560) must land at their measured ink-tops, on a
    green radial field. Guards the story ink-top text primitive."""
    img = renderer._story_intro_ppcc(SET)
    assert img.size == (renderer.STORY_W, renderer.STORY_H)
    R, G, B = _channels(img)
    sl = slice(300, 780)  # central x band (the headline stack)

    yellow = ((R[:, sl] > 190) & (G[:, sl] > 140) & (B[:, sl] < 110)).sum(1)
    white = ((R[:, sl] > 230) & (G[:, sl] > 230) & (B[:, sl] > 230)).sum(1)
    y_top = next(r for r in range(400, 1000) if yellow[r] > 80)
    w_top = next(r for r in range(400, 1000) if white[r] > 40)

    assert abs(y_top - 635) <= TOL, f"yellow '40' ink-top drifted: {y_top}"
    assert abs(w_top - 561) <= TOL, f"white 'EL TOP' ink-top drifted: {w_top}"

    # The radial field is green (accent at top-centre, darker deep at the edge).
    tc = [int(x) for x in np.asarray(img.convert("RGB"))[2, 540]]
    corner = [int(x) for x in np.asarray(img.convert("RGB"))[2, 2]]
    assert tc[1] > tc[0] and tc[1] > tc[2], f"top-centre not green: {tc}"
    assert corner[1] < tc[1], f"edge should be darker than centre: {corner} vs {tc}"


def test_outro_is_yellow_dominant():
    """The outro stays a yellow field (a measured-majority pin, engine-safe)."""
    img = renderer._story_outro_ppcc(SET)
    R, G, B = _channels(img)
    yellow = ((R > 190) & (G > 140) & (B < 110)).sum()
    assert yellow > R.size * 0.5, f"outro should be yellow-dominant: {yellow}"


def test_story_render_is_deterministic():
    """No grain, no randomness — two renders are byte-identical."""
    a = renderer._story_intro_ppcc(SET).tobytes()
    b = renderer._story_intro_ppcc(SET).tobytes()
    assert a == b
