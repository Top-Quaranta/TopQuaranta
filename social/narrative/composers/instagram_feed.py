"""Instagram feed composer.

IG caption hard limit is 2 200 chars. The body lists the full top
with `@handle` mentions (autolink + notify) and 5–8 hashtags. We
pick the hero scenario with `long` length and append a secondary
beat at `medium` when a second scenario fires. The "Cap a la bio"
CTA is plain text because IG strips clickable URLs from feed
captions anyway.
"""

from __future__ import annotations

from typing import Optional

from social.captions import _artist_label, _setmana_label
from social.narrative.phrases import TERRITORY_HASHTAGS
from social.narrative.registry import pick_phrase


CHANNEL = "instagram_feed"
MAX_CHARS = 2200


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
    header_lines = [
        f"Top {territori_label} · {label}",
    ]
    if scenarios:
        hero = scenarios[0]
        _, hero_text = pick_phrase(hero, "long", territori, CHANNEL, rng=rng)
        if hero_text:
            header_lines.append("")
            header_lines.append(hero_text)
        if len(scenarios) >= 2:
            secondary = scenarios[1]
            _, sec_text = pick_phrase(
                secondary, "medium", territori, CHANNEL, rng=rng
            )
            if sec_text:
                header_lines.append(sec_text)
    header_lines.append("")
    body_lines = []
    for e in entries:
        label_a = _artist_label(e, use_handle=True)
        body_lines.append(
            f"{e.get('posicio', '?')}. {e.get('canco_nom', '—')} · {label_a}"
        )
    hashtags = TERRITORY_HASHTAGS.get(territori, ["#TopQuaranta", "#MúsicaEnCatalà"])
    # Pad with secondary discovery hashtags up to 5–8 total for IG.
    extras = ["#TopSetmanal", "#PaísosCatalans", "#NovaMúsica"]
    full_tags = list(hashtags) + [t for t in extras if t not in hashtags]
    full_tags = full_tags[:8]

    text = "\n".join(header_lines + body_lines)
    # IG strips clickable links from feed captions; surface the
    # public URL as plain text for users who can copy-paste.
    cta = "Cap a topquaranta.cat per al top complet."
    footer = "\n\n" + cta + "\n\n" + " ".join(full_tags)

    full = text + footer
    # Hard truncate trailing rows if we exceed 2 200 chars. The
    # hero + top-N readability matters more than the long tail.
    while len(full) > MAX_CHARS and body_lines:
        body_lines.pop()
        text = "\n".join(header_lines + body_lines)
        full = text + footer

    return {"text": full, "hashtags": full_tags, "cta": cta}
