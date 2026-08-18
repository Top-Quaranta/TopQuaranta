import logging
import time
from datetime import date

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
RATE_LIMIT_SLEEP = 0.1
MAX_RETRIES = 3


class RateLimitedError(RuntimeError):
    """Raised by UserSpotifyClient when Spotify returns 429 with a
    Retry-After larger than the configured tolerance (60s by default).

    A 24h `Retry-After: 86076` was hit on the first FASE C dry-run
    (2026-05-22), and the previous code just `time.sleep`d it, hanging
    the cron for a full day. We now raise instead so the caller can
    surface the failure cleanly and the watchdog flips status=FAIL.
    """

    def __init__(self, retry_after_s: int, path: str) -> None:
        super().__init__(
            f"Spotify rate limited on {path}; Retry-After={retry_after_s}s "
            f"(> client tolerance). Aborting instead of sleeping."
        )
        self.retry_after_s = retry_after_s
        self.path = path


class UserSpotifyClient:
    """OAuth refresh-token-backed client for playlist management.

    `SpotifyAuth` is populated once by the `autoritzar_spotify` mgmt
    command. On every call we lazily refresh the access token; on 401
    mid-flight we refresh once and retry.

    Rate limiting (2026-05-22, adaptive 2026-05-23):
      * Every request waits `throttle` seconds before firing (default
        0.2s = 5 req/s, well under Spotify's typical /search limit).
        Caller can pass a more conservative value via the command's
        `--throttle` flag.
      * **Adaptive throttle (2026-05-23)**: on a short 429 (Retry-After
        <= tolerance) the per-request sleep doubles after each hit,
        capped at ``MAX_ADAPTIVE_THROTTLE_S`` (30s). This spreads the
        remaining calls over a longer window and avoids exhausting
        Spotify's per-hour quota. The adaptive value resets on each
        new client instantiation (i.e. each cron run).
      * On 429 we honour `Retry-After` only when it is <=
        `max_retry_after_s` (default 60s). Larger values raise
        `RateLimitedError` so the cron fails fast instead of sleeping
        for hours.
    """

    # NOTE: `user-read-private` is required to receive a populated
    # `product` field on /v1/me. Without it Spotify returns
    # `product=""` even for Premium accounts, which made the staff
    # callback reject a valid Premium token as "no longer Premium"
    # (caught on the first wet OAuth on 2026-05-22). Keep all three
    # together; the staff oauth-start endpoint and `check_spotify_premium`
    # both rely on this constant.
    OAUTH_SCOPES = "playlist-modify-private playlist-modify-public user-read-private"
    # Spotify allows up to 100 URIs per add/replace call.
    PLAYLIST_TRACK_BATCH = 100
    # Default throttle (seconds) between API calls. Empirically the cron
    # in regime hits 200-300 /search calls per run; 0.2s spreads them
    # over ~1 minute and stays clear of Spotify's per-minute window.
    DEFAULT_THROTTLE_S = 0.2
    # Anything past this is "Spotify is asking us to back off for hours" —
    # we refuse to sleep that long and bubble up the failure instead.
    DEFAULT_MAX_RETRY_AFTER_S = 60
    # Adaptive throttle ceiling. After repeated short 429s the per-call
    # sleep doubles each time, but never past this cap.
    MAX_ADAPTIVE_THROTTLE_S = 30.0

    def __init__(
        self,
        auth,
        throttle_s: float | None = None,
        max_retry_after_s: int | None = None,
    ) -> None:
        # Imported lazily to avoid a models-not-ready issue at module load.
        self._auth = auth
        self._access_token: str | None = None
        self._throttle_s = (
            throttle_s if throttle_s is not None else self.DEFAULT_THROTTLE_S
        )
        self._max_retry_after_s = (
            max_retry_after_s
            if max_retry_after_s is not None
            else self.DEFAULT_MAX_RETRY_AFTER_S
        )
        # Adaptive throttle: starts at the configured value and doubles
        # on each short 429, capped at MAX_ADAPTIVE_THROTTLE_S.
        self._current_throttle_s = self._throttle_s

    # ── Auth ────────────────────────────────────────────────────────────
    def _refresh_access_token(self) -> None:
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._auth.refresh_token,
            },
            auth=(settings.SPOTIFY_CLIENT_ID, settings.SPOTIFY_CLIENT_SECRET),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        # Spotify sometimes rotates the refresh_token. Persist the new
        # one when it arrives so we don't drift out of sync.
        new_refresh = payload.get("refresh_token")
        if new_refresh and new_refresh != self._auth.refresh_token:
            self._auth.refresh_token = new_refresh
            self._auth.save(update_fields=["refresh_token"])

    def _headers(self) -> dict:
        if not self._access_token:
            self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{API_BASE}{path}"
        for attempt in range(MAX_RETRIES):
            # Proactive adaptive throttle: starts at the configured value
            # and doubles after each short 429 to avoid exhausting the
            # per-hour quota.
            time.sleep(self._current_throttle_s)
            resp = requests.request(
                method, url, headers=self._headers(), timeout=20, **kwargs
            )
            if resp.status_code == 401:
                logger.info("Spotify token expired mid-flight; refreshing")
                self._refresh_access_token()
                continue
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2))
                if wait > self._max_retry_after_s:
                    # Refuse to hang the cron for hours: surface to caller.
                    logger.error(
                        "Spotify rate limited on %s with Retry-After=%ds "
                        "(> %ds tolerance); aborting",
                        path,
                        wait,
                        self._max_retry_after_s,
                    )
                    raise RateLimitedError(wait, path)
                logger.warning("Spotify rate limited; sleeping %ds", wait)
                time.sleep(wait)
                # Adaptive back-off: double the proactive throttle so
                # subsequent calls spread further apart.
                new_throttle = min(
                    self._current_throttle_s * 2 or self._throttle_s,
                    self.MAX_ADAPTIVE_THROTTLE_S,
                )
                if new_throttle != self._current_throttle_s:
                    self._current_throttle_s = new_throttle
                    logger.info(
                        "Spotify throttle increased to %.1fs after rate limit",
                        self._current_throttle_s,
                    )
                continue
            resp.raise_for_status()
            return resp
        # Attempts exhausted.
        raise RuntimeError(
            f"Spotify {method} {path} failed after {MAX_RETRIES} attempts"
        )

    # ── Operations we use ──────────────────────────────────────────────
    def me(self) -> dict:
        return self._request("GET", "/me").json()

    def search_isrc(self, isrc: str) -> str | None:
        """Return a Spotify track URI matching the ISRC, or None."""
        if not isrc:
            return None
        resp = self._request(
            "GET",
            "/search",
            params={"q": f"isrc:{isrc}", "type": "track", "limit": 1},
        )
        items = resp.json().get("tracks", {}).get("items", [])
        return items[0]["uri"] if items else None

    def search_isrc_principal_artist(self, isrc: str) -> str | None:
        """Return the principal Spotify artist id for an ISRC in
        ONE API call.

        Used by the rebuig backfill's orphan flow
        (`enriquir_spotify_rebuigs.py`) which only needs
        `artista_spotify_id` for HR rows whose Canco was deleted.
        Skips the `get_track` + `get_artist` round-trips because
        the principal artist id is already in the `/search`
        response. Returns None if no track matches or the result
        carries no artist payload.
        """
        if not isrc:
            return None
        resp = self._request(
            "GET",
            "/search",
            params={"q": f"isrc:{isrc}", "type": "track", "limit": 1},
        )
        items = resp.json().get("tracks", {}).get("items", [])
        if not items:
            return None
        artists = items[0].get("artists") or []
        for a in artists:
            aid = (a or {}).get("id") or ""
            if aid:
                return aid
        return None

    def get_track(self, spotify_id: str) -> dict | None:
        """Fetch the full Spotify track JSON for a known spotify_id.

        Returns a dict with the fields ADR-0012 confirms are populated
        for our prod app (id, name, duration_ms, explicit, is_playable,
        track_number, disc_number, external_ids.isrc, album.*,
        artists[]). Fields like popularity / preview_url /
        available_markets come back NULL on Wave-One-restricted apps;
        callers must not rely on them.

        Returns None on 404 (the spotify_id is no longer valid in the
        Spotify catalogue — happens with takedowns, re-uploads). Other
        non-200 statuses raise via `_request.raise_for_status`.

        Batch endpoint `/v1/tracks?ids=` is 403 for our app, so we
        always go one-at-a-time. The throttle in `_request` keeps the
        bulk-loop budget under Spotify's per-minute window.
        """
        if not spotify_id:
            return None
        try:
            resp = self._request("GET", f"/tracks/{spotify_id}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
        return resp.json()

    def get_artist(self, spotify_id: str) -> dict | None:
        """Fetch the full Spotify artist JSON for a known artist ID.

        Returns id, uri, name, images (3 sizes), external_urls. The
        genres list usually comes back empty on Wave-One-restricted
        apps (kept in the response for forward compatibility);
        followers / popularity come back NULL.

        Returns None on 404 (artist was removed from the catalogue).
        Other non-200 statuses raise.
        """
        if not spotify_id:
            return None
        try:
            resp = self._request("GET", f"/artists/{spotify_id}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise
        return resp.json()

    def replace_playlist_tracks(self, playlist_id: str, uris: list[str]) -> None:
        """Replace the whole playlist in place.

        Spotify's PUT /playlists/<id>/items caps at 100 URIs per call.
        For larger lists we PUT the first 100 (which also truncates
        anything beyond) then POST the rest in 100-URI chunks. We
        never exceed 100 in practice (top-40 + novetats <= 100), but
        the chunking keeps the helper general.

        Endpoint note (2026-05-22): the previous path
        `/playlists/<id>/tracks` was deprecated by Spotify's February
        2026 Web API migration and now returns 403 Forbidden to apps
        in Development Mode. The new path is `/items` with the same
        request and response shape (`{"uris": [...]}`). Migrating to
        `/items` is the entire fix for the 2026-05-22 "all 12 playlists
        return 403" incident.
        """
        first = uris[: self.PLAYLIST_TRACK_BATCH]
        self._request(
            "PUT",
            f"/playlists/{playlist_id}/items",
            json={"uris": first},
        )
        for i in range(self.PLAYLIST_TRACK_BATCH, len(uris), self.PLAYLIST_TRACK_BATCH):
            chunk = uris[i : i + self.PLAYLIST_TRACK_BATCH]
            self._request(
                "POST",
                f"/playlists/{playlist_id}/items",
                json={"uris": chunk},
            )

    def update_playlist_details(
        self, playlist_id: str, name: str, description: str
    ) -> None:
        """Set a playlist's name and description in place.

        `PUT /playlists/<id>` with `{"name": ..., "description": ...}`.
        Same Spotify endpoint Process A uses for everything else, so a
        rename flows through the sanctioned sync pipeline rather than a
        manual edit in the Spotify UI. Idempotent: Spotify accepts the
        same values on every call."""
        self._request(
            "PUT",
            f"/playlists/{playlist_id}",
            json={"name": name, "description": description},
        )
