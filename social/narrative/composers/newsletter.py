"""Newsletter composer.

Email body has no hard char limit but readability does. We pick a
hero at `long` length, optionally a secondary at `medium`, list the
full top (with plain names), and finish with an explicit link to
the public top page. Hashtags exist purely as a "share this"
helper for the rare reader who'd copy them to their socials.
"""

from __future__ import annotations

from social.captions import _artist_label, _setmana_label, utm_url
from social.narrative.phrases import TERRITORY_HASHTAGS
from social.narrative.registry import pick_phrase

CHANNEL = "newsletter"


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

    parts: list[str] = [f"Top {territori_label} · {label}"]
    if scenarios:
        _, hero_text = pick_phrase(scenarios[0], "long", territori, CHANNEL, rng=rng)
        if hero_text:
            parts.append("")
            parts.append(hero_text)
        if len(scenarios) >= 2:
            _, sec_text = pick_phrase(
                scenarios[1], "medium", territori, CHANNEL, rng=rng
            )
            if sec_text:
                parts.append(sec_text)
    parts.append("")
    for e in entries:
        name = _artist_label(e, use_handle=False)
        parts.append(f"{e.get('posicio', '?')}. {e.get('canco_nom', '—')} · {name}")
    link = utm_url(CHANNEL, "top_ppcc", setmana, territori=territori)
    parts.append("")
    parts.append(f"Top complet a {link}")
    hashtags = TERRITORY_HASHTAGS.get(territori, ["#TopQuaranta", "#MúsicaEnCatalà"])
    parts.append("")
    parts.append(" ".join(hashtags))

    return {
        "text": "\n".join(parts),
        "hashtags": hashtags,
        "cta": link,
    }
