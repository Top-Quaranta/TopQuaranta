"""Narrative engine for weekly social posts (Fase 4 PR 1).

Three layers:
  * `scenarios.py` — universal pattern detectors that inspect
    `TopSetmanal` and return `Scenario` objects (code, severity,
    interpolation data).
  * `phrases.py` — a curated bank of templated phrases per scenario
    and per length tier (short/medium/long). Plus per-territori
    hashtag tables.
  * `registry.py` — anti-repetition ledger backed by
    `social.NarrativePhraseUsage`. Helper `pick_phrase` filters
    out templates already used at this (channel, territori) in
    the last N weeks and returns the chosen text.
  * `composers/` — per-network text assemblers. Each takes a list
    of `Scenario`s + entry rows + targeting context, returns a
    dict with `text`, `hashtags`, optional `cta`.

This package is consumed by NOTHING yet (Fase 4 PR 1 is library
work). Integration with `social/captions.py` and
`publicar_social.py` lands in a later PR after the bank, detectors
and composers have stabilised.
"""

from social.narrative.scenarios import Scenario, detect_all

__all__ = ["Scenario", "detect_all"]
