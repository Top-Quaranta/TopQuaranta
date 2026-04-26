from datetime import date
from decimal import Decimal

import pytest

from ranking.models import ConfiguracioGlobal, TopProvisional, TopSetmanal


@pytest.mark.django_db
class TestConfiguracioGlobal:
    def test_load_creates_singleton(self):
        config = ConfiguracioGlobal.load()
        assert config.pk == 1
        assert config.dia_setmana_ranking == 6

    def test_save_forces_pk_1(self):
        config = ConfiguracioGlobal(pk=99, coeficient_penalitzacio_top=Decimal("0.05"))
        config.save()
        assert config.pk == 1
        assert ConfiguracioGlobal.objects.count() == 1

    def test_load_returns_existing(self):
        ConfiguracioGlobal.objects.create(
            pk=1, coeficient_penalitzacio_top=Decimal("0.05")
        )
        config = ConfiguracioGlobal.load()
        assert float(config.coeficient_penalitzacio_top) == 0.05


@pytest.mark.django_db
class TestRankingProvisional:
    @pytest.fixture
    def setup_data(self):
        from music.models import Album, Artista, Canco, Territori

        Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})
        artista = Artista.objects.create(nom="Test", lastfm_nom="Test")
        album = Album.objects.create(artista=artista, nom="Album")
        canco = Canco.objects.create(
            artista=artista,
            album=album,
            nom="Track",
            data_llancament=date(2026, 1, 1),
            verificada=True,
        )
        return canco

    def test_create_provisional(self, setup_data):
        rp = TopProvisional.objects.create(
            canco=setup_data,
            territori="CAT",
            posicio=1,
            score_setmanal=85.5,
            escoltes_setmanals=1000,
        )
        assert rp.posicio == 1
        assert rp.territori == "CAT"
        assert str(rp) == "#1 Track (CAT)"

    def test_unique_canco_territori(self, setup_data):
        TopProvisional.objects.create(
            canco=setup_data,
            territori="CAT",
            posicio=1,
            score_setmanal=80.0,
        )
        with pytest.raises(Exception):
            TopProvisional.objects.create(
                canco=setup_data,
                territori="CAT",
                posicio=2,
                score_setmanal=70.0,
            )


@pytest.mark.django_db
class TestRankingSetmanal:
    def test_str(self):
        from music.models import Album, Artista, Canco

        artista = Artista.objects.create(nom="Zoo", lastfm_nom="Zoo")
        album = Album.objects.create(artista=artista, nom="Raval")
        canco = Canco.objects.create(artista=artista, album=album, nom="Llum")
        rs = TopSetmanal.objects.create(
            canco=canco,
            territori="VAL",
            setmana=date(2026, 4, 13),
            posicio=3,
            score_setmanal=72.1,
        )
        assert "#3" in str(rs)
        assert "Llum" in str(rs)
        assert "VAL" in str(rs)
