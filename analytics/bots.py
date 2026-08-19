"""Canonical bot User-Agent markers (single source of truth in Python).

The reverse proxy (Caddy) routes known crawlers to the Django SSR path
via the `@bot` matcher in `deploy/Caddyfile`. That matcher is a
case-insensitive regex alternation over User-Agent substrings.

This module holds the SAME marker list in Python so the analytics
middleware can classify a pageview as "bot" or "human" at write time
WITHOUT storing the raw User-Agent (privacy posture: the UA is read
transiently, only its classification is persisted in `dimensio_2`).

A parity test (`analytics/tests/test_bots.py`) asserts this list stays
equivalent to the Caddyfile regex so the two never drift.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

# Lowercase substrings. Mirrors the alternation in
# `deploy/Caddyfile` (`@bot` matcher, header_regexp User-Agent).
# Regex escapes are unescaped here (`developers\.google\.com` ->
# `developers.google.com`); the matcher is substring/case-insensitive,
# so a lowercase `in` test is the faithful equivalent.
BOT_UA_MARKERS: tuple[str, ...] = (
    "googlebot",
    "google-inspectiontool",
    "google-richresultstest",
    "google-pagerenderer",
    "googleother",
    "adsbot-google",
    "bingbot",
    "bingpreview",
    "duckduckbot",
    "yandexbot",
    "applebot",
    "baiduspider",
    "slurp",
    "mastodon",
    "pleroma",
    "akkoma",
    "misskey",
    "bluesky",
    "slackbot",
    "telegrambot",
    "whatsapp",
    "facebookexternalhit",
    "twitterbot",
    "linkedinbot",
    "discordbot",
    "skypeuripreview",
    "gptbot",
    "claudebot",
    "perplexitybot",
    "bytespider",
    "amazonbot",
    "chatgpt-user",
    "cohere-ai",
    "anthropic-ai",
    "aria/",
    "ia_archiver",
    "petalbot",
    "seznambot",
    "vkshare",
    "w3c_validator",
    "developers.google.com",
)

# The two classification labels stored in `pageview.dimensio_2`.
CLASS_BOT = "bot"
CLASS_HUMAN = "human"


def classify_ua(user_agent: str | None) -> str:
    """Return `"bot"` if the User-Agent matches a known crawler marker,
    else `"human"`.

    Mirrors the Caddy `@bot` decision: a non-matching (or empty) UA is
    treated the same way Caddy treats it (served the SPA), i.e. "human".
    The UA string itself is never persisted by the caller.
    """
    ua = (user_agent or "").lower()
    if not ua:
        return CLASS_HUMAN
    for marker in BOT_UA_MARKERS:
        if marker in ua:
            return CLASS_BOT
    return CLASS_HUMAN
