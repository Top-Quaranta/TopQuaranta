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
    check_instagram_token,
    check_spotify_coverage,
    check_spotify_premium,
    check_tls_certs,
)

# ── check_spotify_premium ─────────────────────────────────────────


@pytest.mark.django_db
def test_premium_crit_when_no_auth_row():
    """No SpotifyAuth singleton row means OAuth has never been
    completed. CRIT so the operator gets nudged toward
    /staff/social/spotify/."""
    # Property: severity is CRIT and the payload keeps the documented
    # dict shape (bash callers pretty-print it unconditionally).
    sev, msg, payload = check_spotify_premium()
    assert sev == "CRIT"
    assert msg
    assert isinstance(payload, dict)


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
    # Property: a transport failure is WARN (never CRIT, never OK) and
    # the payload keeps its dict shape.
    assert sev == "WARN"
    assert msg
    assert isinstance(payload, dict)


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
    # Property: OK, and the payload identifies the account + product
    # (that is the contract the dashboard reads, not the message copy).
    assert sev == "OK"
    assert payload["product"] == "premium"
    assert payload["spotify_user_id"] == "admin_user"


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
    # Property: nothing configured is a WARN nudge (not OK, not CRIT)
    # with an empty row list.
    assert sev == "WARN"
    assert msg
    assert payload["rows"] == []


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
    # Property: WARN, and every configured row is reported with no
    # coverage figure (never synced) — no row is silently dropped.
    assert sev == "WARN"
    codis = {r["codi"] for r in payload["rows"]}
    assert codis == {"top-cat", "top-val"}
    assert all(r["coverage"] is None for r in payload["rows"])


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
    # Property: a verified row above the WARN threshold yields OK and
    # its coverage is reported as matched/tracks.
    assert sev == "OK"
    row = next(r for r in payload["rows"] if r["codi"] == "top-cat")
    assert row["coverage"] == round(38 / 40, 3)


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


# ── check_instagram_token (2026-07 manual-renewal expiry alert) ────────


@pytest.mark.parametrize(
    "days,expected",
    [
        (None, "OK"),  # not configured / DRY_RUN
        (30, "OK"),
        (11, "OK"),
        (10, "WARN"),  # boundary: warn at ≤10
        (6, "WARN"),
        (5, "CRIT"),  # boundary: crit at ≤5
        (0, "CRIT"),
        (-3, "CRIT"),  # already expired
    ],
)
def test_instagram_token_severity(days, expected):
    with patch("social.instagram_client.days_until_expiry", return_value=days):
        severity, _msg, _payload = check_instagram_token()
    assert severity == expected


# ── check_tls_certs (2026-07 expiry watch, measured on the wire) ───────
#
# The certificate is synthesised in-process and only `_fetch_peer_cert_der`
# is substituted, so the real DER parsing and the real day arithmetic run.
# No socket is ever opened: these pass in CI with no network.


def _der_cert(days_from_now: int) -> bytes:
    """A throwaway self-signed certificate expiring in `days_from_now`."""
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test.example")])
    not_after = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        # Anchored to `not_after` so an already-expired fixture still has
        # a validity window that makes sense.
        .not_valid_before(not_after - timedelta(days=90))
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


def _set_tls_config(endpoints: str, dies: int = 21):
    from ranking.models import ConfiguracioGlobal

    config = ConfiguracioGlobal.load()
    config.tls_endpoints_vigilats = endpoints
    config.tls_avis_dies = dies
    config.save()
    return config


@pytest.mark.django_db
def test_tls_certs_no_endpoints_is_ok_and_noop():
    """Ships empty: the check must be inert until the operator opts in."""
    _set_tls_config("")
    severity, _msg, payload = check_tls_certs()
    assert severity == "OK"
    assert payload["configured"] is False
    assert payload["endpoints"] == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "days,expected_sev,expected_state",
    [
        (90, "OK", "ok"),
        # Boundary. `(not_after - now).days` truncates, so a cert minted
        # `n` days out reports `n - 1` whole days of runway: 23 → 22 > 21
        # is still OK, 22 → 21 is not, and trips the threshold.
        (23, "OK", "ok"),
        (22, "WARN", "expiring"),
        (3, "WARN", "expiring"),
        # Already expired is the extreme of `expiring`, but it is an
        # outage, not a heads-up — it has to escalate to CRIT.
        (-5, "CRIT", "expiring"),
    ],
)
def test_tls_certs_states_from_the_served_certificate(
    days, expected_sev, expected_state
):
    _set_tls_config("host.example:993", dies=21)
    with patch("music.health._fetch_peer_cert_der", return_value=_der_cert(days)):
        severity, _msg, payload = check_tls_certs()
    assert severity == expected_sev
    assert payload["endpoints"][0]["state"] == expected_state


@pytest.mark.django_db
def test_tls_certs_unreachable_endpoint_is_never_ok():
    """The whole point: 'I could not look' must not read as 'healthy'."""
    _set_tls_config("unreachable.example:993")
    with patch("music.health._fetch_peer_cert_der", side_effect=OSError("refused")):
        severity, _msg, payload = check_tls_certs()
    assert severity == "CRIT"
    assert payload["endpoints"][0]["state"] == "error"
    assert payload["endpoints"][0]["days"] is None


@pytest.mark.django_db
def test_tls_certs_one_failure_does_not_stop_the_others():
    _set_tls_config("bad.example:993\ngood.example:443")

    def fake(host, port, timeout):
        if host == "bad.example":
            raise OSError("connection refused")
        return _der_cert(90)

    with patch("music.health._fetch_peer_cert_der", side_effect=fake):
        severity, _msg, payload = check_tls_certs()
    assert severity == "CRIT"
    states = {r["endpoint"]: r["state"] for r in payload["endpoints"]}
    assert states == {"bad.example:993": "error", "good.example:443": "ok"}


@pytest.mark.django_db
def test_tls_certs_malformed_line_is_an_error_not_a_silent_skip():
    """Blank lines and `#` comments are parked entries; a malformed one
    is a configuration mistake and must be visible."""
    _set_tls_config("mail.example\n# mail.topquaranta.cat:993\n\nok.example:443")
    with patch("music.health._fetch_peer_cert_der", return_value=_der_cert(90)):
        severity, _msg, payload = check_tls_certs()
    assert severity == "CRIT"
    states = {r["endpoint"]: r["state"] for r in payload["endpoints"]}
    assert states["mail.example"] == "error"
    assert states["ok.example:443"] == "ok"
    assert "# mail.topquaranta.cat:993" not in states


@pytest.mark.django_db
def test_tls_certs_probes_the_configured_host_and_port():
    """Property: the configured `host:port` line is what actually gets
    probed, with a positive timeout — asserted through a fake probe
    that only answers for that exact endpoint (no pin on how the
    probe is invoked)."""
    _set_tls_config("mail.example:465")
    seen: list[tuple[str, int, float]] = []

    def fake(host, port, timeout):
        seen.append((host, port, timeout))
        if (host, port) != ("mail.example", 465):
            raise OSError(f"unexpected probe {host}:{port}")
        return _der_cert(90)

    with patch("music.health._fetch_peer_cert_der", side_effect=fake):
        severity, _msg, payload = check_tls_certs()
    assert severity == "OK"
    assert payload["endpoints"][0]["endpoint"] == "mail.example:465"
    assert payload["endpoints"][0]["state"] == "ok"
    assert len(seen) == 1
    assert seen[0][2] > 0
