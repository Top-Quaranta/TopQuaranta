import logging
import time
from datetime import date, timedelta

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
RATE_LIMIT_SLEEP = 0.1
MAX_RETRIES = 3


class SpotifyClient:
    """
    Spotify Web API client using Client Credentials flow.
    Only individual endpoints — batch endpoints are broken in Development Mode.
    """

    def __init__(self) -> None:
        self._token: str | None = None

    def _authenticate(self) -> None:
        """Obtain an access token via Client Credentials flow."""
        response = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(settings.SPOTIFY_CLIENT_ID, settings.SPOTIFY_CLIENT_SECRET),
            timeout=10,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]

    def _headers(self) -> dict:
        if not self._token:
            self._authenticate()
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, url: str, params: dict | None = None) -> dict | None:
        """
        GET request with retry and token refresh on 401.
        Returns parsed JSON or None on failure.
        """
        for attempt in range(MAX_RETRIES):
            try:
                time.sleep(RATE_LIMIT_SLEEP)
                resp = requests.get(
                    url, headers=self._headers(), params=params, timeout=10
                )

                if resp.status_code == 401:
                    logger.info("Spotify token expired, re-authenticating...")
                    self._authenticate()
                    continue

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    logger.warning("Spotify rate limited, waiting %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.RequestException as exc:
                wait = 2**attempt
                logger.warning(
                    "Spotify attempt %d/%d failed for %s: %s — retry in %ds",
                    attempt + 1,
                    MAX_RETRIES,
                    url,
                    exc,
                    wait,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)

        logger.error("Spotify: all retries exhausted for %s", url)
        return None

    def get_artist_albums(
        self, artist_id: str, min_date: date | None = None
    ) -> list[dict]:
        """
        Fetch all albums/singles/EPs for an artist.
        Filters by min_date if provided.
        Returns list of album dicts with keys: id, name, release_date,
        album_type, images.
        """
        albums = []
        url = f"{API_BASE}/artists/{artist_id}/albums"
        params = {
            "include_groups": "album,single",
            "limit": 50,
            "market": "ES",
        }

        while url:
            data = self._get(url, params=params)
            if not data:
                break

            for item in data.get("items", []):
                release_date_str = item.get("release_date", "")
                release_date = _parse_release_date(release_date_str)

                if min_date and release_date and release_date < min_date:
                    continue

                album_type = item.get("album_type", "album")
                images = item.get("images", [])
                image_url = images[0]["url"] if images else ""

                albums.append(
                    {
                        "id": item["id"],
                        "name": item.get("name", ""),
                        "release_date": release_date,
                        "album_type": album_type,
                        "image_url": image_url,
                    }
                )

            # Pagination
            next_url = data.get("next")
            if next_url:
                url = next_url
                params = None  # next URL includes params
            else:
                break

        return albums

    def get_album_tracks(self, album_id: str) -> list[dict]:
        """
        Fetch all tracks for an album.
        Returns list of track dicts with keys: id, name, duration_ms,
        track_number, artists, isrc.
        """
        tracks = []
        url = f"{API_BASE}/albums/{album_id}"

        data = self._get(url)
        if not data:
            return tracks

        for item in data.get("tracks", {}).get("items", []):
            # ISRC is on the full track object, not the simplified one.
            # We need to fetch the full album which includes external_ids
            # at the album level but not track level. We'll get ISRC separately.
            tracks.append(
                {
                    "id": item["id"],
                    "name": item.get("name", ""),
                    "duration_ms": item.get("duration_ms"),
                    "track_number": item.get("track_number", 0),
                    "artists": [
                        {"id": a["id"], "name": a["name"]}
                        for a in item.get("artists", [])
                    ],
                }
            )

        return tracks

    def get_track(self, track_id: str) -> dict | None:
        """
        Fetch a single track to get ISRC and other details.
        Returns track dict or None.
        """
        url = f"{API_BASE}/tracks/{track_id}"
        params = {"market": "ES"}
        data = self._get(url, params=params)
        if not data:
            return None

        external_ids = data.get("external_ids", {})
        artists = [{"id": a["id"], "name": a["name"]} for a in data.get("artists", [])]

        return {
            "id": data["id"],
            "name": data.get("name", ""),
            "duration_ms": data.get("duration_ms"),
            "isrc": external_ids.get("isrc", ""),
            "artists": artists,
        }


def _parse_release_date(date_str: str) -> date | None:
    """Parse Spotify release date (YYYY, YYYY-MM, or YYYY-MM-DD)."""
    if not date_str:
        return None
    parts = date_str.split("-")
    try:
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        elif len(parts) == 1:
            return date(int(parts[0]), 1, 1)
    except (ValueError, TypeError):
        return None
    return None


# ─────────────────────────────────────────────────────────────────────────
# User OAuth client — for playlist management (weekly sync cron).
#
# The class above uses Client Credentials and can't touch user-scoped
# endpoints like /me/playlists or /playlists/<id>/tracks. This one reads
# the refresh_token stored in `music.SpotifyAuth` and manages a short-
# lived access token on top so we can mutate user-owned playlists.
# ─────────────────────────────────────────────────────────────────────────


class UserSpotifyClient:
    """OAuth refresh-token-backed client for playlist management.

    `SpotifyAuth` is populated once by the `autoritzar_spotify` mgmt
    command. On every call we lazily refresh the access token; on 401
    mid-flight we refresh once and retry; on 429 we honour Retry-After.
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

    def __init__(self, auth) -> None:
        # Imported lazily to avoid a models-not-ready issue at module load.
        self._auth = auth
        self._access_token: str | None = None

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
            time.sleep(RATE_LIMIT_SLEEP)
            resp = requests.request(
                method, url, headers=self._headers(), timeout=20, **kwargs
            )
            if resp.status_code == 401:
                logger.info("Spotify token expired mid-flight; refreshing")
                self._refresh_access_token()
                continue
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2))
                logger.warning("Spotify rate limited; sleeping %ds", wait)
                time.sleep(wait)
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

    def replace_playlist_tracks(self, playlist_id: str, uris: list[str]) -> None:
        """Replace the whole playlist in place.

        Spotify's PUT /playlists/<id>/tracks caps at 100 URIs per call.
        For larger lists we PUT the first 100 (which also truncates
        anything beyond) then POST the rest in 100-URI chunks. We
        never exceed 100 in practice (top-40 + novetats ≲ 100), but
        the chunking keeps the helper general.
        """
        first = uris[: self.PLAYLIST_TRACK_BATCH]
        self._request(
            "PUT",
            f"/playlists/{playlist_id}/tracks",
            json={"uris": first},
        )
        for i in range(self.PLAYLIST_TRACK_BATCH, len(uris), self.PLAYLIST_TRACK_BATCH):
            chunk = uris[i : i + self.PLAYLIST_TRACK_BATCH]
            self._request(
                "POST",
                f"/playlists/{playlist_id}/tracks",
                json={"uris": chunk},
            )
