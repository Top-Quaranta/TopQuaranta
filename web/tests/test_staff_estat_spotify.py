"""Tests for the Spotify enrichment block of the staff /estat endpoint.

Covers:
  * `_spotify_enrichment_stats` returns the expected dict shape.
  * Counts split correctly across found / not_found / not_attempted.
  * The verificada axis (public vs pending) tallies independently.
  * Cançons without a SpotifyMetadata row count as not_attempted.
  * Coverage ratios computed correctly and are None when denominator
    is zero.

All counts come from the ORM; no Spotify HTTP at all.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from music.models import Album, Artista, Canco, SpotifyMetadata
from web.api.staff.estat import _spotify_enrichment_stats


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="estat_spotify_tester",
        email="es@example.com",
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


def _fixture_catalog(db):
    """Build a small but representative catalogue:
      * 2 public cançons (verificada=True, activa=True), 1 enriched, 1 not.
      * 3 pending cançons (verificada=False, activa=True), 1 enriched,
        1 not_found, 1 not_attempted (has SM row).
      * 1 pending without any SpotifyMetadata row.
    Total Cançons = 6; expected found=2, not_found=1, not_attempted=3."""
    # Wipe pre-existing rows so the assertions are deterministic
    # regardless of fixtures the test session has accumulated.
    Canco.objects.all().delete()
    SpotifyMetadata.objects.all().delete()
    a = Artista.objects.create(nom="EXEMPLE A", lastfm_nom="EXEMPLE A")
    al = Album.objects.create(artista=a, nom="EXEMPLE Al")

    def mk(idx, *, verificada, sm_status=None, with_row=True):
        c = Canco.objects.create(
            artista=a,
            album=al,
            nom=f"EXEMPLE-{idx}",
            isrc=f"ZZ00ES{idx:07d}",
            verificada=verificada,
            activa=True,
        )
        if with_row:
            SpotifyMetadata.objects.create(
                canco=c,
                enrichment_status=sm_status or SpotifyMetadata.STATUS_NOT_ATTEMPTED,
            )
        return c

    mk(1, verificada=True, sm_status=SpotifyMetadata.STATUS_FOUND)
    mk(2, verificada=True, sm_status=SpotifyMetadata.STATUS_NOT_ATTEMPTED)
    mk(3, verificada=False, sm_status=SpotifyMetadata.STATUS_FOUND)
    mk(4, verificada=False, sm_status=SpotifyMetadata.STATUS_NOT_FOUND)
    mk(5, verificada=False, sm_status=SpotifyMetadata.STATUS_NOT_ATTEMPTED)
    mk(6, verificada=False, with_row=False)  # no SM row


@pytest.mark.django_db
def test_spotify_enrichment_stats_shape_and_counts():
    _fixture_catalog(None)
    stats = _spotify_enrichment_stats()
    assert stats["canco_total"] == 6
    assert stats["found"] == 2
    assert stats["not_found"] == 1
    # 1 with row in not_attempted + 1 without any row = 2.
    assert stats["not_attempted"] == 3
    # Public axis: 2 total (verificada=True), 1 found.
    assert stats["public_total"] == 2
    assert stats["found_public"] == 1
    # Pending axis: 4 total (verificada=False, activa=True), 1 found.
    assert stats["pending_total"] == 4
    assert stats["found_pending"] == 1
    assert stats["coverage_total"] == round(2 / 6, 3)
    assert stats["coverage_public"] == round(1 / 2, 3)
    assert stats["coverage_pending"] == round(1 / 4, 3)
    # ETA on the unattempted backlog at the current cron rate.
    assert stats["enrich_per_hour"] == 50
    assert stats["eta_hours_to_clear_backlog"] == round(3 / 50, 1)


@pytest.mark.django_db
def test_spotify_enrichment_stats_empty_catalog():
    """Empty catalogue -> every coverage ratio is None instead of div-by-0."""
    Canco.objects.all().delete()
    SpotifyMetadata.objects.all().delete()
    stats = _spotify_enrichment_stats()
    assert stats["canco_total"] == 0
    assert stats["found"] == 0
    assert stats["coverage_total"] is None
    assert stats["coverage_public"] is None
    assert stats["coverage_pending"] is None
    assert stats["eta_hours_to_clear_backlog"] is None


@pytest.mark.django_db
def test_estat_endpoint_exposes_spotify_enrichment(staff_client):
    """The dashboard endpoint surfaces the new block under
    `pipeline.spotify_enrichment`, side-by-side with whisper and
    musicbrainz."""
    _fixture_catalog(None)
    r = staff_client.get("/api/v1/staff/estat/")
    assert r.status_code == 200, r.content
    data = r.json()
    block = data["spotify_enrichment"]
    # Smoke: same keys we test in _spotify_enrichment_stats above.
    assert block["found"] == 2
    assert block["pending_total"] == 4
    assert block["coverage_total"] == round(2 / 6, 3)
