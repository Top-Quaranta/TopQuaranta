"""Instagram-feed composer (Fase 4 reset).

2200-char ceiling. Generous budget: hero (long) + optional
secondary (medium) + top5 mention (long with cançó detail) +
CTA + 8-12 hashtags. NO enumerated list at the body — the listing
slides ARE the bullet list."""

from __future__ import annotations

import random

from social.captions import _setmana_label, instagram_username
from social.narrative import scenarios as scen
from social.narrative.banks import connectors as connectors_bank
from social.narrative.banks import cta as cta_bank
from social.narrative.banks import hashtags as hashtags_bank
from social.narrative.banks import top5 as top5_bank
from social.narrative.registry import pick_phrase
from social.narrative.utils import territori_label

CHANNEL = "instagram_feed"
MAX_CHARS = 2200


def _ig_label(artista_nom: str, instagram_url: str | None) -> str:
    """Return `@handle` when the artist has an Instagram URL stored,
    else the plain `artista_nom`. ADR-0007: Instagram autolinks `@h`
    so the artist gets notified; on the other 4 channels we keep the
    plain name (different mention syntax per platform — see
    `social/captions.py::_artist_label`)."""
    u = instagram_username(instagram_url) if instagram_url else ""
    return f"@{u}" if u else artista_nom


def _ig_entry(entry: dict) -> dict:
    """Shallow copy of `entry` with `artista_nom` rewritten to
    `@handle` when available. Top-5 bank reads `artista_nom` so a
    name swap is enough — no bank-level change needed."""
    label = _ig_label(
        entry.get("artista_nom") or "—", entry.get("artista_instagram_url")
    )
    return {**entry, "artista_nom": label}


def _ig_hero_data(hero_data: dict, entries: list[dict]) -> dict:
    """Rewrite `{artista}`, `{de_artista}`, `{per_a_artista}` and
    `{per_artista}` in the hero's data dict so the bank's
    interpolation produces `@handle` where available. The lookup
    is by exact artista_nom match against `entries` (which carry
    `artista_instagram_url`). If no match → no change.

    The other three preposition variants are computed from the
    final label: `@h` never elides nor contracts, so they all
    become `de @h`, `per a @h`, `per @h`."""
    nom = hero_data.get("artista") or ""
    ig_url = next(
        (
            e.get("artista_instagram_url")
            for e in entries
            if e.get("artista_nom") == nom
        ),
        None,
    )
    label = _ig_label(nom, ig_url)
    if label == nom:
        return hero_data  # no Instagram URL → leave as-is
    # `@handle` is a token that doesn't elide/contract — emit the
    # straight preposition + label form.
    return {
        **hero_data,
        "artista": label,
        "de_artista": f"de {label}",
        "per_a_artista": f"per a {label}",
        "per_artista": f"per {label}",
    }


def compose(scenarios, entries, *, territori, setmana, rng=None) -> dict:
    rng = rng or random.Random()
    label_setmana = _setmana_label(setmana)
    label_terr = territori_label(territori)

    hero = scenarios[0] if scenarios else scen.fallback_scenario(territori)
    # ADR-0007: swap artista_nom → @handle for Instagram only. We
    # rewrite the scenario's data and the entries' artista_nom so
    # banks (hero + top5) stay channel-agnostic.
    hero = scen.Scenario(
        code=hero.code,
        severity=hero.severity,
        data=_ig_hero_data(hero.data, entries),
    )
    pid_hero, hero_text = pick_phrase(hero, "long", territori, CHANNEL, rng=rng)

    secondary_text = ""
    pid_secondary = ""
    secondary_canco = ""
    if len(scenarios) >= 2:
        sec = scenarios[1]
        sec = scen.Scenario(
            code=sec.code,
            severity=sec.severity,
            data=_ig_hero_data(sec.data, entries),
        )
        pid_secondary, secondary_text = pick_phrase(
            sec, "medium", territori, CHANNEL, rng=rng
        )
        secondary_canco = sec.data.get("canco") or ""
    connector = connectors_bank.pick_connector(rng=rng) if secondary_text else ""
    if connector.endswith(","):
        secondary_text = connectors_bank.lowercase_first(secondary_text)

    # ADR-0008: tertiary slot for the long-budget IG feed only. We
    # surface a third scene (short tier) when there's still narrative
    # to tell after the headline + the secondary. Truncation logic
    # below drops tertiary first, before the secondary.
    tertiary_text = ""
    pid_tertiary = ""
    tertiary_canco = ""
    if len(scenarios) >= 3:
        ter = scenarios[2]
        ter = scen.Scenario(
            code=ter.code,
            severity=ter.severity,
            data=_ig_hero_data(ter.data, entries),
        )
        pid_tertiary, tertiary_text = pick_phrase(
            ter, "short", territori, CHANNEL, rng=rng
        )
        tertiary_canco = ter.data.get("canco") or ""
    connector2 = connectors_bank.pick_connector(rng=rng) if tertiary_text else ""
    if connector2.endswith(","):
        tertiary_text = connectors_bank.lowercase_first(tertiary_text)

    hero_canco = hero.data.get("canco") or ""
    # Filter top-5 by cançó: drop hero + secondary referents. The
    # entries are rewritten with @handle (when present) AFTER the
    # cançó-based filter so the lookup keys stay stable.
    top5 = entries[:5]
    skip_cancons = {c for c in (hero_canco, secondary_canco, tertiary_canco) if c}
    remaining = [_ig_entry(e) for e in top5 if e.get("canco_nom") not in skip_cancons]
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

    def assemble(h_text, sec_text, ter_text, t5_text, hts):
        # Fase 4 esmena 1: no robotic header. The body starts with
        # the hero directly; the territori_label and week context
        # are inside the hero phrase itself.
        parts: list[str] = []
        if h_text:
            parts.append(h_text)
        if sec_text:
            parts += ["", f"{connector} {sec_text}"]
        if ter_text:
            parts += ["", f"{connector2} {ter_text}"]
        if t5_text:
            parts += ["", t5_text]
        parts += ["", cta]
        if hts:
            parts += ["", " ".join(hts)]
        return "\n".join(parts)

    text = assemble(hero_text, secondary_text, tertiary_text, top5_text, hashtags)
    # Truncate priority: tertiary → secondary → top5 detail → hashtags.
    if len(text) > MAX_CHARS and tertiary_text:
        tertiary_text = ""
        pid_tertiary = ""
        text = assemble(hero_text, secondary_text, tertiary_text, top5_text, hashtags)
    if len(text) > MAX_CHARS and secondary_text:
        secondary_text = ""
        pid_secondary = ""
        text = assemble(hero_text, secondary_text, tertiary_text, top5_text, hashtags)
    if len(text) > MAX_CHARS and top5_text:
        top5_text = ""
        text = assemble(hero_text, secondary_text, tertiary_text, top5_text, hashtags)
    while len(text) > MAX_CHARS and hashtags:
        hashtags = hashtags[:-1]
        text = assemble(hero_text, secondary_text, tertiary_text, top5_text, hashtags)

    phrase_ids: list[str] = []
    if pid_hero:
        phrase_ids.append(pid_hero)
    if pid_secondary:
        phrase_ids.append(pid_secondary)
    if pid_tertiary:
        phrase_ids.append(pid_tertiary)
    return {
        "text": text,
        "hashtags": hashtags,
        "cta": cta,
        "phrase_ids": phrase_ids,
    }
