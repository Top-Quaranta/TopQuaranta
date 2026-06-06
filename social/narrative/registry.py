"""Anti-repetition registry for the narrative engine — hero bank.

Picks a hero template that hasn't been used in the last N weeks
for the same (channel, territori), then interpolates the scenario
data. If every template has been used recently, returns from the
full bank instead of refusing to deliver (the post must go out).

`mark_used` records the choice. The composer is expected to call
it after the post actually publishes (not at compose time) so a
dry-run / failed publication doesn't poison future selections.
Hooked from `publicar_social.py` / `publicar_canal.py`.

Only the **hero** bank is tracked. CTAs / connectors / top5 /
transitions are ephemeral and don't benefit from anti-repetition:
they're short, there are many variants, and the cost of an
occasional collision is nil."""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Optional

from social.narrative.banks import phrase_id
from social.narrative.banks.hero import HERO
from social.narrative.utils import dies_str, territori_label, territori_ordinal

# Substrings that mark a release-freshness assertion in a hero template.
# Used to drop the freshness touch from a scenario whose song is not a
# verified recent release (see `pick_phrase`'s `freshness_blocked` path).
# These are the only release-freshness phrasings the mixed scenarios
# (a4) carry; the pure-freshness scenario a6 is suppressed at the
# detector instead, so it never reaches this filter.
_FRESHNESS_MARKERS = ("primera setmana",)


def _asserts_freshness(template: str) -> bool:
    low = template.lower()
    return any(marker in low for marker in _FRESHNESS_MARKERS)


def filter_unused(
    scenario_code: str,
    length: str,
    territori: str,
    channel: str,
    weeks: int = 4,
) -> list[tuple[int, str]]:
    """Return `(idx, template)` pairs from `HERO[scenario_code][length]`
    whose phrase_id is NOT recorded in `NarrativePhraseUsage` within
    the last `weeks` weeks for `(channel, territori)`. Falls back to
    the full list when every template has been used (so the caller
    always has something to print)."""
    from django.utils import timezone

    from social.models import NarrativePhraseUsage

    bank = (HERO.get(scenario_code) or {}).get(length) or []
    all_pairs = list(enumerate(bank))
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
        if phrase_id("hero", scenario_code, idx, length) not in used_ids
    ]
    # Falling back to the full bank when exhausted is intentional:
    # the post must go out even if the same opener repeats. Extend
    # the bank to keep variety; we don't gate publication on the
    # registry.
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
    `length`. Picks a fresh template via `filter_unused` then
    `.format`s the scenario data.

    `rng` lets tests force a deterministic choice (`random.Random(0)`).
    In production it defaults to the global `random` module."""
    candidates = filter_unused(scenario.code, length, territori, channel, weeks)
    if scenario.data.get("freshness_blocked"):
        # The scenario's song is not a verified recent release; drop the
        # phrase variants that assert release freshness (the "first week"
        # touch) and keep the pure position/movement ones. Never empty the
        # pool at runtime (the post must go out) — at dev time every
        # scenario that sets this flag is checked to have non-freshness
        # variants; otherwise the rule is to STOP, not invent a phrase.
        non_fresh = [c for c in candidates if not _asserts_freshness(c[1])]
        candidates = non_fresh or candidates
    if not candidates:
        return ("", "")
    chooser = rng.choice if rng is not None else random.choice
    idx, template = chooser(candidates)
    # Backfill the two territori placeholders from the `territori` argument
    # when the scenario didn't supply them. `_base_data` always sets both,
    # but this guards detectors that build `data` by hand (and legacy test
    # fixtures that predate `territori_ordinal`). `territori_label/ordinal`
    # raise KeyError on an unknown code (e.g. ALT), which the except below
    # turns into a skip rather than a crash.
    data = dict(scenario.data)
    try:
        data.setdefault("territori_label", territori_label(territori))
        data.setdefault("territori_ordinal", territori_ordinal(territori))
    except KeyError:
        pass
    # Derive the agreement-correct day string from a raw `dies` count when
    # the scenario supplied `dies` but not `dies_str` (hand-built data /
    # legacy fixtures predating dies_str).
    if "dies" in data and "dies_str" not in data:
        data["dies_str"] = dies_str(int(data["dies"]))
    try:
        text = template.format(**data)
    except KeyError:
        # Defensive: a template referencing a var that the scenario
        # data doesn't supply must not crash the publication. Skip.
        return ("", "")
    return phrase_id("hero", scenario.code, idx, length), text


def mark_used(pid: str, territori: str, setmana, channel: str) -> None:
    """Record that `pid` shipped at this slot. Idempotent enough:
    no unique constraint applies, so a publish-retry just appends
    a second row."""
    from social.models import NarrativePhraseUsage

    NarrativePhraseUsage.objects.create(
        phrase_id=pid,
        territori=territori,
        setmana=setmana,
        channel=channel,
    )
