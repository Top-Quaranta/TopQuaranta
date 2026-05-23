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
    """Five SpotifyPlaylist rows mimicking the production seed.

    Wipes any pre-existing rows first because FASE C's data migration
    seeds 7 no-verif-N rows that would otherwise inflate the count
    assertions further down."""
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.all().delete()
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
    # The scope must include `user-read-private`, otherwise Spotify
    # returns an empty `product` field on /me even for Premium accounts
    # and the callback rejects the valid auth as "no longer Premium".
    # (Regression guard for the 2026-05-22 first-OAuth incident.)
    assert "user-read-private" in url
    assert "playlist-modify-private" in url
    assert "playlist-modify-public" in url


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


# ── FASE D UI: weekly + target_coverage ───────────────────────────


@pytest.fixture
def fase_d_playlists(db):
    """SpotifyPlaylist set matching FASE D shape: daily-tops +
    weekly mirrors + a no_verificades chunk. Wipes existing rows so
    the test owns the universe."""
    from music.models import SpotifyPlaylist

    SpotifyPlaylist.objects.all().delete()
    daily = [
        ("top-cat", "CAT", "DAILYCAT"),
        ("top-val", "VAL", "DAILYVAL"),
    ]
    weekly = [
        ("top-cat-weekly", "CAT", "WEEKLYCAT"),
        ("top-val-weekly", "VAL", "WEEKLYVAL"),
        ("top-alt-weekly", "ALT", "WEEKLYALT"),
    ]
    for codi, terr, pid in daily:
        SpotifyPlaylist.objects.create(
            codi=codi,
            kind=SpotifyPlaylist.KIND_TOP,
            freq=SpotifyPlaylist.FREQ_DAILY,
            territori=terr,
            spotify_playlist_id=pid,
        )
    for codi, terr, pid in weekly:
        SpotifyPlaylist.objects.create(
            codi=codi,
            kind=SpotifyPlaylist.KIND_TOP,
            freq=SpotifyPlaylist.FREQ_WEEKLY,
            territori=terr,
            spotify_playlist_id=pid,
        )
    return None


@pytest.mark.django_db
def test_estat_payload_includes_freq_and_target_coverage(
    staff_client, fase_d_playlists
):
    """Every playlist row in /estat/ carries `freq` and a
    `target_coverage` dict. Target_coverage shows None when there is
    no source data yet (no TopProvisional / TopSetmanal rows)."""
    r = staff_client.get("/api/v1/staff/social/spotify/estat/")
    assert r.status_code == 200, r.content
    data = r.json()

    by_codi = {pl["codi"]: pl for pl in data["playlists"]}
    assert "top-cat" in by_codi and "top-cat-weekly" in by_codi
    assert by_codi["top-cat"]["freq"] == "daily"
    assert by_codi["top-cat-weekly"]["freq"] == "weekly"

    # No ranking source rows -> total=0, ratio=None for each.
    for codi in ("top-cat", "top-cat-weekly", "top-val-weekly"):
        tc = by_codi[codi]["target_coverage"]
        assert tc["total"] == 0
        assert tc["found"] == 0
        assert tc["ratio"] is None


@pytest.mark.django_db
def test_estat_target_coverage_for_weekly_reads_topsetmanal(
    staff_client, fase_d_playlists
):
    """target_coverage for a freq=weekly playlist counts how many of
    the latest TopSetmanal cançons (per territori) have a
    SpotifyMetadata row in status=found."""
    from datetime import date

    from music.models import Album, Artista, Canco, SpotifyMetadata
    from ranking.models import TopSetmanal

    a = Artista.objects.create(nom="EXEMPLE TC", lastfm_nom="EXEMPLE TC")
    al = Album.objects.create(artista=a, nom="EXEMPLE TC Al")
    # 3 cançons on the latest weekly chart for CAT.
    cancons = []
    for i in range(3):
        c = Canco.objects.create(
            artista=a,
            album=al,
            nom=f"EXEMPLE-tc-{i}",
            isrc=f"ZZ00TC0000{i:03d}",
        )
        TopSetmanal.objects.create(
            canco=c,
            territori="CAT",
            setmana=date(2026, 5, 19),
            posicio=i + 1,
            score_setmanal=1.0,
        )
        cancons.append(c)
    # 2 of the 3 already enriched; 1 still not_attempted.
    SpotifyMetadata.objects.create(
        canco=cancons[0],
        spotify_id="A",
        enrichment_status=SpotifyMetadata.STATUS_FOUND,
    )
    SpotifyMetadata.objects.create(
        canco=cancons[1],
        spotify_id="B",
        enrichment_status=SpotifyMetadata.STATUS_FOUND,
    )
    SpotifyMetadata.objects.create(canco=cancons[2])  # not_attempted

    r = staff_client.get("/api/v1/staff/social/spotify/estat/")
    by_codi = {pl["codi"]: pl for pl in r.json()["playlists"]}
    tc = by_codi["top-cat-weekly"]["target_coverage"]
    assert tc["total"] == 3
    assert tc["found"] == 2
    assert tc["ratio"] == round(2 / 3, 3)


@pytest.mark.django_db
def test_estat_target_coverage_picks_latest_setmana(staff_client, fase_d_playlists):
    """When TopSetmanal has multiple setmanas for a territori, the
    target_coverage payload reflects only the most recent one (the
    same setmana the sync command would push)."""
    from datetime import date

    from music.models import Album, Artista, Canco, SpotifyMetadata
    from ranking.models import TopSetmanal

    a = Artista.objects.create(nom="EXEMPLE TC2", lastfm_nom="EXEMPLE TC2")
    al = Album.objects.create(artista=a, nom="EXEMPLE TC2 Al")
    old = Canco.objects.create(
        artista=a,
        album=al,
        nom="EXEMPLE-old",
        isrc="ZZOLD0000001",
    )
    new = Canco.objects.create(
        artista=a,
        album=al,
        nom="EXEMPLE-new",
        isrc="ZZNEW0000001",
    )
    # Old setmana with no enrichment.
    TopSetmanal.objects.create(
        canco=old,
        territori="VAL",
        setmana=date(2026, 4, 21),
        posicio=1,
        score_setmanal=1.0,
    )
    # New setmana with enrichment.
    TopSetmanal.objects.create(
        canco=new,
        territori="VAL",
        setmana=date(2026, 5, 19),
        posicio=1,
        score_setmanal=1.0,
    )
    SpotifyMetadata.objects.create(
        canco=new,
        spotify_id="N",
        enrichment_status=SpotifyMetadata.STATUS_FOUND,
    )

    r = staff_client.get("/api/v1/staff/social/spotify/estat/")
    by_codi = {pl["codi"]: pl for pl in r.json()["playlists"]}
    tc = by_codi["top-val-weekly"]["target_coverage"]
    # Only the new setmana row counted -> 1/1, not 1/2.
    assert tc["total"] == 1
    assert tc["found"] == 1
    assert tc["ratio"] == 1.0


@pytest.mark.django_db
def test_sync_endpoint_forwards_freq_weekly(staff_client, fase_d_playlists):
    """The sync endpoint passes `freq=weekly` to the underlying
    management command. Cache-only contract (no /search) is enforced
    by Process A's own test fixture; here we only assert the kwarg
    plumbing."""
    with patch("web.api.staff.social.spotify.call_command") as mock_cmd:

        def fake_call(name, **kwargs):
            import sys

            print(f"called {name} freq={kwargs.get('freq')}", file=sys.stdout)

        mock_cmd.side_effect = fake_call

        r = staff_client.post(
            "/api/v1/staff/social/spotify/sync/",
            {"freq": "weekly", "dry_run": False},
            format="json",
        )

    assert r.status_code == 200, r.content
    data = r.json()
    assert data["ok"] is True
    assert data["freq"] == "weekly"
    # The command got the freq kwarg.
    args, kwargs = mock_cmd.call_args
    assert args == ("actualitzar_playlists_spotify",)
    assert kwargs.get("freq") == "weekly"
