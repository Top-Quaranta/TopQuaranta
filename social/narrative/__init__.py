"""Narrative engine for weekly social posts (Fase 4 reset).

Layers:
  * `utils.py` — Catalan-specific helpers (`apostrof_de`,
    `llista_amb_i`, `territori_label`).
  * `scenarios.py` — eight pattern detectors over `TopSetmanal` +
    a fallback. Each returns at most one `Scenario` with the
    interpolation data pre-rendered.
  * `banks/` — phrase banks: hero (anti-repetition tracked), top5
    (completion mention), connectors, ctas, hashtags, transitions
    (newsletter only).
  * `registry.py` — anti-repetition ledger backed by
    `social.NarrativePhraseUsage`. Only hero pids are tracked.
  * `composers/` — per-channel narrative assemblers. Zero bullet
    lists at the body level; the listing image is the bullet
    list. Newsletter is the exception: its HTML template still
    renders an `<ol>` after the narrative paragraph.

Public entrypoint for the rest of the codebase is
`social.captions.compose_for_channel`."""

from social.narrative.scenarios import Scenario, detect_all, fallback_scenario

__all__ = ["Scenario", "detect_all", "fallback_scenario"]
