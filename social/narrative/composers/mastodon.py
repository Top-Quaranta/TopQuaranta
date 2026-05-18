"""Mastodon composer.

500-char hard limit, plain-name mentions (the IG-style `@handle`
syntax doesn't autolink on the fediverse and looks broken — see
the Fase 1 decision documented in CLAUDE.md §6). We pick a hero
scenario at `medium` length, list the top 5 with plain artist
names, and append a UTM-tagged short link plus 2–3 hashtags.
"""

from __future__ import annotations

from social.captions import _artist_label, _setmana_label, utm_url
from social.narrative.phrases import TERRITORY_HASHTAGS
from social.narrative.registry import pick_phrase

CHANNEL = "mastodon"
MAX_CHARS = 500
N_ROWS = 5


def compose(
    scenarios: list,
    entries: list[dict],
    *,
    territori: str,
    setmana,
    rng=None,
) -> dict:
    territori_label = (
        scenarios[0].data.get("territori_label", territori) if scenarios else territori
    )
    label = _setmana_label(setmana)

    parts: list[str] = []
    if scenarios:
        _, hero_text = pick_phrase(scenarios[0], "medium", territori, CHANNEL, rng=rng)
        if hero_text:
            parts.append(hero_text)
    parts.append(f"Top {territori_label} · {label}")
    rows: list[str] = []
    for e in entries[:N_ROWS]:
        name = _artist_label(e, use_handle=False)
        rows.append(f"{e.get('posicio', '?')}. {e.get('canco_nom', '—')} · {name}")
    parts.extend(rows)

    link = utm_url(CHANNEL, "top_ppcc", setmana, territori=territori)
    cta = f"Top complet a {link}"
    hashtags = TERRITORY_HASHTAGS.get(territori, ["#TopQuaranta", "#MúsicaEnCatalà"])[
        :3
    ]
    parts.append(cta)
    parts.append(" ".join(hashtags))

    text = "\n".join(parts)
    # Truncate trailing rows if we exceed 500 chars; keep hero +
    # at least the first row plus the CTA + hashtags.
    while len(text) > MAX_CHARS and rows:
        rows.pop()
        parts_truncated = [p for p in parts if p not in rows]
        # rebuild
        parts = []
        if scenarios:
            _, hero_text = pick_phrase(
                scenarios[0], "medium", territori, CHANNEL, rng=rng
            )
            if hero_text:
                parts.append(hero_text)
        parts.append(f"Top {territori_label} · {label}")
        parts.extend(rows)
        parts.append(cta)
        parts.append(" ".join(hashtags))
        text = "\n".join(parts)

    return {"text": text, "hashtags": hashtags, "cta": cta}
