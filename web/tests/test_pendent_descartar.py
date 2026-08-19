"""Regression tests for `pendent_descartar` — tombstone, never delete.

The Last.fm similar→reject resurrection loop (audit 2026-06-02): a
discarded song-less pendent used to be hard-deleted, leaving no row for
`obtenir_metadata_lastfm._resolve_similar_target` to match, so an
approved artist that still recommended the name re-created the pendent
every sync. Discarding must now leave a tombstone (aprovat=False,
pendent_review=False).

# Spec: docs/architecture/ingesta.md
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from comptes.models import Usuari
from music.models import Album, Artista, Canco


@pytest.fixture
def staff_client(db):
    u = Usuari.objects.create_user(
        username="staffdesc",
        email="staffdesc@example.com",
        password="x",
        is_staff=True,
    )
    c = APIClient()
    c.force_authenticate(user=u)
    return c


@pytest.mark.django_db
def test_descartar_songless_placeholder_tombstones_not_deletes(staff_client):
    """(a) A lastfm_similar placeholder with no songs is tombstoned, not
    deleted: the row survives with aprovat=False, pendent_review=False."""
    a = Artista.objects.create(
        nom="Tremenda Jauría",
        lastfm_nom="Tremenda Jauría",
        aprovat=False,
        pendent_review=True,
        auto_descobert=True,
        font_descoberta="lastfm_similar",
    )
    r = staff_client.post(f"/api/v1/staff/pendents/{a.pk}/descartar/")
    assert r.status_code == 200, r.content
    assert r.json()["action"] == "tombstoned"
    # Row still exists (NOT deleted) and is out of the pendent queue.
    a.refresh_from_db()
    assert a.aprovat is False
    assert a.pendent_review is False
    assert Artista.objects.filter(pk=a.pk).exists()


@pytest.mark.django_db
def test_descartar_keeps_artist_with_verified_tracks(staff_client):
    """(c) Discarding a pendent that has verified tracks still works:
    pendent_review drops to False, the row (and its songs) stay."""
    a = Artista.objects.create(
        nom="Amb Cançons", lastfm_nom="Amb Cançons", aprovat=False, pendent_review=True
    )
    alb = Album.objects.create(artista=a, nom="Disc", slug="disc-desc")
    Canco.objects.create(
        artista=a, album=alb, nom="Tema", slug="tema-desc", verificada=True, activa=True
    )
    r = staff_client.post(f"/api/v1/staff/pendents/{a.pk}/descartar/")
    assert r.status_code == 200, r.content
    a.refresh_from_db()
    assert a.pendent_review is False
    assert Artista.objects.filter(pk=a.pk).exists()
    assert a.cancons.filter(verificada=True).count() == 1


@pytest.mark.django_db
def test_descartar_drops_from_pendents_list(staff_client):
    """The tombstoned artist no longer appears in the pendents queue."""
    a = Artista.objects.create(
        nom="The Fades",
        lastfm_nom="The Fades",
        aprovat=False,
        pendent_review=True,
        font_descoberta="lastfm_similar",
    )
    staff_client.post(f"/api/v1/staff/pendents/{a.pk}/descartar/")
    listing = staff_client.get("/api/v1/staff/pendents/").json()
    pks = {row["pk"] for row in listing.get("results", listing)}
    assert a.pk not in pks
