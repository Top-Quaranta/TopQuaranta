"""Staff Spotify endpoints — FASE B of the playlists revival.

Coverage:
  * Auth: anon hits return 401/403.
  * /estat/: happy paths for "no auth row" and "auth row with mocked /me".
  * /oauth-start/: returns the Authorise URL and stashes state on session.
  * /oauth-callback/: refuses on bad state, refuses on Free product,
    persists on Premium.
  * /sync/: forwards to `call_command` and surfaces stdout.

External HTTP is mocked. No real Spotify calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="spotify_tester",
        email="sp@example.com",
        password="x",
        is_staff=True,
    )
    # Same OTP defeat as test_staff_endpoints.
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def spotify_playlists(db):
    """Five SpotifyPlaylist rows mimicking the production seed."""
    from music.models import SpotifyPlaylist

    rows = [
        ("top-cat", SpotifyPlaylist.KIND_TOP, "CAT", "0Vzdo5gpRPeSBpWVFUKE1G"),
        ("top-val", SpotifyPlaylist.KIND_TOP, "VAL", "0zt9V8u8lRsgdPPRVIc9kC"),
        ("top-bal", SpotifyPlaylist.KIND_TOP, "BAL", "2MMTTGmQkpte20Ripx3hxa"),
        ("top-alt", SpotifyPlaylist.KIND_TOP, "ALT", "3qvaDqSrhbvrR5TOvANEvp"),
        ("novetats", SpotifyPlaylist.KIND_NOVETATS, "", "4nBIangCLrNMFj0L1Uj2jb"),
    ]
    objs = []
    for codi, kind, terr, pid in rows:
        obj = SpotifyPlaylist.objects.create(
            codi=codi, kind=kind, territori=terr, spotify_playlist_id=pid
        )
        objs.append(obj)
    return objs


# ── Auth ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_spotify_endpoints_require_staff(anon_client):
    for path in ("/api/v1/staff/social/spotify/estat/",):
        r = anon_client.get(path)
        assert r.status_code in (401, 403)
    for path in (
        "/api/v1/staff/social/spotify/oauth-start/",
        "/api/v1/staff/social/spotify/oauth-callback/",
        "/api/v1/staff/social/spotify/sync/",
    ):
        r = anon_client.post(path, {}, format="json")
        assert r.status_code in (401, 403)


# ── /estat/ ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_estat_no_auth_row_returns_oauth_present_false(staff_client, spotify_playlists):
    r = staff_client.get("/api/v1/staff/social/spotify/estat/")
    assert r.status_code == 200, r.content
    data = r.json()
    assert data["oauth_present"] is False
    assert data["spotify_user_id"] is None
    assert data["product"] is None
    # Playlists row count survives even without OAuth.
    assert len(data["playlists"]) == 5
    # Cron silenced flag comes from deploy/cron-meta.json on disk;
    # value depends on the repo state. Just assert it's a bool.
    assert isinstance(data["cron_silenced"], bool)


@pytest.mark.django_db
def test_estat_with_auth_row_calls_live_me(staff_client, spotify_playlists):
    from music.models import SpotifyAuth

    SpotifyAuth.objects.create(
        pk=1,
        refresh_token="dummy-rt",
        scope="playlist-modify-private playlist-modify-public",
        spotify_user_id="legacy_user",
    )
    # Mock the UserSpotifyClient.me() call so we don't hit Spotify.
    with patch("web.api.staff.social.spotify.UserSpotifyClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.me.return_value = {
            "id": "admin_user_id",
            "product": "premium",
            "display_name": "Admin TopQuaranta",
            "country": "ES",
        }
        mock_client_cls.return_value = mock_client
        r = staff_client.get("/api/v1/staff/social/spotify/estat/")

    assert r.status_code == 200
    data = r.json()
    assert data["oauth_present"] is True
    # The live /me id overrides the stale row id.
    assert data["spotify_user_id"] == "admin_user_id"
    assert data["product"] == "premium"
    assert data["display_name"] == "Admin TopQuaranta"
    assert data["country"] == "ES"


# ── /oauth-start/ ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_oauth_start_returns_url_with_state(staff_client, settings):
    settings.SPOTIFY_CLIENT_ID = "fake_id"
    settings.SPOTIFY_CLIENT_SECRET = "fake_secret"
    r = staff_client.post(
        "/api/v1/staff/social/spotify/oauth-start/", {}, format="json"
    )
    assert r.status_code == 200, r.content
    url = r.json()["url"]
    assert url.startswith("https://accounts.spotify.com/authorize?")
    assert "client_id=fake_id" in url
    assert "show_dialog=true" in url
    assert "state=" in url


@pytest.mark.django_db
def test_oauth_start_500_when_creds_missing(staff_client, settings):
    settings.SPOTIFY_CLIENT_ID = ""
    settings.SPOTIFY_CLIENT_SECRET = ""
    r = staff_client.post(
        "/api/v1/staff/social/spotify/oauth-start/", {}, format="json"
    )
    assert r.status_code == 500


# ── /oauth-callback/ ──────────────────────────────────────────────


@pytest.mark.django_db
def test_oauth_callback_rejects_bad_state(staff_client):
    # No /oauth-start/ called → no state in session → reject.
    r = staff_client.post(
        "/api/v1/staff/social/spotify/oauth-callback/",
        {"code": "abc", "state": "nope"},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_oauth_callback_rejects_free_product(staff_client, settings):
    """ADR-0009 invariant: refuse to persist a refresh_token from a
    non-Premium account. The cron would 403 on every subsequent call."""
    settings.SPOTIFY_CLIENT_ID = "fake_id"
    settings.SPOTIFY_CLIENT_SECRET = "fake_secret"
    # Bootstrap a state token via /oauth-start/ first so the callback
    # has something to validate against.
    r = staff_client.post(
        "/api/v1/staff/social/spotify/oauth-start/", {}, format="json"
    )
    url = r.json()["url"]
    state = url.split("state=")[1].split("&")[0]

    # Mock the Spotify exchange + /me responses.
    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {
        "access_token": "fake_access",
        "refresh_token": "fake_refresh",
        "scope": "playlist-modify-private",
    }
    me_response = MagicMock()
    me_response.status_code = 200
    me_response.json.return_value = {
        "id": "free_user",
        "product": "free",  # ← the rejection trigger
    }

    with patch("web.api.staff.social.spotify.requests") as mock_req:
        mock_req.post.return_value = token_response
        mock_req.get.return_value = me_response
        r = staff_client.post(
            "/api/v1/staff/social/spotify/oauth-callback/",
            {"code": "fake_code", "state": state},
            format="json",
        )

    assert r.status_code == 400
    assert "Premium" in r.json()["error"]
    # And the row was NOT created.
    from music.models import SpotifyAuth

    assert SpotifyAuth.objects.count() == 0


@pytest.mark.django_db
def test_oauth_callback_persists_on_premium(staff_client, settings):
    settings.SPOTIFY_CLIENT_ID = "fake_id"
    settings.SPOTIFY_CLIENT_SECRET = "fake_secret"
    r = staff_client.post(
        "/api/v1/staff/social/spotify/oauth-start/", {}, format="json"
    )
    state = r.json()["url"].split("state=")[1].split("&")[0]

    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {
        "access_token": "fake_access",
        "refresh_token": "fake_refresh",
        "scope": "playlist-modify-private playlist-modify-public",
    }
    me_response = MagicMock()
    me_response.status_code = 200
    me_response.json.return_value = {
        "id": "admin_user",
        "product": "premium",
    }

    with patch("web.api.staff.social.spotify.requests") as mock_req:
        mock_req.post.return_value = token_response
        mock_req.get.return_value = me_response
        r = staff_client.post(
            "/api/v1/staff/social/spotify/oauth-callback/",
            {"code": "fake_code", "state": state},
            format="json",
        )

    assert r.status_code == 200, r.content
    assert r.json()["ok"] is True
    assert r.json()["product"] == "premium"

    from music.models import SpotifyAuth

    row = SpotifyAuth.objects.get(pk=1)
    assert row.refresh_token == "fake_refresh"
    assert row.spotify_user_id == "admin_user"


# ── /sync/ ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sync_forwards_to_management_command(staff_client, spotify_playlists):
    """The endpoint shells out to `call_command`; we mock it so the
    test doesn't try to talk to Spotify. We assert the kwargs make
    it through."""
    with patch("web.api.staff.social.spotify.call_command") as mock_cmd:
        # Make stdout/stderr appear in the buffer; the endpoint reads
        # them after the call returns.
        def fake_call(name, **kwargs):
            import sys

            print(f"calling {name} with {kwargs}", file=sys.stdout)

        mock_cmd.side_effect = fake_call

        r = staff_client.post(
            "/api/v1/staff/social/spotify/sync/",
            {"dry_run": True, "only": "top-cat"},
            format="json",
        )

    assert r.status_code == 200, r.content
    data = r.json()
    assert data["ok"] is True
    assert data["dry_run"] is True
    assert data["only"] == "top-cat"
    assert "calling actualitzar_playlists_spotify" in data["stdout"]
    # The endpoint always returns the current playlist payload.
    assert len(data["playlists"]) == 5
