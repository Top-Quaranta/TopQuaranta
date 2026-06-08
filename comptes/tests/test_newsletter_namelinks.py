"""Slice 1 name-link wiring: per-artist card render (principal linked,
collaborators bold) + prose linkifier applied to the injected narrative
through `render_newsletter_preview`. Render-only, no send.
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


def _entry(pos, canco, canco_slug, names, artista_slug):
    return {
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


def test_enrich_entry_principal_linked_collab_bold():
    e = _entry(3, "Nois", "nois", ["Ouineta", "Mushkaa"], "ouineta")
    row = _enrich_entry(e, "top_3", 40, hero=False, torna=False)
    ar = row["artistes_render"]
    assert ar[0]["nom"] == "Ouineta" and "/artista/ouineta" in ar[0]["url"]
    assert ar[1]["nom"] == "Mushkaa" and ar[1]["url"] is None
    assert row["artistes_truncated"] is False


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
    rows, truncated = _artistes_render(names, "la-fumiga", "top_17", 40)
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
    rows, truncated = _artistes_render(names, "la-fumiga", "top_17", 40)
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
    assert nm["Mushkaa"] == (None, "artista")  # collaborator: bold, no url


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
