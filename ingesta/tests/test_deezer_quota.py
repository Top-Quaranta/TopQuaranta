"""Deezer's quota flag — the half of `_get` nobody exercised.

The audit of 2026-08-15 disabled `_quota_exhausted` entirely and not one
of the 18 Deezer tests noticed: they all mock `_get` itself, so retries,
error code 4 and the session-wide latch had zero coverage.

It matters because of the shape of the failure, which is the same one
that cost us 27 artists on the YouTube side two days earlier: `_get`
returns the **same `None`** for "quota exhausted", "API error" and "this
artist doesn't exist". Callers that read `None` as "not found" then write
that non-answer into the database as a fact. The flag is what stops a
dead quota from being re-asked — and re-misread — thousands of times in
one run.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ingesta.clients import deezer


@pytest.fixture(autouse=True)
def _reset_flag():
    """Module-level latch: without this, one test's quota death would
    silently make every later test's request a no-op."""
    deezer._quota_exhausted = False
    yield
    deezer._quota_exhausted = False


def _resposta(payload):
    class _R:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return payload

    return _R()


@pytest.mark.django_db
def test_error_code_4_latches_the_quota_flag():
    quota = _resposta({"error": {"code": 4, "message": "Quota limit exceeded"}})
    with (
        patch("ingesta.clients.deezer.requests.get", return_value=quota),
        patch("ingesta.clients.deezer.time.sleep"),
    ):
        assert deezer._get("https://api.deezer.com/artist/1") is None
    assert deezer.quota_exhausted() is True


@pytest.mark.django_db
def test_once_the_quota_is_gone_no_further_request_is_made():
    """The whole point of the latch: a run that keeps asking would spend
    thousands of calls collecting `None`s and writing them down as
    answers."""
    quota = _resposta({"error": {"code": 4, "message": "Quota limit exceeded"}})
    with (
        patch("ingesta.clients.deezer.requests.get", return_value=quota) as g,
        patch("ingesta.clients.deezer.time.sleep"),
    ):
        deezer._get("https://api.deezer.com/artist/1")
        for _ in range(5):
            deezer._get("https://api.deezer.com/artist/2")
        assert g.call_count == 1, g.call_count


@pytest.mark.django_db
def test_an_ordinary_api_error_does_not_latch_the_flag():
    """Only the quota codes stop the run. A per-resource error must not
    blind us to the rest of the catalogue."""
    fallada = _resposta({"error": {"code": 800, "message": "no data"}})
    with (
        patch("ingesta.clients.deezer.requests.get", return_value=fallada),
        patch("ingesta.clients.deezer.time.sleep"),
    ):
        assert deezer._get("https://api.deezer.com/artist/1") is None
    assert deezer.quota_exhausted() is False


@pytest.mark.django_db
def test_a_transport_failure_is_retried_then_gives_up():
    """Network flakiness is not quota death: retry, then return None with
    the flag untouched so the next artist is still attempted."""
    import requests as _req

    with (
        patch(
            "ingesta.clients.deezer.requests.get",
            side_effect=_req.RequestException("boom"),
        ) as g,
        patch("ingesta.clients.deezer.time.sleep"),
    ):
        assert deezer._get("https://api.deezer.com/artist/1") is None
        assert g.call_count == deezer.MAX_RETRIES, g.call_count
    assert deezer.quota_exhausted() is False


@pytest.mark.django_db
def test_a_good_response_comes_back_intact():
    with (
        patch(
            "ingesta.clients.deezer.requests.get",
            return_value=_resposta({"id": 7, "name": "Auxili"}),
        ),
        patch("ingesta.clients.deezer.time.sleep"),
    ):
        assert deezer._get("https://api.deezer.com/artist/7") == {
            "id": 7,
            "name": "Auxili",
        }
    assert deezer.quota_exhausted() is False
