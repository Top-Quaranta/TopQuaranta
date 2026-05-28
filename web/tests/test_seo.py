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


# ── Thin artiste pages (200 + noindex) — audit flags #3/#6 ──────────


def _meta_desc(html: str) -> str:
    m = re.search(r'<meta name="description" content="(.*?)"', html, re.DOTALL)
    return m.group(1) if m else ""


@pytest.mark.django_db
def test_artista_thin_200_noindex_generated_desc(client, db):
    """Case A: approved artiste with no indexable cançó → 200 +
    noindex, generated description (never the Last.fm placeholder),
    minimal JSON-LD (no discography)."""
    a = Artista.objects.create(
        nom="Thin Band",
        slug="thin-band",
        aprovat=True,
        lastfm_bio_summary="Read more on Last.fm",
    )
    r = client.get(f"/artista/{a.slug}")
    assert r.status_code == 200
    body = r.content.decode()
    assert 'name="robots" content="noindex' in body
    assert "Thin Band" in body
    desc = _meta_desc(body)
    assert desc and "Read more on Last.fm" not in desc
    # Minimal MusicGroup: name present, no album/track arrays.
    mg = next(b for b in _jsonld_blocks(body) if b.get("@type") == "MusicGroup")
    assert mg["name"] == "Thin Band"
    assert "album" not in mg and "track" not in mg


@pytest.mark.django_db
def test_artista_indexable_is_index_not_noindex(client, artista):
    """Case B: approved artiste WITH indexable cançó → 200, indexable
    (no noindex)."""
    r = client.get(f"/artista/{artista.slug}")
    assert r.status_code == 200
    body = r.content.decode()
    assert 'name="robots" content="index' in body
    assert "noindex" not in body


@pytest.mark.django_db
def test_artista_placeholder_bio_not_emitted_when_indexable(client, artista):
    """Case C: approved + indexable but bio is the Last.fm placeholder
    → 200, no noindex, description falls back to generated (placeholder
    never emitted)."""
    artista.bio = ""
    artista.lastfm_bio_summary = "Read more on Last.fm"
    artista.save()
    r = client.get(f"/artista/{artista.slug}")
    assert r.status_code == 200
    body = r.content.decode()
    assert "noindex" not in body
    desc = _meta_desc(body)
    assert desc and "Read more on Last.fm" not in desc


@pytest.mark.django_db
def test_artista_seo_404_when_missing(client, db):
    """Case E: non-existent slug → 404."""
    r = client.get("/artista/no-existeix-xyz")
    assert r.status_code == 404


@pytest.mark.django_db
def test_seo_api_artista_thin_is_noindex(client, db):
    """SPA parity: the helmet endpoint reports noindex + minimal
    JSON-LD for a thin artiste."""
    a = Artista.objects.create(nom="Thin API", slug="thin-api", aprovat=True)
    r = client.get(f"/api/v1/seo/artista/{a.slug}/")
    assert r.status_code == 200
    payload = r.json()
    assert "noindex" in payload["robots"]
    mg = next(b for b in payload["jsonld"] if b.get("@type") == "MusicGroup")
    assert "album" not in mg and "track" not in mg


@pytest.mark.django_db
def test_sitemap_excludes_thin_artista(client, db):
    """A thin artiste (no indexable cançó) must NOT appear in the
    artistes sitemap (it's served noindex)."""
    Artista.objects.create(nom="Thin Sitemap", slug="thin-sitemap", aprovat=True)
    r = client.get("/sitemap-artistes.xml")
    assert r.status_code == 200
    assert "/artista/thin-sitemap" not in r.content.decode()


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
