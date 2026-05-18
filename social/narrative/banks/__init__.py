"""Phrase banks for the narrative engine.

The hero bank is anti-repetition-tracked via
`NarrativePhraseUsage`. CTAs / connectors / top5 / transitions are
ephemeral — many variants, low cost to repeat, no tracking.
"""

from __future__ import annotations


def phrase_id(bank: str, code: str, idx: int, length: str) -> str:
    """Deterministic key used by the anti-repetition registry.

    `bank` is `"hero"` for now — added as the first segment so
    future banks (e.g. story overlays) can opt into tracking
    without colliding with hero pids. Stable across reorderings
    only if `idx` stays put; append new entries at the end."""
    return f"{bank}_{code}_{idx}_{length}"
