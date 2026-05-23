"""Tests for the Instagram collaborator tagging (Sprint Triple PART C).

Covers:
  * `_instagram_urls_for_canco` returns principal + collabs in order,
    skipping those without an instagram_url, no duplicates.
  * `build_top` puts that list under `artistes_instagram_urls` on
    every entry (alongside the legacy single-URL field).
  * `Command._slide_tags` produces one tag per artist+collab on each
    slide and respects the 20-tags-per-image cap.
  * Backward compat: an entry built by an older code path (only
    `artista_instagram_url`) still produces one tag.
"""

from __future__ import annotations

from datetime import date

import pytest

from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal
from social.management.commands.publicar_social import Command
from social.models import SocialPost
from social.payload import _instagram_urls_for_canco, build_top


@pytest.fixture
def trio(db):
    """Three artistes: principal with handle, two collaborators (one
    with handle, one without)."""
    p = Artista.objects.create(
        nom="EXEMPLE Principal",
        lastfm_nom="EXEMPLE Principal",
        instagram_url="https://instagram.com/exemple_principal",
    )
    c1 = Artista.objects.create(
        nom="EXEMPLE Collab1",
        lastfm_nom="EXEMPLE Collab1",
        instagram_url="https://instagram.com/exemple_collab1",
    )
    c2 = Artista.objects.create(
        nom="EXEMPLE Collab2",
        lastfm_nom="EXEMPLE Collab2",
        # No instagram_url -> excluded from the tag list.
    )
    return p, c1, c2


def _make_canco(p, c1, c2):
    al = Album.objects.create(artista=p, nom="EXEMPLE Album")
    c = Canco.objects.create(
        artista=p,
        album=al,
        nom="EXEMPLE Canco",
        isrc="ZZ00IG0000001",
        verificada=True,
        activa=True,
    )
    c.artistes_col.add(c1, c2)
    return c


@pytest.mark.django_db
def test_instagram_urls_for_canco_returns_principal_then_collabs(trio):
    p, c1, c2 = trio
    c = _make_canco(p, c1, c2)
    urls = _instagram_urls_for_canco(c)
    # Principal first, then collabs (c2 omitted: no instagram_url).
    assert urls == [
        "https://instagram.com/exemple_principal",
        "https://instagram.com/exemple_collab1",
    ]


@pytest.mark.django_db
def test_instagram_urls_for_canco_handles_none():
    assert _instagram_urls_for_canco(None) == []


@pytest.mark.django_db
def test_instagram_urls_for_canco_dedupes():
    """A collab pointing to the same handle as the principal should
    not generate a duplicate tag."""
    p = Artista.objects.create(
        nom="EXEMPLE P",
        lastfm_nom="EXEMPLE P",
        instagram_url="https://instagram.com/duplicate",
    )
    dup_collab = Artista.objects.create(
        nom="EXEMPLE Dup",
        lastfm_nom="EXEMPLE Dup",
        instagram_url="https://instagram.com/duplicate",
    )
    al = Album.objects.create(artista=p, nom="EXEMPLE Al")
    c = Canco.objects.create(
        artista=p,
        album=al,
        nom="EXEMPLE C",
        isrc="ZZ00IG0000002",
        verificada=True,
        activa=True,
    )
    c.artistes_col.add(dup_collab)
    urls = _instagram_urls_for_canco(c)
    assert urls == ["https://instagram.com/duplicate"]


@pytest.mark.django_db
def test_build_top_includes_artistes_instagram_urls(trio):
    p, c1, c2 = trio
    c = _make_canco(p, c1, c2)
    TopSetmanal.objects.create(
        canco=c,
        territori="CAT",
        setmana=date(2026, 5, 19),
        posicio=1,
        score_setmanal=1.0,
    )
    payload = build_top("CAT", date(2026, 5, 19))
    entry = payload["entries"][0]
    assert entry["artistes_instagram_urls"] == [
        "https://instagram.com/exemple_principal",
        "https://instagram.com/exemple_collab1",
    ]
    # Backward-compat field still present.
    assert entry["artista_instagram_url"] == "https://instagram.com/exemple_principal"


def _entry(urls: list[str]) -> dict:
    """Bare entry shape sufficient for _slide_tags."""
    return {
        "artistes_instagram_urls": urls,
        # Legacy single URL field still populated for the fallback
        # branch below; matches the principal of the new list.
        "artista_instagram_url": urls[0] if urls else "",
    }


def test_slide_tags_top_tags_principal_and_collabs():
    """Every artist with a handle gets a `user_tags` entry on the
    slide its cançó was drawn on."""
    data = {
        "entries": [
            _entry(
                [
                    "https://instagram.com/p1",
                    "https://instagram.com/c1",
                ]
            ),
            _entry(["https://instagram.com/p2"]),
        ]
    }
    # 1 cover + 1 list slide (only 2 entries, all fit on page 1).
    out = Command._slide_tags(SocialPost.TIPUS_TOP_PPCC, 2, data)
    assert out[0] == []  # cover slide
    handles = [t["username"] for t in out[1]]
    # Order: p1, c1, p2. The exact order matters less than presence
    # of all three.
    assert set(handles) == {"p1", "c1", "p2"}
    assert len(out[1]) == 3


def test_slide_tags_top_respects_20_cap():
    """A slide with many collabs caps at 20 tags (Meta's per-image
    limit). Principal gets priority because we iterate principal-first."""
    # 10 entries, each with 3 artist handles -> 30 candidate tags;
    # the slide should be truncated to 20.
    entries = [
        _entry(
            [
                f"https://instagram.com/p{i}",
                f"https://instagram.com/c{i}a",
                f"https://instagram.com/c{i}b",
            ]
        )
        for i in range(10)
    ]
    data = {"entries": entries}
    out = Command._slide_tags(SocialPost.TIPUS_TOP_PPCC, 2, data)
    assert len(out[1]) == 20


def test_slide_tags_backward_compat_single_url():
    """An entry from a stale payload (only `artista_instagram_url`,
    no `artistes_instagram_urls`) still produces one tag."""
    entry = {
        "artista_instagram_url": "https://instagram.com/legacy",
    }
    data = {"entries": [entry]}
    out = Command._slide_tags(SocialPost.TIPUS_TOP_PPCC, 2, data)
    assert [t["username"] for t in out[1]] == ["legacy"]


def test_slide_tags_skips_artists_without_handle():
    """Entries with empty `artistes_instagram_urls` produce no tags,
    they don't fail the run."""
    data = {
        "entries": [
            _entry([]),
            _entry(["https://instagram.com/visible"]),
        ]
    }
    out = Command._slide_tags(SocialPost.TIPUS_TOP_PPCC, 2, data)
    handles = [t["username"] for t in out[1]]
    assert handles == ["visible"]
