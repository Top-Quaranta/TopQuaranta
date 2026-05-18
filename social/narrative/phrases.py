"""Templated copy bank for the narrative engine (Fase 4 PR 1).

Each scenario code maps to a list of 15 dict entries; each entry
carries three length tiers (`short` ≤ 80 chars, `medium` ≤ 200,
`long` no hard cap). The composer picks one entry per scenario via
`registry.pick_phrase` and `.format(**scenario.data)`-interpolates
the chosen tier.

Editorial guidelines for additions:
  * Catalan, colloquial register, no em-dashes.
  * 1–2 emojis when they help; never decorative-only.
  * Vary the opener: celebrate, observe, highlight a detail,
    address the reader. Avoid the dry "L'artista X aconsegueix la
    posició Y" template — it reads like a press release.
  * Interpolation variables per scenario:
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
# AND/CNO/FRA/ALG/ALG are empty for now because the public charts
# don't carry them yet (audit 2026-05-18 confirmed TopSetmanal has
# no rows for these territoris). Add them when relevant.
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
        "short": "{artista} segueix al #1 {territori_label} 🎯",
        "medium": "{streak}a setmana consecutiva al #1 de {territori_label}: {artista} amb «{canco}». 🎯",
        "long": "Ja en porten {streak}. {artista} no s'aparta del cim del Top {territori_label} amb «{canco}». 🎯",
    },
    {
        "short": "{streak} setmanes seguides al cim ✨",
        "medium": "«{canco}» de {artista} aguanta el #1 de {territori_label} per {streak}a setmana. ✨",
        "long": "I van {streak}. «{canco}» de {artista} segueix manant al Top {territori_label} setmana rere setmana. ✨",
    },
    {
        "short": "No es mou: {artista} al #1 ({streak}a) 🔥",
        "medium": "{artista} no afluixa: {streak}a setmana al #1 de {territori_label} amb «{canco}». 🔥",
        "long": "«{canco}» de {artista} no es mou. {streak}a setmana liderant el Top {territori_label}, i pinta que encara n'hi haurà més. 🔥",
    },
    {
        "short": "{artista} encara manen 👑",
        "medium": "{streak} setmanes al #1 de {territori_label} per a {artista}. «{canco}» no es deixa pas. 👑",
        "long": "{streak} setmanes ja. {artista} continuen al cim del Top {territori_label} amb «{canco}». Resistència pura. 👑",
    },
    {
        "short": "{canco} resisteix al #1 ({streak}a) 💪",
        "medium": "«{canco}» de {artista} encadena {streak} setmanes al cim de {territori_label}. 💪",
        "long": "Resistència. «{canco}» de {artista} ja porta {streak} setmanes al #1 del Top {territori_label}, i el ritme no cau. 💪",
    },
    {
        "short": "{artista} no deixen anar {territori_label} 🎶",
        "medium": "{streak}a vegada que {artista} obre el Top {territori_label} amb «{canco}». 🎶",
        "long": "Una setmana més. {artista} obre el Top {territori_label} per {streak}a vegada consecutiva amb «{canco}». 🎶",
    },
    {
        "short": "Cims que aguanten: {streak}a setmana 🏔️",
        "medium": "{artista} aguanten el cim de {territori_label} per {streak}a setmana amb «{canco}». 🏔️",
        "long": "Cims que aguanten. {artista} viuen a dalt del Top {territori_label} des de fa {streak} setmanes amb «{canco}». 🏔️",
    },
    {
        "short": "Tornen al #1: {artista} ({streak}a) 🎵",
        "medium": "{artista} tanquen {streak}a setmana al capdamunt de {territori_label} amb «{canco}». 🎵",
        "long": "Mira-ho com vulguis. {streak} setmanes seguides per a «{canco}» de {artista} a dalt del Top {territori_label}. 🎵",
    },
    {
        "short": "{canco} no cau · {streak} setmanes ⚓",
        "medium": "«{canco}» ancorada al #1 de {territori_label}. {streak} setmanes per a {artista}. ⚓",
        "long": "Ancorats. «{canco}» de {artista} acumula {streak} setmanes al cim de {territori_label}. ⚓",
    },
    {
        "short": "{artista} de nou al #1 🎙️",
        "medium": "Una altra setmana per a {artista} al cim de {territori_label}. {streak}a consecutiva amb «{canco}». 🎙️",
        "long": "Una altra. {artista} repeteixen al #1 del Top {territori_label}, ja són {streak} setmanes amb «{canco}». 🎙️",
    },
    {
        "short": "Lideratge ferm · {streak} setmanes 🚩",
        "medium": "{artista} signen {streak}a setmana al #1 de {territori_label} amb «{canco}». 🚩",
        "long": "Lideratge ferm. {artista} marquen {streak}a setmana al cim del Top {territori_label} amb «{canco}». 🚩",
    },
    {
        "short": "{artista} repeteixen #1 a {territori_label} 🎼",
        "medium": "Repetició al cim: {streak} setmanes de {artista} amb «{canco}» a {territori_label}. 🎼",
        "long": "Repetició al cim. {artista} arriben a {streak} setmanes al #1 del Top {territori_label} amb «{canco}». 🎼",
    },
    {
        "short": "Setmana {streak}: encara {artista} 🌟",
        "medium": "Setmana {streak} per a {artista} al #1 de {territori_label} amb «{canco}». 🌟",
        "long": "Setmana {streak} i comptant. {artista} mantenen el #1 del Top {territori_label} amb «{canco}». 🌟",
    },
    {
        "short": "{canco} segueix manant 🎤",
        "medium": "«{canco}» de {artista} segueix manant {territori_label}: {streak}a setmana al #1. 🎤",
        "long": "Aquí no es mou res. «{canco}» de {artista} aguanta {streak} setmanes seguides al #1 del Top {territori_label}. 🎤",
    },
    {
        "short": "Cap on les escolten més? 👀",
        "medium": "{streak} setmanes que {artista} guanyen {territori_label} amb «{canco}». On les escolten més? 👀",
        "long": "{streak} setmanes seguides. {artista} dominen el Top {territori_label} amb «{canco}». La pregunta és: on les escolten més, aquí o als concerts? 👀",
    },
]


# ── A4 strong debut — new entry at ≤ #3 ──────────────────────────
A4_DEBUT_ALT = [
    {
        "short": "Entrada forta de {artista} al #{posicio} 🚀",
        "medium": "{artista} debuten directament al #{posicio} de {territori_label} amb «{canco}». 🚀",
        "long": "Entrada per la porta gran. {artista} es planten al #{posicio} de {territori_label} amb «{canco}» a la primera setmana. 🚀",
    },
    {
        "short": "{canco} debuta al #{posicio} 🎯",
        "medium": "«{canco}» de {artista} entra de cop al #{posicio} del Top {territori_label}. 🎯",
        "long": "Què tal? «{canco}» de {artista} debuta al #{posicio} del Top {territori_label}. No s'ho ha pres de broma. 🎯",
    },
    {
        "short": "Sorpresa al #{posicio}: {artista} ✨",
        "medium": "Sorpresa al Top {territori_label}: {artista} salten directament al #{posicio} amb «{canco}». ✨",
        "long": "Sorpresa al Top {territori_label}. {artista} salten directament al #{posicio} amb «{canco}» sense passar per cap setmana de transició. ✨",
    },
    {
        "short": "{artista} ho fan a la primera 💥",
        "medium": "Ho fan a la primera: {artista} entren al #{posicio} de {territori_label} amb «{canco}». 💥",
        "long": "Ho fan a la primera. {artista} aterren al #{posicio} del Top {territori_label} amb «{canco}», sense rondalla prèvia. 💥",
    },
    {
        "short": "Directes al #{posicio}: {canco} 🔝",
        "medium": "Directes al cim: «{canco}» de {artista} entra al #{posicio} de {territori_label}. 🔝",
        "long": "Directes al cim. «{canco}» de {artista} debuta al #{posicio} del Top {territori_label} aquesta setmana. 🔝",
    },
    {
        "short": "Top 3 de cop · {artista} 🎼",
        "medium": "{artista} entren al Top 3 de {territori_label} a la primera amb «{canco}» (#{posicio}). 🎼",
        "long": "Top 3 sense escala. {artista} debuten al #{posicio} del Top {territori_label} amb «{canco}». 🎼",
    },
    {
        "short": "{canco} pica fort: #{posicio} 🥊",
        "medium": "Cançó nova, picada forta: {artista} entren al #{posicio} de {territori_label} amb «{canco}». 🥊",
        "long": "Cançó nova, picada forta. {artista} es planten al #{posicio} del Top {territori_label} amb «{canco}» a la primera. 🥊",
    },
    {
        "short": "Aquí venen: {artista} al #{posicio} 👋",
        "medium": "Aquí venen. {artista} debuten al #{posicio} de {territori_label} amb «{canco}». 👋",
        "long": "Aquí venen. {artista} es presenten al #{posicio} del Top {territori_label} amb «{canco}», ja sense gens de timidesa. 👋",
    },
    {
        "short": "{artista}: #{posicio} de bones a primeres 🎶",
        "medium": "Cap d'asaig: {artista} entren al #{posicio} de {territori_label} amb «{canco}» de bones a primeres. 🎶",
        "long": "Cap d'asaig. {artista} fan la primera al #{posicio} del Top {territori_label} amb «{canco}» de bones a primeres. 🎶",
    },
    {
        "short": "Bona setmana per a {artista} 🎉",
        "medium": "Setmana per a celebrar: {artista} debuten al #{posicio} de {territori_label} amb «{canco}». 🎉",
        "long": "Setmana per a celebrar. {artista} entren amb «{canco}» directament al #{posicio} del Top {territori_label}. 🎉",
    },
    {
        "short": "{canco} ha sortit i ja és al #{posicio} 🆕",
        "medium": "Cançó nova de {artista}: «{canco}» ja és al #{posicio} de {territori_label}. 🆕",
        "long": "Recent recent. {artista} treuen «{canco}» i ja la trobem al #{posicio} del Top {territori_label}. 🆕",
    },
    {
        "short": "Mira qui ha arribat al #{posicio} 👀",
        "medium": "Mira qui ha arribat al Top {territori_label}: {artista} al #{posicio} amb «{canco}». 👀",
        "long": "Mira qui ha arribat. {artista} debuten al #{posicio} del Top {territori_label} aquesta setmana amb «{canco}». 👀",
    },
    {
        "short": "{artista}, debut al cim · #{posicio} 🎬",
        "medium": "Debut al cim: {artista} aterren al #{posicio} de {territori_label} amb «{canco}». 🎬",
        "long": "Debut al cim. {artista} aterren al #{posicio} del Top {territori_label} sense avís previ, amb «{canco}». 🎬",
    },
    {
        "short": "Entrada solta de {canco} · #{posicio} 🎵",
        "medium": "Entrada solta: «{canco}» de {artista} es planta al #{posicio} de {territori_label}. 🎵",
        "long": "Entrada solta. «{canco}» de {artista} apareix de cop al #{posicio} del Top {territori_label} sense haver-hi passat abans. 🎵",
    },
    {
        "short": "{artista} no es presenten poc · #{posicio} 💫",
        "medium": "{artista} no es presenten poc: directament al #{posicio} de {territori_label} amb «{canco}». 💫",
        "long": "{artista} no es presenten poc. La primera setmana al Top {territori_label} els deixa al #{posicio} amb «{canco}». 💫",
    },
]


# ── A5 multiple cançons per artista (≥3) ─────────────────────────
A5_ARTISTA_MULTIPLE = [
    {
        "short": "{artista} copen {territori_label} · {n_cancons} cançons 🎶",
        "medium": "{artista} signen {n_cancons} cançons al Top {territori_label} aquesta setmana. 🎶",
        "long": "{artista} fan història al Top {territori_label}: {n_cancons} cançons seves a la llista d'aquesta setmana. 🎶",
    },
    {
        "short": "{n_cancons} cançons de {artista} al top 🔥",
        "medium": "{n_cancons} cançons de {artista} simultàniament al Top {territori_label}. Domini total. 🔥",
        "long": "Domini total. {artista} col·loquen {n_cancons} cançons al Top {territori_label} aquesta setmana. 🔥",
    },
    {
        "short": "{artista} prenen {territori_label} 🎤",
        "medium": "Setmana d'{artista}: {n_cancons} cançons seves al Top {territori_label}. 🎤",
        "long": "Setmana de {artista}. {n_cancons} cançons seves estan al Top {territori_label}. Una rere l'altra. 🎤",
    },
    {
        "short": "Top monopolitzat: {artista} (x{n_cancons}) 🎯",
        "medium": "Top monopolitzat. {artista} col·loquen {n_cancons} cançons al cim de {territori_label}. 🎯",
        "long": "Top monopolitzat. {artista} arriben a {n_cancons} cançons al Top {territori_label} simultàniament. 🎯",
    },
    {
        "short": "{artista} per tot arreu · {n_cancons} 🌊",
        "medium": "{artista} per tot arreu: {n_cancons} cançons al Top {territori_label}. 🌊",
        "long": "{artista} per tot arreu. {n_cancons} cançons seves circulen alhora pel Top {territori_label}. 🌊",
    },
    {
        "short": "Pas a {artista}: {n_cancons} entrades 🚪",
        "medium": "Feu pas. {artista} signen {n_cancons} entrades al Top {territori_label}. 🚪",
        "long": "Feu pas. {artista} ocupen {n_cancons} llocs del Top {territori_label} aquesta setmana. 🚪",
    },
    {
        "short": "{n_cancons} vegades {artista} al top 🎼",
        "medium": "{n_cancons} vegades {artista} al Top {territori_label}. Aquí no s'amaguen. 🎼",
        "long": "{n_cancons} cops {artista} al Top {territori_label} aquesta setmana. Aquí no s'amaguen. 🎼",
    },
    {
        "short": "{artista}, x{n_cancons} al top ⚡",
        "medium": "{artista} multipliquen: {n_cancons} cançons al Top {territori_label}. ⚡",
        "long": "{artista} multipliquen. {n_cancons} cançons seves comparteixen el Top {territori_label} aquesta setmana. ⚡",
    },
    {
        "short": "Setmana de {artista} · {n_cancons} 🎙️",
        "medium": "Setmana de {artista}: {n_cancons} cançons seves al Top {territori_label}. 🎙️",
        "long": "Setmana de {artista}. {n_cancons} cançons seves fan rotllo al Top {territori_label}. 🎙️",
    },
    {
        "short": "{artista}, dominadors de {territori_label} 👑",
        "medium": "{artista}, dominadors de {territori_label}: {n_cancons} cançons al top. 👑",
        "long": "{artista}, dominadors de {territori_label}. {n_cancons} cançons seves al Top aquesta setmana. 👑",
    },
    {
        "short": "{n_cancons} cançons, un sol nom: {artista} ✨",
        "medium": "{n_cancons} cançons, un sol nom al Top {territori_label}: {artista}. ✨",
        "long": "{n_cancons} cançons, un sol nom. {artista} marquen el Top {territori_label} aquesta setmana amb totes elles. ✨",
    },
    {
        "short": "Tot {artista}: {n_cancons} cançons 🎶",
        "medium": "Tot {artista}. {n_cancons} cançons seves al Top {territori_label}. 🎶",
        "long": "Tot {artista}, tot {artista}. {n_cancons} cançons seves al Top {territori_label} aquesta setmana. 🎶",
    },
    {
        "short": "{artista} colpegen fort · x{n_cancons} 🥊",
        "medium": "{artista} colpegen fort: {n_cancons} cançons al Top {territori_label}. 🥊",
        "long": "{artista} colpegen fort. {n_cancons} cançons seves a la llista del Top {territori_label}. 🥊",
    },
    {
        "short": "{n_cancons} entries de {artista} 📈",
        "medium": "{artista} amb {n_cancons} entrades simultànies al Top {territori_label}. 📈",
        "long": "{artista} ocupen {n_cancons} llocs simultanis del Top {territori_label}. Hi pots passejar amb la seva playlist. 📈",
    },
    {
        "short": "{artista} per tot el top ({n_cancons}) 🌟",
        "medium": "{artista} apareixen {n_cancons} cops al Top {territori_label}. Setmana brutal. 🌟",
        "long": "{artista} apareixen {n_cancons} cops al Top {territori_label}. Una setmana brutal per a ells. 🌟",
    },
]


# ── Public table ──────────────────────────────────────────────────
PHRASES: dict[str, list[dict]] = {
    "a2_streak": A2_STREAK,
    "a4_debut_alt": A4_DEBUT_ALT,
    "a5_artista_multiple": A5_ARTISTA_MULTIPLE,
}
