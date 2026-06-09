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


def test_enrich_entry_principal_linked_collab_bold_backcompat():
    """A pre-Slice-2 payload (no `artistes_slugs`) keeps the old behaviour:
    principal linked, collaborators bold without link."""
    e = _entry(3, "Nois", "nois", ["Ouineta", "Mushkaa"], "ouineta")
    row = _enrich_entry(e, "top_3", 40, hero=False, torna=False)
    ar = row["artistes_render"]
    assert ar[0]["nom"] == "Ouineta" and "/artista/ouineta" in ar[0]["url"]
    assert ar[1]["nom"] == "Mushkaa" and ar[1]["url"] is None
    assert row["artistes_truncated"] is False


def test_enrich_entry_collab_linked_when_slug_present():
    """Slice 2: with `artistes_slugs`, the collaborator carries a link too."""
    e = _entry(
        3,
        "Nois",
        "nois",
        ["Ouineta", "Mushkaa"],
        "ouineta",
        artistes_slugs=["ouineta", "mushkaa"],
    )
    row = _enrich_entry(e, "top_3", 40, hero=False, torna=False)
    ar = row["artistes_render"]
    assert ar[0]["nom"] == "Ouineta" and "/artista/ouineta" in ar[0]["url"]
    assert ar[1]["nom"] == "Mushkaa" and "/artista/mushkaa" in ar[1]["url"]


def test_enrich_entry_collab_without_slug_stays_bold():
    """A collaborator whose slug is None stays bold even in a Slice-2
    payload (the principal still links)."""
    e = _entry(
        3,
        "Nois",
        "nois",
        ["Ouineta", "Mushkaa"],
        "ouineta",
        artistes_slugs=["ouineta", None],
    )
    row = _enrich_entry(e, "top_3", 40, hero=False, torna=False)
    ar = row["artistes_render"]
    assert "/artista/ouineta" in ar[0]["url"]
    assert ar[1]["nom"] == "Mushkaa" and ar[1]["url"] is None


def test_enrich_entry_truncates_long_collab_list():
    names = ["Principal"] + [f"Col {i}" for i in range(40)]
    e = _entry(17, "Massiva", "massiva", names, "principal")
    row = _enrich_entry(e, "top_17", 40, hero=False, torna=False)
    assert row["artistes_truncated"] is True
    assert len(row["artistes_render"]) < len(names)


def test_truncation_budget_is_over_names_and_keeps_whole_artists():
    """The #17-style case (La Fúmiga + 38). Truncation must drop WHOLE
    artist names measured against the 80-char NAME budget (never cut into
    a name), so the rendered HTML can never contain a sliced <a>/<strong>."""
    names = ["La Fúmiga"] + [f"Col {i}" for i in range(38)]
    rows, truncated = _artistes_render(names, ["la-fumiga"] + [None] * 38, "top_17", 40)
    assert truncated is True
    kept = [r["nom"] for r in rows]
    # Kept names are an exact prefix of the input (whole names, in order).
    assert kept == names[: len(kept)]
    # Budget is measured on the NAMES (joined + ellipsis), not on HTML:
    # the kept set fits in 80 chars and adding one more would overflow.
    assert len(", ".join(kept) + "…") <= 80
    assert len(", ".join(names[: len(kept) + 1]) + "…") > 80


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


def test_name_map_kinds_and_urls():
    entries = [
        _entry(1, "Divinize", "divinize", ["Rosalía"], "rosalia"),
        _entry(3, "Nois", "nois", ["Ouineta", "Mushkaa"], "ouineta"),
    ]
    nm = {n: (u, k) for n, u, k in _name_map_from_entries(entries, 40)}
    assert nm["Divinize"][1] == "canco" and "/canco/divinize" in nm["Divinize"][0]
    assert nm["Rosalía"][1] == "artista" and "/artista/rosalia" in nm["Rosalía"][0]
    # Back-compat (no artistes_slugs): collaborator bold, no url.
    assert nm["Mushkaa"] == (None, "artista")


def test_name_map_links_collaborator_with_slug():
    """Slice 2: a collaborator with a slug gets a prose URL, first
    occurrence only (deduped by the canonical name)."""
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
    nm = {n: (u, k) for n, u, k in _name_map_from_entries(entries, 40)}
    assert nm["Mushkaa"][1] == "artista" and "/artista/mushkaa" in nm["Mushkaa"][0]


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
