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


def test_story_render_is_deterministic():
    """No grain, no randomness — two renders are byte-identical."""
    a = renderer._story_intro_ppcc(SET).tobytes()
    b = renderer._story_intro_ppcc(SET).tobytes()
    assert a == b
