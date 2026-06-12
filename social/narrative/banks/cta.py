"""Per-channel call-to-action banks.

Instagram's feed strips URLs from captions, so its CTA is plain
text pointing at the bio. The other channels can carry a clickable
URL; templates interpolate `{url}` (a UTM-tagged short link)."""

from __future__ import annotations

import random

CTA_INSTAGRAM_FEED: list[str] = [
    "Top sencer al perfil.",
    "Mira el top complet a la web.",
    "Cap a topquaranta.cat per al top sencer.",
    "Tot al perfil i a topquaranta.cat.",
    "Repassa el top a topquaranta.cat.",
    "El top complet, al perfil.",
    "Veure el top sencer: topquaranta.cat.",
    "topquaranta.cat per al top de la setmana.",
    "Top complet i context: topquaranta.cat.",
    "Tota la classificació, a la bio.",
]

CTA_INSTAGRAM_STORY: list[str] = [
    "topquaranta.cat",
    "Top sencer al perfil",
]

CTA_MASTODON: list[str] = [
    "Top sencer: {url}",
    "Repassa el top: {url}",
    "El top complet, ací: {url}",
    "Continua a {url}",
    "Rànquing complet de la setmana: {url}",
    "Tot el top: {url}",
    "El top sencer, a {url}",
    "Tens el top complet aquí: {url}",
    "La classificació sencera: {url}",
    "Top de la setmana al complet: {url}",
]

CTA_BLUESKY: list[str] = [
    "{url}",
    "Top sencer: {url}",
    "Ací: {url}",
    "El top complet: {url}",
    "Rànquing sencer: {url}",
    "Tot: {url}",
]

CTA_TELEGRAM: list[str] = [
    "👉 Top sencer: {url}",
    "Repassa el top complet: {url}",
    "👉 {url}",
    "Tot el top: {url}",
    "Classificació sencera: {url}",
    "Rànquing complet aquí: {url}",
    "👉 Continua amb el top sencer: {url}",
    "Top de la setmana al complet: {url}",
    "Rànquing detallat: {url}",
    "El top sencer és a {url}",
]

CTA_NEWSLETTER: list[str] = [
    "Continua amb el top complet a topquaranta.cat.",
    "Tens el top sencer i les fitxes de cada cançó a topquaranta.cat.",
    "Per al top complet i el context: topquaranta.cat.",
    "Tota la llista setmanal, a la web: topquaranta.cat.",
    "Si vols aprofundir, topquaranta.cat té la classificació sencera.",
    "Continua la lectura amb el top sencer a topquaranta.cat.",
    "El top complet i comparatives, a topquaranta.cat.",
    "Tota la setmana en xifres a topquaranta.cat.",
]


_BY_CHANNEL = {
    "instagram_feed": CTA_INSTAGRAM_FEED,
    "instagram_story": CTA_INSTAGRAM_STORY,
    "mastodon": CTA_MASTODON,
    "bluesky": CTA_BLUESKY,
    "telegram": CTA_TELEGRAM,
    "newsletter": CTA_NEWSLETTER,
}


def pick_cta(
    channel: str,
    url: str = "",
    rng: random.Random | None = None,
) -> str:
    """Pick a CTA for `channel`. `url` is interpolated when the
    template contains `{url}` (everything except IG / newsletter).
    Falls back to a bare URL on unknown channels."""
    bank = _BY_CHANNEL.get(channel)
    if not bank:
        return url
    tpl = (rng or random).choice(bank)
    return tpl.format(url=url) if "{url}" in tpl else tpl
