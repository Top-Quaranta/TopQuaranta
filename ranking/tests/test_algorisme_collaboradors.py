"""
Test that tracks with collaborating artists appear in both
the main artist's territory and the collaborator's territory rankings.
"""

from datetime import date, timedelta

import pytest

from ranking.algorisme import calcular_top_territori
from ranking.models import ConfiguracioGlobal, SenyalDiari

# The PostgreSQL gate these carried is gone (2026-08-15): the algorithm
# stopped being raw SQL at v2.0, the test settings are SQLite, so the
# gate never opened and nobody noticed the fixture had gone stale.


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

        llancament = date.today() - timedelta(days=60)
        album = Album.objects.create(
            artista=artista_cat,
            nom="Collab Album",
            data_llancament=llancament,
        )
        collab_track = Canco.objects.create(
            artista=artista_cat,
            album=album,
            nom="Collab Song",
            data_llancament=llancament,
            verificada=True,
            activa=True,
        )
        collab_track.artistes_col.add(artista_val)

        # Growing, not flat: `lastfm_playcount` is cumulative, so a flat
        # series is zero plays this week and the song never charts.
        today = date.today()
        for day_offset in range(7):
            d = today - timedelta(days=day_offset)
            SenyalDiari.objects.create(
                canco=collab_track,
                data=d,
                lastfm_playcount=5000 + (6 - day_offset) * 200,
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
