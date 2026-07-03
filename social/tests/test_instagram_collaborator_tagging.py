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
from social.payload import (
    _album_collabs,
    _instagram_urls_for_canco,
    build_top,
)
from social.top_redesign import _artist_credit


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


@pytest.mark.django_db
def test_album_collabs(trio):
    """Per-album collaborator artistes (principal excluded, deduped by
    artist). Both collaborators are returned — including c2 without a
    handle — so the visible credit (`artistes_noms`) shows every artist;
    handle filtering happens later when the tag list is derived."""
    p, c1, c2 = trio
    c = _make_canco(p, c1, c2)
    collabs = _album_collabs([c.album_id])
    assert [a.id for a in collabs[c.album_id]] == [c1.id, c2.id]


def test_artist_credit_joins_collaborators():
    """Top rows must show principal + collaborators (was principal-only,
    while stories already showed all)."""
    assert (
        _artist_credit({"artistes_noms": ["Main", "Col 1", "Col 2"]})
        == "Main, Col 1, Col 2"
    )
    # Legacy fallback when only the single field is present.
    assert _artist_credit({"artista_nom": "Solo"}) == "Solo"


def test_feed_redesign_artist_credit_joins_collaborators():
    """Novetats feed slides (album + singles) must show every artist
    too — same parity fix as the top rows, applied to feed_redesign."""
    from social.feed_redesign import _artist_credit as feed_credit

    assert (
        feed_credit({"artistes_noms": ["Main", "Guest"]}) == "Main, Guest"
    )
    assert feed_credit({"artista_nom": "Solo"}) == "Solo"
    assert feed_credit({}) == "—"


@pytest.mark.django_db
def test_build_novetats_carries_artistes_noms(trio):
    """`build_novetats` items expose `artistes_noms` (principal + track
    collaborators, both handled and un-handled) so the feed/story
    renderers can show the full credit — while `artistes_instagram_urls`
    stays handle-only for the tagger."""
    from social.payload import build_novetats

    p, c1, c2 = trio
    al = Album.objects.create(
        artista=p,
        nom="EXEMPLE Single",
        tipus="single",
        data_llancament=date(2026, 5, 20),
    )
    c = Canco.objects.create(
        artista=p,
        album=al,
        nom="EXEMPLE Track",
        isrc="ZZ00IG0000009",
        verificada=True,
        activa=True,
    )
    c.artistes_col.add(c1, c2)
    data = build_novetats(
        "nous_singles", date(2026, 5, 18), publish_date=date(2026, 5, 22)
    )
    item = next(i for i in data["items"] if i["slug"] == al.slug)
    # Every artist visible — including c2 (no handle).
    assert item["artistes_noms"] == [
        "EXEMPLE Principal",
        "EXEMPLE Collab1",
        "EXEMPLE Collab2",
    ]
    # Tagger list stays handle-only, principal first.
    assert item["artistes_instagram_urls"] == [
        "https://instagram.com/exemple_principal",
        "https://instagram.com/exemple_collab1",
    ]


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


def test_slide_tags_principal_first_round_robin_protects_all_entries():
    """Worst-case from prod 2026-05-23: one cançó with 1 principal +
    25 collabs would, under the naive flat-list algorithm, consume
    all 20 tag slots and starve the other 9 entries of their
    principal. With principal-first round-robin every entry that has
    a handle keeps its principal, and the remaining budget feeds
    collabs of the verbose entry."""
    # Entry 0: 1 principal + 25 collabs (well above the 20 cap on its own).
    big_entry = _entry(
        ["https://instagram.com/big_principal"]
        + [f"https://instagram.com/collab_{i:02d}" for i in range(25)]
    )
    # Entries 1..9: principal only, no collabs.
    small_entries = [
        _entry([f"https://instagram.com/solo_{i:02d}"]) for i in range(1, 10)
    ]
    data = {"entries": [big_entry, *small_entries]}
    out = Command._slide_tags(SocialPost.TIPUS_TOP_PPCC, 2, data)
    tags = out[1]
    assert len(tags) <= 20, "cap violated"
    handles = [t["username"] for t in tags]

    # 1. Every entry's principal IS present (10 of them).
    assert "big_principal" in handles
    for i in range(1, 10):
        assert (
            f"solo_{i:02d}" in handles
        ), f"solo_{i:02d} missing - the verbose entry monopolised the budget"

    # 2. The 10 remaining slots are filled with collabs of the big
    #    entry (the only one that has any).
    collab_handles = [h for h in handles if h.startswith("collab_")]
    assert len(collab_handles) == 10
    # 3. Total budget exhausted exactly.
    assert len(tags) == 20


def test_slide_tags_round_robin_when_multiple_entries_have_collabs():
    """Two entries with collabs: budget shared via round-robin so
    every entry gets its principal AND its first collab before any
    entry gets its second collab.

    NOTE: the slide is built in the renderer's countdown order, which
    REVERSES each block, so entry `b` (drawn first on the slide)
    precedes entry `a` within every pass."""
    a = _entry(
        [
            "https://instagram.com/a_p",
            "https://instagram.com/a_c1",
            "https://instagram.com/a_c2",
        ]
    )
    b = _entry(
        [
            "https://instagram.com/b_p",
            "https://instagram.com/b_c1",
            "https://instagram.com/b_c2",
        ]
    )
    data = {"entries": [a, b]}
    out = Command._slide_tags(SocialPost.TIPUS_TOP_PPCC, 2, data)
    handles = [t["username"] for t in out[1]]
    # Principals first (reversed block order → b before a).
    assert handles[0] == "b_p"
    assert handles[1] == "a_p"
    # Then 1st collab of every entry before any 2nd collab.
    assert handles[2] == "b_c1"
    assert handles[3] == "a_c1"
    # Then 2nd collabs.
    assert handles[4] == "b_c2"
    assert handles[5] == "a_c2"


def test_slide_tags_top_mirror_renderer_countdown_order():
    """Regression for the pre-2026-06 bug: slides render 40→1 but tags
    were built 1→40, mismatching every tag to the wrong artist. The
    tag chunks must now mirror `render_feed_top`'s countdown blocks
    ([(30,40),(20,30),(10,20),(0,10)], each reversed)."""
    # 40 entries, principal handle = "p{posicio}" (posicio = i + 1).
    entries = [_entry([f"https://instagram.com/p{i + 1}"]) for i in range(40)]
    data = {"entries": entries}
    # 1 cover + 4 list slides.
    out = Command._slide_tags(SocialPost.TIPUS_TOP_PPCC, 5, data)
    # Slide 1 = block (30,40) reversed → positions 40,39,…,31.
    assert [t["username"] for t in out[1]] == [f"p{n}" for n in range(40, 30, -1)]
    # Slide 4 = block (0,10) reversed → positions 10,9,…,1.
    assert [t["username"] for t in out[4]] == [f"p{n}" for n in range(10, 0, -1)]


def test_slide_tags_novetats_singles_tags_collabs():
    """nous_singles slides tag the principal + every collaborator with
    a handle (was principal-only before 2026-06)."""
    data = {
        "items": [
            _entry(["https://instagram.com/s_p", "https://instagram.com/s_c"]),
            _entry(["https://instagram.com/t_p"]),
        ]
    }
    out = Command._slide_tags(SocialPost.TIPUS_NOUS_SINGLES, 2, data)
    assert set(t["username"] for t in out[1]) == {"s_p", "s_c", "t_p"}


def test_slide_tags_novetats_albums_tags_collabs():
    """nous_albums: one slide per album, tagging the album artist +
    its track collaborators."""
    data = {
        "items": [
            _entry(["https://instagram.com/al_p", "https://instagram.com/al_c"]),
        ]
    }
    out = Command._slide_tags(SocialPost.TIPUS_NOUS_ALBUMS, 2, data)
    assert set(t["username"] for t in out[1]) == {"al_p", "al_c"}
