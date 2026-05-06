"""Tests for the `ArtistaQuerySet` managers (May-2026 audit).

Mirrors the `CancoQuerySet` pattern. The managers consolidate
filter pairs that were repeated across 20+ callsites:

  * `.public()`   →  `aprovat=True`
  * `.pendents()` →  `aprovat=False, pendent_review=True`
  * `.with_mbid()` →  has a non-empty MusicBrainz ID
  * `.with_ppcc()` →  has at least one PPCC localitat (i.e. an
                      ArtistaLocalitat with a non-NULL `municipi` FK)
"""

from __future__ import annotations

import pytest

from music.models import (
    Artista,
    ArtistaLocalitat,
    Municipi,
    Territori,
)


@pytest.mark.django_db
class TestArtistaQuerySetPublic:
    def test_public_returns_only_approved(self):
        Artista.objects.create(nom="Aprovat", lastfm_nom="A", aprovat=True)
        Artista.objects.create(
            nom="Pendent", lastfm_nom="P", aprovat=False, pendent_review=True
        )
        Artista.objects.create(
            nom="Descartat", lastfm_nom="D", aprovat=False, pendent_review=False
        )

        public = list(Artista.objects.public().values_list("nom", flat=True))
        assert public == ["Aprovat"]

    def test_public_chains_with_filter(self):
        Artista.objects.create(nom="Boira", lastfm_nom="Boira", aprovat=True)
        Artista.objects.create(nom="Manel", lastfm_nom="Manel", aprovat=True)
        result = Artista.objects.public().filter(nom__startswith="B")
        assert [a.nom for a in result] == ["Boira"]


@pytest.mark.django_db
class TestArtistaQuerySetPendents:
    def test_pendents_only_in_review_queue(self):
        Artista.objects.create(nom="Aprovat", lastfm_nom="A", aprovat=True)
        Artista.objects.create(
            nom="Pendent", lastfm_nom="P", aprovat=False, pendent_review=True
        )
        # Descartat: kept for FK integrity but not in queue.
        Artista.objects.create(
            nom="Descartat", lastfm_nom="D", aprovat=False, pendent_review=False
        )

        pendents = list(Artista.objects.pendents().values_list("nom", flat=True))
        assert pendents == ["Pendent"]


@pytest.mark.django_db
class TestArtistaQuerySetWithMbid:
    def test_with_mbid_includes_only_set(self):
        Artista.objects.create(
            nom="A",
            lastfm_nom="A",
            musicbrainz_id="11111111-1111-1111-1111-111111111111",
        )
        Artista.objects.create(nom="B", lastfm_nom="B", musicbrainz_id="")
        Artista.objects.create(nom="C", lastfm_nom="C")  # default ""

        names = sorted(Artista.objects.with_mbid().values_list("nom", flat=True))
        assert names == ["A"]


@pytest.mark.django_db
class TestArtistaQuerySetWithPpcc:
    def test_with_ppcc_excludes_non_ppcc_and_no_localitat(self):
        terr, _ = Territori.objects.get_or_create(
            codi="CAT", defaults={"nom": "Catalunya"}
        )
        muni = Municipi.objects.create(nom="Lloret", comarca="Selva", territori=terr)

        ppcc = Artista.objects.create(nom="PPCC", lastfm_nom="P", aprovat=True)
        ArtistaLocalitat.objects.create(artista=ppcc, municipi=muni)

        non_ppcc = Artista.objects.create(nom="NonPPCC", lastfm_nom="N", aprovat=True)
        ArtistaLocalitat.objects.create(
            artista=non_ppcc, municipi=None, localitat_manual="London"
        )

        no_loc = Artista.objects.create(nom="NoLoc", lastfm_nom="X", aprovat=True)

        names = sorted(Artista.objects.with_ppcc().values_list("nom", flat=True))
        assert names == ["PPCC"]
        assert "NonPPCC" not in names
        assert "NoLoc" not in names

    def test_with_ppcc_distinct(self):
        """Two PPCC localitats on the same artista must NOT yield two rows."""
        terr, _ = Territori.objects.get_or_create(
            codi="CAT", defaults={"nom": "Catalunya"}
        )
        m1 = Municipi.objects.create(nom="Lloret", comarca="Selva", territori=terr)
        m2 = Municipi.objects.create(nom="Tossa", comarca="Selva", territori=terr)

        a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
        ArtistaLocalitat.objects.create(artista=a, municipi=m1)
        ArtistaLocalitat.objects.create(artista=a, municipi=m2)

        assert Artista.objects.with_ppcc().count() == 1
