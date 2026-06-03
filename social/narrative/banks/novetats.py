"""Phrase bank for the novetats narrative engine (audit #5, 2026-06-01).

Parallel to `banks/hero.py` but for the weekly new-release roundups
(`nous_albums` / `nous_singles`). Detectors live in
`social/narrative/novetats.py`; the composer in
`composers/novetats.py`.

Placeholders (filled by `novetats._novetat_data`):
  {artista} {de_artista} {per_artista}  — artist + preposition variants
  {titol}                               — the release title
  {tipus_paraula}                       — "àlbum" / "single" / "EP"
  {dies_str}                            — agreement-correct days ("1 dia")
  {segell}                              — record label (n4 only)
  {n_total}                             — number of releases this week

No territori placeholders — novetats aren't territori-specific.
"""

from __future__ import annotations

# n1 — a release by an artist already present in the weekly top.
N1_DEBUT_ARTIST_KNOWN = {
    "short": [
        "Cara coneguda del top: {artista} estrena «{titol}» 🎧",
        "{artista}, habitual del rànquing, treu «{titol}» 🆕",
        "Novetat d'un nom del top: «{titol}» {de_artista} ✨",
        "{artista} torna amb «{titol}» 🔊",
        "Del top a la novetat: «{titol}», {de_artista} 🎶",
    ],
    "medium": [
        "Un nom que ja sona al top torna amb material nou: {artista} publica «{titol}», fa {dies_str}. 🎧",
        "{artista}, presència habitual al rànquing, estrena «{titol}» ({tipus_paraula} de fa {dies_str}). 🆕",
        "Novetat d'una cara coneguda del top: «{titol}», {de_artista}, ja és aquí des de fa {dies_str}. ✨",
        "Del rànquing a la sortida nova: {artista} treu «{titol}», publicat fa {dies_str}. 🔊",
    ],
    "long": [
        "Un nom que el top ja coneix torna amb material fresc: {artista} publica «{titol}», {tipus_paraula} sortit fa {dies_str}. Quan un artista amb presència recent al rànquing estrena, val la pena seguir-li la pista: el salt de la novetat al top sol ser curt. 🎧",
        "{artista}, una cara habitual del rànquing, signa una de les novetats de la setmana amb «{titol}» (fa {dies_str}). Les estrenes d'artistes ja consolidats al top són les que tenen més números d'aterrar-hi de nou aviat. ✨",
        "De les sortides de la setmana, una destaca per la firma: {artista}, que el top ja ha vist, estrena «{titol}» fa {dies_str}. La trajectòria recent al rànquing fa d'aquesta novetat una de les que mirarem de prop. 🔊",
    ],
}

# n2 — the first release we have ever catalogued from this artist.
N2_FIRST_RELEASE = {
    "short": [
        "Estrena absoluta: «{titol}», {de_artista} 🌱",
        "Primer llançament {de_artista}: «{titol}» 🐣",
        "Nova firma: {artista} debuta amb «{titol}» ✨",
        "Primera vegada per a {artista}: «{titol}» 🎬",
        "Debut discogràfic {de_artista}: «{titol}» 🌟",
    ],
    "medium": [
        "Primera aparició al nostre catàleg: {artista} debuta amb «{titol}», {tipus_paraula} de fa {dies_str}. 🌱",
        "Una firma nova entra en escena: «{titol}», {de_artista}, és el primer llançament que li detectem (fa {dies_str}). 🐣",
        "Debut discogràfic: {artista} estrena «{titol}» fa {dies_str}, la primera obra seva que arxivem. ✨",
        "Cara nova de la setmana: «{titol}» és el primer {tipus_paraula} {de_artista} que registrem, sortit fa {dies_str}. 🎬",
    ],
    "long": [
        "Una firma del tot nova entra a escena: {artista} debuta amb «{titol}», {tipus_paraula} sortit fa {dies_str} i el primer llançament seu que detectem. Els debuts són sempre incerts, però són també l'origen de tota trajectòria; els seguim des del primer dia. 🌱",
        "De les novetats de la setmana, «{titol}» té un valor especial: és la primera obra {de_artista} que arxivem. Cada debut és una incògnita, i precisament per això mereix una ullada abans que ningú més hi pari atenció. ✨",
        "{artista} fa el seu primer pas discogràfic amb «{titol}» (fa {dies_str}). Començar a seguir un artista des del seu debut és la millor manera d'entendre'n el recorregut quan, si tot va bé, arribi al top. 🐣",
    ],
}

# n3 — the release carries a featuring / collaboration.
N3_COLLABORATION = {
    "short": [
        "Col·laboració nova: «{titol}», {de_artista} 🤝",
        "{artista} treu «{titol}» amb featuring 🎙️",
        "Trobada d'artistes a «{titol}» {de_artista} 🔗",
        "Novetat a quatre mans: «{titol}», {de_artista} 🎶",
    ],
    "medium": [
        "Una col·laboració entre la novetat de la setmana: «{titol}», {de_artista}, arriba amb featuring (fa {dies_str}). 🤝",
        "{artista} signa «{titol}» amb col·laboració convidada, {tipus_paraula} de fa {dies_str}. 🎙️",
        "Trobada d'artistes a la nova sortida: «{titol}», {de_artista}, reuneix més d'una firma (fa {dies_str}). 🔗",
        "Novetat compartida: «{titol}», {de_artista}, porta una col·laboració, publicada fa {dies_str}. 🎶",
    ],
    "long": [
        "Les col·laboracions són sovint les sortides més interessants de la setmana, i «{titol}», {de_artista}, n'és una: el {tipus_paraula}, de fa {dies_str}, reuneix més d'una firma. Quan dos noms s'ajunten, el resultat acostuma a portar públics que abans no es creuaven. 🤝",
        "{artista} aposta per la col·laboració a «{titol}» (fa {dies_str}). Les trobades entre artistes són una de les vies més fèrtils de l'escena en català, i aquesta novetat s'hi suma amb una sortida a diverses mans. 🔗",
    ],
}

# n4 — release on a label with repeated presence in the top.
N4_LABEL_RELEASE = {
    "short": [
        "{segell} suma novetat: «{titol}», {de_artista} 🏷️",
        "Nova sortida del segell {segell}: «{titol}» 💿",
        "{segell} continua: «{titol}», {de_artista} 🎚️",
        "De la casa {segell}: «{titol}» {de_artista} 📀",
    ],
    "medium": [
        "El segell {segell}, amb presència repetida al top, suma novetat: «{titol}», {de_artista} (fa {dies_str}). 🏷️",
        "Nova sortida de la casa {segell}: «{titol}», {de_artista}, {tipus_paraula} de fa {dies_str}. 💿",
        "{segell} continua alimentant el rànquing: estrena «{titol}» {de_artista}, fa {dies_str}. 🎚️",
        "Del catàleg de {segell}, un segell habitual del top: «{titol}», {de_artista} (fa {dies_str}). 📀",
    ],
    "long": [
        "El segell {segell}, que el top coneix bé, suma una nova sortida: «{titol}», {de_artista}, {tipus_paraula} de fa {dies_str}. Quan un segell acumula presència al rànquing, les seves novetats arrosseguen una expectativa que val la pena registrar. 🏷️",
        "Una novetat amb segell de garantia: {segell}, casa de més d'un nom del top, publica «{titol}» {de_artista} (fa {dies_str}). El criteri d'un segell consolidat sovint és un bon predictor d'on val la pena fixar-s'hi. 💿",
    ],
}

# Fallback — generic roundup line when no detector fires.
FALLBACK_NOVETAT = {
    "short": [
        "Novetat de la setmana: «{titol}», {de_artista} 🎵",
        "Nova sortida: «{titol}» {de_artista} 🆕",
        "«{titol}», {de_artista}, ja es pot escoltar 🔊",
        "Estrena recent: «{titol}», {de_artista} ✨",
    ],
    "medium": [
        "Entre les novetats de la setmana, «{titol}», {de_artista}, {tipus_paraula} sortit fa {dies_str}. 🎵",
        "Nova sortida en català: «{titol}», {de_artista}, publicada fa {dies_str}. 🆕",
        "«{titol}», {de_artista}, s'afegeix a les estrenes de la setmana (fa {dies_str}). 🔊",
    ],
    "long": [
        "Entre les estrenes de la setmana destaca «{titol}», {de_artista}, {tipus_paraula} sortit fa {dies_str}. Cada setmana l'escena en català suma sortides noves; aquesta és una de les que recollim per a no perdre-les de vista. 🎵",
        "La setmana porta noves sortides en català, i «{titol}», {de_artista} (fa {dies_str}), n'és una. El degoteig constant de novetats és, en si mateix, una bona notícia per a l'escena. 🆕",
    ],
}


NOVETATS: dict[str, dict[str, list[str]]] = {
    "n1_debut_artist_known": N1_DEBUT_ARTIST_KNOWN,
    "n2_first_release": N2_FIRST_RELEASE,
    "n3_collaboration": N3_COLLABORATION,
    "n4_label_release": N4_LABEL_RELEASE,
    "fallback_novetat": FALLBACK_NOVETAT,
}
