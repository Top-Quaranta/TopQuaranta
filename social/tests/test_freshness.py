"""Tests for the verified-recent-release fact (`social/narrative/freshness.py`).

The function is pure (reads attributes, never touches the DB), so these
use lightweight stubs instead of `django_db` fixtures.
"""

import datetime

from social.narrative import freshness

REF = datetime.date(2026, 5, 25)


class _Artista:
    def __init__(self, mb_end_date=None):
        self.mb_end_date = mb_end_date


class _Canco:
    def __init__(self, nom, data_llancament, artista=None):
        self.nom = nom
        self.data_llancament = data_llancament
        self.artista = artista


def _verdict(nom, dl, mb_end=None, **kw):
    c = _Canco(nom, dl, _Artista(mb_end))
    return freshness.assess_recent_release(c, ref_date=REF, **kw)


def test_fresh_original_release_is_verified():
    v = _verdict("Tots Som Súpers", REF - datetime.timedelta(days=1))
    assert v.is_verified_recent_release is True
    assert v.age_days == 1
    assert v.reasons == ()


def test_old_release_is_not_recent():
    v = _verdict("Cançó Vella", REF - datetime.timedelta(days=120))
    assert v.is_verified_recent_release is False
    assert "older_than_window" in v.reasons
    assert v.age_days == 120


def test_version_marker_in_title_blocks_verification():
    for title in (
        "Camins (En Directe a Cap Roig)",
        "Bandida (Remix)",
        "Buguenvíl·lies (Live)",
        "Tema (Remasteritzat)",
    ):
        v = _verdict(title, REF - datetime.timedelta(days=5))
        assert v.is_verified_recent_release is False, title
        assert "version_marker_in_title" in v.reasons


def test_posthumous_reissue_is_not_verified():
    # Pau Riba case: died 2022, "release" dated 2026.
    v = _verdict(
        "Noia de Porcellana",
        datetime.date(2026, 4, 24),
        mb_end=datetime.date(2022, 3, 6),
    )
    assert v.is_verified_recent_release is False
    assert "artist_deceased_before_release" in v.reasons


def test_living_artist_recent_release_passes():
    v = _verdict(
        "Nova",
        REF - datetime.timedelta(days=3),
        mb_end=None,
    )
    assert v.is_verified_recent_release is True


def test_missing_release_date_is_false_with_none_age():
    v = _verdict("Sense Data", None)
    assert v.is_verified_recent_release is False
    assert v.age_days is None
    assert v.reasons == ("no_release_date",)


def test_future_release_clamps_age_to_zero():
    v = _verdict("Avançada", REF + datetime.timedelta(days=4))
    assert v.age_days == 0
    assert v.is_verified_recent_release is True


def test_custom_window():
    dl = REF - datetime.timedelta(days=60)
    assert _verdict("X", dl).is_verified_recent_release is False
    assert _verdict("X", dl, max_age_days=90).is_verified_recent_release is True


def test_boolean_wrapper_matches_verdict():
    c = _Canco("Nova", REF - datetime.timedelta(days=2), _Artista())
    assert freshness.is_verified_recent_release(c, ref_date=REF) is True
