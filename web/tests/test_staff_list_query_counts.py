"""N+1 regression guards for the staff LIST endpoints.

Caught 2026-06-07 (auditoria de monitoratge, informe 2b): the row
builders for the cançons and artistes/pendents lists issued one query
per row (collab M2M, reverse Spotify OneToOne, localitat re-query that
defeated the prefetch, Last.fm aliases). With the default page size of
50 (capped at 200) that meant up to hundreds of queries per page.

These tests are DIFFERENTIAL: they assert the query count does NOT grow
with the number of rows. A genuine N+1 makes the larger dataset cost
more queries than the smaller one; a properly prefetched endpoint costs
the same. This is robust to unrelated base-query drift (auth, pagination
count, the propostes/homonym maps) because those are row-count
independent.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from music.models import (
    Album,
    Artista,
    ArtistaDeezer,
    ArtistaLastfmAlias,
    ArtistaLocalitat,
    Canco,
    Municipi,
    SpotifyMetadata,
    Territori,
)


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="qcount_tester",
        email="qc@example.com",
        password="x",
        is_staff=True,
    )
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _query_count(client, url) -> int:
    with CaptureQueriesContext(connection) as ctx:
        r = client.get(url)
        assert r.status_code == 200, r.content
    return len(ctx)


def _make_pending_cancons(n: int, *, start: int) -> None:
    """n pendent cançons, each with its own artista + album + one
    collaborator + a SpotifyMetadata row — i.e. every per-row relation
    the cançons row builder touches."""
    for i in range(start, start + n):
        a = Artista.objects.create(nom=f"QC-A{i}", slug=f"qc-a{i}", aprovat=True)
        col = Artista.objects.create(nom=f"QC-COL{i}", slug=f"qc-col{i}", aprovat=False)
        al = Album.objects.create(nom=f"QC-AL{i}", slug=f"qc-al{i}", artista=a)
        c = Canco.objects.create(
            nom=f"QC-C{i}",
            slug=f"qc-c{i}",
            artista=a,
            album=al,
            verificada=False,
            activa=True,
        )
        c.artistes_col.add(col)
        SpotifyMetadata.objects.create(canco=c)


def _make_pending_artistes(n: int, *, terr: Territori, start: int) -> None:
    """n pendent artistes, each with a localitat (municipi), a Deezer ID
    and a Last.fm alias — the per-row relations the artist card reads."""
    for i in range(start, start + n):
        a = Artista.objects.create(
            nom=f"QC-P{i}", slug=f"qc-p{i}", aprovat=False, pendent_review=True
        )
        m = Municipi.objects.create(nom=f"QC-M{i}", comarca="QC", territori=terr)
        ArtistaLocalitat.objects.create(artista=a, municipi=m)
        ArtistaDeezer.objects.create(artista=a, deezer_id=900000 + i)
        ArtistaLastfmAlias.objects.create(artista=a, nom=f"QC-alias{i}")


@pytest.mark.django_db
def test_cancons_list_no_n_plus_one(staff_client):
    """Query count for /staff/cancons/ must be independent of row count
    (guards select_related('spotify') + prefetch_related('artistes_col'))."""
    _make_pending_cancons(2, start=0)
    small = _query_count(staff_client, "/api/v1/staff/cancons/")
    _make_pending_cancons(6, start=2)  # now 8 rows total
    large = _query_count(staff_client, "/api/v1/staff/cancons/")
    assert large == small, (
        f"cançons list scales with rows (N+1): {small} q for 2 rows, "
        f"{large} q for 8 rows"
    )


@pytest.mark.django_db
def test_pendents_list_no_n_plus_one(staff_client):
    """Query count for /staff/pendents/ must be independent of row count
    (guards the localitat prefetch use + lastfm_aliases prefetch)."""
    terr = Territori.objects.create(codi="QCX", nom="QC Terr")
    _make_pending_artistes(2, terr=terr, start=0)
    small = _query_count(staff_client, "/api/v1/staff/pendents/")
    _make_pending_artistes(6, terr=terr, start=2)  # now 8 rows total
    large = _query_count(staff_client, "/api/v1/staff/pendents/")
    assert large == small, (
        f"pendents list scales with rows (N+1): {small} q for 2 rows, "
        f"{large} q for 8 rows"
    )


@pytest.mark.django_db
def test_artistes_list_no_n_plus_one(staff_client):
    """Same guard on /staff/artistes/ (shares _artista_card)."""
    terr = Territori.objects.create(codi="QCY", nom="QC Terr Y")
    # Approved artistes show in the default artistes list.
    for i in range(2):
        a = Artista.objects.create(nom=f"QC-AP{i}", slug=f"qc-ap{i}", aprovat=True)
        m = Municipi.objects.create(nom=f"QC-AM{i}", comarca="QC", territori=terr)
        ArtistaLocalitat.objects.create(artista=a, municipi=m)
        ArtistaDeezer.objects.create(artista=a, deezer_id=800000 + i)
        ArtistaLastfmAlias.objects.create(artista=a, nom=f"QC-apalias{i}")
    small = _query_count(staff_client, "/api/v1/staff/artistes/")
    for i in range(2, 8):
        a = Artista.objects.create(nom=f"QC-AP{i}", slug=f"qc-ap{i}", aprovat=True)
        m = Municipi.objects.create(nom=f"QC-AM{i}", comarca="QC", territori=terr)
        ArtistaLocalitat.objects.create(artista=a, municipi=m)
        ArtistaDeezer.objects.create(artista=a, deezer_id=800000 + i)
        ArtistaLastfmAlias.objects.create(artista=a, nom=f"QC-apalias{i}")
    large = _query_count(staff_client, "/api/v1/staff/artistes/")
    assert large == small, (
        f"artistes list scales with rows (N+1): {small} q for 2 rows, "
        f"{large} q for 8 rows"
    )
