"""resolve_mbid location-aware behaviour.

Caught 2026-04-29 ("Casual" case): MB returns multiple homonyms with
varying scores. Old logic blindly returned the single one above
score 95, ignoring location. New logic should prefer the PPCC-area
candidate when our artist has PPCC localitats, even if its score is
lower.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from music.mb_sync import resolve_mbid
from music.models import Artista, ArtistaLocalitat, Municipi, Territori


@pytest.fixture
def cat_municipi(db):
    territori, _ = Territori.objects.get_or_create(
        codi="CAT", defaults={"nom": "Catalunya"}
    )
    return Municipi.objects.create(
        nom="Barcelona", comarca="Barcelonès", territori=territori
    )


@pytest.fixture
def cat_artist(db, cat_municipi):
    art = Artista.objects.create(nom="Casual", aprovat=False)
    ArtistaLocalitat.objects.create(artista=art, municipi=cat_municipi)
    return art


@pytest.fixture
def no_loc_artist(db):
    return Artista.objects.create(nom="Solo Match", aprovat=False)


def _mb_candidates(*tuples):
    """Helper: build MB-shaped dicts from `(name, score, area_name,
    disambiguation, mbid)` tuples."""
    out = []
    for name, score, area, disamb, mbid in tuples:
        c = {"id": mbid, "name": name, "score": score, "disambiguation": disamb}
        if area:
            c["area"] = {"name": area}
        out.append(c)
    return out


@pytest.mark.django_db
def test_picks_ppcc_candidate_over_higher_scored_non_ppcc(cat_artist):
    """The Casual case: US rapper at 100, CAT band at 91. Old logic
    picked the rapper. New logic must pick the band."""
    cands = _mb_candidates(
        ("Casual", 100, "United States", "US rapper", "us-rapper-id"),
        ("Casual", 91, "Catalunya", "dark rock band", "cat-band-id"),
        ("Casual", 86, "Russia", "rock band", "ru-id"),
    )
    with patch("music.mb_sync.mb.search_artist", return_value=cands):
        assert resolve_mbid(cat_artist) == "cat-band-id"


@pytest.mark.django_db
def test_refuses_when_only_non_ppcc_match(cat_artist):
    """If our artist is PPCC and the only candidate is explicitly
    non-PPCC, refuse — staff has to disambiguate."""
    cands = _mb_candidates(
        ("Casual", 100, "United States", "US rapper", "us-rapper-id"),
    )
    with patch("music.mb_sync.mb.search_artist", return_value=cands):
        assert resolve_mbid(cat_artist) is None


@pytest.mark.django_db
def test_refuses_when_no_localitats(no_loc_artist):
    """No localitats on our artist → can't disambiguate honestly →
    refuse the auto-match. Staff has to either add localitats or
    paste the MBID manually."""
    cands = _mb_candidates(
        ("Solo Match", 100, "United States", "rapper", "us-id"),
        ("Solo Match", 80, "Catalunya", "obscure", "cat-id"),
    )
    with patch("music.mb_sync.mb.search_artist", return_value=cands):
        assert resolve_mbid(no_loc_artist) is None


@pytest.mark.django_db
def test_refuses_when_multiple_ppcc_candidates(cat_artist):
    """Two PPCC candidates → ambiguous, staff picks."""
    cands = _mb_candidates(
        ("Casual", 95, "Catalunya", "band one", "cat-1"),
        ("Casual", 90, "Valencia", "band two", "cat-2"),
    )
    with patch("music.mb_sync.mb.search_artist", return_value=cands):
        assert resolve_mbid(cat_artist) is None


@pytest.mark.django_db
def test_blocked_mbid_excluded(cat_artist):
    """mb_blocked_mbids prevents re-suggesting a previously-rejected ID."""
    cat_artist.mb_blocked_mbids = ["us-rapper-id"]
    cat_artist.save(update_fields=["mb_blocked_mbids"])
    cands = _mb_candidates(
        ("Casual", 100, "United States", "US rapper", "us-rapper-id"),
        ("Casual", 91, "Catalunya", "dark rock band", "cat-band-id"),
    )
    with patch("music.mb_sync.mb.search_artist", return_value=cands):
        assert resolve_mbid(cat_artist) == "cat-band-id"


@pytest.mark.django_db
def test_refuses_areaeless_candidates(cat_artist):
    """Even with our PPCC localitats, an MB candidate with empty area
    can't be confirmed as the right one — refuse rather than risk a
    homonym whose MB record just hasn't been location-tagged yet."""
    cands = _mb_candidates(
        ("Casual", 96, "", "indie", "no-area-id"),
    )
    with patch("music.mb_sync.mb.search_artist", return_value=cands):
        assert resolve_mbid(cat_artist) is None


@pytest.mark.django_db
def test_score_floor_50_lets_low_score_ppcc_through(cat_artist):
    """The score floor is now low (50) so MB's relevance ranking
    stops being the gatekeeper; we trust name + location instead."""
    cands = _mb_candidates(
        ("Casual", 100, "United States", "rapper", "us-id"),
        (
            "Casual",
            60,
            "Catalunya",
            "small band",
            "cat-id",
        ),  # would have failed pre-fix
    )
    with patch("music.mb_sync.mb.search_artist", return_value=cands):
        assert resolve_mbid(cat_artist) == "cat-id"
