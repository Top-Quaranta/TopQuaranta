"""Pageview + UTM-landing middleware.

What we measure:
  * `pageview` for every successful (2xx/3xx) GET on a public
    SPA route — `dim1` is the path. We *don't* count API calls,
    static assets, /staff/* (low-volume + irrelevant), HEAD or
    OPTIONS. Bots are not filtered here (left to GoAccess on Caddy
    logs); the public-route filter alone keeps noise low.
  * `utm_landing` when the request URL carries `?utm_source=…` —
    `dim1` is the source, `dim2` is the campaign. Each user lands
    once per campaign per session for our purposes; we count every
    landing because the alternative (set a cookie) is too close to
    individual tracking for the privacy posture.
  * `referrer` for every *human* public pageview — `dim1` is the
    acquisition bucket (directe / cerca_organica / social / referral),
    `dim2` is the bare referring host. Answers "where do humans come
    from?" without UTM tags. See `analytics/referrers.py`.

What we deliberately don't capture:
  * IP address (neither stored nor hashed).
  * User-Agent string (could fingerprint). The UA is read transiently
    to classify a pageview as "bot" | "human" (`dimensio_2`), but the
    string itself is never persisted. See `analytics/bots.py`.
  * Referer path or query. The Referer header is read transiently to
    classify the acquisition source; only the coarse bucket + bare host
    are stored. The path/query (where tokens could leak) are dropped,
    and in-site (`intern`) referrers are not recorded at all. See
    `analytics/referrers.py`.
  * `request.user.pk` (no per-user paths).

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

from analytics.bots import CLASS_HUMAN, classify_ua
from analytics.events import register
from analytics.referrers import classify_referrer

# Path prefixes we never count. The SPA serves /staff/* internally
# but it's a tiny audience and the data would skew the public
# pageview totals.
_SKIP_PREFIXES = (
    "/api/",
    "/static/",
    "/media/",
    "/favicon",
    "/robots.txt",
    # "/sitemap" and not "/sitemap.xml": the index is at that exact path
    # but the real ones are "/sitemap-artistes.xml", "/sitemap-cancons.xml"
    # …, and a dot is not a dash. They were counted as pageviews, and
    # because a crawler whose UA we don't know is classified "human",
    # they became the entire "top human pages" list in the weekly digest
    # (2026-08-17). A sitemap is a machine endpoint; it is never a visit.
    "/sitemap",
    "/staff/",
    "/compte/2fa/",  # auth screens, low value, sensitive
    "/health",
)


def _is_public_pageview(request) -> bool:
    if request.method not in ("GET", "HEAD"):
        return False
    path = request.path or "/"
    for p in _SKIP_PREFIXES:
        if path.startswith(p):
            return False
    return True


class AnalyticsMiddleware:
    """Lightweight middleware: counts pageviews + UTM landings.

    Hooks the *response* phase so we only count requests that
    actually got a 2xx/3xx (skip 404/500 — broken paths shouldn't
    inflate "page X is popular").
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._record(request, response)
        except Exception:
            # Analytics MUST NOT break the response. `register()` is
            # itself fail-open, but the path-extraction logic could
            # in theory raise — guard it too.
            pass
        return response

    def _record(self, request, response) -> None:
        status = getattr(response, "status_code", 0)
        if status < 200 or status >= 400:
            return

        # Pageview
        if _is_public_pageview(request):
            # Path is bounded by url length (Django caps at ~2 KB),
            # but our `dimensio_1` is 80 chars — truncate. Anything
            # above 80 is almost certainly a tracker URL or attack
            # noise; the truncation merges them into one bucket which
            # is fine for trend lines.
            #
            # `dimensio_2` carries the bot/human classification derived
            # from the User-Agent (the UA itself is NOT stored). Rows
            # written before this slice have an empty dim2 and stay
            # "unclassified" — that's correct, not reclassifiable.
            kind = classify_ua(request.META.get("HTTP_USER_AGENT", ""))
            register("pageview", dim1=(request.path or "/")[:80], dim2=kind)

            # Acquisition source — humans only (bots carry preview-fetch
            # referers that aren't real visits). `intern` (in-site
            # navigation) is not an acquisition source, so it's dropped.
            if kind == CLASS_HUMAN:
                bucket, host = classify_referrer(
                    request.META.get("HTTP_REFERER"), request.get_host()
                )
                if bucket != "intern":
                    register("referrer", dim1=bucket, dim2=host[:80])

        # UTM landing — captured even on auth/staff URLs because
        # what we care about is "where did the click come from",
        # not where it landed.
        utm_source = (request.GET.get("utm_source") or "").strip().lower()
        if utm_source:
            campaign = (request.GET.get("utm_campaign") or "").strip().lower()
            register("utm_landing", dim1=utm_source[:80], dim2=campaign[:80])
