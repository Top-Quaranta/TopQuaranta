from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from ranking.models import ConfiguracioGlobal, SenyalDiari, TopProvisional

# These used to be gated on PostgreSQL, from the days the algorithm was
# raw SQL (DISTINCT ON, ::text casts). v2.0 is pure ORM, the test settings
# are SQLite, so the gate never opened and the file never ran — long
# enough for its fixtures to stop describing the algorithm. Removed
# 2026-08-15; see the module docstring of test_coherencia_ranking.py.


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
        # Relative to today: a hardcoded date silently ages out of the
        # 365-day window and takes the whole file down with it.
        llancament = date.today() - timedelta(days=60)
        album = Album.objects.create(
            artista=artista,
            nom="Album",
            data_llancament=llancament,
        )

        cancons = []
        for i in range(5):
            c = Canco.objects.create(
                artista=artista,
                album=album,
                nom=f"Track {i}",
                data_llancament=llancament,
                verificada=True,
                activa=True,
            )
            cancons.append(c)

        # 7 days of signal that GROWS. `lastfm_playcount` is cumulative,
        # so a flat series means zero plays this week and the song is
        # filtered out by `min_escoltes_top` — which is exactly what the
        # old fixture did, and why these tests failed the moment they
        # were allowed to run.
        today = date.today()
        for day_offset in range(7):
            d = today - timedelta(days=day_offset)
            for j, c in enumerate(cancons):
                SenyalDiari.objects.create(
                    canco=c,
                    data=d,
                    lastfm_playcount=(j + 1) * 1000 + (6 - day_offset) * 100,
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
