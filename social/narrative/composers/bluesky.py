"""Bluesky composer (Fase 4 reset).

300-char hard ceiling, 280-char soft target. The tightest budget:
hero (short) + optional top5 + CTA + 1-2 hashtags. Truncation
order — drop top5 → drop hashtags → fall back to a bare hero +
CTA. The hero is sacred only as long as the soft target is met;
if even the bare hero+CTA blows past 300 we replace it with a
generic sentinel."""

from __future__ import annotations

import random

from social.captions import utm_url
from social.narrative import scenarios as scen
from social.narrative.banks import cta as cta_bank
from social.narrative.banks import hashtags as hashtags_bank
from social.narrative.banks import top5 as top5_bank
from social.narrative.registry import pick_phrase

CHANNEL = "bluesky"
SOFT_TARGET = 280  # Fase 4 ajust 2: leave margin under the 300 ceiling
HARD_CEILING = 300


def compose(scenarios, entries, *, territori, setmana, rng=None) -> dict:
    rng = rng or random.Random()

    # Distinct-subject slots (audit #1/#6) — consistent with the other
    # composers; Bluesky only renders the hero, so this is a no-op now.
    scenarios = scen.select_slots(scenarios, 2)

    hero = scenarios[0] if scenarios else scen.fallback_scenario(territori)
    pid, hero_text = pick_phrase(hero, "short", territori, CHANNEL, rng=rng)
    if not hero_text:
        hero_text = "Top setmanal: ja és aquí."

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

    def assemble(h_text, t5_text, hts):
        parts = [h_text]
        if t5_text:
            parts += ["", t5_text]
        parts += ["", cta]
        if hts:
            parts += [" ".join(hts)]
        return "\n".join(parts)

    text = assemble(hero_text, top5_text, hashtags)
    # Step 1 — soft target. Drop top5 as soon as we'd exceed 280.
    if len(text) > SOFT_TARGET and top5_text:
        top5_text = ""
        text = assemble(hero_text, top5_text, hashtags)
    # Step 2 — drop hashtags one by one to stay under soft target.
    while len(text) > SOFT_TARGET and hashtags:
        hashtags = hashtags[:-1]
        text = assemble(hero_text, top5_text, hashtags)
    # Step 3 — last resort. If even the bare hero+CTA blows past
    # the HARD ceiling (a hero with a really long artist name +
    # cançó title), replace the hero with a generic sentinel and
    # surrender the pid (it didn't ship). This guarantees the
    # text always fits.
    if len(text) > HARD_CEILING:
        hero_text = "Top setmanal: ja és aquí."
        pid = ""
        text = assemble(hero_text, "", hashtags)
        while len(text) > HARD_CEILING and hashtags:
            hashtags = hashtags[:-1]
            text = assemble(hero_text, "", hashtags)

    phrase_ids = [pid] if pid else []
    return {
        "text": text,
        "hashtags": hashtags,
        "cta": cta,
        "phrase_ids": phrase_ids,
    }
