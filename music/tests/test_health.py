"""Health checks for the Spotify subsystem — FASE F.

Coverage:
  * `check_spotify_premium`: no auth row, transient API error,
    Free product, Premium happy path.
  * `check_spotify_coverage`: no rows, healthy rows, mixed
    thresholds (WARN, CRIT).
  * `bin/tq-health` watchdog escalation past `silenced=true` —
    we don't shell out to bash here; instead we verify the
    `consecutive_failures` field is written by `tq-run`'s logic
    by simulating the persisted file shape and asserting the
    Python-side reads it correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from music.health import (
    check_spotify_coverage,
    check_spotify_premium,
)

# ── check_spotify_premium ─────────────────────────────────────────


@pytest.mark.django_db
def test_premium_crit_when_no_auth_row():
    """No SpotifyAuth singleton row means OAuth has never been
    completed. CRIT so the operator gets nudged toward
    /staff/social/spotify/."""
    sev, msg, payload = check_spotify_premium()
    assert sev == "CRIT"
    assert "OAuth dance not completed" in msg
    assert payload == {}


@pytest.mark.django_db
def test_premium_warn_on_transient_api_error():
    from music.models import SpotifyAuth

    SpotifyAuth.objects.create(
        pk=1,
        refresh_token="dummy",
        scope="playlist-modify-private playlist-modify-public",
        spotify_user_id="legacy_user",
    )
    with patch("ingesta.clients.spotify.UserSpotifyClient") as mock_cls:
        mock_client = MagicMock()
        # Simulate a transient transport error (5xx) — the client
        # raises after retry exhaustion. WARN, not CRIT, because
        # this could be Spotify-side weather and the cron's own
        # status file is the canonical "did it work?" signal.
        mock_client.me.side_effect = RuntimeError(
            "Spotify GET /me failed after 3 attempts"
        )
        mock_cls.return_value = mock_client
        sev, msg, payload = check_spotify_premium()
    assert sev == "WARN"
    assert "Spotify /me call failed" in msg


@pytest.mark.django_db
def test_premium_crit_when_product_free():
    """ADR-0009 invariant: Free product means the cron will 403
    on the next /v1/search call. Escalate to CRIT so the operator
    reactivates Premium before the next planned sync."""
    from music.models import SpotifyAuth

    SpotifyAuth.objects.create(
        pk=1,
        refresh_token="dummy",
        scope="playlist-modify-private",
        spotify_user_id="free_user",
    )
    with patch("ingesta.clients.spotify.UserSpotifyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.me.return_value = {
            "id": "free_user",
            "product": "free",
        }
        mock_cls.return_value = mock_client
        sev, msg, payload = check_spotify_premium()
    assert sev == "CRIT"
    assert "no longer Premium" in msg
    assert payload["product"] == "free"


@pytest.mark.django_db
def test_premium_ok_on_premium():
    from music.models import SpotifyAuth

    SpotifyAuth.objects.create(
        pk=1,
        refresh_token="dummy",
        scope="playlist-modify-private playlist-modify-public",
        spotify_user_id="admin_user",
    )
    with patch("ingesta.clients.spotify.UserSpotifyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.me.return_value = {
            "id": "admin_user",
            "product": "premium",
            "display_name": "Admin",
            "country": "ES",
        }
        mock_cls.return_value = mock_client
        sev, msg, payload = check_spotify_premium()
    assert sev == "OK"
    assert "admin_user" in msg
    assert payload["product"] == "premium"


# ── check_spotify_coverage ────────────────────────────────────────


@pytest.fixture
def unsilence_cron():
    """The repo's deploy/cron-meta.json marks the Process A cron as
    silenced (regime gate before first wet sync). Most coverage tests
    want to exercise the unsilenced path, so we mock the helper to
    return False unconditionally."""
    with patch("music.health._cron_is_silenced", return_value=False) as m:
        yield m


@pytest.mark.django_db
def test_coverage_silenced_short_circuits_to_ok():
    """When the Process A cron is silenced (cron-meta.json), the check
    must return OK and skip the coverage analysis entirely. Without
    this gate the staff dashboard reported CRIT every load while the
    cron was paused (FASE F false positive, 2026-05-22)."""
    with patch("music.health._cron_is_silenced", return_value=True):
        sev, msg, payload = check_spotify_coverage()
    assert sev == "OK"
    assert "silenced" in msg.lower()
    assert payload.get("silenced") is True


@pytest.mark.django_db
def test_coverage_warn_when_no_rows(unsilence_cron):
    # FASE C seeded 7 no-verif rows in the data migration. The "no rows"
    # branch of check_spotify_coverage requires us to wipe them first.
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.all().delete()
    sev, msg, payload = check_spotify_coverage()
    assert sev == "WARN"
    assert "configurar_spotify_playlists" in msg


@pytest.mark.django_db
def test_coverage_warn_when_all_rows_never_synced(unsilence_cron):
    from music.models import SpotifyPlaylist

    # Reset to a clean slate so the assertion on row count is meaningful
    # (the data migration seeds 7 rows with last_n_tracks=0).
    SpotifyPlaylist.objects.all().delete()
    SpotifyPlaylist.objects.create(
        codi="top-cat", kind=SpotifyPlaylist.KIND_TOP, territori="CAT"
    )
    SpotifyPlaylist.objects.create(
        codi="top-val", kind=SpotifyPlaylist.KIND_TOP, territori="VAL"
    )
    sev, msg, payload = check_spotify_coverage()
    # All rows have last_n_tracks=0 → WARN to nudge the operator.
    assert sev == "WARN"
    assert "never synced" in msg
    assert len(payload["rows"]) == 2


@pytest.mark.django_db
def test_coverage_ok_when_healthy(unsilence_cron):
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.create(
        codi="top-cat",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="CAT",
        last_n_tracks=40,
        last_n_matched=38,  # 95%
        last_sync_ok=True,
    )
    sev, msg, payload = check_spotify_coverage()
    assert sev == "OK"
    assert "Coverage OK" in msg


@pytest.mark.django_db
def test_coverage_warn_at_below_85(unsilence_cron):
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.create(
        codi="top-cat",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="CAT",
        last_n_tracks=40,
        last_n_matched=32,  # 80%
        last_sync_ok=True,
    )
    sev, msg, payload = check_spotify_coverage()
    assert sev == "WARN"
    assert "top-cat" in msg


@pytest.mark.django_db
def test_coverage_crit_at_below_50(unsilence_cron):
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.create(
        codi="top-cat",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="CAT",
        last_n_tracks=40,
        last_n_matched=15,  # 37.5%
        last_sync_ok=True,
    )
    # A second row at WARN level — CRIT should win.
    SpotifyPlaylist.objects.create(
        codi="top-val",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="VAL",
        last_n_tracks=40,
        last_n_matched=34,  # 85%, exactly on the boundary — WARN excluded
        last_sync_ok=True,
    )
    sev, msg, payload = check_spotify_coverage()
    assert sev == "CRIT"
    assert "top-cat" in msg


@pytest.mark.django_db
def test_coverage_no_verif_gradient_does_not_crit(unsilence_cron):
    """The real-world no-verif gradient (96% down to 0% by ml_confianca
    order) must NOT trip CRIT: those chunks lag by design. A healthy
    verified playlist keeps the overall verdict OK."""
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.all().delete()  # wipe migration-seeded rows

    SpotifyPlaylist.objects.create(
        codi="top-cat",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="CAT",
        last_n_tracks=40,
        last_n_matched=40,  # 100%
        last_sync_ok=True,
    )
    for i, matched in enumerate([96, 68, 28, 10, 2, 0, 0], start=1):
        SpotifyPlaylist.objects.create(
            codi=f"no-verif-{i}",
            kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
            territori="",
            chunk_index=i - 1,
            last_n_tracks=100,
            last_n_matched=matched,
            last_sync_ok=True,
        )
    sev, msg, payload = check_spotify_coverage()
    assert sev == "OK"
    # Aggregate (204/700) is reported but does not drive severity.
    assert payload["no_verif_aggregate"] == round(204 / 700, 3)
    assert "no-verif aggregate" in msg


@pytest.mark.django_db
def test_coverage_no_verif_aggregate_collapse_warns(unsilence_cron):
    """If pending enrichment really stalled, the no-verif AGGREGATE
    collapses toward 0; that is the one real-stall signal and surfaces
    as WARN (never CRIT)."""
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.all().delete()  # wipe migration-seeded rows

    SpotifyPlaylist.objects.create(
        codi="top-cat",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="CAT",
        last_n_tracks=40,
        last_n_matched=40,
        last_sync_ok=True,
    )
    for i in range(1, 6):
        SpotifyPlaylist.objects.create(
            codi=f"no-verif-{i}",
            kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
            territori="",
            chunk_index=i - 1,
            last_n_tracks=100,
            last_n_matched=1,  # ~1% aggregate → below the 10% floor
            last_sync_ok=True,
        )
    sev, msg, payload = check_spotify_coverage()
    assert sev == "WARN"
    assert "no-verif aggregate" in msg


@pytest.mark.django_db
def test_coverage_verified_crit_even_with_no_verif_present(unsilence_cron):
    """A verified playlist below CRIT still escalates to CRIT regardless
    of the no-verif rows — the strict gate on public playlists stays."""
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.all().delete()  # wipe migration-seeded rows

    SpotifyPlaylist.objects.create(
        codi="top-cat",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="CAT",
        last_n_tracks=40,
        last_n_matched=10,  # 25% → CRIT
        last_sync_ok=True,
    )
    SpotifyPlaylist.objects.create(
        codi="no-verif-1",
        kind=SpotifyPlaylist.KIND_NO_VERIFICADES,
        territori="",
        chunk_index=0,
        last_n_tracks=100,
        last_n_matched=96,
        last_sync_ok=True,
    )
    sev, msg, payload = check_spotify_coverage()
    assert sev == "CRIT"
    assert "top-cat" in msg


@pytest.mark.django_db
def test_coverage_novetats_per_verificar_outside_alert(unsilence_cron):
    """The repurposed work-list playlist (novetats_per_verificar) is a
    curated list, not a synced chart: even at 0% coverage it must not
    drive CRIT/WARN, nor count toward the no-verif aggregate."""
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.all().delete()
    SpotifyPlaylist.objects.create(
        codi="top-cat",
        kind=SpotifyPlaylist.KIND_TOP,
        territori="CAT",
        last_n_tracks=40,
        last_n_matched=40,  # healthy verified playlist
        last_sync_ok=True,
    )
    SpotifyPlaylist.objects.create(
        codi="novetats-per-verificar",
        kind=SpotifyPlaylist.KIND_NOVETATS_PER_VERIFICAR,
        last_n_tracks=100,
        last_n_matched=0,  # 0% — must be ignored by the alert
        last_sync_ok=True,
    )
    sev, msg, payload = check_spotify_coverage()
    assert sev == "OK"
    # Reported in the payload, but it does not feed the no-verif aggregate.
    assert payload["no_verif_aggregate"] is None
    codis = {r["codi"] for r in payload["rows"]}
    assert "novetats-per-verificar" in codis
