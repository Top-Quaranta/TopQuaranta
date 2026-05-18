"""Anti-repetition registry for the narrative engine.

Picks a templated phrase that hasn't been used in the last N weeks
for the same (channel, territori), then interpolates the scenario
data. If every phrase has been used recently, returns from the full
bank instead of refusing to deliver (the post must go out).

`mark_used` records the choice. The composer is expected to call it
after the post actually publishes (not at compose time) so a
dry-run / failed publication doesn't poison future selections —
hooked from `publicar_social.py` in a later PR.
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Optional

from social.narrative.phrases import PHRASES, phrase_id


def filter_unused(
    scenario_code: str,
    length: str,
    territori: str,
    channel: str,
    weeks: int = 4,
) -> list[tuple[int, str]]:
    """Return `(idx, template)` pairs from `PHRASES[scenario_code]`
    whose phrase_id is NOT recorded in `NarrativePhraseUsage` within
    the last `weeks` weeks for `(channel, territori)`. Falls back to
    the full list when every phrase has been used (so the caller
    always has something to print).
    """
    from django.utils import timezone

    from social.models import NarrativePhraseUsage

    bank = PHRASES.get(scenario_code) or []
    all_pairs = [(i, e[length]) for i, e in enumerate(bank)]
    if not all_pairs:
        return []

    cutoff = timezone.localdate() - timedelta(weeks=weeks)
    used_ids = set(
        NarrativePhraseUsage.objects.filter(
            channel=channel,
            territori=territori,
            setmana__gte=cutoff,
        ).values_list("phrase_id", flat=True)
    )
    fresh = [
        (idx, tpl)
        for idx, tpl in all_pairs
        if phrase_id(scenario_code, idx, length) not in used_ids
    ]
    # Falling back to the full list when exhausted is intentional:
    # the post must go out even if the same opener repeats. The
    # operator can extend the bank to keep variety; we don't gate
    # the publication on the registry.
    return fresh or all_pairs


def pick_phrase(
    scenario,
    length: str,
    territori: str,
    channel: str,
    weeks: int = 4,
    rng: Optional[random.Random] = None,
) -> tuple[str, str]:
    """Return `(phrase_id, interpolated_text)` for `scenario` at
    the requested length tier. Picks a fresh template via
    `filter_unused` then `.format`s the scenario data.

    `rng` lets tests force a deterministic choice (`random.Random(0)`).
    In production it defaults to the global `random` module.
    """
    candidates = filter_unused(scenario.code, length, territori, channel, weeks)
    if not candidates:
        # Empty bank for the requested code+length combination — let
        # the composer fall back to its own copy. Sentinel: empty pid.
        return ("", "")
    chooser = rng.choice if rng is not None else random.choice
    idx, template = chooser(candidates)
    text = template.format(**scenario.data)
    return phrase_id(scenario.code, idx, length), text


def mark_used(
    pid: str,
    territori: str,
    setmana,
    channel: str,
) -> None:
    """Record that `pid` was used at this slot. Idempotent enough:
    same row created twice doesn't break anything because no unique
    constraint applies (we want to count repeated emissions of the
    same id should a publish retry happen)."""
    from social.models import NarrativePhraseUsage

    NarrativePhraseUsage.objects.create(
        phrase_id=pid,
        territori=territori,
        setmana=setmana,
        channel=channel,
    )
