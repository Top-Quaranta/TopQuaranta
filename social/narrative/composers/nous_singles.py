"""Thin entry point for the `nous_singles` novetats roundup.

All logic lives in `composers/novetats.py`; this wrapper just pins the
tipus so `captions.compose_for_channel` can route uniformly."""

from __future__ import annotations

from social.narrative.composers import novetats as _novetats

TIPUS = "nous_singles"


def compose(channel: str, items, *, setmana, rng=None) -> dict:
    return _novetats.compose(channel, TIPUS, items, setmana=setmana, rng=rng)
