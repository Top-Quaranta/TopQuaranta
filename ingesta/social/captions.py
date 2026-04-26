"""Caption (text body) generator for Instagram posts.

Instagram caps captions at 2 200 chars and doesn't make links
clickable in the feed, so the body is intentionally compact: a
title + the listing + hashtags + handle.
"""

from __future__ import annotations

import datetime

TERRITORI_NOM = {
    "PPCC": "Global · Països Catalans",
    "CAT": "Catalunya",
    "VAL": "País Valencià",
    "BAL": "Illes Balears",
    "AND": "Andorra",
    "CNO": "Catalunya del Nord",
    "FRA": "Franja de Ponent",
    "ALG": "L'Alguer",
    "ALT": "Altres",
}

# Per-territori hashtag (lowercase, no spaces). Always combined with
# the always-on triplet below.
HASHTAG_TERR = {
    "PPCC": "PaïsosCatalans",
    "CAT": "Catalunya",
    "VAL": "PaísValencià",
    "BAL": "IllesBalears",
    "AND": "Andorra",
    "CNO": "CatalunyaNord",
    "FRA": "FranjaPonent",
    "ALG": "Alguer",
}

HASHTAGS_BASE = ["musicaencatala", "topquaranta", "PaïsosCatalans"]

MES_CA = [
    "gener",
    "febrer",
    "març",
    "abril",
    "maig",
    "juny",
    "juliol",
    "agost",
    "setembre",
    "octubre",
    "novembre",
    "desembre",
]


def _setmana_label(setmana: datetime.date) -> str:
    dissabte = setmana + datetime.timedelta(days=5)
    return f"{dissabte.day} de {MES_CA[dissabte.month - 1]}"


def _mention(handle: str | None) -> str:
    """Extract an Instagram @handle from a stored URL like
    `https://instagram.com/foo/`. Returns "" on anything malformed —
    we'd rather drop the mention than crash the caption."""
    if not handle:
        return ""
    h = handle.strip().rstrip("/")
    if "instagram.com" in h:
        h = h.rsplit("/", 1)[-1]
    h = h.lstrip("@")
    if not h or any(c in h for c in " \n\t?&="):
        return ""
    return f"@{h}"


def _hashtags(territori: str) -> str:
    tags = list(HASHTAGS_BASE)
    extra = HASHTAG_TERR.get(territori)
    if extra and extra not in tags:
        tags.append(extra)
    return " ".join(f"#{t}" for t in tags)


def caption_top(
    tipus: str, territori: str, setmana: datetime.date, entries: list[dict]
) -> str:
    """`entries` is a list of {posicio, canco_nom, artista_nom,
    artista_instagram_url?} for the rows being featured."""
    nom = TERRITORI_NOM.get(territori, territori)
    label = _setmana_label(setmana)
    header = f"Top — {nom}\nSetmana del {label}\n\n"
    body_lines = []
    for e in entries:
        mention = _mention(e.get("artista_instagram_url"))
        suffix = f" {mention}" if mention else ""
        body_lines.append(
            f"{e['posicio']}. {e['canco_nom']} · {e['artista_nom']}{suffix}"
        )
    body = "\n".join(body_lines)
    footer = "\n\n" + _hashtags(territori)
    text = header + body + footer
    if len(text) > 2200:
        # Truncate trailing entries gracefully to fit the limit.
        max_body = 2200 - len(header) - len(footer) - 10
        text = header + body[:max_body] + "…" + footer
    return text


def caption_novetats(tipus: str, setmana: datetime.date, entries: list[dict]) -> str:
    label = _setmana_label(setmana)
    title = "Nous àlbums" if tipus == "nous_albums" else "Nous singles"
    header = f"{title} · setmana del {label}\n\n"
    body_lines = []
    for e in entries:
        mention = _mention(e.get("artista_instagram_url"))
        suffix = f" {mention}" if mention else ""
        body_lines.append(f"· {e['nom']} — {e['artista_nom']}{suffix}")
    body = "\n".join(body_lines)
    footer = "\n\n" + " ".join(f"#{t}" for t in HASHTAGS_BASE + ["novetats"])
    text = header + body + footer
    if len(text) > 2200:
        max_body = 2200 - len(header) - len(footer) - 10
        text = header + body[:max_body] + "…" + footer
    return text
