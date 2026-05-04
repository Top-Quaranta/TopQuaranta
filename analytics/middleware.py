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

What we deliberately don't capture:
  * IP address (neither stored nor hashed).
  * User-Agent string (could fingerprint).
  * Referer (could leak inbound URLs that contain tokens).
  * `request.user.pk` (no per-user paths).
"""

from __future__ import annotations

from analytics.events import register

# Path prefixes we never count. The SPA serves /staff/* internally
# but it's a tiny audience and the data would skew the public
# pageview totals.
_SKIP_PREFIXES = (
    "/api/",
    "/static/",
    "/media/",
    "/favicon",
    "/robots.txt",
    "/sitemap.xml",
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
            register("pageview", dim1=(request.path or "/")[:80])

        # UTM landing — captured even on auth/staff URLs because
        # what we care about is "where did the click come from",
        # not where it landed.
        utm_source = (request.GET.get("utm_source") or "").strip().lower()
        if utm_source:
            campaign = (request.GET.get("utm_campaign") or "").strip().lower()
            register("utm_landing", dim1=utm_source[:80], dim2=campaign[:80])
