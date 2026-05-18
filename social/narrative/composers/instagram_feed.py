"""Instagram-feed composer (Fase 4 reset).

2200-char ceiling. Generous budget: hero (long) + optional
secondary (medium) + top5 mention (long with cançó detail) +
CTA + 8-12 hashtags. NO enumerated list at the body — the listing
slides ARE the bullet list."""

from __future__ import annotations

import random

from social.captions import _setmana_label
from social.narrative import scenarios as scen
from social.narrative.banks import connectors as connectors_bank
from social.narrative.banks import cta as cta_bank
from social.narrative.banks import hashtags as hashtags_bank
from social.narrative.banks import top5 as top5_bank
from social.narrative.registry import pick_phrase
from social.narrative.utils import territori_label

CHANNEL = "instagram_feed"
MAX_CHARS = 2200


def compose(scenarios, entries, *, territori, setmana, rng=None) -> dict:
    rng = rng or random.Random()
    label_setmana = _setmana_label(setmana)
    label_terr = territori_label(territori)

    hero = scenarios[0] if scenarios else scen.fallback_scenario(territori)
    pid_hero, hero_text = pick_phrase(hero, "long", territori, CHANNEL, rng=rng)

    secondary_text = ""
    pid_secondary = ""
    secondary_canco = ""
    if len(scenarios) >= 2:
        pid_secondary, secondary_text = pick_phrase(
            scenarios[1], "medium", territori, CHANNEL, rng=rng
        )
        secondary_canco = scenarios[1].data.get("canco") or ""
    connector = connectors_bank.pick_connector(rng=rng) if secondary_text else ""
    if connector.endswith(","):
        secondary_text = connectors_bank.lowercase_first(secondary_text)

    hero_canco = hero.data.get("canco") or ""
    # Filter top-5 by cançó: drop hero + secondary referents.
    top5 = entries[:5]
    skip_cancons = {c for c in (hero_canco, secondary_canco) if c}
    remaining = [e for e in top5 if e.get("canco_nom") not in skip_cancons]
    # Case A vs Case B (Fase 4 esmena 4): if the hero referent is
    # NOT at the cim, frame the #1 separately so we don't list it
    # like a completing artist.
    leader = next((e for e in remaining if e.get("posicio") == 1), None)
    others = (
        [e for e in remaining if e.get("posicio") != 1][:3] if leader else remaining[:3]
    )
    top5_text = top5_bank.pick_long(others, leader=leader, rng=rng)

    cta = cta_bank.pick_cta(CHANNEL, url="", rng=rng)
    hashtags = hashtags_bank.build_hashtags(territori, CHANNEL, rng=rng)

    def assemble(h_text, sec_text, t5_text, hts):
        # Fase 4 esmena 1: no robotic header. The body starts with
        # the hero directly; the territori_label and week context
        # are inside the hero phrase itself.
        parts: list[str] = []
        if h_text:
            parts.append(h_text)
        if sec_text:
            parts += ["", f"{connector} {sec_text}"]
        if t5_text:
            parts += ["", t5_text]
        parts += ["", cta]
        if hts:
            parts += ["", " ".join(hts)]
        return "\n".join(parts)

    text = assemble(hero_text, secondary_text, top5_text, hashtags)
    # Truncate priority: secondary → top5 detail → hashtags.
    if len(text) > MAX_CHARS and secondary_text:
        secondary_text = ""
        pid_secondary = ""
        text = assemble(hero_text, secondary_text, top5_text, hashtags)
    if len(text) > MAX_CHARS and top5_text:
        top5_text = ""
        text = assemble(hero_text, secondary_text, top5_text, hashtags)
    while len(text) > MAX_CHARS and hashtags:
        hashtags = hashtags[:-1]
        text = assemble(hero_text, secondary_text, top5_text, hashtags)

    phrase_ids: list[str] = []
    if pid_hero:
        phrase_ids.append(pid_hero)
    if pid_secondary:
        phrase_ids.append(pid_secondary)
    return {
        "text": text,
        "hashtags": hashtags,
        "cta": cta,
        "phrase_ids": phrase_ids,
    }
