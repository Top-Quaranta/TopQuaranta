from datetime import date, timedelta
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command

from ranking.models import ConfiguracioGlobal, SenyalDiari, TopProvisional

# Raw SQL uses PostgreSQL-specific syntax (DISTINCT ON, ::text casts).
_is_postgres = "postgresql" in settings.DATABASES["default"].get("ENGINE", "")
pytestmark = pytest.mark.skipif(not _is_postgres, reason="Requires PostgreSQL")


@pytest.mark.django_db
class TestCalcularRankingCommand:
    @pytest.fixture
    def setup_data(self):
        """Create minimal data for ranking: config + territory + artist + tracks + signals."""
        from music.models import Album, Artista, Canco, Territori

        ConfiguracioGlobal.objects.create(pk=1)
        cat, _ = Territori.objects.get_or_create(
            codi="CAT", defaults={"nom": "Catalunya"}
        )
        artista = Artista.objects.create(nom="Feliu", lastfm_nom="Feliu", aprovat=True)
        artista.territoris.add(cat)
        album = Album.objects.create(
            artista=artista,
            nom="Album",
            data_llancament=date(2026, 3, 1),
        )

        cancons = []
        for i in range(5):
            c = Canco.objects.create(
                artista=artista,
                album=album,
                nom=f"Track {i}",
                data_llancament=date(2026, 3, 1),
                verificada=True,
                activa=True,
            )
            cancons.append(c)

        # Create 7 days of signal data
        today = date.today()
        for day_offset in range(7):
            d = today - timedelta(days=day_offset)
            for j, c in enumerate(cancons):
                SenyalDiari.objects.create(
                    canco=c,
                    data=d,
                    lastfm_playcount=(j + 1) * 1000,
                    lastfm_listeners=(j + 1) * 100,
                    error=False,
                )

        return cancons

    def test_dry_run_no_writes(self, setup_data):
        out = StringIO()
        call_command("calcular_top", "--dry-run", "--territori", "CAT", stdout=out)
        output = out.getvalue()
        assert "DRY RUN" in output or "dry" in output.lower()
        from ranking.models import TopSetmanal

        assert TopSetmanal.objects.count() == 0

    def test_provisional_flag_writes_to_provisional(self, setup_data):
        out = StringIO()
        call_command("calcular_top", "--provisional", "--territori", "CAT", stdout=out)
        assert TopProvisional.objects.filter(territori="CAT").exists()

    def test_provisional_truncates_on_rerun(self, setup_data):
        call_command(
            "calcular_top", "--provisional", "--territori", "CAT", stdout=StringIO()
        )
        first_count = TopProvisional.objects.filter(territori="CAT").count()
        call_command(
            "calcular_top", "--provisional", "--territori", "CAT", stdout=StringIO()
        )
        second_count = TopProvisional.objects.filter(territori="CAT").count()
        assert first_count == second_count
