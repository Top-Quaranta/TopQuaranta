import pytest

from music.models import Album, Artista, Canco, Territori


@pytest.fixture
def territoris():
    """Get or create the 3 standard territories."""
    cat, _ = Territori.objects.get_or_create(codi="CAT", defaults={"nom": "Catalunya"})
    val, _ = Territori.objects.get_or_create(
        codi="VAL", defaults={"nom": "País Valencià"}
    )
    bal, _ = Territori.objects.get_or_create(
        codi="BAL", defaults={"nom": "Illes Balears"}
    )
    return {"CAT": cat, "VAL": val, "BAL": bal}


@pytest.mark.django_db
class TestArtista:
    def test_get_territoris_multiple(self, territoris):
        a = Artista.objects.create(nom="Marala", lastfm_nom="Marala")
        a.territoris.set([territoris["CAT"], territoris["VAL"], territoris["BAL"]])
        assert set(a.get_territoris()) == {"CAT", "VAL", "BAL"}

    def test_get_territoris_single(self, territoris):
        a = Artista.objects.create(nom="Zoo", lastfm_nom="Zoo")
        a.territoris.set([territoris["VAL"]])
        assert a.get_territoris() == ["VAL"]

    def test_get_territoris_empty(self):
        a = Artista.objects.create(nom="Nou", lastfm_nom="Nou")
        assert a.get_territoris() == []


@pytest.mark.django_db
class TestCanco:
    def _make_canco(self, territoris_fixture, lastfm_nom="", col_territoris=None):
        artista = Artista.objects.create(nom="Zoo", lastfm_nom="Zoo")
        artista.territoris.set([territoris_fixture["VAL"]])
        album = Album.objects.create(nom="Raval", artista=artista)
        canco = Canco.objects.create(
            nom="Estimar-te com la Terra",
            lastfm_nom=lastfm_nom,
            album=album,
            artista=artista,
        )
        if col_territoris:
            for nom_col, codis in col_territoris:
                col = Artista.objects.create(nom=nom_col, lastfm_nom=nom_col)
                col.territoris.set([territoris_fixture[c] for c in codis])
                canco.artistes_col.add(col)
        return canco

    def test_lastfm_lookup_nom_uses_lastfm_nom(self, territoris):
        c = self._make_canco(territoris, lastfm_nom="Estimar-te Com La Terra")
        assert c.lastfm_lookup_nom == "Estimar-te Com La Terra"

    def test_lastfm_lookup_nom_falls_back_to_nom(self, territoris):
        c = self._make_canco(territoris, lastfm_nom="")
        assert c.lastfm_lookup_nom == "Estimar-te com la Terra"

    def test_get_territoris_main_artist_only(self, territoris):
        """Track with single artist → only that artist's territories."""
        c = self._make_canco(territoris)
        assert c.get_territoris() == {"VAL"}

    def test_get_territoris_with_collaborator(self, territoris):
        """Txarango (CAT) + Zoo (VAL) collab → track in CAT and VAL."""
        c = self._make_canco(
            territoris,
            col_territoris=[("Txarango", ["CAT"])],
        )
        assert c.get_territoris() == {"VAL", "CAT"}
