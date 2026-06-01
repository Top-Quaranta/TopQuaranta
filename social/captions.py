"""Caption (text body) generator for social posts.

# Spec: docs/architecture/social.md

Two paths live here:

1. **Top-of-the-week captions** (`top_ppcc` / `top_territorial`) go
   through the narrative engine via `compose_for_channel`. Each
   channel has its own composer that picks a hero scenario + the
   right length tier + the right mention style for that network.
   `caption_top` and `caption_short` are kept as thin string-only
   wrappers around `compose_for_channel` so existing call sites
   don't break.

2. **Novetats captions** (`nous_albums` / `nous_singles`) keep the
   legacy plain-list format — there are no narrative scenarios for
   weekly release roundups. `caption_novetats` is untouched and
   used directly by `publicar_social.py`; the short-form variant is
   handled by the `_caption_short_legacy` path inside
   `compose_for_channel`.

Robustness: every engine call sits inside a try/except. If the
narrative pipeline fails for ANY reason (DB hiccup, registry
crash, template bug, …) the channel falls back to the legacy
caption format and logs the exception. A publication never goes
out empty because of an engine bug.

Instagram caps captions at 2 200 chars and doesn't make links
clickable in the feed, so the IG body is intentionally compact:
a title + the listing + hashtags + handle.
"""

from __future__ import annotations

import datetime
import logging
from urllib.parse import urlparse

from music.dates import project_week_number
from social.narrative.utils import TERRITORI_SHORT

logger = logging.getLogger(__name__)

# Short standalone territori label (renderer pills, OG/story titles,
# caption headers). Single source of truth in `social.narrative.utils`
# so the renderer and the narrative engine never drift — BAL is
# "Balears" (not the peninsular-sounding "Illes"), PPCC is "Global"
# (never "Països Catalans"). The genitive form ("de les Illes Balears",
# "del País Valencià") used after "Top …"/"al Nè …" lives there too as
# `territori_label` and is applied by the narrative composers.
TERRITORI_NOM = TERRITORI_SHORT

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

# Novetats hashtags — TitleCase + diacritics, consistent with the top
# posts' bank (`social/narrative/banks/hashtags.py`). Audit #2: the old
# lowercase set (#musicaencatala …) clashed with the tops' #TopQuaranta.
HASHTAGS_NOVETATS = ["#TopQuaranta", "#MúsicaEnCatalà", "#Novetats"]

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


def _artist_label(entry: dict, *, use_handle: bool) -> str:
    """Pick the in-caption label for a top/novetats entry.

    `use_handle=True` (Instagram path): try the artist's Instagram
    handle so the caption autolinks and notifies them. Falls back to
    the plain name if no handle is stored. We only autolink the
    main artist — collaborators don't have their handles stored.

    `use_handle=False` (Mastodon, Bluesky, Telegram, Newsletter): the
    plain comma-joined list of the main artist + collaborators. The
    `@handle` is Instagram-specific and would show up as broken-looking
    literal text on every other network (mention syntax differs by
    platform, and we don't store handles per network). Decision
    2026-05-16 + Tasca B2 2026-05-18: collaborators added to the
    plain-name surfaces via `artistes_noms`.
    """
    if use_handle:
        u = instagram_username(entry.get("artista_instagram_url"))
        if u:
            return f"@{u}"
    names = entry.get("artistes_noms") or [entry.get("artista_nom") or "—"]
    return _join_artists_text(names, max_chars=80)


def _join_artists_text(names: list[str], *, max_chars: int = 80) -> str:
    """Comma-join a list of artist names for plain-text surfaces.

    Same shape semantics as the renderer's `_join_artists` but
    measured in characters rather than pixels — used by Mastodon /
    Bluesky / Telegram / Newsletter row listings where the constraint
    is the channel char budget, not a pixel slot. Drops trailing
    names one at a time and appends `…` after the last fitting name;
    falls back to char-level truncation of the first name only as a
    last resort.
    """
    if not names:
        return "—"
    full = ", ".join(names)
    if len(full) <= max_chars:
        return full
    for i in range(len(names) - 1, 0, -1):
        candidate = ", ".join(names[:i]) + "…"
        if len(candidate) <= max_chars:
            return candidate
    # Only the main artist still doesn't fit — char-truncate the
    # main name itself with an ellipsis. Take max_chars-1 chars of
    # the name + 1 char for the ellipsis. If max_chars < 2 we can't
    # even fit the ellipsis; return a bare prefix as a degenerate
    # safety net.
    first = names[0]
    if max_chars >= 2:
        return first[: max_chars - 1] + "…"
    return first[:max_chars]


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


def _caption_short_legacy(
    tipus: str,
    territori: str,
    setmana: datetime.date,
    entries: list[dict],
    *,
    max_chars: int = 480,
    n: int = 5,
    channel: str = "",
) -> str:
    """Legacy plain-list short caption (pre-narrative-engine).

    Kept as the fallback path inside `compose_for_channel` when the
    engine raises, and as the direct path for novetats (which have
    no narrative scenarios). Also still used by callers that omit
    `channel` (no UTM, no engine — bare-bones safe default).

    `entries` may be either top entries (with `posicio`/`canco_nom`)
    or novetats items (with `nom`). We sniff the keys.

    `channel`, when given, switches the footer link to a UTM-tagged
    URL via `utm_url()` so the analytics dashboard can attribute
    landings per channel × campaign.
    """
    nom = TERRITORI_NOM.get(territori, territori or "")
    label = _setmana_label(setmana)
    # Non-Instagram channels: plain name only. @handle would render
    # as broken-looking literal text on Mastodon/Bluesky/Telegram.
    if tipus in ("nous_albums", "nous_singles"):
        title = "Nous àlbums" if tipus == "nous_albums" else "Nous singles"
        header = f"{title} · {label}\n"
        rows = []
        for e in entries[:n]:
            artist_label = _artist_label(e, use_handle=False)
            rows.append(f"· {e.get('nom', '—')} — {artist_label}")
    else:
        header = f"Top {nom} · {label}\n"
        rows = []
        for e in entries[:n]:
            artist_label = _artist_label(e, use_handle=False)
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


def _caption_top_legacy(
    tipus: str, territori: str, setmana: datetime.date, entries: list[dict]
) -> str:
    """Legacy IG-feed top caption (pre-narrative-engine). Same shape
    as before: title + numbered list + always-on hashtags. Kept as
    the fallback path when `compose_for_channel` can't run the
    engine.

    `entries` is a list of {posicio, canco_nom, artista_nom,
    artista_instagram_url?} for the rows being featured."""
    nom = TERRITORI_NOM.get(territori, territori)
    label = _setmana_label(setmana)
    header = f"Top — {nom}\n{label}\n\n"
    body_lines = []
    for e in entries:
        # Instagram-only caption: prefer @handle so the post both
        # autolinks and notifies the artist. Plain name fallback.
        artist_label = _artist_label(e, use_handle=True)
        body_lines.append(f"{e['posicio']}. {e['canco_nom']} · {artist_label}")
    body = "\n".join(body_lines)
    footer = "\n\n" + _hashtags(territori)
    text = header + body + footer
    if len(text) > 2200:
        # Truncate trailing entries gracefully to fit the limit.
        max_body = 2200 - len(header) - len(footer) - 10
        text = header + body[:max_body] + "…" + footer
    return text


# ── Narrative-engine dispatcher ─────────────────────────────────────
#
# `compose_for_channel` is the single entrypoint for top captions
# across every publishing channel. It runs the scenario detector,
# delegates to the channel-specific composer, and returns the
# assembled text along with the `phrase_ids` that were actually
# used (so the caller can mark them post-publication).
#
# Every step is wrapped in a try/except: if anything inside the
# engine raises, we log and fall back to the legacy caption shape.
# Phrase ids are returned empty in that case, so `mark_used` is a
# no-op and the bug doesn't poison the registry either.
#
# Novetats (`nous_albums` / `nous_singles`) don't go through the
# engine at all — there are no narrative scenarios for weekly
# release roundups. They route to the legacy caption straight.

_NARRATIVE_TIPUS = ("top_ppcc", "top_territorial")

_CHANNEL_MAX_CHARS = {
    "mastodon": 480,
    "bluesky": 280,
    "telegram": 900,
    "newsletter": 9999,
}


def _legacy_for(channel: str, tipus: str, territori: str, setmana, entries):
    """Pick the right legacy function for (channel, tipus). Used as
    fallback when the engine raises and as the primary path for
    novetats. Returns a plain string."""
    if channel == "instagram_feed":
        if tipus in ("nous_albums", "nous_singles"):
            return caption_novetats(tipus, setmana, entries)
        return _caption_top_legacy(tipus, territori, setmana, entries)
    # short channels
    return _caption_short_legacy(
        tipus,
        territori,
        setmana,
        entries,
        max_chars=_CHANNEL_MAX_CHARS.get(channel, 480),
        channel=channel if channel != "newsletter" else channel,
    )


def compose_for_channel(
    channel: str,
    tipus: str,
    territori: str,
    setmana: datetime.date,
    entries: list[dict],
    *,
    rng=None,
) -> dict:
    """Build the post body for `channel` via the narrative engine.

    Returns a dict `{text, hashtags, cta, phrase_ids}`. `phrase_ids`
    is the list of `phrase_id` strings actually emitted into the
    body — the caller is expected to `registry.mark_used(...)` each
    of them AFTER a successful publication (not at compose time —
    a dry-run or a failed publish should not poison the registry).

    `channel` ∈ {instagram_feed, instagram_story, mastodon, bluesky,
    telegram, newsletter}.

    Fallback contract: if anything inside the engine raises, log and
    return the legacy caption shape with `phrase_ids=[]`. The
    publication never goes out empty because of an engine bug.
    """
    # Novetats bypass the engine entirely.
    if tipus not in _NARRATIVE_TIPUS:
        return {
            "text": _legacy_for(channel, tipus, territori, setmana, entries),
            "hashtags": [],
            "cta": "",
            "phrase_ids": [],
        }

    try:
        # Imports are local: keeps captions.py importable in
        # contexts without Django ready (e.g. some unit tests that
        # don't load the full app) — only the engine path needs the
        # DB. Also avoids a circular import at module load
        # (composers import _artist_label / _setmana_label from
        # here).
        from social.narrative import scenarios as scen
        from social.narrative.composers import (
            bluesky,
            instagram_feed,
            instagram_story,
            mastodon,
            newsletter,
            telegram,
        )

        composer = {
            "instagram_feed": instagram_feed,
            "instagram_story": instagram_story,
            "mastodon": mastodon,
            "bluesky": bluesky,
            "telegram": telegram,
            "newsletter": newsletter,
        }[channel]

        scenarios = scen.detect_all(territori, setmana)
        result = composer.compose(
            scenarios,
            entries,
            territori=territori,
            setmana=setmana,
            rng=rng,
        )
        # Normalise: every composer must surface phrase_ids; default
        # to [] if a composer was updated lazily.
        result.setdefault("phrase_ids", [])
        result.setdefault("hashtags", [])
        result.setdefault("cta", "")
        return result
    except Exception:
        # Engine path failed. Log with full context and fall back to
        # the legacy caption — the post must go out.
        logger.exception(
            "narrative engine failed; falling back to legacy caption "
            "(channel=%s tipus=%s territori=%s setmana=%s)",
            channel,
            tipus,
            territori,
            setmana,
        )
        return {
            "text": _legacy_for(channel, tipus, territori, setmana, entries),
            "hashtags": [],
            "cta": "",
            "phrase_ids": [],
        }


# ── Public string-only wrappers (signature-stable) ──────────────────
#
# These are the entrypoints the rest of the codebase already calls.
# They keep their original (text-returning) signature so existing
# callers — and tests — continue to work unchanged. New callers
# that also need phrase_ids should use `compose_for_channel`
# directly.


def caption_top(
    tipus: str, territori: str, setmana: datetime.date, entries: list[dict]
) -> str:
    """Instagram-feed top caption. Now backed by the narrative
    engine for top types; falls back to the legacy plain-list
    shape on engine failure or for novetats."""
    return compose_for_channel("instagram_feed", tipus, territori, setmana, entries)[
        "text"
    ]


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
    """Compact caption for Mastodon / Bluesky / Telegram / Newsletter.

    When `channel` is one of those four AND `tipus` is a top type,
    we route through the narrative engine. Otherwise (no channel,
    or novetats) we keep the legacy plain-list shape exactly as
    before — including `max_chars` and `n`, which the engine
    ignores in favour of per-channel composer budgets.
    """
    if channel in _CHANNEL_MAX_CHARS and tipus in _NARRATIVE_TIPUS:
        return compose_for_channel(channel, tipus, territori, setmana, entries)["text"]
    return _caption_short_legacy(
        tipus,
        territori,
        setmana,
        entries,
        max_chars=max_chars,
        n=n,
        channel=channel,
    )


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
        # Tasca B2: include collaborators in alt-text so a screen-
        # reader user hears the same artist list a sighted user sees
        # on the painted slide. 100-char budget per row is generous
        # — alt-text isn't pixel-bounded.
        names = e.get("artistes_noms") or [e.get("artista_nom") or "—"]
        artists = _join_artists_text(names, max_chars=100)
        rows.append(
            f"{e.get('posicio', '?')} {e.get('canco_nom', '—')} " f"de {artists}"
        )
    return head + ", ".join(rows) + "."


def _alt_album_slide(item: dict) -> str:
    # Tasca C (2026-05-18): article-stripping for Catalan
    # contractions on artist names with leading articles
    # ("Els Catarres" → "dels Catarres").
    from social.narrative.utils import with_preposition

    artist = item.get("artista_nom", "—")
    return f"Nou àlbum: «{item.get('nom', '—')}» {with_preposition(artist, 'de')}"


def _alt_singles_slide(chunk: list[dict], start_idx: int, end_idx: int) -> str:
    from social.narrative.utils import with_preposition

    head = f"Nous singles {start_idx} a {end_idx}: "
    rows = [
        f"«{e.get('nom', '—')}» {with_preposition(e.get('artista_nom', '—'), 'de')}"
        for e in chunk
    ]
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
        # Instagram-only caption: see caption_top for the rationale.
        artist_label = _artist_label(e, use_handle=True)
        body_lines.append(f"· {e['nom']} — {artist_label}")
    body = "\n".join(body_lines)
    footer = "\n\n" + " ".join(HASHTAGS_NOVETATS)
    text = header + body + footer
    if len(text) > 2200:
        max_body = 2200 - len(header) - len(footer) - 10
        text = header + body[:max_body] + "…" + footer
    return text
