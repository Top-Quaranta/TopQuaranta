"""Referrer-source classification for human pageviews.

The analytics middleware reads the inbound ``Referer`` header transiently
to answer one question — *where did this human come from?* — and stores
only the coarse bucket plus the bare referring host. The path and query
of the referer (where session tokens could leak) are **never** persisted,
which keeps this within the same privacy posture as the rest of
``analytics/`` (see the middleware docstring).

Buckets:
  * ``directe``        — no Referer header (typed URL, bookmark, app).
  * ``intern``         — referer is our own site (in-site navigation).
                         The middleware drops these: internal clicks are
                         not an acquisition source.
  * ``cerca_organica`` — a search engine (Google, Bing, DuckDuckGo, …).
  * ``social``         — a social network / messenger.
  * ``referral``       — any other external site.

Matching is host-label based (not naive substring) so a host like
``client.com`` is never misread as the ``t.co`` shortener.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Engine / network identifiers matched as a whole DNS label, so they hit
# every ccTLD (google.es, google.co.uk, …) and subdomain (news.google.com)
# without enumerating them, and never match a label substring.
_SEARCH_LABELS: frozenset[str] = frozenset(
    {
        "google",
        "bing",
        "duckduckgo",
        "yahoo",
        "yandex",
        "baidu",
        "ecosia",
        "qwant",
        "startpage",
        "kagi",
        "mojeek",
        "presearch",
        "searx",
        "aol",
        "ask",
        "brave",  # search.brave.com (brave.com referrers are negligible)
    }
)

_SOCIAL_LABELS: frozenset[str] = frozenset(
    {
        "facebook",
        "instagram",
        "twitter",
        "reddit",
        "linkedin",
        "youtube",
        "pinterest",
        "tumblr",
        "mastodon",
        "threads",
        "telegram",
        "tiktok",
        "snapchat",
        "bsky",
        "bluesky",
        "whatsapp",
    }
)

# Short hosts whose label set doesn't carry the network name.
_SOCIAL_HOSTS: frozenset[str] = frozenset(
    {
        "t.co",
        "x.com",
        "fb.com",
        "fb.me",
        "t.me",
        "youtu.be",
        "lnkd.in",
        "wa.me",
    }
)

_OWN_DOMAIN = "topquaranta.cat"


def _host_of(url: str) -> str:
    """Lowercase registrable host of `url`, sans credentials/port/`www.`."""
    netloc = urlsplit(url).netloc.lower()
    netloc = netloc.split("@")[-1].split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def classify_referrer(referer: str | None, own_host: str) -> tuple[str, str]:
    """Return ``(bucket, host)`` for an inbound Referer.

    `own_host` is `request.get_host()`; it's used to detect in-site
    navigation. `host` is the bare referring host (no path/query),
    or ``""`` for the ``directe`` bucket.
    """
    if not referer:
        return ("directe", "")
    host = _host_of(referer)
    if not host:
        return ("directe", "")

    own = own_host.lower().split(":")[0]
    if own.startswith("www."):
        own = own[4:]
    if host == own or host == _OWN_DOMAIN or host.endswith("." + _OWN_DOMAIN):
        return ("intern", host[:80])

    labels = set(host.split("."))
    if labels & _SEARCH_LABELS:
        return ("cerca_organica", host[:80])
    if host in _SOCIAL_HOSTS or (labels & _SOCIAL_LABELS):
        return ("social", host[:80])
    return ("referral", host[:80])
