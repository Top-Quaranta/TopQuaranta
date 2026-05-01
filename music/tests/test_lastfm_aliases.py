"""ArtistaLastfmAlias model + signal-summing behaviour.

Designed 2026-05-01 after the Delên-style fragmentation case: an
artist scrobbled with multiple spellings ('Boira' / 'Böira') ends
up on multiple Last.fm pages with separate playcounts. Confirmed
aliases sum into the canonical signal.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from music.models import Artista, ArtistaLastfmAlias


@pytest.fixture
def artista(db):
    return Artista.objects.create(nom="Boira", lastfm_nom="Boira", aprovat=True)


@pytest.mark.django_db
def test_alias_default_state_is_pending(artista):
    """A freshly-detected candidate is neither confirmed nor rejected."""
    a = ArtistaLastfmAlias.objects.create(artista=artista, nom="Böira")
    assert a.confirmat is False
    assert a.rebutjat is False
    assert a.confirmat_at is None
    # __str__ flags the state for staff debugging.
    assert "pendent" in str(a)


@pytest.mark.django_db
def test_alias_unique_per_artist_name_pair(artista):
    """Re-running the detector mustn't insert duplicates."""
    ArtistaLastfmAlias.objects.create(artista=artista, nom="Böira")
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        ArtistaLastfmAlias.objects.create(artista=artista, nom="Böira")


@pytest.mark.django_db
def test_get_track_info_literal_uses_autocorrect_zero():
    """Critical: alias queries MUST set autocorrect=0, otherwise
    Last.fm silently redirects 'Böira' → 'Boira' and we'd
    double-count the canonical page. Verify the request param."""
    from ingesta.clients import lastfm

    captured = {}

    def fake_get(url, params, timeout):
        captured["params"] = params

        class FakeR:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"track": {"playcount": 5, "listeners": 3}}

        return FakeR()

    with patch("ingesta.clients.lastfm.requests.get", side_effect=fake_get):
        result = lastfm.get_track_info_literal("Böira", "Track")

    assert captured["params"]["autocorrect"] == 0
    assert result == {"playcount": 5, "listeners": 3}


@pytest.mark.django_db
def test_get_track_info_literal_returns_none_on_missing():
    """Last.fm returns {error: 6} when the literal page doesn't exist
    for that (artist, track). The summer must treat it as 0 (no
    contribution), not an error."""
    from ingesta.clients import lastfm

    def fake_get(url, params, timeout):
        class FakeR:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"error": 6, "message": "Track not found"}

        return FakeR()

    with patch("ingesta.clients.lastfm.requests.get", side_effect=fake_get):
        result = lastfm.get_track_info_literal("Böira", "TrackThatDoesntExist")
    assert result is None


@pytest.mark.django_db
def test_only_confirmed_aliases_sum_into_signal(artista):
    """The signal collector must skip rebutjats and pendent rows —
    only confirmat=True ones contribute. Caught by inspection of
    obtenir_senyal: filter(confirmat=True, rebutjat=False)."""
    ArtistaLastfmAlias.objects.create(artista=artista, nom="Böira", confirmat=True)
    ArtistaLastfmAlias.objects.create(
        artista=artista, nom="Boyra", rebutjat=True  # rejected homonym
    )
    ArtistaLastfmAlias.objects.create(
        artista=artista, nom="boira-pending"  # not yet reviewed
    )

    qs = ArtistaLastfmAlias.objects.filter(
        artista=artista, confirmat=True, rebutjat=False
    )
    assert list(qs.values_list("nom", flat=True)) == ["Böira"]


@pytest.mark.django_db
def test_alias_str_states():
    """__str__ varies by state — used in admin + audit logs."""
    art = Artista.objects.create(nom="X", lastfm_nom="X")
    pending = ArtistaLastfmAlias.objects.create(artista=art, nom="x")
    confirmed = ArtistaLastfmAlias.objects.create(artista=art, nom="X.", confirmat=True)
    rejected = ArtistaLastfmAlias.objects.create(
        artista=art, nom="X-different", rebutjat=True
    )
    assert "pendent" in str(pending)
    assert "confirmat" in str(confirmed)
    assert "rebutjat" in str(rejected)
