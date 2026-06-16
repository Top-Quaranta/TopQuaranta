"""Tests for referrer-source classification."""

from __future__ import annotations

import pytest

from analytics.referrers import classify_referrer

_OWN = "www.topquaranta.cat"


@pytest.mark.parametrize(
    "referer,expected_bucket,expected_host",
    [
        (None, "directe", ""),
        ("", "directe", ""),
        ("https://www.google.com/search?q=cat+music", "cerca_organica", "google.com"),
        ("https://www.google.es/", "cerca_organica", "google.es"),
        ("https://news.google.com/foo", "cerca_organica", "news.google.com"),
        ("https://duckduckgo.com/", "cerca_organica", "duckduckgo.com"),
        ("https://search.brave.com/search", "cerca_organica", "search.brave.com"),
        ("https://www.instagram.com/p/abc/", "social", "instagram.com"),
        ("https://t.co/xyz", "social", "t.co"),
        ("https://x.com/someone", "social", "x.com"),
        ("https://mastodon.social/@user", "social", "mastodon.social"),
        ("https://bsky.app/profile/x", "social", "bsky.app"),
        ("https://example.org/blog/post", "referral", "example.org"),
        # naive substring would mis-bucket this as t.co — must be referral
        ("https://client.com/page", "referral", "client.com"),
    ],
)
def test_classify_referrer_buckets(referer, expected_bucket, expected_host):
    bucket, host = classify_referrer(referer, _OWN)
    assert bucket == expected_bucket
    assert host == expected_host


@pytest.mark.parametrize(
    "referer",
    [
        "https://www.topquaranta.cat/top",
        "https://topquaranta.cat/artista/x",
        "https://mail.topquaranta.cat/inbox",
    ],
)
def test_in_site_referrer_is_intern(referer):
    bucket, _ = classify_referrer(referer, _OWN)
    assert bucket == "intern"


def test_host_strips_credentials_and_port():
    bucket, host = classify_referrer("https://user:pw@example.org:8443/x", _OWN)
    assert bucket == "referral"
    assert host == "example.org"
