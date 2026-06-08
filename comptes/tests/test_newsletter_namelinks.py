"""Slice 1 name-link wiring: per-artist card render (principal linked,
collaborators bold) + prose linkifier applied to the injected narrative
through `render_newsletter_preview`. Render-only, no send.
"""

from __future__ import annotations

import datetime

import pytest

from comptes.newsletter import (
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
