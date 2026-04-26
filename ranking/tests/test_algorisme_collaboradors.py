"""
Test that tracks with collaborating artists appear in both
the main artist's territory and the collaborator's territory rankings.
"""

from datetime import date, timedelta

import pytest

# These tests require PostgreSQL (raw SQL uses DISTINCT ON, ::text casts).
# Skipped automatically when running with SQLite (test settings).
from django.conf import settings

from ranking.algorisme import calcular_top_territori
from ranking.models import ConfiguracioGlobal, SenyalDiari

_is_postgres = "postgresql" in settings.DATABASES["default"].get("ENGINE", "")
pytestmark = pytest.mark.skipif(not _is_postgres, reason="Requires PostgreSQL")


@pytest.mark.django_db
class TestCollaboratorTerritoryInclusion:
    @pytest.fixture
    def setup_collab(self):
        """
        Create a track where main artist is CAT and collaborator is VAL.
        The track should appear in both CAT and VAL rankings.
        """
        from music.models import Album, Artista, Canco, Territori

        ConfiguracioGlobal.objects.create(pk=1)
        cat, _ = Territori.objects.get_or_create(
            codi="CAT", defaults={"nom": "Catalunya"}
        )
        val, _ = Territori.objects.get_or_create(
            codi="VAL", defaults={"nom": "Pais Valencia"}
        )

        artista_cat = Artista.objects.create(
            nom="Txarango",
            lastfm_nom="Txarango",
            aprovat=True,
        )
        artista_cat.territoris.add(cat)

        artista_val = Artista.objects.create(
            nom="La Fumiga",
            lastfm_nom="La Fumiga",
            aprovat=True,
        )
        artista_val.territoris.add(val)

        album = Album.objects.create(
            artista=artista_cat,
            nom="Collab Album",
            data_llancament=date(2026, 3, 1),
        )
        collab_track = Canco.objects.create(
            artista=artista_cat,
            album=album,
            nom="Collab Song",
            data_llancament=date(2026, 3, 1),
            verificada=True,
            activa=True,
        )
        collab_track.artistes_col.add(artista_val)

        # Create 7 days of signal
        today = date.today()
        for day_offset in range(7):
            d = today - timedelta(days=day_offset)
            SenyalDiari.objects.create(
                canco=collab_track,
                data=d,
                lastfm_playcount=5000,
                lastfm_listeners=500,
                error=False,
            )

        return collab_track

    def test_collab_track_in_main_artist_territory(self, setup_collab):
        results = calcular_top_territori("CAT")
        canco_ids = {r["canco_id"] for r in results}
        assert setup_collab.pk in canco_ids

    def test_collab_track_in_collaborator_territory(self, setup_collab):
        results = calcular_top_territori("VAL")
        canco_ids = {r["canco_id"] for r in results}
        assert setup_collab.pk in canco_ids
