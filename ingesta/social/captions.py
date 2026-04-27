"""Caption (text body) generator for Instagram posts.

Instagram caps captions at 2 200 chars and doesn't make links
clickable in the feed, so the body is intentionally compact: a
title + the listing + hashtags + handle.
"""

from __future__ import annotations

import datetime

from music.dates import project_week_number

TERRITORI_NOM = {
    "PPCC": "Global",
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
    "CAT": "Catalunya",
    "VAL": "PaísValencià",
    "BAL": "IllesBalears",
    "AND": "Andorra",
    "CNO": "CatalunyaNord",
    "FRA": "FranjaPonent",
    "ALG": "Alguer",
}

HASHTAGS_BASE = ["musicaencatala", "topquaranta"]

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
    """User-facing label for a TQ-week. Project-week numbering, not
    raw dates: the week that opens on Sat 25 Apr 2026 = "Setmana 34".
    `setmana` is the ISO Monday stored on SocialPost; the Saturday
    that opens its TQ-week is `setmana + 5d`.
    """
    dissabte = setmana + datetime.timedelta(days=5)
    return f"Setmana {project_week_number(dissabte)}"


def instagram_username(handle: str | None) -> str:
    """Extract a bare IG username (no leading `@`) from a stored
    URL like `https://instagram.com/foo/`. Returns "" on anything
    malformed — used both for caption mentions and for the API's
    `user_tags` payload (which expects raw usernames).
    """
    if not handle:
        return ""
    h = handle.strip().rstrip("/")
    if "instagram.com" in h:
        h = h.rsplit("/", 1)[-1]
    h = h.lstrip("@")
    if not h or any(c in h for c in " \n\t?&="):
        return ""
    return h


def _mention(handle: str | None) -> str:
    """Same extraction as `instagram_username` but prefixed with `@`
    for caption use. Returns "" on malformed input."""
    u = instagram_username(handle)
    return f"@{u}" if u else ""


def _hashtags(territori: str) -> str:
    tags = list(HASHTAGS_BASE)
    extra = HASHTAG_TERR.get(territori)
    if extra and extra not in tags:
        tags.append(extra)
    return " ".join(f"#{t}" for t in tags)


def caption_short(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    entries: list[dict],
    *,
    max_chars: int = 480,
    n: int = 5,
) -> str:
    """Compact caption for Mastodon (500 char default) and Bluesky
    (300 char) — list the top-N + a link to the public site.

    `entries` may be either top entries (with `posicio`/`canco_nom`)
    or novetats items (with `nom`). We sniff the keys.
    """
    nom = TERRITORI_NOM.get(territori, territori or "")
    label = _setmana_label(setmana)
    if tipus in ("nous_albums", "nous_singles"):
        title = "Nous àlbums" if tipus == "nous_albums" else "Nous singles"
        header = f"{title} · {label}\n"
        rows = []
        for e in entries[:n]:
            mention = _mention(e.get("artista_instagram_url"))
            artist_label = mention if mention else e.get("artista_nom", "—")
            rows.append(f"· {e.get('nom', '—')} — {artist_label}")
    else:
        header = f"Top {nom} · {label}\n"
        rows = []
        for e in entries[:n]:
            mention = _mention(e.get("artista_instagram_url"))
            artist_label = mention if mention else e.get("artista_nom", "—")
            rows.append(
                f"{e.get('posicio', '?')}. {e.get('canco_nom', '—')} · {artist_label}"
            )
    body = "\n".join(rows)
    footer = "\n\nTot el top a https://topquaranta.cat"
    text = header + body + footer
    while len(text) > max_chars and rows:
        rows.pop()
        body = "\n".join(rows)
        text = header + body + footer
    return text


def caption_top(
    tipus: str, territori: str, setmana: datetime.date, entries: list[dict]
) -> str:
    """`entries` is a list of {posicio, canco_nom, artista_nom,
    artista_instagram_url?} for the rows being featured."""
    nom = TERRITORI_NOM.get(territori, territori)
    label = _setmana_label(setmana)
    header = f"Top — {nom}\n{label}\n\n"
    body_lines = []
    for e in entries:
        # Prefer the @handle when we have one — it both
        # autolinks in the IG caption and notifies the artist.
        # Fall back to the display name when no handle is stored.
        mention = _mention(e.get("artista_instagram_url"))
        artist_label = mention if mention else e["artista_nom"]
        body_lines.append(f"{e['posicio']}. {e['canco_nom']} · {artist_label}")
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
    header = f"{title} · {label}\n\n"
    body_lines = []
    for e in entries:
        mention = _mention(e.get("artista_instagram_url"))
        artist_label = mention if mention else e["artista_nom"]
        body_lines.append(f"· {e['nom']} — {artist_label}")
    body = "\n".join(body_lines)
    footer = "\n\n" + " ".join(f"#{t}" for t in HASHTAGS_BASE + ["novetats"])
    text = header + body + footer
    if len(text) > 2200:
        max_body = 2200 - len(header) - len(footer) - 10
        text = header + body[:max_body] + "…" + footer
    return text
