"""Telegram composer.

Telegram caption limit is 1024 chars when attached to a media-group
(our case). Plain-name mentions, abundant emojis, link at the end
(Telegram parses URLs and shows a rich preview automatically).
"""

from __future__ import annotations

from social.captions import _artist_label, _setmana_label, utm_url
from social.narrative.phrases import TERRITORY_HASHTAGS
from social.narrative.registry import pick_phrase


CHANNEL = "telegram"
MAX_CHARS = 1024
N_ROWS = 10


def compose(
    scenarios: list,
    entries: list[dict],
    *,
    territori: str,
    setmana,
    rng=None,
) -> dict:
    territori_label = (
        scenarios[0].data.get("territori_label", territori)
        if scenarios
        else territori
    )
    label = _setmana_label(setmana)

    hero_text = ""
    if scenarios:
        _, hero_text = pick_phrase(
            scenarios[0], "medium", territori, CHANNEL, rng=rng
        )

    rows: list[str] = []
    for e in entries[:N_ROWS]:
        name = _artist_label(e, use_handle=False)
        rows.append(f"{e.get('posicio', '?')}. {e.get('canco_nom', '—')} · {name}")
    link = utm_url(CHANNEL, "top_ppcc", setmana, territori=territori)
    hashtags = TERRITORY_HASHTAGS.get(territori, ["#TopQuaranta", "#MúsicaEnCatalà"])[:3]

    def _assemble() -> str:
        parts: list[str] = []
        parts.append(f"🎵 Top {territori_label} · {label}")
        if hero_text:
            parts.append("")
            parts.append(hero_text)
        parts.append("")
        parts.extend(rows)
        parts.append("")
        parts.append(f"👉 {link}")
        parts.append(" ".join(hashtags))
        return "\n".join(parts)

    text = _assemble()
    while len(text) > MAX_CHARS and rows:
        rows.pop()
        text = _assemble()

    return {"text": text, "hashtags": hashtags, "cta": link}
