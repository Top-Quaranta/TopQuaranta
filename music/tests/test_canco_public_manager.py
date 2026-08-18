"""No-regression pin for `Canco.objects.public()`.

The June-2026 DRY pass swapped the hand-rolled
`Canco.objects.filter(verificada=True, activa=True)` for the
`.public()` manager in the public-output paths (sitemap, SEO/estat,
PSI metrics). The swap is only safe while `.public()` selects the
EXACT same row set as the inline pair. This test asserts that
equivalence id-by-id and fails if they diverge by a single row, so a
future edit to the manager definition cannot silently change the
public site / sitemap / SEO output.
"""

from __future__ import annotations

from datetime import date

import pytest

from music.models import Album, Artista, Canco


def _mk_canco(artista, *, verificada, activa, nom):
    return Canco.objects.create(
        artista=artista,
        album=Album.objects.create(
            artista=artista, nom=f"alb-{nom}", data_llancament=date(2026, 1, 1)
        ),
        nom=nom,
        data_llancament=date(2026, 1, 1),
        verificada=verificada,
        activa=activa,
    )


@pytest.mark.django_db
class TestCancoPublicManagerEquivalence:
    def _seed(self):
        a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
        # One row of every verificada/activa combination so the pin
        # exercises both flags independently, not just the happy path.
        public = _mk_canco(a, verificada=True, activa=True, nom="public")
        _mk_canco(a, verificada=False, activa=True, nom="pendent")
        _mk_canco(a, verificada=True, activa=False, nom="verified-inactive")
        _mk_canco(a, verificada=False, activa=False, nom="discarded")
        return public

    def test_public_manager_has_expected_semantics(self):
        public = self._seed()
        assert set(Canco.objects.public().values_list("id", flat=True)) == {public.id}
