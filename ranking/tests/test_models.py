from datetime import date
from decimal import Decimal

import pytest

from ranking.models import ConfiguracioGlobal, TopProvisional, TopSetmanal


@pytest.mark.django_db
class TestConfiguracioGlobal:
    def test_load_creates_singleton(self):
        config = ConfiguracioGlobal.load()
        assert config.pk == 1
        assert config.min_escoltes_top == 5

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


@pytest.mark.django_db
class TestPotPublicar:
    """The master switch `distribucio_activa` + per-channel `*_actiu`
    gate, shared by every publisher (2026-06-07)."""

    ALL = ["instagram", "mastodon", "bluesky", "telegram", "newsletter", "rss"]

    def _cfg(self, **kw):
        cfg = ConfiguracioGlobal.load()
        # Turn every channel ON so the test isolates the master.
        for c in self.ALL:
            setattr(cfg, f"{c}_actiu", True)
        cfg.distribucio_activa = True
        for k, v in kw.items():
            setattr(cfg, k, v)
        cfg.save()
        return cfg

    def test_master_off_blocks_all_six(self):
        cfg = self._cfg(distribucio_activa=False)
        for c in self.ALL:
            assert cfg.pot_publicar(c) is False, c

    def test_master_on_all_channels_on(self):
        cfg = self._cfg()
        for c in self.ALL:
            assert cfg.pot_publicar(c) is True, c

    def test_channel_off_blocks_only_that_channel(self):
        cfg = self._cfg(newsletter_actiu=False)
        assert cfg.pot_publicar("newsletter") is False
        for c in [x for x in self.ALL if x != "newsletter"]:
            assert cfg.pot_publicar(c) is True, c

    def test_master_overrides_channel_on(self):
        # Master off wins even if the channel switch is on.
        cfg = self._cfg(distribucio_activa=False, instagram_actiu=True)
        assert cfg.pot_publicar("instagram") is False

    def test_unknown_channel_raises(self):
        cfg = self._cfg()
        with pytest.raises(ValueError):
            cfg.pot_publicar("tiktok")

    def test_default_is_active(self):
        # A freshly-loaded config does not pause anything new (default
        # True): the per-channel switch decides.
        cfg = ConfiguracioGlobal.load()
        assert cfg.distribucio_activa is True
        assert cfg.pot_publicar("instagram") == cfg.instagram_actiu
