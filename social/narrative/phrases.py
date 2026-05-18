"""Templated copy bank for the narrative engine (Fase 4 PR 1).

Each scenario code maps to a list of 15 dict entries; each entry
carries three length tiers (`short` ≤ 80 chars, `medium` ≤ 200,
`long` no hard cap). The composer picks one entry per scenario via
`registry.pick_phrase` and `.format(**scenario.data)`-interpolates
the chosen tier.

Editorial guidelines for additions:
  * Catalan, colloquial register, no em-dashes.
  * 1–2 emojis when they help; never decorative-only. Keep the
    emoji palette varied — no single emoji more than twice within
    a single scenario bank.
  * Vary the opener: celebrate, observe, highlight a detail,
    address the reader. Avoid the dry "L'artista X aconsegueix la
    posició Y" press-release template.

**Grammatical-neutrality contract (Fase 4 PR 1.5, 2026-05-18):**
the artist name is interpolated raw; it can be singular feminine
(Maria Jaume), singular masculine (Lluís Llach), a band with a
singular conventional name (Manel), a plural-marked band (Els
Catarres) or an articled form (La Fúmiga). Therefore:
  * Never let `{artista}` be the subject of a finite verb — the
    verb agreement would break for at least one of those shapes.
    Make the artist a complement instead (`amb {artista}`,
    `per a {artista}`, `de {artista}`, `{artista}:`).
  * Subjects allowed: invariant nouns (`el #1`, `el cim`, `la
    setmana`, `el top`, `el rànquing`), or `«{canco}»` which is
    always singular feminine and therefore safe with verbs in 3rd
    singular and feminine adjectives.
  * No elision on `de {artista}`. The rule is literal: never
    `d'{artista}` even before vowels, and never write `del`/`dels`
    around the variable — Catalan readers see `de Els Catarres`
    or `de La Fúmiga` and it parses fine.

Interpolation variables per scenario:
    a2_streak           — {artista} {canco} {streak} {territori_label}
    a4_debut_alt        — {artista} {canco} {posicio} {territori_label}
    a5_artista_multiple — {artista} {n_cancons} {territori_label}

Length budgets are nominal; the composer enforces hard channel
limits with truncate-or-skip logic after assembly.
"""

from __future__ import annotations

# ── Per-territori hashtags ────────────────────────────────────────
#
# Three-level approach: an always-on duo + a territori-specific
# accent. The composer mixes them per channel (IG abundant,
# Mastodon/Bluesky moderate, Telegram moderate).
#
# AND/CNO/FRA/ALG are reserved for now — the public charts don't
# carry rows for them yet (audit 2026-05-18 confirmed TopSetmanal
# has no entries for these territoris). Add as soon as relevant.
TERRITORY_HASHTAGS: dict[str, list[str]] = {
    "PPCC": ["#TopQuaranta", "#MúsicaEnCatalà"],
    "CAT": ["#TopQuaranta", "#MúsicaEnCatalà", "#Catalunya"],
    "VAL": ["#TopQuaranta", "#MúsicaEnValencià", "#PaísValencià"],
    "BAL": ["#TopQuaranta", "#MúsicaBalear", "#Illes"],
    "AND": ["#TopQuaranta", "#MúsicaEnCatalà", "#Andorra"],
    "CNO": ["#TopQuaranta", "#MúsicaEnCatalà", "#CatalunyaNord"],
    "FRA": ["#TopQuaranta", "#MúsicaEnCatalà", "#FranjaPonent"],
    "ALG": ["#TopQuaranta", "#MúsicaEnCatalà", "#Alguer"],
}


def phrase_id(code: str, idx: int, length: str) -> str:
    """Deterministic key used by the anti-repetition registry.
    Stable across reorderings of the bank only if the index stays
    put — appending new phrases at the end is safe; reordering is
    not. Keep this in mind when editing PHRASES."""
    return f"{code}_{idx}_{length}"


# ── A2 streak — same canço at #1 N consecutive weeks ──────────────
A2_STREAK = [
    {
        "short": "{artista} al #1 de {territori_label} · {streak}a setmana 🎯",
        "medium": "{streak}a setmana al cim de {territori_label}: «{canco}», amb {artista}. 🎯",
        "long": "Ja fa {streak} setmanes que «{canco}» encapçala el Top {territori_label}, signada per {artista}. 🎯",
    },
    {
        "short": "{streak} setmanes al cim per a {artista} ✨",
        "medium": "Al #1 de {territori_label} segueix «{canco}», amb {artista}. {streak}a setmana consecutiva. ✨",
        "long": "I van {streak}. «{canco}» continua manant el Top {territori_label}, amb {artista} al darrere. ✨",
    },
    {
        "short": "El #1 no es mou · {artista} ({streak}a) 🔥",
        "medium": "Res no es belluga al cim de {territori_label}: {streak}a setmana per a {artista} amb «{canco}». 🔥",
        "long": "Al cim del Top {territori_label} no s'hi mou res. {streak}a setmana amb «{canco}», amb signatura de {artista}. 🔥",
    },
    {
        "short": "Encara el #1 per a {artista} 👑",
        "medium": "{streak} setmanes al #1 de {territori_label} per a {artista}. «{canco}» no afluixa. 👑",
        "long": "Encara {streak} setmanes. El cim del Top {territori_label} segueix amb {artista}, gràcies a «{canco}». 👑",
    },
    {
        "short": "«{canco}» resisteix al #1 ({streak}a) 💪",
        "medium": "«{canco}» encadena {streak} setmanes al cim de {territori_label}. Mèrit de {artista}. 💪",
        "long": "Resistència. «{canco}» suma {streak} setmanes al #1 del Top {territori_label}, amb {artista} al timó. 💪",
    },
    {
        "short": "Una setmana més per a {artista} al cim 🎸",
        "medium": "Una vegada més. {streak}a setmana al Top {territori_label} amb {artista} i «{canco}». 🎸",
        "long": "Una setmana més. {streak}a vegada que el Top {territori_label} obre amb {artista} i «{canco}». 🎸",
    },
    {
        "short": "Cims que aguanten · {streak}a setmana 🏔️",
        "medium": "El cim de {territori_label} segueix igual: {streak}a setmana amb {artista} i «{canco}». 🏔️",
        "long": "Cims que aguanten. Ja fa {streak} setmanes que «{canco}», de {artista}, mana al Top {territori_label}. 🏔️",
    },
    {
        "short": "Torna al #1 · «{canco}» ({streak}a) 🎵",
        "medium": "«{canco}» tanca {streak}a setmana al capdamunt de {territori_label}, amb {artista}. 🎵",
        "long": "Mira-ho com vulguis: {streak} setmanes seguides al cim del Top {territori_label} per a «{canco}», amb {artista}. 🎵",
    },
    {
        "short": "«{canco}» no cau · {streak} setmanes ⚓",
        "medium": "«{canco}» ancorada al #1 de {territori_label}. {streak} setmanes per a {artista}. ⚓",
        "long": "Àncora al cim. «{canco}», de {artista}, acumula {streak} setmanes al cim de {territori_label}. ⚓",
    },
    {
        "short": "Una altra setmana per a {artista} al #1 🎙️",
        "medium": "Una altra setmana al cim de {territori_label} per a {artista}. {streak}a consecutiva amb «{canco}». 🎙️",
        "long": "Repetició. El Top {territori_label} torna a obrir amb {artista} i «{canco}»: ja són {streak} setmanes. 🎙️",
    },
    {
        "short": "Lideratge ferm · {streak} setmanes 🚩",
        "medium": "{streak}a setmana al #1 de {territori_label} per a {artista} amb «{canco}». 🚩",
        "long": "Lideratge ferm al Top {territori_label}: {streak} setmanes per a {artista} amb «{canco}». 🚩",
    },
    {
        "short": "Repetició al cim · {artista} 🎼",
        "medium": "Repetició al cim de {territori_label}: {streak} setmanes amb {artista} i «{canco}». 🎼",
        "long": "Repetició al cim. Al Top {territori_label} ja fa {streak} setmanes que mana «{canco}», cançó de {artista}. 🎼",
    },
    {
        "short": "Setmana {streak} · encara per a {artista} 🌟",
        "medium": "Setmana {streak} al #1 de {territori_label} per a {artista} amb «{canco}». 🌟",
        "long": "Setmana {streak} i comptant. Al cim del Top {territori_label} segueix «{canco}», cançó de {artista}. 🌟",
    },
    {
        "short": "«{canco}» segueix manant 🎤",
        "medium": "«{canco}» segueix manant a {territori_label}: {streak}a setmana al #1 amb {artista}. 🎤",
        "long": "Al Top {territori_label} no s'hi mou res. «{canco}» suma {streak} setmanes al #1, signada per {artista}. 🎤",
    },
    {
        "short": "Quina insistència · {streak}a setmana 👀",
        "medium": "{streak} setmanes seguides al #1 de {territori_label} per a {artista} amb «{canco}». 👀",
        "long": "Insistència. {streak} setmanes seguides al cim del Top {territori_label} amb «{canco}», cançó de {artista}. 👀",
    },
]


# ── A4 strong debut — new entry at ≤ #3 ──────────────────────────
A4_DEBUT_ALT = [
    {
        "short": "Entrada forta al #{posicio} · {artista} 🚀",
        "medium": "Nou al Top {territori_label}: «{canco}», de {artista}, directa al #{posicio}. 🚀",
        "long": "Entrada per la porta gran. «{canco}», de {artista}, debuta directament al #{posicio} del Top {territori_label}. 🚀",
    },
    {
        "short": "«{canco}» debuta al #{posicio} 🎯",
        "medium": "«{canco}», cançó de {artista}, entra de cop al #{posicio} del Top {territori_label}. 🎯",
        "long": "Què tal? «{canco}» debuta al #{posicio} del Top {territori_label}. Material nou de {artista}. 🎯",
    },
    {
        "short": "Sorpresa al #{posicio} amb {artista} ✨",
        "medium": "Sorpresa al Top {territori_label}: «{canco}», de {artista}, salta directament al #{posicio}. ✨",
        "long": "Sorpresa al Top {territori_label}. «{canco}», de {artista}, apareix de cop al #{posicio} sense setmana de transició. ✨",
    },
    {
        "short": "A la primera al #{posicio} · {artista} 💥",
        "medium": "A la primera. «{canco}», de {artista}, entra al #{posicio} de {territori_label}. 💥",
        "long": "A la primera setmana, sense rondalla prèvia. «{canco}», de {artista}, aterra al #{posicio} del Top {territori_label}. 💥",
    },
    {
        "short": "Directe al #{posicio} · «{canco}» 🔝",
        "medium": "Directament al cim: «{canco}», de {artista}, entra al #{posicio} de {territori_label}. 🔝",
        "long": "Directe al cim. «{canco}», de {artista}, debuta al #{posicio} del Top {territori_label} aquesta setmana. 🔝",
    },
    {
        "short": "Top 3 a la primera · {artista} 🎼",
        "medium": "Debut al Top 3 de {territori_label}: «{canco}», de {artista}, al #{posicio}. 🎼",
        "long": "Top 3 sense escala. «{canco}», de {artista}, fa el debut al #{posicio} del Top {territori_label}. 🎼",
    },
    {
        "short": "«{canco}» pica fort · #{posicio} 🥊",
        "medium": "Cançó nova i picada forta: «{canco}», de {artista}, al #{posicio} de {territori_label}. 🥊",
        "long": "Cançó nova, picada forta. «{canco}», de {artista}, es planta al #{posicio} del Top {territori_label} a la primera. 🥊",
    },
    {
        "short": "Estrena al #{posicio} · {artista} 👋",
        "medium": "Estrena al Top {territori_label}. «{canco}», amb signatura de {artista}, al #{posicio}. 👋",
        "long": "Estrena al Top {territori_label}. «{canco}», amb signatura de {artista}, surt al #{posicio} de bones a primeres. 👋",
    },
    {
        "short": "Sense escalfar · #{posicio} · {artista} 🎬",
        "medium": "Sense escalfar. «{canco}», de {artista}, al #{posicio} de {territori_label}. 🎬",
        "long": "Sense escalfar prèviament. «{canco}», de {artista}, debuta al #{posicio} del Top {territori_label}. 🎬",
    },
    {
        "short": "Setmana per celebrar · {artista} 🎉",
        "medium": "Setmana per celebrar: «{canco}», de {artista}, debuta al #{posicio} de {territori_label}. 🎉",
        "long": "Setmana per celebrar. «{canco}», de {artista}, entra directament al #{posicio} del Top {territori_label}. 🎉",
    },
    {
        "short": "Cançó nova al #{posicio} · {artista} 🆕",
        "medium": "Cançó nova: «{canco}», de {artista}, ja és al #{posicio} de {territori_label}. 🆕",
        "long": "Recent recent. «{canco}», material nou de {artista}, ja ocupa el #{posicio} del Top {territori_label}. 🆕",
    },
    {
        "short": "Atenció al #{posicio} · {artista} 👀",
        "medium": "Atenció al Top {territori_label}: «{canco}», de {artista}, debuta al #{posicio}. 👀",
        "long": "Atenció. «{canco}», de {artista}, fa la primera al #{posicio} del Top {territori_label} aquesta setmana. 👀",
    },
    {
        "short": "Debut al cim · #{posicio} · {artista} 🏆",
        "medium": "Debut al cim: «{canco}», de {artista}, aterra al #{posicio} de {territori_label}. 🏆",
        "long": "Debut al cim. «{canco}», de {artista}, aterra al #{posicio} del Top {territori_label} sense avís previ. 🏆",
    },
    {
        "short": "Aparició directa al #{posicio} 💫",
        "medium": "Aparició directa: «{canco}», de {artista}, es planta al #{posicio} de {territori_label}. 💫",
        "long": "Aparició directa. «{canco}», de {artista}, surt de cop al #{posicio} del Top {territori_label} sense haver-hi passat abans. 💫",
    },
    {
        "short": "Quina entrada · {artista} al #{posicio} ⭐",
        "medium": "Quina entrada al Top {territori_label}. «{canco}», de {artista}, directa al #{posicio}. ⭐",
        "long": "Quina entrada. La primera setmana al Top {territori_label} arrenca amb «{canco}», de {artista}, al #{posicio}. ⭐",
    },
]


# ── A5 multiple cançons per artista (≥3) ─────────────────────────
A5_ARTISTA_MULTIPLE = [
    {
        "short": "{n_cancons} cançons de {artista} al top 🎶",
        "medium": "{n_cancons} cançons de {artista} al Top {territori_label} aquesta setmana. 🎶",
        "long": "Història al Top {territori_label}: {n_cancons} cançons de {artista} a la llista d'aquesta setmana. 🎶",
    },
    {
        "short": "Domini total · {artista} x{n_cancons} 🔥",
        "medium": "Domini total al Top {territori_label}: {n_cancons} cançons de {artista}. 🔥",
        "long": "Domini total. Al Top {territori_label} hi caben {n_cancons} cançons de {artista} alhora aquesta setmana. 🔥",
    },
    {
        "short": "Setmana per a {artista} · {n_cancons} cançons 🎤",
        "medium": "Setmana per a {artista}: {n_cancons} cançons al Top {territori_label}. 🎤",
        "long": "Setmana per a {artista}. {n_cancons} cançons seves passegen pel Top {territori_label}, una rere l'altra. 🎤",
    },
    {
        "short": "Top monopolitzat · {artista} x{n_cancons} 🎯",
        "medium": "Top monopolitzat: {n_cancons} cançons de {artista} al cim de {territori_label}. 🎯",
        "long": "Top monopolitzat. Al Top {territori_label} hi conviuen {n_cancons} cançons de {artista} alhora. 🎯",
    },
    {
        "short": "{artista} per tot el top · {n_cancons} 🌊",
        "medium": "{artista} per tot arreu: {n_cancons} cançons al Top {territori_label}. 🌊",
        "long": "{artista} per tot arreu. {n_cancons} cançons seves circulen alhora pel Top {territori_label}. 🌊",
    },
    {
        "short": "Pas a {artista} · {n_cancons} entrades 🚪",
        "medium": "Feu pas: {n_cancons} entrades de {artista} al Top {territori_label}. 🚪",
        "long": "Feu pas. Al Top {territori_label} hi ha {n_cancons} entrades de {artista} aquesta setmana. 🚪",
    },
    {
        "short": "{n_cancons} vegades {artista} al top 🎼",
        "medium": "{n_cancons} cops {artista} al Top {territori_label}. Aquí no s'amaga ningú. 🎼",
        "long": "{n_cancons} cops {artista} al Top {territori_label} aquesta setmana. Aquí no s'amaga ningú. 🎼",
    },
    {
        "short": "x{n_cancons} per a {artista} al top ⚡",
        "medium": "Multiplicació: {n_cancons} cançons de {artista} al Top {territori_label}. ⚡",
        "long": "Multiplicació. {n_cancons} cançons de {artista} comparteixen el Top {territori_label} aquesta setmana. ⚡",
    },
    {
        "short": "Setmana de {artista} · {n_cancons} 🎙️",
        "medium": "Setmana de {artista}: {n_cancons} cançons seves al Top {territori_label}. 🎙️",
        "long": "Setmana de {artista}. {n_cancons} cançons seves fan rotllo al Top {territori_label}. 🎙️",
    },
    {
        "short": "Domini a {territori_label} · {artista} x{n_cancons} 👑",
        "medium": "Domini de {artista} a {territori_label}: {n_cancons} cançons al top. 👑",
        "long": "Domini clar a {territori_label}. {n_cancons} cançons de {artista} al Top aquesta setmana. 👑",
    },
    {
        "short": "{n_cancons} cançons, un sol nom · {artista} ✨",
        "medium": "{n_cancons} cançons, un sol nom al Top {territori_label}: {artista}. ✨",
        "long": "{n_cancons} cançons, un sol nom. Al Top {territori_label}, aquesta setmana, només hi ha {artista}. ✨",
    },
    {
        "short": "Pluja de {artista} · {n_cancons} cançons 🎸",
        "medium": "Pluja de {artista}. {n_cancons} cançons seves al Top {territori_label}. 🎸",
        "long": "Pluja de {artista}. {n_cancons} cançons diferents seves passen pel Top {territori_label} aquesta setmana. 🎸",
    },
    {
        "short": "Cop fort de {artista} · x{n_cancons} 🥊",
        "medium": "Cop fort: {n_cancons} cançons de {artista} al Top {territori_label}. 🥊",
        "long": "Cop fort. {n_cancons} cançons de {artista} apareixen a la llista del Top {territori_label}. 🥊",
    },
    {
        "short": "x{n_cancons} entrades de {artista} 📈",
        "medium": "{n_cancons} entrades simultànies de {artista} al Top {territori_label}. 📈",
        "long": "{n_cancons} llocs simultanis del Top {territori_label} ocupats per {artista}. Hi pots passejar amb la seva playlist. 📈",
    },
    {
        "short": "Setmana brutal per a {artista} · x{n_cancons} 🌟",
        "medium": "{n_cancons} cops {artista} al Top {territori_label}. Setmana brutal. 🌟",
        "long": "Setmana brutal per a {artista}. {n_cancons} cançons seves apareixen al Top {territori_label}. 🌟",
    },
]


# ── Public table ──────────────────────────────────────────────────
PHRASES: dict[str, list[dict]] = {
    "a2_streak": A2_STREAK,
    "a4_debut_alt": A4_DEBUT_ALT,
    "a5_artista_multiple": A5_ARTISTA_MULTIPLE,
}
