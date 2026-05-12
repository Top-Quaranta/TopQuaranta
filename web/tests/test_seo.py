"""Smoke tests for the SEO/SSR surface.

What we're locking in:
  - Each entity URL renders 200 with a unique <title>.
  - Each response carries Vary: User-Agent (so caches don't cross
    over between bot HTML and SPA shell).
  - JSON-LD blocks are present + parse as JSON.
  - Indexability rules: un-approved artist → 404, un-verified
    canco → 404, descartat album → 404.
  - Helmet hook (`/api/v1/seo/<entity>/<slug>/`) returns the same
    title the SSR template uses.
"""

from __future__ import annotations

import datetime
import json
import re

import pytest
from django.test import Client

from music.models import Album, Artista, Canco


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def artista(db):
    # /artista/<slug> now requires at least one verified active cançó
    # (web/seo/views.py::artista_seo). Build a minimal indexable
    # artist by attaching a default album + canco. Tests that exercise
    # the un-indexable case flip `aprovat=False`, which still trumps
    # this gate.
    a = Artista.objects.create(
        nom="Test Artist",
        slug="test-artist",
        aprovat=True,
    )
    default_album = Album.objects.create(
        nom="Default Album",
        slug="test-artist-default-album",
        artista=a,
        descartat=False,
    )
    Canco.objects.create(
        nom="Default Track",
        slug="test-artist-default-track",
        artista=a,
        album=default_album,
        verificada=True,
        activa=True,
    )
    return a


@pytest.fixture
def album(db, artista):
    # Same indexability gate: /album/<slug> now requires ≥1 verified
    # active cançó on the album itself, not just on its artista.
    # test_album_seo_404_when_descartat flips descartat after this
    # setup, exercising the gate it actually intends to test.
    al = Album.objects.create(
        nom="Test Album",
        slug="test-album",
        artista=artista,
        descartat=False,
    )
    Canco.objects.create(
        nom="Album Track",
        slug="test-album-track",
        artista=artista,
        album=al,
        verificada=True,
        activa=True,
    )
    return al


@pytest.fixture
def canco(db, artista, album):
    return Canco.objects.create(
        nom="Test Track",
        slug="test-track",
        artista=artista,
        album=album,
        verificada=True,
        activa=True,
    )


def _jsonld_blocks(html: str) -> list[dict]:
    blocks = re.findall(
        r'<script type="application/ld\+json">(.+?)</script>', html, re.DOTALL
    )
    return [json.loads(b) for b in blocks]


@pytest.mark.django_db
def test_homepage_seo_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.content.decode()
    assert "TopQuaranta" in body
    assert "<title>" in body
    assert "User-Agent" in r.get("Vary", "")


@pytest.mark.django_db
def test_artista_seo_unique_title(client, artista):
    r = client.get(f"/artista/{artista.slug}")
    assert r.status_code == 200
    body = r.content.decode()
    assert "Test Artist" in body
    # Title is per-page, NOT the homepage one.
    assert "Test Artist" in re.search(r"<title>(.+?)</title>", body).group(1)


@pytest.mark.django_db
def test_artista_seo_jsonld_is_musicgroup(client, artista):
    r = client.get(f"/artista/{artista.slug}")
    blocks = _jsonld_blocks(r.content.decode())
    musicgroup = next((b for b in blocks if b.get("@type") == "MusicGroup"), None)
    assert musicgroup is not None
    assert musicgroup["name"] == "Test Artist"


@pytest.mark.django_db
def test_canco_seo_404_when_unverified(client, canco):
    canco.verificada = False
    canco.save()
    r = client.get(f"/canco/{canco.slug}")
    assert r.status_code == 404


@pytest.mark.django_db
def test_artista_seo_404_when_unapproved(client, artista):
    artista.aprovat = False
    artista.save()
    r = client.get(f"/artista/{artista.slug}")
    assert r.status_code == 404


@pytest.mark.django_db
def test_album_seo_404_when_descartat(client, album):
    album.descartat = True
    album.save()
    r = client.get(f"/album/{album.slug}")
    assert r.status_code == 404


@pytest.mark.django_db
def test_seo_api_endpoint_for_helmet(client, artista):
    r = client.get(f"/api/v1/seo/artista/{artista.slug}/")
    assert r.status_code == 200
    payload = r.json()
    assert "Test Artist" in payload["title"]
    assert payload["canonical_url"].endswith(f"/artista/{artista.slug}")
    assert payload["og_image"]


@pytest.mark.django_db
def test_seo_api_unknown_entity_400(client):
    r = client.get("/api/v1/seo/squirrel/something/")
    assert r.status_code == 400


@pytest.mark.django_db
def test_breadcrumbs_present(client, artista):
    blocks = _jsonld_blocks(client.get(f"/artista/{artista.slug}").content.decode())
    bc = next((b for b in blocks if b.get("@type") == "BreadcrumbList"), None)
    assert bc is not None
    items = bc["itemListElement"]
    assert len(items) >= 2  # at least Inici + leaf
    assert items[0]["name"] == "Inici"


@pytest.mark.django_db
def test_canonical_url_is_absolute(client, artista):
    body = client.get(f"/artista/{artista.slug}").content.decode()
    canonical = re.search(r'<link rel="canonical" href="(.+?)"', body).group(1)
    assert canonical.startswith("https://www.topquaranta.cat/")


@pytest.mark.django_db
def test_hreflang_ca_present(client, artista):
    body = client.get(f"/artista/{artista.slug}").content.decode()
    assert 'hreflang="ca"' in body


# ── Block C: long-tail SSR routes ──────────────────────────────────


@pytest.mark.django_db
def test_territori_cat_renders(client):
    r = client.get("/territori/CAT")
    assert r.status_code == 200
    body = r.content.decode()
    assert "Catalunya" in body


@pytest.mark.django_db
def test_territori_unknown_404(client):
    r = client.get("/territori/XYZ")
    assert r.status_code == 404


@pytest.mark.django_db
def test_decada_thin_404(client):
    """Decade with no tracks returns 404 — don't expose thin pages."""
    r = client.get("/decada/1900")
    assert r.status_code == 404


@pytest.mark.django_db
def test_decada_invalid_format_404(client):
    r = client.get("/decada/202")  # not 4 digits ending in 0
    assert r.status_code == 404


@pytest.mark.django_db
def test_top_historic_no_data_404(client):
    """Historical week without TopSetmanal data → 404."""
    r = client.get("/top/CAT/setmana/1999-W30")
    assert r.status_code == 404


@pytest.mark.django_db
def test_top_historic_invalid_format_404(client):
    r = client.get("/top/CAT/setmana/notaweek")
    assert r.status_code == 404


@pytest.mark.django_db
def test_sitemap_index_lists_all_sections(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    body = r.content.decode()
    for s in [
        "sitemap-static.xml",
        "sitemap-artistes.xml",
        "sitemap-albums.xml",
        "sitemap-cancons.xml",
        "sitemap-territoris.xml",
        "sitemap-comarques.xml",
        "sitemap-decades.xml",
        "sitemap-top_historic.xml",
    ]:
        assert s in body, f"sitemap-index missing {s}"


@pytest.mark.django_db
def test_indexnow_key_file(client):
    r = client.get("/8f4c2e5b3a9d7c1f6e0b8a5d4c2e9f7b.txt")
    assert r.status_code == 200
    assert b"8f4c2e5b3a9d7c1f6e0b8a5d4c2e9f7b" in r.content
