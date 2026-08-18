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
    obtenir_senyal: filter(confirmat=True, rebutjat=False).

    Property asserted: running `obtenir_senyal` against a mocked
    Last.fm writes a SenyalDiari whose playcount is canonical +
    confirmed-alias plays ONLY — a rejected homonym and a pending
    candidate contribute nothing, however many plays their pages have.
    """
    from datetime import date, timedelta
    from io import StringIO

    from django.core.management import call_command

    from music.models import Album, Canco
    from ranking.models import SenyalDiari

    ArtistaLastfmAlias.objects.create(artista=artista, nom="Böira", confirmat=True)
    ArtistaLastfmAlias.objects.create(
        artista=artista, nom="Boyra", rebutjat=True  # rejected homonym
    )
    ArtistaLastfmAlias.objects.create(
        artista=artista, nom="boira-pending"  # not yet reviewed
    )
    album = Album.objects.create(
        artista=artista, nom="Vida", data_llancament=date.today() - timedelta(days=30)
    )
    canco = Canco.objects.create(
        artista=artista,
        album=album,
        nom="L'horitzó",
        lastfm_nom="L'horitzó",
        data_llancament=date.today() - timedelta(days=30),
        verificada=True,
        activa=True,
    )

    # Every alias page "exists" on Last.fm with a distinctive playcount,
    # so any leak from a non-confirmed row shows up in the total.
    plays = {"Böira": (500, 50), "Boyra": (9_000, 900), "boira-pending": (7_000, 700)}

    def fake_literal(alias, track, canonical_artist=None, **_):
        pc, li = plays[alias]
        return {"playcount": pc, "listeners": li}

    with (
        patch(
            "ingesta.management.commands.obtenir_senyal.get_track_info",
            return_value={
                "playcount": 1_000,
                "listeners": 100,
                "returned_track": "L'horitzó",
                "returned_artist": "Boira",
            },
        ),
        patch(
            "ingesta.management.commands.obtenir_senyal.get_track_info_literal",
            side_effect=fake_literal,
        ),
    ):
        call_command("obtenir_senyal", stdout=StringIO())

    row = SenyalDiari.objects.get(canco=canco)
    assert row.lastfm_playcount == 1_000 + 500
    assert row.lastfm_listeners == 100 + 50


@pytest.mark.django_db
def test_get_track_info_literal_skips_case_fold_collapse():
    """Critical: even with autocorrect=0, Last.fm case-folds the
    artist name and returns the canonical page's data. Caught
    2026-05-01 with 'ADRIÀ PUNTÍ' returning the same playcount
    (117 347) as 'Adrià Puntí'. The literal-page lookup must
    detect this and return None so we don't double-count.
    """
    from ingesta.clients import lastfm

    def fake_get(url, params, timeout):
        # Last.fm's response: track is real but the artist field
        # carries the *canonical* name even though we asked for
        # 'ADRIÀ PUNTÍ' (case-fold).
        class FakeR:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "track": {
                        "playcount": 117347,
                        "listeners": 5000,
                        "artist": {"name": "Adrià Puntí"},
                    }
                }

        return FakeR()

    with patch("ingesta.clients.lastfm.requests.get", side_effect=fake_get):
        # Without canonical guard → returns the (double-counting) playcount.
        no_guard = lastfm.get_track_info_literal("ADRIÀ PUNTÍ", "Penyora")
        assert no_guard["playcount"] == 117347

        # With the canonical guard → recognises the case-fold
        # collapse and returns None (don't sum).
        with_guard = lastfm.get_track_info_literal(
            "ADRIÀ PUNTÍ", "Penyora", canonical_artist="Adrià Puntí"
        )
        assert with_guard is None


@pytest.mark.django_db
def test_get_track_info_literal_keeps_genuine_variant():
    """Counterpart to the case-fold test: a genuine variant page
    (different artist name in the response, e.g. typographic
    apostrophe vs ASCII) must still sum normally."""
    from ingesta.clients import lastfm

    def fake_get(url, params, timeout):
        class FakeR:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                # 'Anna Roig…' vs 'Anna Roig…' (typographic apostrophe).
                return {
                    "track": {
                        "playcount": 25530,
                        "listeners": 1200,
                        "artist": {"name": "Anna Roig i L’ombre de ton chien"},
                    }
                }

        return FakeR()

    with patch("ingesta.clients.lastfm.requests.get", side_effect=fake_get):
        result = lastfm.get_track_info_literal(
            "Anna Roig i L’ombre de ton chien",
            "Track",
            canonical_artist="Anna Roig i L'ombre de ton chien",
        )
        # Names differ in the apostrophe character → the response's
        # artist matches what we asked for (typographic), not the
        # canonical (ASCII) → sum normally.
        assert result["playcount"] == 25530
