"""Name-link wiring: per-artist card render + prose linkifier applied to
the injected narrative through `render_newsletter_preview`. Slice 1
linked the principal (collaborators bold); Slice 2 links collaborators
too when the payload carries `artistes_slugs`. Render-only, no send.
"""

from __future__ import annotations

import datetime

import pytest
from django.template.loader import render_to_string

from comptes.newsletter import (
    _artistes_render,
    _enrich_entry,
    _name_map_from_entries,
    render_newsletter_preview,
)


def _entry(pos, canco, canco_slug, names, artista_slug, artistes_slugs=None):
    e = {
        "posicio": pos,
        "posicio_anterior": pos,
        "canco_nom": canco,
        "canco_slug": canco_slug,
        "artistes_noms": names,
        "artista_nom": names[0],
        "artista_slug": artista_slug,
        "cover_url": None,
        "album_deezer_id": None,
    }
    if artistes_slugs is not None:
        e["artistes_slugs"] = artistes_slugs
    return e


@pytest.mark.django_db
def test_enrich_entry_collab_without_slug_stays_bold():
    """A collaborator whose slug is None stays bold even in a Slice-2
    payload (the principal still links).
    Property asserted on the rendered email: the collaborator's name is
    present but is NOT the text of any link (no `/artista/None`, no link
    to a guessed slug), while the principal is linked."""
    import re

    e = _entry(
        3,
        "Nois",
        "nois",
        ["Ouineta", "Mushkaa"],
        "ouineta",
        artistes_slugs=["ouineta", None],
    )
    setmana = datetime.date(2026, 6, 1)
    html = render_newsletter_preview(
        "top_ppcc",
        "PPCC",
        setmana,
        setmana + datetime.timedelta(days=5),
        [e],
        subject_override="Subj",
        narrative_html_override="<p>Sense noms.</p>",
    )
    assert "Mushkaa" in html
    assert "/artista/ouineta" in html
    # Every link text: Mushkaa never appears as the text of an <a>.
    link_texts = re.findall(r"<a\b[^>]*>(.*?)</a>", html, flags=re.S)
    assert not any("Mushkaa" in t for t in link_texts), link_texts
    # No broken href built from a missing slug.
    assert "/artista/None" not in html and "/artista/mushkaa" not in html


def test_truncation_budget_is_over_names_and_keeps_whole_artists():
    """The #17-style case (La Fúmiga + 38). Truncation must drop WHOLE
    artist names measured against the 80-char NAME budget (never cut into
    a name), so the rendered HTML can never contain a sliced <a>/<strong>."""
    names = ["La Fúmiga"] + [f"Col {i}" for i in range(38)]
    import inspect

    # Property asserted: whole names, prefix order, and the budget is the
    # function's own `max_chars` default (read, not hardcoded): the kept
    # names + ellipsis fit, one more name would not.
    budget = inspect.signature(_artistes_render).parameters["max_chars"].default
    rows, truncated = _artistes_render(names, ["la-fumiga"] + [None] * 38, "top_17", 40)
    assert truncated is True
    kept = [r["nom"] for r in rows]
    assert 1 <= len(kept) < len(names)
    # Kept names are an exact prefix of the input (whole names, in order).
    assert kept == names[: len(kept)]
    # Budget is measured on the NAMES (joined + ellipsis), not on HTML.
    assert len(", ".join(kept) + "…") <= budget
    assert len(", ".join(names[: len(kept) + 1]) + "…") > budget


def test_truncated_partial_renders_valid_balanced_html():
    """Rendering the long list through the partial yields balanced markup:
    every <a>/<strong>/<em> opened is closed, exactly one anchor (the
    principal), and an ellipsis. No tag is ever cut by truncation."""
    names = ["La Fúmiga"] + [f"Col {i}" for i in range(38)]
    rows, truncated = _artistes_render(names, ["la-fumiga"] + [None] * 38, "top_17", 40)
    html = render_to_string(
        "comptes/_nl_artistes.html", {"arts": rows, "trunc": truncated}
    )
    assert html.count("<a ") == html.count("</a>") == 1  # principal only
    assert html.count("<strong>") == html.count("</strong>") == len(rows)
    assert "…" in html
    # The principal anchor is whole (opened and closed in the same string).
    assert '<strong><a href="' in html and "</a></strong>" in html


@pytest.mark.django_db
def test_preview_linkifies_injected_narrative_and_cards():
    entries = [
        _entry(1, "Divinize", "divinize", ["Rosalía"], "rosalia"),
        _entry(3, "Nois", "nois", ["Ouineta", "Mushkaa"], "ouineta"),
    ]
    setmana = datetime.date(2026, 6, 1)
    html = render_newsletter_preview(
        "top_ppcc",
        "PPCC",
        setmana,
        setmana + datetime.timedelta(days=5),
        entries,
        subject_override="Subj",
        narrative_html_override="<p>Rosalía firma Divinize amb Mushkaa.</p>",
    )
    # Prose: principal linked, song italic+linked, collaborator bold (no link).
    assert "/artista/rosalia" in html
    assert "firma <em>" in html and "/canco/divinize" in html
    assert "amb <strong>Mushkaa</strong>" in html
    # Cards: the #3 principal (Ouineta) renders bold + link.
    assert "/artista/ouineta" in html


@pytest.mark.django_db
def test_preview_links_collaborator_in_prose_and_cards():
    """Slice 2: with `artistes_slugs`, the collaborator (Mushkaa) is a
    <strong><a> in BOTH the prose and the card list."""
    entries = [
        _entry(
            3,
            "Nois",
            "nois",
            ["Ouineta", "Mushkaa"],
            "ouineta",
            artistes_slugs=["ouineta", "mushkaa"],
        ),
    ]
    setmana = datetime.date(2026, 6, 1)
    html = render_newsletter_preview(
        "top_ppcc",
        "PPCC",
        setmana,
        setmana + datetime.timedelta(days=5),
        entries,
        subject_override="Subj",
        narrative_html_override="<p>Ouineta firma Nois amb Mushkaa.</p>",
    )
    assert "/artista/mushkaa" in html
    # Prose: the collaborator is now a linked strong, not a bare bold.
    assert "amb <strong>Mushkaa</strong>" not in html
