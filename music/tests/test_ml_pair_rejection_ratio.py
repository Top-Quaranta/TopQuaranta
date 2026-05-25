"""Pins for the per-pair rejection-ratio feature in `music.ml`.

Replaces the legacy `_get_rejection_ratio(artista_nom)` test
coverage (it lived inline in `test_services` and didn't pin the
pair semantics). Confirms:

  - Same (deezer, spotify) pair: rows under the pair count;
    rows of a homonym (same deezer, different spotify) are
    excluded.
  - Falls back to deezer-only when no spotify_artist_id is given.
  - Falls back to artista_nom when no deezer is given (legacy).
  - Cold-start (no matching rows) returns the 0.5 prior.
"""

# Spec: docs/architecture/pipeline.md

from __future__ import annotations

import pytest

from music.ml import _get_rejection_ratio
from music.models import HistorialRevisio


def _hr(*, dz, sp="", nom="X", decisio="rebutjada"):
    HistorialRevisio.objects.create(
        canco_deezer_id=1,
        canco_nom="t",
        artista_nom=nom,
        artista_deezer_id=dz,
        artista_spotify_id=sp,
        decisio=decisio,
        motiu="desvincular_canco" if decisio == "rebutjada" else "ok",
    )


@pytest.mark.django_db
def test_pair_ratio_isolates_homonym_spotify_ids():
    """Same deezer_id, two distinct spotify_artist_id values: each
    should see only its own rows."""
    # Wrong-Aion: 3 rebuigs under (deezer=99, spotify="SP_WRONG").
    for _ in range(3):
        _hr(dz=99, sp="SP_WRONG", decisio="rebutjada")
    # Real-Aion: 2 approvals under (deezer=99, spotify="SP_REAL").
    for _ in range(2):
        _hr(dz=99, sp="SP_REAL", decisio="aprovada")

    total_w, ratio_w = _get_rejection_ratio(
        "Aion", artista_deezer_id=99, artista_spotify_id="SP_WRONG"
    )
    total_r, ratio_r = _get_rejection_ratio(
        "Aion", artista_deezer_id=99, artista_spotify_id="SP_REAL"
    )
    assert total_w == 3
    assert ratio_w > 0.6  # mostly rebuig under the wrong pair
    assert total_r == 2
    assert ratio_r < 0.4  # mostly approval under the real pair


@pytest.mark.django_db
def test_pair_ratio_falls_back_to_deezer_only_when_no_spotify():
    """No spotify_artist_id on the candidate -> group by deezer_id
    alone. The legacy by-name homonyms (Aion-real, Aion-wrong both
    under the same name but different deezer_ids) still separate."""
    for _ in range(4):
        _hr(dz=11, decisio="rebutjada", nom="Aion")  # wrong-Aion
    for _ in range(2):
        _hr(dz=22, decisio="aprovada", nom="Aion")  # real-Aion

    total_w, ratio_w = _get_rejection_ratio("Aion", artista_deezer_id=11)
    total_r, ratio_r = _get_rejection_ratio("Aion", artista_deezer_id=22)
    assert total_w == 4
    assert ratio_w > 0.7  # 4 rebuigs / 9 with prior pull ≈ 0.72
    assert total_r == 2
    assert ratio_r < 0.4  # 2 aprovades / 7 with prior pull ≈ 0.36


@pytest.mark.django_db
def test_pair_ratio_falls_back_to_name_as_last_resort():
    """Neither deezer_id nor spotify_id given -> group by name
    (legacy behaviour). Useful for the very oldest HR rows where
    the snapshot was incomplete."""
    for _ in range(5):
        _hr(dz=None, decisio="rebutjada", nom="Cactus")
    total, ratio = _get_rejection_ratio("Cactus")
    assert total == 5
    assert ratio > 0.7


@pytest.mark.django_db
def test_pair_ratio_cold_start_returns_prior():
    total, ratio = _get_rejection_ratio(
        "NeverSeen",
        artista_deezer_id=12345,
        artista_spotify_id="SP_NEW",
    )
    assert total == 0
    assert ratio == 0.5


@pytest.mark.django_db
def test_pair_ratio_empty_inputs_returns_prior():
    """No name, no ids -> the resolver can't pick a key. Prior."""
    total, ratio = _get_rejection_ratio("")
    assert total == 0
    assert ratio == 0.5
