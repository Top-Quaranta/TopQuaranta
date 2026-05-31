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


def test_no_template_comment_leaks_into_render():
    """Caught 2026-05-09 (recovery send): the multi-line comment
    `{# ... #}` I'd added to explain the `{% if %}` workaround
    leaked into the rendered output because Django's `{# #}`
    syntax is SINGLE-LINE only — multi-line requires
    `{% comment %}...{% endcomment %}`. Every recipient saw the
    explanation rendered as plain text in front of each row.

    This test pins the invariant: no `{#` or `#}` markers should
    appear anywhere in the rendered HTML, period.
    """
    html = _render(
        [
            {"canco_nom": "Test", "artista_nom": "Test"},
        ]
    )
    assert "{#" not in html
    assert "#}" not in html
    # The plaintext fallback (strip_tags) goes through the same
    # template, so leaks would appear in the text body too.
    from django.utils.html import strip_tags

    text = strip_tags(html)
    assert "{#" not in text
    assert "Django's" not in text  # comment body must not show


@pytest.mark.django_db
def test_no_comment_leak_with_narrative_html():
    """The Fase-4 `{% if narrative_html %}` true-branch carried a
    multi-line `{# ... #}` comment that leaked into every real top
    newsletter (Django `{# #}` is single-line only). The previous leak
    test only exercised the `{% else %}` branch (no `narrative_html`),
    so it missed this. Render the narrative branch and assert nothing
    leaks — neither the markers nor the comment body.
    """
    from django.utils.html import strip_tags

    html = render_to_string(
        "comptes/email_newsletter_top.html",
        {
            "subject": "Test",
            "heading": "Top Test",
            "territori_nom": "Catalunya",
            "project_week": 99,
            "entries": [{"canco_nom": "X", "artista_nom": "Y"}],
            "unsub_url": "https://example.com/unsub",
            "top_url": "https://example.com/top",
            "narrative_html": "<p>Un paràgraf editorial.</p>",
        },
    )
    assert "Un paràgraf editorial." in html  # the narrative branch DID render
    for marker in ("{#", "#}", "{ #", "Fase 4 reset", "narrative engine"):
        assert marker not in html, f"leaked {marker!r}"
    text = strip_tags(html)
    assert "{#" not in text and "Fase 4 reset" not in text


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
