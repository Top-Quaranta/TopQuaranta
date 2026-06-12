"""Novetats composer (audit #5, 2026-06-01).

Builds the weekly new-release caption for every channel from the
`novetats` detectors. Shared logic; `nous_albums.py` / `nous_singles.py`
are thin per-tipus entry points. Mirrors the top composers: a hero beat
(+ optional secondary / tertiary depending on the channel budget),
deduped by artist via `scenarios.select_slots`, then a short list of the
remaining releases, a CTA and TitleCase hashtags.
"""

from __future__ import annotations

import random

from social.captions import HASHTAGS_NOVETATS, instagram_username, utm_url
from social.narrative import novetats as nov
from social.narrative import scenarios as scen
from social.narrative.banks import connectors as connectors_bank
from social.narrative.banks.novetats import NOVETATS
from social.narrative.utils import llista_amb_i, with_preposition

# Novetats CTAs — the top CTAs ("top sencer") don't fit a release
# roundup. Channels that don't render a URL in body (IG/newsletter) get
# the bare site; the rest interpolate the UTM link.
_CTA_NO_URL = [
    "Totes les novetats de la setmana a topquaranta.cat.",
    "Més música nova en català a topquaranta.cat.",
    "Descobreix-les totes a topquaranta.cat.",
]
_CTA_URL = [
    "Totes les novetats: {url}",
    "Més música nova en català: {url}",
    "Escolta-les aquí: {url}",
]

# Per-channel budget: (max_chars, n_slots, hero_tier, use_list, use_handle,
# n_hashtags).
_CHANNEL_CFG = {
    "instagram_feed": (2200, 3, "long", True, True, 3),
    "telegram": (900, 2, "medium", True, False, 3),
    "newsletter": (9999, 3, "long", True, False, 3),
    "mastodon": (480, 1, "short", False, False, 3),
    "bluesky": (280, 1, "short", False, False, 2),
}

_TIER_FOR_SLOT = {0: None, 1: "medium", 2: "short"}  # hero tier set per channel


def _ig_label(nom: str, ig_url: str | None) -> str:
    u = instagram_username(ig_url) if ig_url else ""
    return f"@{u}" if u else nom


def _rewrite_handle(data: dict, items: list[dict]) -> dict:
    """IG only: rewrite {artista}/{de_artista}/{per_artista} to @handle."""
    nom = data.get("artista") or ""
    ig_url = next(
        (i.get("artista_instagram_url") for i in items if i.get("artista_nom") == nom),
        None,
    )
    label = _ig_label(nom, ig_url)
    if label == nom:
        return data
    return {
        **data,
        "artista": label,
        "de_artista": f"de {label}",
        "per_artista": f"per {label}",
    }


def _pick(code: str, tier: str, rng: random.Random) -> str:
    bank = NOVETATS.get(code) or NOVETATS["fallback_novetat"]
    options = bank.get(tier) or bank["short"]
    return rng.choice(options)


def _release_label(item: dict, *, use_handle: bool) -> str:
    nom = item.get("artista_nom") or "—"
    if use_handle:
        nom = _ig_label(nom, item.get("artista_instagram_url"))
    return f"«{item.get('nom')}» {with_preposition(nom, 'de')}"


def compose(channel: str, tipus: str, items, *, setmana, rng=None) -> dict:
    rng = rng or random.Random()
    max_chars, n_slots, hero_tier, use_list, use_handle, n_tags = _CHANNEL_CFG.get(
        channel, (900, 2, "medium", True, False, 3)
    )

    scenarios = scen.select_slots(nov.detect_novetats(list(items)), n_slots)
    if not scenarios:
        return {"text": "", "hashtags": [], "cta": "", "phrase_ids": []}

    tiers = [hero_tier] + [_TIER_FOR_SLOT[i] for i in range(1, n_slots)]
    blocks: list[str] = []
    used_artista_ids: set = set()
    for idx, s in enumerate(scenarios):
        data = s.data
        if use_handle:
            data = _rewrite_handle(data, items)
        text = _pick(s.code, tiers[idx] or "short", rng).format(**data)
        if idx == 0:
            blocks.append(text)
        else:
            connector = connectors_bank.pick_connector(rng=rng)
            if connector.endswith(","):
                text = connectors_bank.lowercase_first(text)
            blocks.append(f"{connector} {text}")
        if s.data.get("artista_id") is not None:
            used_artista_ids.add(s.data["artista_id"])

    # Remaining releases as a short list (not already a slot's artist).
    list_text = ""
    if use_list:
        rest = [it for it in items if it.get("artista_id") not in used_artista_ids][:4]
        if rest:
            joined = llista_amb_i(
                [_release_label(it, use_handle=use_handle) for it in rest]
            )
            list_text = f"També aquesta setmana: {joined}."

    if channel in ("instagram_feed", "newsletter"):
        cta = rng.choice(_CTA_NO_URL)
    else:
        link = utm_url(channel, tipus, setmana) if setmana is not None else ""
        cta = rng.choice(_CTA_URL).format(url=link).strip()
    hashtags = list(HASHTAGS_NOVETATS[:n_tags])

    def assemble(blks, lst):
        parts = list(blks)
        if lst:
            parts.append(lst)
        if cta:
            parts.append(cta)
        if hashtags:
            parts.append(" ".join(hashtags))
        # One blank line between every non-empty part.
        return "\n\n".join(p for p in parts if p)

    text = assemble(blocks, list_text)
    # Truncate to the channel ceiling: drop list, then trailing slots.
    if len(text) > max_chars and list_text:
        list_text = ""
        text = assemble(blocks, list_text)
    while len(text) > max_chars and len(blocks) > 1:
        blocks = blocks[:-1]
        text = assemble(blocks, list_text)

    return {
        "text": text,
        "hashtags": hashtags,
        "cta": cta,
        "phrase_ids": [],  # novetats banks aren't anti-repeat tracked
    }
