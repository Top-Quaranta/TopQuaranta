"""Deterministic linkifier for the newsletter's editorial prose.

This is a POST-PROCESS step, never an LLM step. Given the week's
`name_map` (canonical artist/song strings -> url + kind), it wraps the
FIRST occurrence of each name in the prose:

  * a song  -> ``<em><a href=...>title</a></em>``
  * an artist with a url (the principal) -> ``<strong><a ...>name</a></strong>``
  * an artist without a url (a collaborator, slice 1) -> ``<strong>name</strong>``

Safety rules (so it never produces a false positive):

  * exact, CASE-SENSITIVE match of the canonical strings;
  * longest-match-first with consumed spans (a song title that contains
    an artist name links as the title, not the inner artist);
  * Unicode word boundaries at both ends (no match inside a larger word);
  * apostrophe/quote variants are normalised for the comparison only,
    with offsets preserved 1:1 (so "On T'has..." matches whatever
    apostrophe the prose used, while the displayed text keeps the
    original character);
  * it walks TEXT nodes only and skips the interior of existing
    ``<a>``/``<strong>``/``<em>`` elements, which makes it idempotent;
  * the matched display text and the href are HTML-escaped; surrounding
    prose is passed through verbatim (escaping it would double-escape on
    a second pass and break idempotency).
"""

from __future__ import annotations

import html as _html
import re

_TAG_RE = re.compile(r"<[^>]*>")
# Opening <a>/<strong>/<em> (not a closing tag): the tag name follows the
# optional whitespace after "<".
_SKIP_OPEN_RE = re.compile(r"<\s*(?:a|strong|em)(?:\s|>|/)", re.IGNORECASE)
_SKIP_CLOSE_RE = re.compile(r"<\s*/\s*(?:a|strong|em)\s*>", re.IGNORECASE)

# Apostrophe / single-quote variants collapsed to a straight apostrophe.
# Every key is a single char mapped to a single char, so string length
# (and therefore match offsets) is preserved.
_APOS = {
    "’": "'",  # right single quotation mark
    "‘": "'",  # left single quotation mark
    "ʼ": "'",  # modifier letter apostrophe
    "´": "'",  # acute accent
    "`": "'",  # grave accent
}


def _norm(s: str) -> str:
    """Offset-preserving apostrophe normalisation for matching only."""
    return "".join(_APOS.get(ch, ch) for ch in s)


def _is_word_char(ch: str) -> bool:
    return ch.isalnum()


def _wrap(url: str | None, kind: str, display: str) -> str:
    esc = _html.escape(display)
    if url:
        href = _html.escape(url, quote=True)
        inner = f'<a href="{href}">{esc}</a>'
    else:
        inner = esc
    tag = "em" if kind == "canco" else "strong"
    return f"<{tag}>{inner}</{tag}>"


def _linkify_text(
    seg: str,
    candidates: list[tuple[str, str | None, str]],
    used: set[str],
    *,
    all_occurrences: bool,
) -> str:
    """Linkify one bare text segment (no tags inside)."""
    norm_seg = _norm(seg)
    n = len(norm_seg)
    occ: list[tuple[int, int, str, str | None, str]] = []
    for name, url, kind in candidates:
        if not all_occurrences and name in used:
            continue
        nn = _norm(name)
        if not nn:
            continue
        start = 0
        while True:
            idx = norm_seg.find(nn, start)
            if idx == -1:
                break
            s, e = idx, idx + len(nn)
            left_ok = s == 0 or not _is_word_char(norm_seg[s - 1])
            right_ok = e == n or not _is_word_char(norm_seg[e])
            if left_ok and right_ok:
                occ.append((s, e, name, url, kind))
                if not all_occurrences:
                    break
            start = idx + 1
    if not occ:
        return seg
    # Longest-match-first: earliest start wins, ties broken by longer span.
    occ.sort(key=lambda o: (o[0], -(o[1] - o[0])))
    out: list[str] = []
    cur = 0
    last_end = -1
    for s, e, name, url, kind in occ:
        if s < last_end or s < cur:
            continue  # overlaps an already-chosen span
        if not all_occurrences and name in used:
            continue
        out.append(seg[cur:s])
        out.append(_wrap(url, kind, seg[s:e]))
        cur = e
        last_end = e
        if not all_occurrences:
            used.add(name)
    out.append(seg[cur:])
    return "".join(out)


def linkify_narrative(
    html_text: str,
    name_map: list[tuple[str, str | None, str]],
    *,
    all_occurrences: bool = False,
) -> str:
    """Wrap canonical names in `html_text` with links/emphasis.

    `name_map` is a list of `(name, url_or_None, kind)` where `kind` is
    `"canco"` or `"artista"`. Returns the rewritten HTML. Idempotent:
    re-running over the result is a no-op (matched names now sit inside
    skip tags).
    """
    if not html_text or not name_map:
        return html_text
    # Longest canonical strings first so a title that contains an artist
    # name is matched as the title.
    candidates = sorted(
        ((n, u, k) for (n, u, k) in name_map if n),
        key=lambda t: -len(t[0]),
    )
    used: set[str] = set()
    parts = _TAG_RE.split(html_text)
    tags = _TAG_RE.findall(html_text)
    # `parts` and `tags` interleave: parts[0], tags[0], parts[1], tags[1]...
    out: list[str] = []
    skip_depth = 0
    for i, text in enumerate(parts):
        if text:
            if skip_depth <= 0:
                out.append(
                    _linkify_text(
                        text, candidates, used, all_occurrences=all_occurrences
                    )
                )
            else:
                out.append(text)
        if i < len(tags):
            tag = tags[i]
            if _SKIP_CLOSE_RE.match(tag):
                skip_depth = max(0, skip_depth - 1)
            elif _SKIP_OPEN_RE.match(tag) and not tag.rstrip().endswith("/>"):
                skip_depth += 1
            out.append(tag)
    return "".join(out)
