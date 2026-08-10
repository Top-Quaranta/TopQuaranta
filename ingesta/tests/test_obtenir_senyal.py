"""Regression tests for `obtenir_senyal` (the daily Last.fm signal cron).

Covers the audit-2026-05-06 critical paths:

1. **Drift detection** (`_detect_drift`): correctly flags artist/track
   divergence; correctly tolerates legitimate decorations like
   "(Remaster 2015)" that `_normalize_track` strips.
2. **Alias summing**: confirmed aliases sum into the canonical track
   playcount; case-fold double-count guard works.
3. **`lastfm_nom` empty guard** (May-2026 audit fix): rows with empty
   `lastfm_nom` are skipped with a logger warning instead of issuing a
   broken `artist=""` request.
4. **MBID threading** (May-2026 audit fix): `track_mbid` and
   `artist_mbid` are passed to `get_track_info` when the Canco /
   Artista has them, even when the track lookup itself succeeds.
5. **Skip-already-ingested**: a track with an existing `SenyalDiari`
   row for the target date isn't re-fetched.
6. **Newly-active artist mark**: `lastfm_te_scrobbles=False` artists
   whose tracks return playcount > 0 are flipped to True in bulk.

External I/O (`get_track_info`, `get_track_info_literal`) is mocked.
No real Last.fm calls.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from ingesta.management.commands.obtenir_senyal import _detect_drift
from music.models import Album, Artista, ArtistaLastfmAlias, Canco
from ranking.models import SenyalDiari

# ── Pure unit tests for _detect_drift (no DB, no mocks) ─────────────


class TestDetectDrift:
    def test_exact_match_no_drift(self):
        assert (
            _detect_drift("Txarango", "Benvolguts", "Txarango", "Benvolguts") is False
        )

    def test_remaster_decoration_is_not_drift(self):
        # `_normalize_track` strips "(Remaster 2015)" so this is the
        # same track with a decoration — must NOT flag.
        assert (
            _detect_drift(
                "Txarango",
                "Benvolguts",
                "Txarango",
                "Benvolguts (Remaster 2015)",
            )
            is False
        )

    def test_feat_decoration_is_not_drift(self):
        assert (
            _detect_drift(
                "Manel",
                "Boomerang",
                "Manel",
                "Boomerang (feat. Núria Graham)",
            )
            is False
        )

    def test_different_artist_is_drift(self):
        # The dangerous case: Last.fm autocorrected "Fades" → "The Fades"
        # and served back a track from the wrong band.
        assert _detect_drift("Fades", "Cançó", "The Fades", "Cançó") is True

    def test_different_track_is_drift(self):
        assert (
            _detect_drift("Txarango", "X", "Txarango", "Y completely different") is True
        )

    def test_empty_returned_artist_treated_as_ok(self):
        # Empty returned names → defensive False (shouldn't happen on
        # success but be robust).
        assert _detect_drift("X", "Y", "", "Y") is False

    def test_accent_insensitive(self):
        # `_normalize_for_match` strips accents — `Lídia` and `Lidia`
        # should match.
        assert _detect_drift("Lídia Pujol", "Cançó", "Lidia Pujol", "Cançó") is False


# ── Integration tests for the management command ───────────────────


@pytest.mark.django_db
class TestObtenirSenyalCommand:
    """Covers the cron's main loop: filtering, lookup, alias summing,
    drift flagging, MBID threading, and the empty-`lastfm_nom` guard."""

    @pytest.fixture
    def base_artist(self):
        a = Artista.objects.create(
            nom="Boira",
            lastfm_nom="Boira",
            aprovat=True,
            musicbrainz_id="11111111-1111-1111-1111-111111111111",
            lastfm_te_scrobbles=False,
        )
        return a

    @pytest.fixture
    def base_canco(self, base_artist):
        album = Album.objects.create(
            artista=base_artist,
            nom="Vida",
            data_llancament=date.today() - timedelta(days=30),
        )
        return Canco.objects.create(
            artista=base_artist,
            album=album,
            nom="L'horitzó",
            lastfm_nom="L'horitzó",
            data_llancament=date.today() - timedelta(days=30),
            verificada=True,
            activa=True,
            mb_recording_id="22222222-2222-2222-2222-222222222222",
        )

    def test_basic_signal_ingestion(self, base_canco):
        """Single track, normal Last.fm response, writes one row."""
        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            m.return_value = {
                "playcount": 5000,
                "listeners": 800,
                "returned_track": "L'horitzó",
                "returned_artist": "Boira",
            }
            call_command("obtenir_senyal", stdout=StringIO())

        rows = SenyalDiari.objects.filter(canco=base_canco)
        assert rows.count() == 1
        r = rows.first()
        assert r.lastfm_playcount == 5000
        assert r.lastfm_listeners == 800
        assert r.error is False
        assert r.corregit is False  # no drift

    def test_mbid_threaded_to_lastfm_call(self, base_canco):
        """Audit fix: when canco has mb_recording_id and artista has
        musicbrainz_id, both flow into get_track_info kwargs."""
        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            m.return_value = {
                "playcount": 1,
                "listeners": 1,
                "returned_track": "L'horitzó",
                "returned_artist": "Boira",
            }
            call_command("obtenir_senyal", stdout=StringIO())

        # Inspect what we passed to Last.fm.
        kwargs = m.call_args.kwargs
        assert kwargs.get("track_mbid") == "22222222-2222-2222-2222-222222222222"
        assert kwargs.get("artist_mbid") == "11111111-1111-1111-1111-111111111111"

    def test_empty_lastfm_nom_is_skipped(self, base_canco, base_artist):
        """Audit fix: artista with empty lastfm_nom must be skipped, NOT
        looked up as `artist=""` (silent zero-plays forever)."""
        base_artist.lastfm_nom = ""
        base_artist.save(update_fields=["lastfm_nom"])

        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            call_command("obtenir_senyal", stdout=StringIO())

        # Last.fm must NOT be called for this canco.
        assert m.call_count == 0
        # And no SenyalDiari row written.
        assert SenyalDiari.objects.filter(canco=base_canco).count() == 0

    def test_drift_flag_persisted(self, base_canco):
        """If get_track_info returns a different artist (Fades → The
        Fades style), `corregit=True` must be set on the row."""
        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            m.return_value = {
                "playcount": 9999,  # contaminated count from wrong band
                "listeners": 500,
                "returned_track": "L'horitzó",
                "returned_artist": "Some Other Band",  # mismatch
            }
            call_command("obtenir_senyal", stdout=StringIO())

        r = SenyalDiari.objects.get(canco=base_canco)
        assert r.corregit is True

    def test_lastfm_confirmed_skips_drift_check(self, base_canco):
        """`canco.lastfm_confirmed=True` is staff's "I checked, this
        autocorrect is fine" opt-out — no drift flag even on mismatch."""
        base_canco.lastfm_confirmed = True
        base_canco.save(update_fields=["lastfm_confirmed"])

        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            m.return_value = {
                "playcount": 100,
                "listeners": 10,
                "returned_track": "L'horitzó",
                "returned_artist": "Different Spelling",
            }
            call_command("obtenir_senyal", stdout=StringIO())

        r = SenyalDiari.objects.get(canco=base_canco)
        assert r.corregit is False

    def test_alias_playcount_sums_into_canonical(self, base_canco, base_artist):
        """Confirmed aliases of an artist sum into the canonical track's
        playcount/listeners — the 2026-05-01 fragmentation fix."""
        ArtistaLastfmAlias.objects.create(
            artista=base_artist,
            nom="Böira",
            confirmat=True,
            rebutjat=False,
        )

        with (
            patch(
                "ingesta.management.commands.obtenir_senyal.get_track_info"
            ) as m_info,
            patch(
                "ingesta.management.commands.obtenir_senyal.get_track_info_literal"
            ) as m_lit,
        ):
            m_info.return_value = {
                "playcount": 1000,
                "listeners": 100,
                "returned_track": "L'horitzó",
                "returned_artist": "Boira",
            }
            m_lit.return_value = {"playcount": 7500, "listeners": 600}
            call_command("obtenir_senyal", stdout=StringIO())

        r = SenyalDiari.objects.get(canco=base_canco)
        assert r.lastfm_playcount == 8500  # 1000 canonical + 7500 alias
        assert r.lastfm_listeners == 700  # 100 + 600

    def test_alias_returns_none_does_not_corrupt_canonical(
        self, base_canco, base_artist
    ):
        """When `get_track_info_literal` returns None for an alias
        (case-fold guard tripped, alias has no page), the canonical
        signal is unchanged."""
        ArtistaLastfmAlias.objects.create(
            artista=base_artist, nom="boira", confirmat=True, rebutjat=False
        )

        with (
            patch(
                "ingesta.management.commands.obtenir_senyal.get_track_info"
            ) as m_info,
            patch(
                "ingesta.management.commands.obtenir_senyal.get_track_info_literal"
            ) as m_lit,
        ):
            m_info.return_value = {
                "playcount": 1000,
                "listeners": 100,
                "returned_track": "L'horitzó",
                "returned_artist": "Boira",
            }
            m_lit.return_value = None
            call_command("obtenir_senyal", stdout=StringIO())

        r = SenyalDiari.objects.get(canco=base_canco)
        assert r.lastfm_playcount == 1000
        assert r.lastfm_listeners == 100

    def test_already_ingested_track_is_skipped(self, base_canco):
        """A SenyalDiari row already exists for today → no Last.fm
        call, no second row."""
        SenyalDiari.objects.create(
            canco=base_canco,
            data=date.today(),
            lastfm_playcount=42,
            lastfm_listeners=42,
            error=False,
        )

        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            call_command("obtenir_senyal", stdout=StringIO())

        assert m.call_count == 0
        assert SenyalDiari.objects.filter(canco=base_canco).count() == 1

    def test_lastfm_returns_none_writes_error_row(self, base_canco):
        """When Last.fm fails entirely (None), the row is written with
        `error=True` and NULL playcount — not a 0 (which would be
        ambiguous with a real-zero-plays case)."""
        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            m.return_value = None
            call_command("obtenir_senyal", stdout=StringIO())

        r = SenyalDiari.objects.get(canco=base_canco)
        assert r.error is True
        assert r.lastfm_playcount is None
        assert r.lastfm_listeners is None

    def test_lastfm_te_scrobbles_flipped_when_plays_seen(self, base_canco, base_artist):
        """Audit-fixed flag: artist with `lastfm_te_scrobbles=False`
        whose track returns playcount > 0 must be flipped to True."""
        assert base_artist.lastfm_te_scrobbles is False

        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            m.return_value = {
                "playcount": 50,
                "listeners": 10,
                "returned_track": "L'horitzó",
                "returned_artist": "Boira",
            }
            call_command("obtenir_senyal", stdout=StringIO())

        base_artist.refresh_from_db()
        assert base_artist.lastfm_te_scrobbles is True

    def test_lastfm_te_scrobbles_not_flipped_on_zero_plays(
        self, base_canco, base_artist
    ):
        """Zero-plays response should not flip the flag — distinguish
        an indexed-with-no-plays artist from a genuinely listened one."""
        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            m.return_value = {
                "playcount": 0,
                "listeners": 0,
                "returned_track": "L'horitzó",
                "returned_artist": "Boira",
            }
            call_command("obtenir_senyal", stdout=StringIO())

        base_artist.refresh_from_db()
        assert base_artist.lastfm_te_scrobbles is False

    def test_inactive_track_not_processed(self, base_canco):
        """`activa=False` tracks must be excluded from the eligibility
        filter regardless of verification or release date."""
        base_canco.activa = False
        base_canco.save(update_fields=["activa"])

        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            call_command("obtenir_senyal", stdout=StringIO())

        assert m.call_count == 0

    def test_unverified_track_not_processed(self, base_canco):
        """`verificada=False` tracks must not be ingested."""
        base_canco.verificada = False
        base_canco.save(update_fields=["verificada"])

        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            call_command("obtenir_senyal", stdout=StringIO())

        assert m.call_count == 0

    def test_unapproved_artist_not_processed(self, base_canco, base_artist):
        """`artista.aprovat=False` tracks must not be ingested."""
        base_artist.aprovat = False
        base_artist.save(update_fields=["aprovat"])

        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            call_command("obtenir_senyal", stdout=StringIO())

        assert m.call_count == 0


@pytest.mark.django_db
class TestCollaboratorFallback:
    """A collaboration filed on Last.fm under a credit that isn't our
    `Canco.artista` used to record `error=True` forever — the lookup only
    ever asked the primary artist. Caught 2026-08-10 on "Tu Contra el Món"
    (Deezer's main artist is Poetas Puestos; we store it under Auxili)."""

    @pytest.fixture
    def collab_canco(self):
        principal = Artista.objects.create(
            nom="Auxili", lastfm_nom="Auxili", aprovat=True
        )
        col = Artista.objects.create(
            nom="Poetas Puestos", lastfm_nom="Poetas Puestos", aprovat=False
        )
        album = Album.objects.create(
            artista=principal,
            nom="Tu Contra el Món",
            data_llancament=date.today() - timedelta(days=10),
        )
        c = Canco.objects.create(
            artista=principal,
            album=album,
            nom="Tu Contra el Món",
            lastfm_nom="Tu Contra el Món",
            data_llancament=date.today() - timedelta(days=10),
            verificada=True,
            activa=True,
        )
        c.artistes_col.add(col)
        return c

    def test_recovers_under_a_collaborator(self, collab_canco):
        def fake(artist, track, **kw):
            if artist != "Poetas Puestos":
                return None
            return {
                "playcount": 116,
                "listeners": 66,
                "returned_track": "Tu contra el Món",
                "returned_artist": "Poetas Puestos",
            }

        with patch(
            "ingesta.management.commands.obtenir_senyal.get_track_info",
            side_effect=fake,
        ):
            call_command("obtenir_senyal", stdout=StringIO())

        row = SenyalDiari.objects.get(canco=collab_canco)
        assert row.error is False
        assert row.lastfm_playcount == 116
        # The whole point: the row must stay usable by the ranking. Drift is
        # judged against the name we actually asked (the collaborator), not
        # against the primary — otherwise `corregit=True` and
        # `_top_for_territoris` filters the recovered row straight back out.
        assert row.corregit is False

    def test_no_collaborator_match_still_records_the_error(self, collab_canco):
        with patch(
            "ingesta.management.commands.obtenir_senyal.get_track_info",
            return_value=None,
        ):
            call_command("obtenir_senyal", stdout=StringIO())

        row = SenyalDiari.objects.get(canco=collab_canco)
        assert row.error is True
        assert "Auxili" in row.error_msg

    def test_primary_artist_is_tried_first(self, collab_canco):
        """The fallback must not fire when the primary answers."""
        with patch("ingesta.management.commands.obtenir_senyal.get_track_info") as m:
            m.return_value = {
                "playcount": 9,
                "listeners": 3,
                "returned_track": "Tu Contra el Món",
                "returned_artist": "Auxili",
            }
            call_command("obtenir_senyal", stdout=StringIO())

        assert m.call_count == 1
        assert m.call_args[0][0] == "Auxili"

    def test_aliases_are_not_summed_onto_a_collaborator(self, collab_canco):
        """Aliases belong to `canco.artista`. Summing them onto a
        collaborator's playcount would mix two different acts."""
        ArtistaLastfmAlias.objects.create(
            artista=collab_canco.artista, nom="Auxili Sound", confirmat=True
        )

        def fake(artist, track, **kw):
            if artist != "Poetas Puestos":
                return None
            return {
                "playcount": 116,
                "listeners": 66,
                "returned_track": "Tu contra el Món",
                "returned_artist": "Poetas Puestos",
            }

        with (
            patch(
                "ingesta.management.commands.obtenir_senyal.get_track_info",
                side_effect=fake,
            ),
            patch(
                "ingesta.management.commands.obtenir_senyal.get_track_info_literal"
            ) as lit,
        ):
            call_command("obtenir_senyal", stdout=StringIO())

        lit.assert_not_called()
        assert SenyalDiari.objects.get(canco=collab_canco).lastfm_playcount == 116
