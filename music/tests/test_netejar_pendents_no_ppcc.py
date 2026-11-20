"""`netejar_pendents_no_ppcc` must sweep dead weight but PRESERVE
recommended candidates.

Regression for the 2026-06-02 backlog audit: the cron now requires
`nb_similars_lastfm = 0` (the same model field the prioritiser
`pendents_list` sorts by), so a pendent with ≥1 approved-artist
recommender is never auto-descarted even when it has 0 tracks /
0 localitat / 0 staff touch.

# Spec: docs/architecture/ingesta.md
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from music.models import Artista


@pytest.mark.django_db
def test_sweeps_dead_weight_without_recommender():
    """0 recommender + 0 tracks + 0 localitat + 0 staff audit → tombstoned."""
    a = Artista.objects.create(
        nom="Dead Weight",
        lastfm_nom="Dead Weight",
        aprovat=False,
        pendent_review=True,
        font_descoberta="lastfm_similar",
        nb_similars_lastfm=0,
    )
    call_command("netejar_pendents_no_ppcc")
    a.refresh_from_db()
    assert a.pendent_review is False  # tombstoned (out of the queue)
    assert a.aprovat is False


@pytest.mark.django_db
def test_preserves_recommended_candidate():
    """≥1 approved recommender → preserved, even with 0 localitat / 0 audit /
    0 tracks (which would otherwise make it a sweep candidate)."""
    a = Artista.objects.create(
        nom="Recommended",
        lastfm_nom="Recommended",
        aprovat=False,
        pendent_review=True,
        font_descoberta="lastfm_similar",
        nb_similars_lastfm=3,  # surfaced by the similars-sort prioritiser
    )
    call_command("netejar_pendents_no_ppcc")
    a.refresh_from_db()
    assert a.pendent_review is True  # left in the queue for triage


@pytest.mark.django_db
def test_un_pendent_que_staff_ja_ha_tocat_no_es_descarta():
    """Any audit row on the artist means a human already weighed in. The
    guard compared against "Artista" while the audit trail stores the
    lowercase model name, so it never matched (found 2026-11-20)."""
    from music.audit import log_staff_action

    a = Artista.objects.create(
        nom="Mirat Per Staff",
        lastfm_nom="Mirat Per Staff",
        aprovat=False,
        pendent_review=True,
        font_descoberta="lastfm_similar",
        nb_similars_lastfm=0,
    )
    log_staff_action(None, "artista_editar", target=a)
    call_command("netejar_pendents_no_ppcc")
    a.refresh_from_db()
    assert a.pendent_review is True
