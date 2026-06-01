"""Newsletter composer (Fase 4 reset).

The newsletter is HTML email; the template (`comptes/templates/
comptes/email_newsletter_top.html`) already renders an `<ol>` of
all 40 entries below the narrative paragraph. The composer's job
is to produce a richer NARRATIVE block: hero (long) + optional
secondary (medium) + a small contextualising paragraph + a soft
transition into the listing. Listing itself stays in the template.

Returns `{narrative_part, list_part, transition, text, hashtags,
cta, phrase_ids}`.

* `narrative_part` — the editorial block (hero + optional secondary +
  small context paragraph). Plain text by default; the template
  may wrap it in <p>'s via `linebreaks` / `linebreaksbr`.
* `list_part` — a plain-text enumerated listing (the fallback for
  the text/plain MIME alternative and for callers that just want a
  joined `text`).
* `transition` — a short hand-off line between narrative and list.
* `text` — `narrative_part + "\n\n" + transition + "\n\n" + list_part`,
  the simple joined form that the `caption_short` wrapper returns
  for callers that don't want to split."""

from __future__ import annotations

import random

from social.captions import _setmana_label, utm_url
from social.narrative import scenarios as scen
from social.narrative.banks import connectors as connectors_bank
from social.narrative.banks import cta as cta_bank
from social.narrative.banks import hashtags as hashtags_bank
from social.narrative.banks import top5 as top5_bank
from social.narrative.banks import transitions as transitions_bank
from social.narrative.registry import pick_phrase
from social.narrative.utils import territori_label

CHANNEL = "newsletter"


def _list_part(entries) -> str:
    """Plain-text numbered listing of all entries (fallback for the
    text/plain MIME alternative).

    Tasca B2: surface collaborators alongside the main artist via
    `_join_artists_text` (whole-name drops, ellipsis at the last
    fitting name). 80-char budget keeps the line readable in mono
    text viewers while still fitting "Main, Col1, Col2" for the
    common case."""
    from social.captions import _join_artists_text

    rows = []
    for e in entries:
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        artist_text = _join_artists_text(names, max_chars=80)
        rows.append(
            f"{e.get('posicio', '?')}. {e.get('canco_nom', '—')} · {artist_text}"
        )
    return "\n".join(rows)


def compose(scenarios, entries, *, territori, setmana, rng=None) -> dict:
    rng = rng or random.Random()
    label_setmana = _setmana_label(setmana)
    label_terr = territori_label(territori)

    # Distinct-subject slots (audit #1/#6 + #13): the newsletter has no
    # length ceiling, so it carries a 3rd paragraph (hero + secondary +
    # tertiary) when the detectors supply 3 distinct subjects.
    scenarios = scen.select_slots(scenarios, 3)

    hero = scenarios[0] if scenarios else scen.fallback_scenario(territori)
    pid_hero, hero_text = pick_phrase(hero, "long", territori, CHANNEL, rng=rng)

    secondary_text = ""
    pid_secondary = ""
    secondary_canco = ""
    if len(scenarios) >= 2:
        pid_secondary, secondary_text = pick_phrase(
            scenarios[1], "long", territori, CHANNEL, rng=rng
        )
        secondary_canco = scenarios[1].data.get("canco") or ""
    connector = connectors_bank.pick_connector(rng=rng) if secondary_text else ""
    if connector.endswith(","):
        secondary_text = connectors_bank.lowercase_first(secondary_text)

    tertiary_text = ""
    pid_tertiary = ""
    tertiary_canco = ""
    if len(scenarios) >= 3:
        pid_tertiary, tertiary_text = pick_phrase(
            scenarios[2], "medium", territori, CHANNEL, rng=rng
        )
        tertiary_canco = scenarios[2].data.get("canco") or ""
    connector2 = connectors_bank.pick_connector(rng=rng) if tertiary_text else ""
    if connector2.endswith(","):
        tertiary_text = connectors_bank.lowercase_first(tertiary_text)

    hero_canco = hero.data.get("canco") or ""
    top5 = entries[:5]
    skip_cancons = {c for c in (hero_canco, secondary_canco, tertiary_canco) if c}
    remaining = [e for e in top5 if e.get("canco_nom") not in skip_cancons]
    leader = next((e for e in remaining if e.get("posicio") == 1), None)
    others = (
        [e for e in remaining if e.get("posicio") != 1][:3] if leader else remaining[:3]
    )
    top5_text = top5_bank.pick_long(others, leader=leader, rng=rng)

    transition = transitions_bank.pick_transition(rng=rng)

    # Fase 4 ajust 1: the narrative_part starts with the hero
    # directly. The HTML template (`comptes/templates/comptes/
    # email_newsletter_top.html`) owns the `<h1>` header showing
    # "Top X · Setmana N"; repeating it in the body would
    # duplicate the title in the email.
    narrative_parts: list[str] = []
    if hero_text:
        narrative_parts.append(hero_text)
    if secondary_text:
        narrative_parts += ["", f"{connector} {secondary_text}"]
    if tertiary_text:
        narrative_parts += ["", f"{connector2} {tertiary_text}"]
    if top5_text:
        narrative_parts += ["", top5_text]
    narrative_part = "\n".join(narrative_parts)

    list_part = _list_part(entries)

    link = utm_url(CHANNEL, "top_ppcc", setmana, territori=territori)
    cta = cta_bank.pick_cta(CHANNEL, url=link, rng=rng)
    hashtags = hashtags_bank.build_hashtags(territori, CHANNEL, rng=rng)

    # Joined form for callers that don't split.
    text_parts = [narrative_part, "", transition, "", list_part, "", cta]
    if hashtags:
        text_parts += ["", " ".join(hashtags)]
    text = "\n".join(text_parts)

    phrase_ids: list[str] = []
    if pid_hero:
        phrase_ids.append(pid_hero)
    if pid_secondary:
        phrase_ids.append(pid_secondary)
    if pid_tertiary:
        phrase_ids.append(pid_tertiary)

    return {
        "text": text,
        "narrative_part": narrative_part,
        "list_part": list_part,
        "transition": transition,
        "hashtags": hashtags,
        "cta": cta,
        "phrase_ids": phrase_ids,
    }
