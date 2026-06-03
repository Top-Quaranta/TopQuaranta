"""Mastodon composer (Fase 4 reset).

500-char ceiling. Pure narrative — no enumerated list at the body.
Structure: hero (medium) + top5 mention (short) + CTA + hashtags.
Plain-name mentions (the IG-style `@handle` doesn't autolink on
the fediverse)."""

from __future__ import annotations

import random

from social.captions import _setmana_label, utm_url
from social.narrative import scenarios as scen
from social.narrative.banks import cta as cta_bank
from social.narrative.banks import hashtags as hashtags_bank
from social.narrative.banks import top5 as top5_bank
from social.narrative.registry import pick_phrase
from social.narrative.utils import territori_label

CHANNEL = "mastodon"
MAX_CHARS = 500


def compose(scenarios, entries, *, territori, setmana, rng=None) -> dict:
    rng = rng or random.Random()
    label_setmana = _setmana_label(setmana)
    label_terr = territori_label(territori)

    # Distinct-subject slots (audit #1/#6) — consistent with the other
    # composers; Mastodon only renders the hero today, so this is a
    # no-op now but keeps the hero subject canonical.
    scenarios = scen.select_slots(scenarios, 2)

    hero = scenarios[0] if scenarios else scen.fallback_scenario(territori)
    pid, hero_text = pick_phrase(hero, "medium", territori, CHANNEL, rng=rng)
    if not hero_text:
        hero_text = f"Repàs setmanal al top {label_terr} · {label_setmana}."

    # Hero referent: only filter the cançó (multi-presence artists
    # still get a mention via other rows). Case A vs Case B per
    # Fase 4 esmena 4 — if the hero referent isn't at the cim,
    # frame the #1 separately.
    hero_canco = hero.data.get("canco") or ""
    top5 = entries[:5]
    remaining = [e for e in top5 if e.get("canco_nom") != hero_canco]
    leader = next((e for e in remaining if e.get("posicio") == 1), None)
    others = (
        [e for e in remaining if e.get("posicio") != 1][:3] if leader else remaining[:3]
    )
    top5_text = top5_bank.pick_short(others, leader=leader, rng=rng)

    link = utm_url(CHANNEL, "top_ppcc", setmana, territori=territori)
    cta = cta_bank.pick_cta(CHANNEL, url=link, rng=rng)
    hashtags = hashtags_bank.build_hashtags(territori, CHANNEL, rng=rng)

    def assemble(t5, hts):
        # Fase 4 esmena 1: no robotic header. Hero phrase already
        # mentions {territori_label}; we don't need a separate
        # "Top X · Setmana N" line.
        parts = [hero_text]
        if t5:
            parts += ["", t5]
        parts += ["", cta]
        if hts:
            parts += ["", " ".join(hts)]
        return "\n".join(parts)

    text = assemble(top5_text, hashtags)
    # Hard fit. Drop top5 first, then hashtags. Hero is sacred.
    if len(text) > MAX_CHARS and top5_text:
        top5_text = ""
        text = assemble(top5_text, hashtags)
    while len(text) > MAX_CHARS and hashtags:
        hashtags = hashtags[:-1]
        text = assemble(top5_text, hashtags)

    phrase_ids = [pid] if pid else []
    return {
        "text": text,
        "hashtags": hashtags,
        "cta": cta,
        "phrase_ids": phrase_ids,
    }
