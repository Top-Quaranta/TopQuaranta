# Spec: docs/architecture/pipeline.md
"""DIES_CADUCITAT guard at every Canco-creation frontier.

Caught 2026-06-02: Tres Fan Ball albums from 1994/1997/2005/2013
were recreating ~38 pendents every ~30 days. P2 of `obtenir_novetats`
re-checks every non-discarded album on a 30-day cadence regardless
of age, `_create_track` created tracks with `data_llancament`
inherited from the (correctly old) album, `netejar_caducades` swept
them every 04:00 UTC without leaving a trail in `HistorialRevisio`,
and the next P2 tick recreated them — invisible to both the rejected-
memory check and the `deezer_id` dedup (the row was physically gone).

Fix: refuse creation at every frontier when the effective
`album.data_llancament` is older than `today - DIES_CADUCITAT`.

Two creation frontiers exist:

  * `obtenir_novetats._create_track` (hourly cron P2/P3) — always
    a strict INSERT, so the guard applies unconditionally.
  * `obtenir_metadata._upsert_track` (on-demand, not cron) — the
    guard only applies to the INSERT branch. If the Canco already
    exists, the upsert proceeds so corrected metadata (ISRC, preview,
    contributors) still lands on staff-curated rows.

NULL `data_llancament` is treated as "unknown → don't caducate" at
both frontiers — same semantics as `netejar_caducades`'s `__lt`
filter. The wider NULL hole is a known follow-up.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from ingesta.caducitat import caducitat_cutoff, is_caducat
from ingesta.management.commands.obtenir_metadata import Command as MetadataCommand
from ingesta.management.commands.obtenir_novetats import Command as NovetatsCommand
from music.constants import DIES_CADUCITAT
from music.models import Album, Artista, ArtistaDeezer, Canco

# ─────────────────────────────────────────────────────────────────────
# helper
# ─────────────────────────────────────────────────────────────────────


def test_is_caducat_pure():
    """`is_caducat` is the single source of truth for the rule.
    NULL → False, equal-to-cutoff → False (strictly older), older →
    True."""
    today = date(2026, 6, 2)
    cutoff = today - timedelta(days=DIES_CADUCITAT)
    assert is_caducat(None, cutoff) is False
    assert is_caducat(cutoff, cutoff) is False  # equal, not strictly older
    assert is_caducat(cutoff - timedelta(days=1), cutoff) is True
    assert is_caducat(today, cutoff) is False


def test_caducitat_cutoff_uses_today():
    """`caducitat_cutoff()` defaults to today; the override is for
    deterministic tests."""
    explicit = caducitat_cutoff(date(2026, 6, 2))
    assert explicit == date(2026, 6, 2) - timedelta(days=DIES_CADUCITAT)


# ─────────────────────────────────────────────────────────────────────
# shared fixtures
# ─────────────────────────────────────────────────────────────────────


def _make_artista() -> Artista:
    a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
    ArtistaDeezer.objects.create(artista=a, deezer_id=1)
    return a


def _track_payload(deezer_id: int = 999, isrc: str = "") -> dict:
    """Minimal Deezer track payload accepted by both creation helpers."""
    return {
        "id": deezer_id,
        "title": "Cançó Test",
        "duration": 180,
        "isrc": isrc,
        "preview": "",
        "contributors": [],
        # No `album_release_date` so the "Fix album date" block is a
        # no-op and the guard reads the album's stored date directly.
        "album_release_date": "",
    }


# ─────────────────────────────────────────────────────────────────────
# obtenir_novetats._create_track — hourly cron frontier
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_novetats_does_not_create_canco_for_ancient_album(db):
    """Track on an album whose `data_llancament` is older than
    DIES_CADUCITAT must NOT be created, even when no rejection trail
    exists for its deezer_id."""
    a = _make_artista()
    ancient = date.today() - timedelta(days=DIES_CADUCITAT + 1)
    album = Album.objects.create(
        artista=a, nom="Vell", deezer_id=10, data_llancament=ancient
    )

    created = NovetatsCommand()._create_track(album, _track_payload(deezer_id=999))

    assert created is False
    assert Canco.objects.filter(deezer_id=999).count() == 0


@pytest.mark.django_db
def test_novetats_creates_canco_for_recent_album(db):
    """Tracks within the DIES_CADUCITAT window are still created."""
    a = _make_artista()
    recent = date.today() - timedelta(days=10)
    album = Album.objects.create(
        artista=a, nom="Recent", deezer_id=11, data_llancament=recent
    )

    created = NovetatsCommand()._create_track(album, _track_payload(deezer_id=1001))

    assert created is True
    canco = Canco.objects.get(deezer_id=1001)
    assert canco.data_llancament == recent
    assert canco.verificada is False


@pytest.mark.django_db
def test_novetats_creates_canco_when_data_llancament_is_null(db):
    """`data_llancament=NULL` is treated as unknown → not caducated.
    Preserves current behaviour at both frontiers."""
    a = _make_artista()
    album = Album.objects.create(
        artista=a, nom="Sense data", deezer_id=12, data_llancament=None
    )

    created = NovetatsCommand()._create_track(album, _track_payload(deezer_id=1002))

    assert created is True
    canco = Canco.objects.get(deezer_id=1002)
    assert canco.data_llancament is None


@pytest.mark.django_db
def test_novetats_ancient_album_rewound_by_track_release_date_also_blocked(db):
    """Reproduces the Tres Fan Ball pattern: Deezer returns the album
    with a recent date at the artist level, but the track payload's
    `album_release_date` is the original (ancient) recording date.
    The "Fix album date" block in `_create_track` rewinds
    `album.data_llancament` to the older value BEFORE the guard runs,
    so the guard must see the rewound (ancient) date and refuse."""
    a = _make_artista()
    recent = date.today() - timedelta(days=30)
    album = Album.objects.create(
        artista=a, nom="Re-issue", deezer_id=13, data_llancament=recent
    )
    ancient_str = (date.today() - timedelta(days=DIES_CADUCITAT + 365 * 11)).isoformat()
    payload = _track_payload(deezer_id=1003)
    payload["album_release_date"] = ancient_str

    created = NovetatsCommand()._create_track(album, payload)

    assert created is False
    assert Canco.objects.filter(deezer_id=1003).count() == 0
    # Side effect of the "Fix album date" block: album date got
    # rewound. That's pre-existing behaviour; we just don't create
    # the Canco for it.
    album.refresh_from_db()
    assert album.data_llancament.isoformat() == ancient_str


# ─────────────────────────────────────────────────────────────────────
# obtenir_metadata._upsert_track — on-demand frontier
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_metadata_upsert_does_not_insert_canco_for_ancient_album(db):
    """No pre-existing Canco for this `deezer_id` + ancient album →
    INSERT branch → must be refused."""
    a = _make_artista()
    ancient = date.today() - timedelta(days=DIES_CADUCITAT + 1)
    album = Album.objects.create(
        artista=a, nom="Vell", deezer_id=20, data_llancament=ancient
    )

    created = MetadataCommand()._upsert_track(
        a, album, _track_payload(deezer_id=2001), force=False
    )

    assert created is False
    assert Canco.objects.filter(deezer_id=2001).count() == 0


@pytest.mark.django_db
def test_metadata_upsert_inserts_canco_for_recent_album(db):
    """Tracks within the DIES_CADUCITAT window are still inserted on
    the on-demand path."""
    a = _make_artista()
    recent = date.today() - timedelta(days=10)
    album = Album.objects.create(
        artista=a, nom="Recent", deezer_id=21, data_llancament=recent
    )

    created = MetadataCommand()._upsert_track(
        a, album, _track_payload(deezer_id=2002), force=False
    )

    assert created is True
    canco = Canco.objects.get(deezer_id=2002)
    assert canco.data_llancament == recent


@pytest.mark.django_db
def test_metadata_upsert_inserts_canco_when_data_llancament_null(db):
    """NULL `data_llancament` does not caducate."""
    a = _make_artista()
    album = Album.objects.create(
        artista=a, nom="Sense data", deezer_id=22, data_llancament=None
    )

    created = MetadataCommand()._upsert_track(
        a, album, _track_payload(deezer_id=2003), force=False
    )

    assert created is True
    canco = Canco.objects.get(deezer_id=2003)
    assert canco.data_llancament is None


@pytest.mark.django_db
def test_metadata_upsert_updates_existing_caducat_canco(db):
    """The UPDATE branch must remain unblocked: a Canco that already
    exists for an ancient album still receives metadata updates
    (corrected ISRC, preview, contributors). Staff may have curated
    the row already; refusing the update would silently break the
    on-demand refresh path."""
    a = _make_artista()
    ancient = date.today() - timedelta(days=DIES_CADUCITAT + 1)
    album = Album.objects.create(
        artista=a, nom="Vell", deezer_id=23, data_llancament=ancient
    )
    # Pre-existing Canco — staff already curated it (verificada=True
    # to make the intent obvious; the guard reads `deezer_id`
    # existence, not the verificada flag).
    Canco.objects.create(
        deezer_id=2004,
        nom="Stale name",
        album=album,
        artista=a,
        isrc="",
        preview_url="",
        data_llancament=ancient,
        verificada=True,
    )

    payload = _track_payload(deezer_id=2004, isrc="ESFRESHISRC001")
    payload["preview"] = "https://cdn.deezer.example/preview.mp3"

    created = MetadataCommand()._upsert_track(a, album, payload, force=True)

    # `force=True` + already-exists → update_or_create returns
    # `created=False`. The metadata must have landed on the row.
    assert created is False
    canco = Canco.objects.get(deezer_id=2004)
    assert canco.isrc == "ESFRESHISRC001"
    assert canco.preview_url == "https://cdn.deezer.example/preview.mp3"
