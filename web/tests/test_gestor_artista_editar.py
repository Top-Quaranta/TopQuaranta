"""Tests for the gestor self-edit endpoint.

Exercises the three permission cases (anon, non-manager, verified
manager) plus the field-allowlist behaviour: critical fields like
`nom`/`slug`/`aprovat` must be silently ignored, and a no-op PATCH
must not write an audit row.
"""

import pytest
from rest_framework.test import APIClient

from comptes.models import UserArtista
from music.models import Artista, StaffAuditLog


@pytest.fixture
def artista(db):
    return Artista.objects.create(
        nom="Test Manager Band",
        slug="test-manager-band",
        aprovat=True,
        genere="indie",
    )


@pytest.fixture
def verified_manager(db, django_user_model, artista):
    u = django_user_model.objects.create_user(
        username="gestor", email="g@example.com", password="x"
    )
    UserArtista.objects.create(
        usuari=u,
        artista=artista,
        sollicitud_text="x" * 25,
        verificat=True,
        estat=UserArtista.ESTAT_APROVAT,
    )
    return u


@pytest.fixture
def other_user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="other", email="o@example.com", password="x"
    )


def _url(pk):
    return f"/api/v1/compte/artista/{pk}/editar/"


def test_anon_rejected(db, artista):
    c = APIClient()
    assert c.get(_url(artista.pk)).status_code in (401, 403)
    assert c.patch(_url(artista.pk), {}, format="json").status_code in (401, 403)


def test_non_manager_forbidden(other_user, artista):
    c = APIClient()
    c.force_authenticate(user=other_user)
    assert c.get(_url(artista.pk)).status_code == 403
    assert c.patch(_url(artista.pk), {"bio": "hi"}, format="json").status_code == 403


def test_verified_manager_can_get(verified_manager, artista):
    c = APIClient()
    c.force_authenticate(user=verified_manager)
    r = c.get(_url(artista.pk))
    assert r.status_code == 200
    body = r.json()
    assert body["nom"] == artista.nom
    assert body["genere"] == "indie"
    assert "social" in body and "spotify_url" in body["social"]
    assert isinstance(body["social_fields"], list)


def test_patch_writes_allowed_fields_and_audits(verified_manager, artista):
    c = APIClient()
    c.force_authenticate(user=verified_manager)
    r = c.patch(
        _url(artista.pk),
        {
            "bio": "Una bio nova.",
            "genere": "pop",
            "spotify_url": "https://open.spotify.com/artist/abc",
        },
        format="json",
    )
    assert r.status_code == 200, r.content
    body = r.json()
    assert set(body["canviats"]) == {"bio", "genere", "spotify_url"}
    artista.refresh_from_db()
    assert artista.bio == "Una bio nova."
    assert artista.genere == "pop"
    assert artista.spotify_url.startswith("https://open.spotify.com/")
    audit = StaffAuditLog.objects.filter(action="gestor_edita_artista").last()
    assert audit is not None
    assert audit.target_id == artista.pk
    assert set(audit.metadata.get("camps", [])) == {"bio", "genere", "spotify_url"}


def test_critical_fields_silently_ignored(verified_manager, artista):
    c = APIClient()
    c.force_authenticate(user=verified_manager)
    r = c.patch(
        _url(artista.pk),
        {
            "nom": "RENAMED",
            "slug": "hacked-slug",
            "aprovat": False,
            "genere": "rock",
        },
        format="json",
    )
    assert r.status_code == 200
    artista.refresh_from_db()
    assert artista.nom == "Test Manager Band"
    assert artista.slug == "test-manager-band"
    assert artista.aprovat is True
    assert artista.genere == "rock"
    assert r.json()["canviats"] == ["genere"]


def test_invalid_url_returns_400(verified_manager, artista):
    c = APIClient()
    c.force_authenticate(user=verified_manager)
    r = c.patch(_url(artista.pk), {"spotify_url": "ftp://nope"}, format="json")
    assert r.status_code == 400
    assert "spotify_url" in r.json()["errors"]


def test_noop_patch_does_not_audit(verified_manager, artista):
    StaffAuditLog.objects.filter(action="gestor_edita_artista").delete()
    c = APIClient()
    c.force_authenticate(user=verified_manager)
    r = c.patch(_url(artista.pk), {"genere": artista.genere}, format="json")
    assert r.status_code == 200
    assert r.json()["canviats"] == []
    assert not StaffAuditLog.objects.filter(action="gestor_edita_artista").exists()
