"""Health checks for the Spotify playlist subsystem.

Two checks, both invoked from `scripts/health/spotify_*.sh` (and
transitively from `bin/tq-health`).

  * `check_spotify_premium()` — confirms that the OAuth refresh
    token still works AND that the account is on a Premium tier.
    Spotify silently switches its `403 Active premium subscription
    required` response on lapse, so a passing /v1/search call is
    not enough; we explicitly call /v1/me and inspect `.product`.

  * `check_spotify_coverage()` — reads `SpotifyPlaylist` rows from
    the DB and computes the per-row matched-over-tracks coverage
    ratio. A sudden coverage cliff usually indicates ISRC drift in
    the upstream Last.fm or Deezer ingestion, not a Spotify-side
    bug.

Both functions return `(severity, message, payload)` where
`severity` is `"OK"`, `"WARN"`, or `"CRIT"`. Bash callers map those
to exit codes 0/1/2 respectively (matching the convention used by
the rest of `bin/tq-health`'s sub-checks).
"""

from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

Severity = Literal["OK", "WARN", "CRIT"]

# Coverage thresholds (matched / total). Below WARN we just flag;
# below CRIT we expect operator intervention. The cron itself
# silently drops ISRC mismatches so a sustained 80% is fine, a
# 50% is "something upstream broke".
COVERAGE_WARN_BELOW = 0.85
COVERAGE_CRIT_BELOW = 0.50

# `me().product` values we treat as healthy. Spotify returns
# "premium" for any active paid subscription (Individual, Family,
# Duo, Student). Anything else fails the gate because the cron
# would 403 on the next /v1/search call (see ADR-0009).
_PREMIUM_OK = {"premium"}


def check_spotify_premium() -> tuple[Severity, str, dict]:
    """Verify Premium is still active on the app owner.

    Returns:
      ("OK",   message, payload)  — `product == "premium"`.
      ("WARN", message, payload)  — transient API error; don't
                                    escalate immediately because
                                    Spotify occasionally 5xxs.
      ("CRIT", message, payload)  — Premium has lapsed, or the
                                    refresh token has been revoked,
                                    or no OAuth row exists yet.

    The payload is always a dict (possibly empty) so the bash
    wrapper can pretty-print it without conditional shape checks.
    """
    # Local imports because this module is loaded by bash via
    # `python -c`, which we want to fail-soft if Django isn't ready.
    try:
        from ingesta.clients.spotify import UserSpotifyClient
        from music.models import SpotifyAuth
    except Exception as exc:  # noqa: BLE001
        return "CRIT", f"Django import failed: {exc}", {}

    auth = SpotifyAuth.load()
    if auth is None:
        return (
            "CRIT",
            (
                "No SpotifyAuth row in DB. OAuth dance not completed "
                "(visit /staff/social/spotify/ to authorise)."
            ),
            {},
        )

    try:
        client = UserSpotifyClient(auth)
        me = client.me()
    except Exception as exc:  # noqa: BLE001
        # The UserSpotifyClient class raises a RuntimeError on
        # exhausted retries (4xx) and a requests.RequestException
        # on transport errors. We can't easily distinguish "Premium
        # lapsed" (401 on /me) from "Spotify is down" without
        # parsing the exception body, so we go with a conservative
        # default: WARN, not CRIT. The watchdog escalates after 3
        # consecutive failures via the standard cron status path.
        return "WARN", f"Spotify /me call failed: {type(exc).__name__}: {exc}", {}

    product = (me.get("product") or "").lower()
    user_id = me.get("id") or ""
    payload = {
        "product": product,
        "spotify_user_id": user_id,
        "display_name": me.get("display_name") or "",
        "country": me.get("country") or "",
    }
    if product not in _PREMIUM_OK:
        return (
            "CRIT",
            (
                f"Spotify account '{user_id}' is no longer Premium "
                f"(product='{product}'). The playlist sync cron will "
                "start failing 403 silently. Reactivate Premium and "
                "reauthorise from /staff/social/spotify/."
            ),
            payload,
        )
    return "OK", f"Premium OK for {user_id} (product={product})", payload


def _cron_is_silenced(cron_name: str) -> bool:
    """Return True iff deploy/cron-meta.json marks this cron as silenced.

    Read at call time (not at import) because the JSON file ships with
    the repo and changes on deploy. Fail-open: if the file is missing
    or malformed we treat the cron as NOT silenced, so a degraded
    cron-meta still produces alerts instead of silently swallowing
    them (worst-case noise > worst-case silence).
    """
    import json
    from pathlib import Path

    candidates = [
        Path("/home/topquaranta/app/deploy/cron-meta.json"),
        Path(__file__).resolve().parents[1] / "deploy" / "cron-meta.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            return False
        entry = data.get(cron_name) or {}
        return bool(entry.get("silenced"))
    return False


def check_spotify_coverage() -> tuple[Severity, str, dict]:
    """Inspect `SpotifyPlaylist.last_n_matched / last_n_tracks`.

    Returns:
      ("OK",   message, payload)  — every successfully-synced row
                                    has matched / total ≥ WARN, OR the
                                    Process A cron is silenced (no
                                    sync expected so low coverage is
                                    not actionable).
      ("WARN", message, payload)  — at least one row below WARN, or
                                    the cron is active and no row has
                                    ever synced.
      ("CRIT", message, payload)  — at least one row below CRIT.

    Silenced gate (added 2026-05-22 after FASE F false-positive
    review): when `actualitzar_playlists_spotify` is silenced in
    `cron-meta.json` we short-circuit to OK regardless of last_n_*
    because the operator has explicitly told us not to expect a
    healthy sync yet. Without this, every staff dashboard load while
    the cron was silenced reported coverage CRIT (all 12 playlists at
    0 tracks until the first wet sync), drowning out real signals.

    Rows with `last_sync_ok=False` are reported via the message but
    don't trigger CRIT on their own; the cron's own status file is
    the canonical "did the last run work?" signal. We're focused on
    the "ran OK but matched very little" silent-degradation case.
    """
    try:
        from music.models import SpotifyPlaylist
    except Exception as exc:  # noqa: BLE001
        return "CRIT", f"Django import failed: {exc}", {}

    # If the operator has silenced the sync cron, low coverage is the
    # expected state, not a regression. Skip the analysis to avoid the
    # false positive on every dashboard load while the cron is paused.
    if _cron_is_silenced("actualitzar_playlists_spotify"):
        return (
            "OK",
            (
                "actualitzar_playlists_spotify is silenced; coverage check "
                "skipped (sync not expected to run)."
            ),
            {"rows": [], "silenced": True},
        )

    rows = list(SpotifyPlaylist.objects.order_by("codi"))
    if not rows:
        return (
            "WARN",
            "No SpotifyPlaylist rows configured (run configurar_spotify_playlists).",
            {"rows": []},
        )

    summary: list[dict] = []
    severity: Severity = "OK"
    bad_msgs: list[str] = []
    no_sync_ok_count = 0

    for pl in rows:
        if pl.last_n_tracks == 0:
            # Never synced — count separately. If NONE of the rows
            # have ever synced and the cron isn't silenced, that's
            # a configuration problem the operator should see.
            no_sync_ok_count += 1
            summary.append(
                {
                    "codi": pl.codi,
                    "coverage": None,
                    "last_n_matched": pl.last_n_matched,
                    "last_n_tracks": pl.last_n_tracks,
                    "last_sync_ok": pl.last_sync_ok,
                }
            )
            continue
        ratio = pl.last_n_matched / pl.last_n_tracks
        summary.append(
            {
                "codi": pl.codi,
                "coverage": round(ratio, 3),
                "last_n_matched": pl.last_n_matched,
                "last_n_tracks": pl.last_n_tracks,
                "last_sync_ok": pl.last_sync_ok,
            }
        )
        if ratio < COVERAGE_CRIT_BELOW:
            severity = "CRIT"
            bad_msgs.append(f"{pl.codi}={ratio:.0%}")
        elif ratio < COVERAGE_WARN_BELOW and severity != "CRIT":
            severity = "WARN"
            bad_msgs.append(f"{pl.codi}={ratio:.0%}")

    payload = {"rows": summary}

    if severity == "OK" and no_sync_ok_count == len(rows):
        # Nothing has ever synced. The cron may have been silenced
        # (in which case the watchdog logic handles it). Surface as
        # WARN to nudge the operator anyway.
        return (
            "WARN",
            f"All {len(rows)} SpotifyPlaylist rows have last_n_tracks=0 (never synced).",
            payload,
        )

    if severity == "OK":
        msg = f"Coverage OK for {len(rows)} playlists."
    else:
        msg = f"{severity}: coverage below threshold for " f"{', '.join(bad_msgs)}."
    return severity, msg, payload


def main(argv: list[str]) -> int:
    """CLI dispatch so the bash wrappers can `python -m music.health <check>`.

    Exit codes match the bash convention used by the rest of
    `bin/tq-health`: 0=OK, 1=WARN, 2=CRIT.
    """
    if len(argv) < 2 or argv[1] not in ("spotify_premium", "spotify_coverage"):
        print("usage: python -m music.health {spotify_premium|spotify_coverage}")
        return 2

    import json

    import django

    django.setup()
    fn = (
        check_spotify_premium
        if argv[1] == "spotify_premium"
        else check_spotify_coverage
    )
    severity, message, payload = fn()
    out = {"severity": severity, "message": message, "payload": payload}
    print(json.dumps(out))
    return {"OK": 0, "WARN": 1, "CRIT": 2}[severity]


if __name__ == "__main__":
    import os
    import sys

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "topquaranta.settings.production")
    sys.exit(main(sys.argv))
