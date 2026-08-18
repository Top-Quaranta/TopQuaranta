"""Guards for the deterministic prose linkifier (`newsletter_linkify`).

Covers: correct artist/song wrapping, longest-match-first, zero false
positives (case, substring, word boundary), first-occurrence-only,
apostrophe/accent matching, ampersand escaping, idempotency, skipping
the interior of existing tags, and collaborator bold-without-link.
"""

from __future__ import annotations

from comptes.newsletter_linkify import linkify_narrative

CANCO = "/canco/x"
ART = "/artista/a"


def _links(html):
    """[(href, text, {open tags around the link})] — structural view so the
    tests assert the property (linked + emphasised) not the exact markup
    or nesting order of <strong>/<em> vs <a>."""
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.out = []
            self.cur = None

        def handle_starttag(self, tag, attrs):
            self.stack.append(tag)
            if tag == "a":
                self.cur = [dict(attrs).get("href"), "", set(self.stack)]

        def handle_endtag(self, tag):
            if tag == "a" and self.cur is not None:
                href, text, ctx = self.cur
                # tags opened *inside* the link count too (a > strong > text)
                self.out.append((href, text, ctx | self.cur[2]))
                self.cur = None
            if tag in self.stack:
                del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag) :]

        def handle_data(self, data):
            if self.cur is not None:
                self.cur[1] += data
                self.cur[2] |= set(self.stack)

    p = _P()
    p.feed(html)
    return p.out


def test_wraps_song_em_and_artist_strong():
    """Property asserted: the artist name is the text of a link to ART
    and is bold; the song title is the text of a link to CANCO and is
    italic — however <strong>/<em> and <a> are nested."""
    nm = [("Divinize", CANCO, "canco"), ("Rosalía", ART, "artista")]
    out = linkify_narrative("<p>Rosalía firma Divinize.</p>", nm)
    links = {href: (text, ctx) for href, text, ctx in _links(out)}
    assert set(links) == {ART, CANCO}
    assert links[ART][0] == "Rosalía" and "strong" in links[ART][1]
    assert links[CANCO][0] == "Divinize" and "em" in links[CANCO][1]
    # Prose outside the names is untouched.
    assert "firma" in out


def test_longest_match_first_title_contains_artist():
    # The song title contains the artist name; the title must win.
    nm = [
        ("Rosalía Forever", "/canco/rf", "canco"),
        ("Rosalía", ART, "artista"),
    ]
    out = linkify_narrative("<p>Escolta Rosalía Forever ja.</p>", nm)
    assert '<em><a href="/canco/rf">Rosalía Forever</a></em>' in out
    # The inner "Rosalía" is consumed by the title, not separately linked.
    assert "<strong>" not in out


def test_no_false_positive_case_sensitive():
    nm = [("Tardor", ART, "artista")]
    out = linkify_narrative("<p>Era tardor quan va eixir.</p>", nm)
    assert "<strong>" not in out and out == "<p>Era tardor quan va eixir.</p>"


def test_no_false_positive_word_boundary():
    nm = [("Ona", ART, "artista")]
    out = linkify_narrative("<p>Les ones del mar.</p>", nm)  # "Ona" inside "ones"
    assert "<strong>" not in out


def test_first_occurrence_only_by_default():
    nm = [("Maria Jaume", ART, "artista")]
    out = linkify_narrative("<p>Maria Jaume puja. Maria Jaume torna.</p>", nm)
    assert out.count("<strong>") == 1
    assert out.count("Maria Jaume") == 2  # second stays as plain text


def test_all_occurrences_when_requested():
    nm = [("Maria Jaume", ART, "artista")]
    out = linkify_narrative(
        "<p>Maria Jaume puja. Maria Jaume torna.</p>", nm, all_occurrences=True
    )
    assert out.count("<strong>") == 2


def test_apostrophe_and_accents_match():
    nm = [("On T'has Ficat Aquesta Nit?", CANCO, "canco")]
    # Prose uses a curly apostrophe; it must still match.
    out = linkify_narrative("<p>Sona On T’has Ficat Aquesta Nit? ara.</p>", nm)
    assert f'<em><a href="{CANCO}">' in out
    assert "Nit?</a></em>" in out


def test_ampersand_in_name_is_escaped():
    nm = [("Renaldo & Clara", "/artista/rc", "artista")]
    out = linkify_narrative("<p>Veies Renaldo & Clara ahir.</p>", nm)
    assert ">Renaldo &amp; Clara</a></strong>" in out


def test_idempotent():
    nm = [("Divinize", CANCO, "canco"), ("Rosalía", ART, "artista")]
    once = linkify_narrative("<p>Rosalía firma Divinize.</p>", nm)
    twice = linkify_narrative(once, nm)
    assert once == twice


def test_skips_inside_existing_anchor():
    nm = [("Divinize", CANCO, "canco")]
    src = '<p>Mira <a href="y">Divinize</a> ja.</p>'
    out = linkify_narrative(src, nm)
    assert out == src  # already inside <a>, untouched


def test_collaborator_bold_without_link():
    nm = [("Mushkaa", None, "artista")]
    out = linkify_narrative("<p>amb Mushkaa al costat.</p>", nm)
    assert "<strong>Mushkaa</strong>" in out
    assert "<a" not in out


def test_href_ampersand_escaped_in_attribute():
    url = "https://x/canco/y?utm_source=newsletter&utm_content=prosa_canco"
    nm = [("Divinize", url, "canco")]
    out = linkify_narrative("<p>Divinize sona.</p>", nm)
    assert "utm_source=newsletter&amp;utm_content=prosa_canco" in out
