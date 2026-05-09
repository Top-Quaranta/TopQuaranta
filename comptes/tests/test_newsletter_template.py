"""Coverage for the weekly-top newsletter template render.

Anchor for the 2026-05-09 lesson: Saturday newsletter cron failed
for every recipient because the template did
`{{ e.canco_nom|default:e.nom }}`. Django's `default` filter
EAGERLY evaluates its argument — so on a top entry (which has
`canco_nom` but no `nom`) it raised `VariableDoesNotExist` and
`send_top_newsletter` swallowed it as a per-user failure (logged
1 ERROR per user), zero emails delivered.

These tests render the template against both shapes of `entries`
the caller passes in (top vs novetats) and assert no exception +
the expected song title appears in the output.
"""

from __future__ import annotations

import pytest
from django.template.loader import render_to_string


def _render(entries):
    return render_to_string(
        "comptes/email_newsletter_top.html",
        {
            "subject": "Test",
            "heading": "Top Test",
            "territori_nom": "Catalunya",
            "project_week": 99,
            "entries": entries,
            "unsub_url": "https://example.com/unsub",
            "top_url": "https://example.com/top",
        },
    )


def test_renders_top_entries_with_canco_nom():
    """Top entries (`payload.build_top`) carry `canco_nom`. The
    pre-fix template raised VariableDoesNotExist here."""
    html = _render(
        [
            {
                "posicio": 1,
                "canco_nom": "Divinize",
                "artista_nom": "Rosalía",
            },
            {
                "posicio": 2,
                "canco_nom": "Estrelles",
                "artista_nom": "Max Navarro",
            },
        ]
    )
    assert "Divinize" in html
    assert "Estrelles" in html
    assert "Rosalía" in html


def test_renders_novetats_items_with_nom():
    """Novetats items (`payload.build_novetats`) carry `nom`
    instead of `canco_nom`. Template must handle both."""
    html = _render(
        [
            {"nom": "Àlbum Nou", "artista_nom": "Banda X"},
            {"nom": "Altre Disc", "artista_nom": "Banda Y"},
        ]
    )
    assert "Àlbum Nou" in html
    assert "Altre Disc" in html
    assert "Banda X" in html


def test_renders_mixed_shape_entries():
    """Defensive: a list mixing both shapes (shouldn't happen in
    practice but proves neither path explodes)."""
    html = _render(
        [
            {"canco_nom": "From Top", "artista_nom": "A"},
            {"nom": "From Novetats", "artista_nom": "B"},
        ]
    )
    assert "From Top" in html
    assert "From Novetats" in html
