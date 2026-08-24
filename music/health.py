"""Health checks run by `bin/tq-health` via `scripts/health/*.sh`.

Spotify playlist checks, the Instagram token expiry check, and the TLS
certificate expiry watch.

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

# `no_verificades` triage chunks lag by DESIGN and must not trip the
# strict per-row gate above. `enriquir_spotify` enriches the pending
# pool in `ml_confianca`-desc order — the same order the chunks are
# built in — so the low-confidence tail (high chunk index) sits near 0%
# coverage as a steady state, not a regression (audit 2026-06-06: no
# stall in any enrichment path; the gradient is backlog by confidence
# order with slow pending throughput). We exclude these rows from the
# per-row CRIT/WARN and instead watch only their AGGREGATE coverage: a
# collapse there is the one signal that pending enrichment has really
# stalled, and that is a WARN nudge, never an operator-critical CRIT.
NO_VERIF_AGG_WARN_BELOW = 0.10
NO_VERIF_AGG_MIN_TRACKS = 100  # don't alert on a tiny / just-seeded set

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
      ("WARN", message, payload)  — at least one VERIFIED (top/novetats)
                                    row below WARN, the cron is active
                                    and no row has ever synced, or the
                                    no-verif AGGREGATE coverage has
                                    collapsed below NO_VERIF_AGG_WARN_BELOW
                                    (the one real-stall signal for
                                    pending enrichment).
      ("CRIT", message, payload)  — at least one VERIFIED row below CRIT.

    `no_verificades` rows are excluded from the per-row CRIT/WARN gate
    (they lag by design — see the threshold constants) and only feed the
    aggregate WARN net; their per-chunk coverage is still reported in the
    payload for staff visibility. Only `top` / `novetats` rows drive the
    strict per-row severity; any other kind (e.g. `novetats_per_verificar`,
    a curated work list) is reported in the payload but kept out of the
    alert entirely.

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
    nv_matched = 0
    nv_tracks = 0

    strict_kinds = (SpotifyPlaylist.KIND_TOP, SpotifyPlaylist.KIND_NOVETATS)
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
        if pl.kind == SpotifyPlaylist.KIND_NO_VERIFICADES:
            # Lags by design — aggregated below, excluded from per-row.
            nv_matched += pl.last_n_matched
            nv_tracks += pl.last_n_tracks
            continue
        if pl.kind not in strict_kinds:
            # e.g. novetats_per_verificar: a curated work list, not a
            # synced chart. Reported in the payload but outside the gate
            # (neither the strict per-row check nor the no-verif net).
            continue
        if ratio < COVERAGE_CRIT_BELOW:
            severity = "CRIT"
            bad_msgs.append(f"{pl.codi}={ratio:.0%}")
        elif ratio < COVERAGE_WARN_BELOW and severity != "CRIT":
            severity = "WARN"
            bad_msgs.append(f"{pl.codi}={ratio:.0%}")

    # No-verif aggregate safety net: only a collapse signals a real
    # pending-enrichment stall, and it is a WARN nudge, not a CRIT.
    nv_agg = (nv_matched / nv_tracks) if nv_tracks else None
    if (
        nv_agg is not None
        and nv_tracks >= NO_VERIF_AGG_MIN_TRACKS
        and nv_agg < NO_VERIF_AGG_WARN_BELOW
        and severity != "CRIT"
    ):
        severity = "WARN"
        bad_msgs.append(f"no-verif aggregate={nv_agg:.0%}")

    payload = {
        "rows": summary,
        "no_verif_aggregate": (round(nv_agg, 3) if nv_agg is not None else None),
    }

    if severity == "OK" and no_sync_ok_count == len(rows):
        # Nothing has ever synced. The cron may have been silenced
        # (in which case the watchdog logic handles it). Surface as
        # WARN to nudge the operator anyway.
        return (
            "WARN",
            f"All {len(rows)} SpotifyPlaylist rows have last_n_tracks=0 (never synced).",
            payload,
        )

    nv_note = (
        f" (no-verif aggregate {nv_agg:.0%}, lags by design)"
        if nv_agg is not None
        else ""
    )
    if severity == "OK":
        msg = f"Coverage OK for {len(rows)} playlists{nv_note}."
    else:
        msg = (
            f"{severity}: coverage below threshold for "
            f"{', '.join(bad_msgs)}{nv_note}."
        )
    return severity, msg, payload


# Instagram long-lived token expiry. The Meta app is in development mode
# (business verification denied), so renewal is MANUAL — there is no
# working auto-refresh (renovar_token_instagram only prints, never
# persists). The real Meta expiry is NOT queryable with our IG-Login
# token (debug_token 400s), so we alert on the stored `expires_at`
# (set to paste+60d). This catches a *natural* lapse with runway; it
# cannot catch an out-of-band invalidation like the 2026-07-07 incident.
IG_TOKEN_WARN_DAYS = 10
IG_TOKEN_CRIT_DAYS = 5


def check_instagram_token() -> tuple[Severity, str, dict]:
    """WARN at ≤10 days, CRIT at ≤5 days before the stored IG token
    expiry, so the operator can re-authorize manually before the cron
    starts failing. OK when not configured / DRY_RUN (no expiry)."""
    try:
        from social.instagram_client import days_until_expiry
    except Exception as exc:  # noqa: BLE001
        return "CRIT", f"Django import failed: {exc}", {}
    days = days_until_expiry()
    if days is None:
        return "OK", "IG token: no configurat o DRY_RUN.", {"days": None}
    payload = {
        "days": days,
        "warn_below": IG_TOKEN_WARN_DAYS,
        "crit_below": IG_TOKEN_CRIT_DAYS,
    }
    if days <= IG_TOKEN_CRIT_DAYS:
        return "CRIT", f"IG token caduca en {days}d — reautoritza JA (manual).", payload
    if days <= IG_TOKEN_WARN_DAYS:
        return (
            "WARN",
            f"IG token caduca en {days}d — planifica reautorització.",
            payload,
        )
    return "OK", f"IG token OK ({days}d fins l'expiració desada).", payload


# GitHub fine-grained PAT that dependabot-automerge uses to merge
# (AUTOMERGE_PAT). The box never holds the token, so the real expiry is
# not queryable from here — we alert on the stored date, same approach
# as the IG token. If the PAT lapses, automerge silently falls back to
# GITHUB_TOKEN and merges stop triggering deploys (DRIFT incident,
# 2026-08-24). Renewal: new fine-grained PAT (contents + pull-requests
# write), `gh secret set AUTOMERGE_PAT`, and bump this date in the same
# PR.
GITHUB_PAT_EXPIRES = "2026-09-23"
GITHUB_PAT_WARN_DAYS = 10
GITHUB_PAT_CRIT_DAYS = 5


def check_github_pat() -> tuple[Severity, str, dict]:
    """WARN at ≤10 days, CRIT at ≤5 days before the stored AUTOMERGE_PAT
    expiry, so the operator can mint a new PAT before dependabot merges
    quietly stop deploying."""
    import datetime

    expires = datetime.date.fromisoformat(GITHUB_PAT_EXPIRES)
    days = (expires - datetime.date.today()).days
    payload = {
        "days": days,
        "expires": GITHUB_PAT_EXPIRES,
        "warn_below": GITHUB_PAT_WARN_DAYS,
        "crit_below": GITHUB_PAT_CRIT_DAYS,
    }
    if days <= GITHUB_PAT_CRIT_DAYS:
        return (
            "CRIT",
            f"AUTOMERGE_PAT caduca en {days}d — renova'l JA "
            "(PAT + gh secret set + bump de GITHUB_PAT_EXPIRES).",
            payload,
        )
    if days <= GITHUB_PAT_WARN_DAYS:
        return (
            "WARN",
            f"AUTOMERGE_PAT caduca en {days}d — planifica la renovació.",
            payload,
        )
    return "OK", f"AUTOMERGE_PAT OK ({days}d fins l'expiració desada).", payload


# ── TLS certificate expiry ────────────────────────────────────────────
# Measured ON THE WIRE, never from a PEM on disk. The July 2026 incident
# is the whole reason this exists: /etc/stalwart/certs held a valid
# certificate from 26 June onwards while the mail server kept serving an
# April one that expired on 26 July. Any check that read the file would
# have reported healthy for a month. See
# `docs/archive/post-mortems/2026-07-26-stalwart-cert-expirat.md`.
#
# The connection deliberately does NOT verify the chain (CERT_NONE +
# check_hostname off). Verification raises on an expired certificate —
# precisely the case we exist to report — and we would then surface it
# as an unreachable endpoint instead of an expiry. So we take the peer
# certificate in DER form and read `notAfter` ourselves.
TLS_TIMEOUT_SECONDS = 5

# Ports where TLS is negotiated with STARTTLS rather than being implicit.
# 25 matters: it is the port that carries inbound mail.
_STARTTLS_SMTP_PORTS = {25, 587}


def _parse_tls_endpoints(raw: str) -> tuple[list[tuple[str, int]], list[str]]:
    """Split the `host:port` lines of `tls_endpoints_vigilats`.

    Returns `(endpoints, bad_lines)`. Blank lines and `#` comments are
    skipped so the operator can park a recommended endpoint in the field
    without enabling it. `rpartition` on the last colon keeps IPv6
    literals in brackets working.
    """
    endpoints: list[tuple[str, int]] = []
    bad: list[str] = []
    for line in (raw or "").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        host, sep, port = entry.rpartition(":")
        if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
            bad.append(entry)
            continue
        endpoints.append((host, int(port)))
    return endpoints, bad


def _fetch_peer_cert_der(host: str, port: int, timeout: float) -> bytes:
    """Open a TLS connection with explicit SNI; return the served cert (DER).

    Separated from `check_tls_certs` so tests can substitute it and run
    the real parsing path against a synthetic certificate, with no
    network in CI.
    """
    import socket
    import ssl

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if port in _STARTTLS_SMTP_PORTS:
        import smtplib

        with smtplib.SMTP(host, port, timeout=timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            der = smtp.sock.getpeercert(binary_form=True)
    else:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            # server_hostname is the SNI sent on the wire. A vhost that
            # serves several names returns the wrong certificate without it.
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                der = tls.getpeercert(binary_form=True)
    if not der:
        raise ValueError("the peer returned no certificate")
    return der


def _not_after_utc(der: bytes):
    """`notAfter` of a DER certificate, as an aware UTC datetime."""
    from cryptography import x509

    cert = x509.load_der_x509_certificate(der)
    try:
        return cert.not_valid_after_utc
    except AttributeError:  # pragma: no cover - cryptography < 42
        from datetime import timezone

        return cert.not_valid_after.replace(tzinfo=timezone.utc)


def check_tls_certs() -> tuple[Severity, str, dict]:
    """Report the expiry of the certificate each endpoint actually serves.

    Per-endpoint state is one of:

      * ``ok``       — more than `tls_avis_dies` days of runway
      * ``expiring`` — inside the threshold, or already past it
      * ``error``    — could not connect, handshake, or parse

    An unreachable endpoint is never reported as ``ok``, and one bad
    endpoint never stops the others from being measured. Severity is
    CRIT when something is already expired or unreachable (both mean the
    operator has to act now), WARN when something is merely approaching
    its threshold, OK otherwise.

    With no endpoints configured the check is a no-op that returns OK —
    the list ships empty on purpose, so deploying this changes nothing
    until the operator opts in.
    """
    from datetime import datetime, timezone

    try:
        from ranking.models import ConfiguracioGlobal
    except Exception as exc:  # noqa: BLE001
        return "CRIT", f"Django import failed: {exc}", {}

    config = ConfiguracioGlobal.load()
    warn_days = int(config.tls_avis_dies)
    endpoints, bad_lines = _parse_tls_endpoints(config.tls_endpoints_vigilats)

    if not endpoints and not bad_lines:
        return (
            "OK",
            "TLS: cap endpoint configurat.",
            {"endpoints": [], "warn_below": warn_days, "configured": False},
        )

    now = datetime.now(timezone.utc)
    results: list[dict] = []

    for entry in bad_lines:
        results.append(
            {
                "endpoint": entry,
                "state": "error",
                "days": None,
                "detail": "format invàlid, s'espera host:port",
            }
        )

    for host, port in endpoints:
        label = f"{host}:{port}"
        try:
            der = _fetch_peer_cert_der(host, port, TLS_TIMEOUT_SECONDS)
            not_after = _not_after_utc(der)
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad: socket, ssl, smtplib and the DER parser
            # raise from different hierarchies, and any of them means the
            # same operational thing — we could not measure this endpoint.
            results.append(
                {
                    "endpoint": label,
                    "state": "error",
                    "days": None,
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        days = (not_after - now).days
        results.append(
            {
                "endpoint": label,
                "state": "ok" if days > warn_days else "expiring",
                "days": days,
                "detail": not_after.strftime("%Y-%m-%d"),
            }
        )

    payload = {"endpoints": results, "warn_below": warn_days, "configured": True}
    errors = [r for r in results if r["state"] == "error"]
    expiring = [r for r in results if r["state"] == "expiring"]
    expired = [r for r in expiring if r["days"] is not None and r["days"] <= 0]

    if errors or expired:
        bits = []
        if expired:
            bits.append("caducat: " + ", ".join(r["endpoint"] for r in expired))
        if errors:
            bits.append("inabastable: " + ", ".join(r["endpoint"] for r in errors))
        return "CRIT", "TLS — " + "; ".join(bits) + ".", payload
    if expiring:
        bits = ", ".join(f"{r['endpoint']} ({r['days']}d)" for r in expiring)
        return "WARN", f"TLS caduca aviat: {bits}.", payload
    return (
        "OK",
        f"TLS OK ({len(results)} endpoints, llindar {warn_days}d).",
        payload,
    )


def main(argv: list[str]) -> int:
    """CLI dispatch so the bash wrappers can `python -m music.health <check>`.

    Exit codes match the bash convention used by the rest of
    `bin/tq-health`: 0=OK, 1=WARN, 2=CRIT.
    """
    checks = {
        "spotify_premium": check_spotify_premium,
        "spotify_coverage": check_spotify_coverage,
        "instagram_token": check_instagram_token,
        "github_pat": check_github_pat,
        "tls_certs": check_tls_certs,
    }
    if len(argv) < 2 or argv[1] not in checks:
        print("usage: python -m music.health {" + "|".join(checks) + "}")
        return 2

    import json

    import django

    django.setup()
    severity, message, payload = checks[argv[1]]()
    out = {"severity": severity, "message": message, "payload": payload}
    print(json.dumps(out))
    return {"OK": 0, "WARN": 1, "CRIT": 2}[severity]


if __name__ == "__main__":
    import os
    import sys

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "topquaranta.settings.production")
    sys.exit(main(sys.argv))
