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


# ── validate_artista_area ─────────────────────────────────────────────


@pytest.mark.django_db
def test_validate_flags_non_ppcc_mbid_when_artist_is_ppcc(cat_artist):
    """The cron's defence-in-depth: even if a previous run assigned
    the wrong MBID, the next iteration must catch it."""
    from music.mb_sync import validate_artista_area

    cat_artist.musicbrainz_id = "us-rapper-id"
    cat_artist.save(update_fields=["musicbrainz_id"])
    mb_data = {"id": "us-rapper-id", "area": {"name": "United States"}}
    with patch("music.mb_sync.mb.get_artist", return_value=mb_data):
        mismatch, reason = validate_artista_area(cat_artist)
    assert mismatch is True
    assert "non-ppcc" in reason


@pytest.mark.django_db
def test_validate_accepts_ppcc_mbid(cat_artist):
    from music.mb_sync import validate_artista_area

    cat_artist.musicbrainz_id = "cat-band-id"
    cat_artist.save(update_fields=["musicbrainz_id"])
    mb_data = {"id": "cat-band-id", "area": {"name": "Catalunya"}}
    with patch("music.mb_sync.mb.get_artist", return_value=mb_data):
        mismatch, reason = validate_artista_area(cat_artist)
    assert mismatch is False


@pytest.mark.django_db
def test_validate_skips_when_no_localitats(no_loc_artist):
    """Without our own location anchor we can't tell — return ok."""
    from music.mb_sync import validate_artista_area

    no_loc_artist.musicbrainz_id = "any-id"
    no_loc_artist.save(update_fields=["musicbrainz_id"])
    mb_data = {"id": "any-id", "area": {"name": "Brazil"}}
    with patch("music.mb_sync.mb.get_artist", return_value=mb_data):
        mismatch, _ = validate_artista_area(no_loc_artist)
    assert mismatch is False


@pytest.mark.django_db
def test_validate_skips_when_mb_area_empty(cat_artist):
    """Many small PPCC bands lack area on MB — don't penalise them."""
    from music.mb_sync import validate_artista_area

    cat_artist.musicbrainz_id = "no-area-id"
    cat_artist.save(update_fields=["musicbrainz_id"])
    mb_data = {"id": "no-area-id", "area": None}
    with patch("music.mb_sync.mb.get_artist", return_value=mb_data):
        mismatch, _ = validate_artista_area(cat_artist)
    assert mismatch is False


# ── Spain / France / Italy / Andorra are inconclusive (2026-04-30) ────


@pytest.mark.django_db
def test_validate_treats_spain_as_inconclusive(cat_artist):
    """`area='Spain'` doesn't tell us if the artist is PPCC or
    elsewhere-in-Spain. Caught 2026-04-30: 207 of 302 auto-unassigns
    had reason='Spain', virtually all false positives."""
    from music.mb_sync import validate_artista_area

    cat_artist.musicbrainz_id = "spain-mbid"
    cat_artist.save(update_fields=["musicbrainz_id"])
    mb_data = {"id": "spain-mbid", "area": {"name": "Spain"}}
    with patch("music.mb_sync.mb.get_artist", return_value=mb_data):
        mismatch, reason = validate_artista_area(cat_artist)
    assert mismatch is False
    assert "inconclusive" in reason


@pytest.mark.django_db
def test_validate_treats_france_as_inconclusive(cat_artist):
    """`area='France'` covers Catalunya Nord — never auto-unassign."""
    from music.mb_sync import validate_artista_area

    cat_artist.musicbrainz_id = "fr-mbid"
    cat_artist.save(update_fields=["musicbrainz_id"])
    mb_data = {"id": "fr-mbid", "area": {"name": "France"}}
    with patch("music.mb_sync.mb.get_artist", return_value=mb_data):
        mismatch, _ = validate_artista_area(cat_artist)
    assert mismatch is False


# ── Specific PPCC municipalities recognised via Municipi table ────────


@pytest.mark.django_db
def test_looks_ppcc_recognises_municipi_by_name():
    """A small PPCC town (Vic, Mataró, Bunyola, …) appears in our
    Municipi table; `_looks_ppcc` cross-references the table so
    short MB area strings still match."""
    from music.mb_sync import _looks_ppcc
    from music.models import Municipi, Territori

    cat_terr, _ = Territori.objects.get_or_create(
        codi="CAT", defaults={"nom": "Catalunya"}
    )
    Municipi.objects.create(nom="Vic", comarca="Osona", territori=cat_terr)
    assert _looks_ppcc("Vic") is True
    assert _looks_ppcc("vic") is True  # case-insensitive
    # A foreign town isn't in our Municipi table.
    assert _looks_ppcc("Leeds") is False


@pytest.mark.django_db
def test_validate_accepts_ppcc_municipi(cat_artist):
    """A specific Catalan town shouldn't get unassigned — it's in
    our Municipi table under territori=CAT."""
    from music.mb_sync import validate_artista_area
    from music.models import Municipi, Territori

    cat_terr, _ = Territori.objects.get_or_create(
        codi="CAT", defaults={"nom": "Catalunya"}
    )
    Municipi.objects.create(nom="Vic", comarca="Osona", territori=cat_terr)
    cat_artist.musicbrainz_id = "vic-band"
    cat_artist.save(update_fields=["musicbrainz_id"])
    mb_data = {"id": "vic-band", "area": {"name": "Vic"}}
    with patch("music.mb_sync.mb.get_artist", return_value=mb_data):
        mismatch, reason = validate_artista_area(cat_artist)
    assert mismatch is False
    assert reason == "ok-ppcc"


@pytest.mark.django_db
def test_validate_still_catches_real_non_ppcc_country(cat_artist):
    """The whole point: a US / MX / JP area still triggers a
    legitimate unassignment. The fix is meant to stop false
    positives, not deactivate the defence-in-depth altogether."""
    from music.mb_sync import validate_artista_area

    cat_artist.musicbrainz_id = "mexican-band"
    cat_artist.save(update_fields=["musicbrainz_id"])
    mb_data = {"id": "mexican-band", "area": {"name": "Mexico"}}
    with patch("music.mb_sync.mb.get_artist", return_value=mb_data):
        mismatch, reason = validate_artista_area(cat_artist)
    assert mismatch is True
    assert "non-ppcc" in reason
