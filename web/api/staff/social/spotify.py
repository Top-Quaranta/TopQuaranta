"""Staff endpoints for Spotify OAuth + playlist sync management.

These four endpoints back the `/staff/social/spotify/` SPA page and
replace the historical SSH-only flow (`manage.py autoritzar_spotify`,
which still works as a fallback but requires terminal access plus
manual paste of the `code` query parameter).

  GET  /api/v1/staff/social/spotify/estat/
       Snapshot of the current Spotify auth row, the 5 (eventually 10)
       SpotifyPlaylist rows with their sync KPIs, and the cron silenced
       flag (read-only — see the `cron_silenced` docstring below).

  POST /api/v1/staff/social/spotify/oauth-start/
       Mints a CSRF state token and returns the Spotify Authorize URL.
       The SPA opens that URL in a new tab; Spotify redirects the user
       back to `/staff/social/spotify/callback` once they approve.

  POST /api/v1/staff/social/spotify/oauth-callback/
       Exchanges the `code` returned by Spotify for a refresh_token
       and persists it to `SpotifyAuth(pk=1)`. Refuses to persist if
       `me().product != "premium"` because the cron would fail
       silently on the first `GET /v1/search` after the activation
       takes effect (Spotify changed their policy in late 2024: any
       Web API call from an app whose owner is on the free tier
       returns 403). See ADR-0009.

  POST /api/v1/staff/social/spotify/sync/
       Runs `actualitzar_playlists_spotify` synchronously for the
       requested freq and returns a summary. Used for manual testing
       and to bootstrap the very first sync after OAuth completes
       (so the operator doesn't have to wait until the next cron tick).

The `unsilence` endpoint described in the sprint spec is intentionally
NOT implemented as a runtime endpoint: `deploy/cron-meta.json` is
checked into git and overwritten on every deploy, so a runtime mutation
would be silently undone on the next `git pull`. The same effect is
achieved with a regular commit to that file (see FASE C.4 of the
revival sprint plan).
"""

from __future__ import annotations

import base64
import datetime
import io
import json
import secrets
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.management import call_command
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from ingesta.clients.spotify import API_BASE, TOKEN_URL, UserSpotifyClient
from music.models import SpotifyAuth, SpotifyPlaylist
from web.api.staff._common import IsStaff

# OAuth state TTL. Spotify expects the state to round-trip through
# the user's browser within a few minutes. We park the state on the
# session itself so we don't need a server-side cache, and we cap
# its validity at 10 min via a stored issued_at timestamp.
_STATE_TTL_SECONDS = 600

# Session keys for the in-flight OAuth state. Namespaced so they
# don't collide with other future OAuth-on-session flows.
_SESSION_STATE_KEY = "spotify_oauth_state"
_SESSION_STATE_AT_KEY = "spotify_oauth_state_at"

# `me().product` values we accept. Spotify returns "premium" for any
# active paid subscription (Individual, Family, Duo, Student). "free"
# triggers a 403 on any /v1/search or /v1/playlists call from the
# app, which is the failure mode ADR-0009 documents.
_VALID_PRODUCTS = {"premium"}


# ── Helpers ────────────────────────────────────────────────────────


def _playlist_payload(pl: SpotifyPlaylist) -> dict:
    """Serialise one SpotifyPlaylist row for the estat endpoint.

    Kept here (not on the model) because the model is shared with the
    cron and we don't want to couple model serialisation to a UI
    contract."""
    return {
        "codi": pl.codi,
        "kind": pl.kind,
        "territori": pl.territori,
        "spotify_playlist_id": pl.spotify_playlist_id,
        "spotify_url": (
            f"https://open.spotify.com/playlist/{pl.spotify_playlist_id}"
            if pl.spotify_playlist_id
            else ""
        ),
        "last_sync_at": pl.last_sync_at.isoformat() if pl.last_sync_at else None,
        "last_sync_ok": pl.last_sync_ok,
        "last_sync_msg": pl.last_sync_msg,
        "last_n_tracks": pl.last_n_tracks,
        "last_n_matched": pl.last_n_matched,
        "coverage": (
            round(pl.last_n_matched / pl.last_n_tracks, 3) if pl.last_n_tracks else None
        ),
    }


def _read_cron_silenced() -> bool:
    """Return whether `actualitzar_playlists_spotify` is marked silenced
    in `deploy/cron-meta.json`.

    Read-only on purpose: the JSON is checked into git, and a runtime
    mutation would be reverted by the next deploy. To unsilence, commit
    a change to that file and deploy."""
    try:
        meta_path = Path(settings.BASE_DIR) / "deploy" / "cron-meta.json"
        with meta_path.open() as fh:
            data = json.load(fh)
        entry = data.get("actualitzar_playlists_spotify") or {}
        return bool(entry.get("silenced"))
    except Exception:
        # If the file is missing or malformed, fall through to "not
        # silenced". The staff endpoint should never crash the page
        # over a cron-meta read.
        return False


def _live_me(auth: SpotifyAuth) -> tuple[dict, str | None]:
    """Call `GET /v1/me` with the refresh token in `auth`.

    Returns `(payload_dict, error_str)`. On success `error_str` is
    None. On failure `payload_dict` is `{}` and `error_str` is a
    human-readable error suitable for the page.

    The cost is one refresh + one /me hit per call; the SPA caches at
    the page level so we don't add a memoising layer here."""
    try:
        client = UserSpotifyClient(auth)
        return client.me(), None
    except Exception as exc:  # noqa: BLE001 — surface to the UI
        return {}, f"{type(exc).__name__}: {exc}"


# ── Endpoints ──────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsStaff])
def spotify_estat(request: Request) -> Response:
    """Aggregate the page's data in one call.

    Live fields (`spotify_user_id`, `product`, `scopes`) are pulled
    via `GET /v1/me` when a `SpotifyAuth` row exists. If the row is
    missing we report `oauth_present=False` and skip the live call —
    the page renders an "authorise" CTA without making any Spotify
    API hit."""
    auth = SpotifyAuth.load()
    payload: dict = {
        "oauth_present": auth is not None,
        "spotify_user_id": auth.spotify_user_id if auth else None,
        "scope": auth.scope if auth else "",
        "updated_at": auth.updated_at.isoformat() if auth else None,
        "product": None,
        "live_error": None,
        "playlists": [
            _playlist_payload(pl) for pl in SpotifyPlaylist.objects.order_by("codi")
        ],
        "cron_silenced": _read_cron_silenced(),
    }
    if auth:
        me, err = _live_me(auth)
        if err:
            payload["live_error"] = err
        else:
            # `me()` returns the canonical user_id; if it disagrees with
            # the row we keep the live one (the row gets refreshed on
            # the next /oauth-callback/). Surface both so the UI can
            # flag the drift.
            payload["spotify_user_id"] = me.get("id") or payload["spotify_user_id"]
            payload["product"] = me.get("product")
            # Convenience: also surface the display_name and country.
            payload["display_name"] = me.get("display_name") or ""
            payload["country"] = me.get("country") or ""
    return Response(payload)


@api_view(["POST"])
@permission_classes([IsStaff])
def spotify_oauth_start(request: Request) -> Response:
    """Generate the authorise URL and stash the state on the session.

    Returns `{"url": "https://accounts.spotify.com/authorize?..."}`.
    The SPA navigates to that URL (`window.location.href = url`) so the
    user lands on Spotify, approves, and gets redirected back to our
    callback page."""
    if not settings.SPOTIFY_CLIENT_ID or not settings.SPOTIFY_CLIENT_SECRET:
        return Response(
            {"error": "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET no configurats."},
            status=500,
        )
    state = secrets.token_urlsafe(24)
    request.session[_SESSION_STATE_KEY] = state
    # Use timezone-aware UTC; `datetime.utcnow()` is deprecated in 3.13.
    request.session[_SESSION_STATE_AT_KEY] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    # Force the session to persist immediately. DRF's `Request`
    # doesn't always trigger Django's session save() at end-of-view
    # if the response is composed elsewhere; setting `.modified` is
    # the documented escape hatch.
    request.session.modified = True

    params = {
        "client_id": settings.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
        "scope": UserSpotifyClient.OAUTH_SCOPES,
        "state": state,
        # `show_dialog=true` forces Spotify to display the consent
        # screen even if the admin has already approved this client.
        # Useful when re-authorising under a different identity (the
        # exact scenario this UI exists to handle).
        "show_dialog": "true",
    }
    auth_url = "https://accounts.spotify.com/authorize?" + urlencode(params)
    return Response({"url": auth_url})


@api_view(["POST"])
@permission_classes([IsStaff])
def spotify_oauth_callback(request: Request) -> Response:
    """Exchange the authorisation `code` for a refresh_token and persist.

    The SPA's callback page POSTs here with the `code` and `state` it
    received from Spotify. We:
      1. Validate the state against what we stashed at /oauth-start/.
      2. POST the code to `accounts.spotify.com/api/token` with our
         client credentials and the same redirect_uri.
      3. Call `/v1/me` with the freshly-minted access token to learn
         `spotify_user_id` and `product`.
      4. Refuse to persist if `product != "premium"` because the cron
         would 403 on any subsequent call (see ADR-0009).
      5. Persist to `SpotifyAuth(pk=1)`."""
    code = (request.data.get("code") or "").strip()
    state = (request.data.get("state") or "").strip()
    if not code or not state:
        return Response({"error": "code i state son obligatoris"}, status=400)

    stashed = request.session.get(_SESSION_STATE_KEY)
    stashed_at_iso = request.session.get(_SESSION_STATE_AT_KEY)
    # Compare states with `secrets.compare_digest` to avoid timing
    # attacks. Cheap and right.
    if not stashed or not secrets.compare_digest(stashed, state):
        return Response({"error": "state no coincideix"}, status=400)
    if stashed_at_iso:
        try:
            stashed_at = datetime.datetime.fromisoformat(stashed_at_iso)
        except ValueError:
            stashed_at = None
        now = datetime.datetime.now(datetime.timezone.utc)
        # `fromisoformat` of the value we wrote preserves tz; compare in
        # the same tz to avoid the "can't subtract aware from naive" trap.
        if stashed_at and stashed_at.tzinfo is None:
            stashed_at = stashed_at.replace(tzinfo=datetime.timezone.utc)
        if stashed_at and (now - stashed_at).total_seconds() > _STATE_TTL_SECONDS:
            return Response(
                {"error": "state caducat; reinicia el flux d'autorització"}, status=400
            )
    # One-shot: pop the state so a replay of the same callback won't
    # succeed even if the code is valid.
    request.session.pop(_SESSION_STATE_KEY, None)
    request.session.pop(_SESSION_STATE_AT_KEY, None)
    request.session.modified = True

    basic = base64.b64encode(
        f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    try:
        token_resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.SPOTIFY_REDIRECT_URI,
            },
            headers={"Authorization": f"Basic {basic}"},
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        return Response(
            {"error": f"No s'ha pogut contactar amb Spotify: {exc}"}, status=502
        )
    if token_resp.status_code != 200:
        return Response(
            {
                "error": (
                    f"Spotify ha rebutjat el code "
                    f"({token_resp.status_code}): {token_resp.text[:300]}"
                )
            },
            status=400,
        )
    payload = token_resp.json()
    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    scope = payload.get("scope", "")
    if not refresh_token:
        return Response(
            {"error": "Spotify no ha tornat refresh_token; reinicia el flux."},
            status=400,
        )

    # Live /me to learn the user_id and product. We use the access_token
    # we just got, NOT the helper, because the helper does a refresh
    # round trip that would discard the rotation Spotify sometimes
    # bundles into the initial response.
    try:
        me_resp = requests.get(
            f"{API_BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        return Response({"error": f"Spotify /me ha fallat: {exc}"}, status=502)
    if me_resp.status_code != 200:
        return Response(
            {
                "error": (
                    f"Spotify /me ha retornat {me_resp.status_code}: "
                    f"{me_resp.text[:300]}"
                )
            },
            status=400,
        )
    me_payload = me_resp.json()
    product = me_payload.get("product") or ""
    spotify_user_id = me_payload.get("id") or ""
    if product not in _VALID_PRODUCTS:
        # We deliberately reject Free / Family-only / etc. Without
        # Premium the cron would 403 on the first /v1/search call
        # (see ADR-0009).
        return Response(
            {
                "error": (
                    f"L'usuari de Spotify '{spotify_user_id}' no és Premium "
                    f"(product='{product}'). Cal una subscripció Premium "
                    f"activa al propietari de l'app per a fer servir la Web API."
                ),
                "product": product,
                "spotify_user_id": spotify_user_id,
            },
            status=400,
        )

    SpotifyAuth.objects.update_or_create(
        pk=1,
        defaults={
            "refresh_token": refresh_token,
            "scope": scope,
            "spotify_user_id": spotify_user_id,
        },
    )
    return Response(
        {
            "ok": True,
            "spotify_user_id": spotify_user_id,
            "product": product,
            "scope": scope,
        }
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def spotify_sync(request: Request) -> Response:
    """Run `actualitzar_playlists_spotify` synchronously.

    Body: `{"freq": "daily"|"weekly"|null, "dry_run": bool,
    "only": "codi" (opc)}`.

    Streams the management command's stdout/stderr into the response
    so the operator can see ISRC match counts inline. Capped at 120s
    (the same timeout DRF uses for synchronous requests behind Caddy).

    NOTE: the `--freq` flag does NOT exist yet on the command (FASE D
    adds it). We pass it conditionally so this endpoint already works
    for the legacy command; once FASE D lands, the SPA can pick
    daily vs weekly explicitly."""
    freq = (request.data.get("freq") or "").strip()
    only = (request.data.get("only") or "").strip()
    dry_run = bool(request.data.get("dry_run"))

    kwargs: dict = {}
    if dry_run:
        kwargs["dry_run"] = True
    if only:
        kwargs["only"] = only
    if freq:
        # FASE D will add this; pre-FASE-D the command ignores the
        # kwarg, so we filter it out via a try/except below.
        kwargs["freq"] = freq

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            call_command("actualitzar_playlists_spotify", **kwargs)
    except TypeError as exc:
        # Pre-FASE-D fallback: the command rejected `freq`. Retry
        # without it so the endpoint stays functional during the
        # transition.
        if "freq" in str(exc) and "freq" in kwargs:
            kwargs.pop("freq")
            out_buf = io.StringIO()
            err_buf = io.StringIO()
            try:
                with redirect_stdout(out_buf), redirect_stderr(err_buf):
                    call_command("actualitzar_playlists_spotify", **kwargs)
            except Exception as exc2:  # noqa: BLE001
                return Response(
                    {
                        "error": f"{type(exc2).__name__}: {exc2}",
                        "stdout": out_buf.getvalue(),
                        "stderr": err_buf.getvalue(),
                    },
                    status=500,
                )
        else:
            return Response(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "stdout": out_buf.getvalue(),
                    "stderr": err_buf.getvalue(),
                },
                status=500,
            )
    except Exception as exc:  # noqa: BLE001
        return Response(
            {
                "error": f"{type(exc).__name__}: {exc}",
                "stdout": out_buf.getvalue(),
                "stderr": err_buf.getvalue(),
            },
            status=500,
        )

    return Response(
        {
            "ok": True,
            "freq": freq or None,
            "only": only or None,
            "dry_run": dry_run,
            "stdout": out_buf.getvalue(),
            "stderr": err_buf.getvalue(),
            # Re-read the playlists so the page can refresh KPIs
            # without a separate /estat/ round trip.
            "playlists": [
                _playlist_payload(pl) for pl in SpotifyPlaylist.objects.order_by("codi")
            ],
        }
    )
