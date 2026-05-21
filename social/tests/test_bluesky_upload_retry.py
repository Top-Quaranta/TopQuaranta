"""ADR-0005 — Bluesky `upload_blob` retry behaviour.

Three flavours covered: transient ReadTimeout retried until success;
HTTP 4xx propagated immediately (no retry); transient failures
exhausting the retry budget propagate after the last attempt.

Tests mock `requests.post` directly. The session-cache shortcut
(`_SESSIONS`) is also primed so we don't hit `createSession` during
the test (which would fail without a real BlueskyAuth row).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from social import bluesky_client


@pytest.fixture
def primed_session(tmp_path, monkeypatch):
    """Stub auth + session cache + dummy PNG payload.

    `is_dry_run()` returns True when no BlueskyAuth row is loaded; we
    force it to False here so the real upload_blob branch runs."""
    monkeypatch.setattr(bluesky_client, "is_dry_run", lambda: False)
    monkeypatch.setattr(
        bluesky_client, "_auth_headers", lambda: {"Authorization": "Bearer test"}
    )
    # Avoid sleeping inside back-off during tests.
    monkeypatch.setattr(bluesky_client.time, "sleep", lambda _s: None)
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic header is enough
    return png


class _R:
    """Minimal `requests.Response`-shaped stub."""

    def __init__(self, *, ok=True, status=200, body=None):
        self.ok = ok
        self.status_code = status
        self.text = "" if ok else "err"
        self._body = body or {"blob": {"$type": "blob", "ref": "ok"}}

    def json(self):
        return self._body


def test_bluesky_upload_retries_on_timeout(primed_session):
    """Two ReadTimeouts then a 200 → 3 calls total, success returned."""
    calls = []

    def fake_post(*a, **kw):
        calls.append(1)
        if len(calls) <= 2:
            raise requests.ReadTimeout("timeout")
        return _R()

    with patch.object(bluesky_client.requests, "post", side_effect=fake_post):
        blob = bluesky_client.upload_blob(primed_session)

    assert len(calls) == 3
    assert blob == {"$type": "blob", "ref": "ok"}


def test_bluesky_upload_no_retry_on_4xx(primed_session):
    """401 on first attempt → propagate immediately, only 1 call."""
    calls = []

    def fake_post(*a, **kw):
        calls.append(1)
        return _R(ok=False, status=401)

    with patch.object(bluesky_client.requests, "post", side_effect=fake_post):
        with pytest.raises(RuntimeError, match="401"):
            bluesky_client.upload_blob(primed_session)

    assert len(calls) == 1


def test_bluesky_upload_exhausted_propagates(primed_session):
    """Three consecutive ReadTimeouts → propagate after the 3rd."""
    calls = []

    def fake_post(*a, **kw):
        calls.append(1)
        raise requests.ReadTimeout("timeout")

    with patch.object(bluesky_client.requests, "post", side_effect=fake_post):
        with pytest.raises(requests.ReadTimeout):
            bluesky_client.upload_blob(primed_session)

    assert len(calls) == bluesky_client.BLUESKY_UPLOAD_RETRIES
