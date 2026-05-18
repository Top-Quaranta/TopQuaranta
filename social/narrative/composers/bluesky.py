"""Bluesky composer.

Tight 300-char budget. We use the `short` length tier and trim
aggressively. Plain-name mentions; 1–2 hashtags max because at
300 chars every space counts.
"""

from __future__ import annotations

from social.captions import _artist_label, _setmana_label, utm_url
from social.narrative.phrases import TERRITORY_HASHTAGS
from social.narrative.registry import pick_phrase

CHANNEL = "bluesky"
MAX_CHARS = 300
N_ROWS = 3


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

    hero_text = ""
    if scenarios:
        _, hero_text = pick_phrase(scenarios[0], "short", territori, CHANNEL, rng=rng)
    rows: list[str] = []
    for e in entries[:N_ROWS]:
        name = _artist_label(e, use_handle=False)
        rows.append(f"{e.get('posicio', '?')}. {e.get('canco_nom', '—')} · {name}")
    link = utm_url(CHANNEL, "top_ppcc", setmana, territori=territori)
    hashtags = TERRITORY_HASHTAGS.get(territori, ["#TopQuaranta"])[:2]

    def _assemble() -> str:
        parts: list[str] = []
        if hero_text:
            parts.append(hero_text)
        parts.append(f"Top {territori_label} · {label}")
        parts.extend(rows)
        parts.append(link)
        parts.append(" ".join(hashtags))
        return "\n".join(parts)

    text = _assemble()
    # Drop rows until we fit. The hero + link + hashtags are
    # non-negotiable; the row list is the elastic part.
    while len(text) > MAX_CHARS and rows:
        rows.pop()
        text = _assemble()
    # If even the elastic-less form still overflows, drop hashtags,
    # then hero. Worst case we ship just the title + link.
    if len(text) > MAX_CHARS and hashtags:
        hashtags = []
        text = _assemble()
    if len(text) > MAX_CHARS and hero_text:
        hero_text = ""
        text = _assemble()

    return {"text": text, "hashtags": hashtags, "cta": link}
