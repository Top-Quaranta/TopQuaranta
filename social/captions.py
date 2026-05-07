"""Caption (text body) generator for Instagram posts.

Instagram caps captions at 2 200 chars and doesn't make links
clickable in the feed, so the body is intentionally compact: a
title + the listing + hashtags + handle.
"""

from __future__ import annotations

import datetime
from urllib.parse import urlparse

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


def utm_url(
    channel: str,
    tipus: str,
    setmana: datetime.date,
    *,
    base: str = "https://topquaranta.cat",
    territori: str = "",
) -> str:
    """Build the public URL for a social-post footer with UTM tags.

    Same convention across every channel so the analytics dashboard
    can pivot cleanly:

        utm_source   = channel slug (mastodon, bluesky, telegram,
                       newsletter, instagram)
        utm_medium   = "social" everywhere except newsletter ("email")
        utm_campaign = "<tipus>-<YYYY>-w<WW>" using the project-week
                       numbering so the campaign name is the same one
                       the post body shows ("Setmana N").

    `territori` is appended to the campaign when present so a Top
    Catalunya post and a Top País Valencià post the same week land in
    different campaign buckets ("top_territorial-2026-w19-cat" vs
    "top_territorial-2026-w19-val"). Top global + novetats stay
    plain. Lowercased + ASCII-only because the analytics dim columns
    are stored lowercase by the ingest.
    """
    medium = "email" if channel == "newsletter" else "social"
    dissabte = setmana + datetime.timedelta(days=5)
    week_n = project_week_number(dissabte)
    campaign = f"{tipus}-{dissabte.year}-w{week_n:02d}"
    if territori and territori not in ("", "PPCC"):
        campaign = f"{campaign}-{territori.lower()}"
    qs = f"utm_source={channel}&utm_medium={medium}&utm_campaign={campaign}"
    # Append `?qs` when the base already has a path segment (e.g.
    # `…/top`) and `/?qs` when it's the bare host (so the URL still
    # has a clean trailing slash on the home route).
    parsed = urlparse(base)
    sep = "?" if parsed.path and parsed.path != "/" else "/?"
    return f"{base.rstrip('/')}{sep}{qs}"


def caption_short(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    entries: list[dict],
    *,
    max_chars: int = 480,
    n: int = 5,
    channel: str = "",
) -> str:
    """Compact caption for Mastodon (500 char default) and Bluesky
    (300 char) — list the top-N + a link to the public site.

    `entries` may be either top entries (with `posicio`/`canco_nom`)
    or novetats items (with `nom`). We sniff the keys.

    `channel`, when given, switches the footer link to a UTM-tagged
    URL via `utm_url()` so the analytics dashboard can attribute
    landings per channel × campaign. Falls back to the plain
    `https://topquaranta.cat` when omitted (safe default, doesn't
    break callers that don't know about channels — e.g. the IG
    flow, where captions are non-clickable anyway).
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
    if channel:
        link = utm_url(channel, tipus, setmana, territori=territori)
    else:
        link = "https://topquaranta.cat"
    footer = f"\n\nTot el top a {link}"
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


# ── Per-slide alt text (a11y) ───────────────────────────────────────
#
# A single function builds the per-slide alt-text list used by every
# multi-image channel (IG carousel, Mastodon media, Bluesky embed.images,
# Telegram media-group). Each slide gets its own alt — screen-reader
# users hear something like "Top setmanal de cançons en català de
# Catalunya. Posicions 1 a 10: 1 Tutu Turú de Siderland, 2 Estrelles
# de Max Navarro, ..." instead of a generic "Top CAT, posicions 1-10".
#
# The renderer's slide chunking is mirrored here (same as
# `_slide_tags` in publicar_social.py): for top, 10 entries per slide;
# nous_albums, 1 album per slide; nous_singles, bin-packed.
#
# `n_slides` includes the cover slide. `slide_alts(...)[i]` corresponds
# to `paths[i]`. Returns exactly `n_slides` items (caller indexes by
# slide position).


def _alt_top_portada(territori: str, setmana: datetime.date) -> str:
    nom = TERRITORI_NOM.get(territori, territori or "")
    return f"Portada del Top setmanal de {nom} · {_setmana_label(setmana)}"


def _alt_novetats_portada(tipus: str, setmana: datetime.date) -> str:
    title = "Nous àlbums" if tipus == "nous_albums" else "Nous singles"
    return f"Portada de {title} · {_setmana_label(setmana)}"


def _alt_top_list(
    territori: str, chunk: list[dict], start_pos: int, end_pos: int
) -> str:
    nom = TERRITORI_NOM.get(territori, territori or "")
    head = (
        f"Top setmanal de cançons en català de {nom}. "
        f"Posicions {start_pos} a {end_pos}: "
    )
    rows = []
    for e in chunk:
        rows.append(
            f"{e.get('posicio', '?')} {e.get('canco_nom', '—')} "
            f"de {e.get('artista_nom', '—')}"
        )
    return head + ", ".join(rows) + "."


def _alt_album_slide(item: dict) -> str:
    return f"Nou àlbum: «{item.get('nom', '—')}» de {item.get('artista_nom', '—')}"


def _alt_singles_slide(chunk: list[dict], start_idx: int, end_idx: int) -> str:
    head = f"Nous singles {start_idx} a {end_idx}: "
    rows = [f"«{e.get('nom', '—')}» de {e.get('artista_nom', '—')}" for e in chunk]
    return head + ", ".join(rows) + "."


def slide_alts(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    entries: list[dict],
    n_slides: int,
) -> list[str]:
    """Per-slide alt-text list, one entry per slide.

    Mirrors the renderer's chunking exactly (same logic as
    `_slide_tags` in publicar_social) so each alt describes the slide
    the screen-reader user is actually on.

    `entries` is `data["entries"]` for top tipus or `data["items"]` for
    novetats. `n_slides` is the total number of slides including the
    cover (index 0).
    """
    out: list[str] = []
    if tipus in ("top_ppcc", "top_territorial"):
        out.append(_alt_top_portada(territori, setmana))
        for page in range(1, n_slides):
            chunk = entries[(page - 1) * 10 : page * 10]
            if not chunk:
                out.append("")
                continue
            start = (page - 1) * 10 + 1
            end = start + len(chunk) - 1
            out.append(_alt_top_list(territori, chunk, start, end))
    elif tipus == "nous_albums":
        out.append(_alt_novetats_portada(tipus, setmana))
        for item in entries[: n_slides - 1]:
            out.append(_alt_album_slide(item))
    elif tipus == "nous_singles":
        out.append(_alt_novetats_portada(tipus, setmana))
        # Mirror render_feed_novetats bin-packing.
        n = len(entries)
        slides = max(1, n_slides - 1)
        per_slide = -(-n // slides) if n else 0
        offset = 0
        for _ in range(slides):
            chunk = entries[offset : offset + per_slide]
            if not chunk:
                out.append("")
            else:
                out.append(_alt_singles_slide(chunk, offset + 1, offset + len(chunk)))
            offset += per_slide
    else:
        out.append("")
    while len(out) < n_slides:
        out.append("")
    return out[:n_slides]


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
