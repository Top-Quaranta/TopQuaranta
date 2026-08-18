"""Shared utilities for the public REST surface.

Houses the page-cache helper for anonymous reads (`cache_for_anon`)
and the pagination helper (`paginate`). Use the cache helper on hot,
mostly-static read endpoints (ranking, directory, map) so a public
traffic spike doesn't translate 1:1 into Postgres queries.

Why "for anonymous": staff and logged-in users may be acting on the
same data (approving an artist, editing a song); they MUST see their
own edits reflected immediately. Anonymous users can tolerate up to
`timeout` seconds of staleness — well within the daily ranking
recalc cadence.

Companion: pair this with `django.views.decorators.http.condition`
for ETag + Last-Modified handling so a re-fetching client gets a
304 (no body) when the resource hasn't changed.
"""

from __future__ import annotations

import hashlib
from functools import wraps

from django.core.cache import caches
from django.core.paginator import Paginator
from django.http import HttpResponse
from rest_framework.throttling import SimpleRateThrottle


def paginate(qs, request, *, default: int = 20, cap: int = 100):
    """Return ``(page, meta)`` for a paginated queryset.

    Centralised May-2026 audit follow-up — the inline
    `min(int(request.GET.get("per_page") or N), MAX)` was duplicated
    across 6+ public endpoints (artistes, publicacions, perfil,
    moderació) and once again in the staff `_paginate`. One helper,
    one place to evolve the contract.

    Parameters
    ----------
    qs : QuerySet
        Queryset to paginate.
    request : DRF Request or HttpRequest
        Reads ``per_page`` and ``page`` from ``request.GET``.
    default : int
        Default page size when the client doesn't request one.
    cap : int
        Hard upper bound on ``per_page``. Public endpoints typically
        use 100; staff (which sees high-density admin tables) uses 200.

    Returns
    -------
    page : Page
        The requested page object — iterate to get its rows.
    meta : dict
        Pagination metadata ready to drop into the JSON response:
        ``page``, ``num_pages``, ``total``, ``per_page``,
        ``has_next``, ``has_previous``.
    """
    try:
        per_page = min(int(request.GET.get("per_page") or default), cap)
    except (TypeError, ValueError):
        per_page = default
    if per_page < 1:
        per_page = default
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(request.GET.get("page") or 1)
    return page, {
        "page": page.number,
        "num_pages": paginator.num_pages,
        "total": paginator.count,
        "per_page": per_page,
        "has_next": page.has_next(),
        "has_previous": page.has_previous(),
    }


def cache_for_anon(timeout: int, *, key_prefix: str = "anon"):
    """Decorator: cache the view's response in `pagecache` for
    `timeout` seconds when the request comes from an anonymous user.
    Authenticated requests skip the cache and always recompute.

    The decorator operates BELOW DRF's `@api_view` wrapper so the
    `request.user` attribute is the DRF `Request.user` (an
    `AnonymousUser` for unauth'd hits). On a miss we let the DRF
    Response complete the render pipeline first (the renderer is
    attached by `api_view` AFTER our wrapper returns), then store a
    plain `HttpResponse` of the rendered bytes — that's what we
    return verbatim on hits, with no further serialiser work.

    Cache key: SHA-1 of `<prefix>:<path>?<query_string>`.
    """
    pagecache = caches["pagecache"]

    def deco(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            qs = request.META.get("QUERY_STRING", "")
            raw_key = f"{key_prefix}:{request.path}?{qs}"
            key = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
            cached = pagecache.get(key)
            if cached is not None:
                return cached
            response = view_func(request, *args, **kwargs)
            # On the first hit DRF hasn't attached the renderer yet;
            # we mark the response with a post-render callback so the
            # plain HttpResponse we cache contains fully-baked bytes.
            if getattr(response, "status_code", 500) < 400 and hasattr(
                response, "add_post_render_callback"
            ):

                def _store(r, _key=key, _to=timeout):
                    plain = HttpResponse(
                        content=r.content,
                        status=r.status_code,
                        content_type=r.get("Content-Type", "application/json"),
                    )
                    pagecache.set(_key, plain, _to)
                    return r

                response.add_post_render_callback(_store)
            return response

        return wrapped

    return deco


class ScopedThrottle(SimpleRateThrottle):
    """A rate limit that reads its scope from the CLASS, not the view.

    DRF's own `ScopedRateThrottle` looks the scope up on the *view*
    (`view.throttle_scope`) and **allows the request unconditionally when
    it is missing**:

        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return True

    Every throttle in this project was declared as a `ScopedRateThrottle`
    subclass setting `scope = "..."`, which that method overwrites on each
    call. No view ever set `throttle_scope`, so all six limits — login,
    data export, newsletter unsubscribe, feedback, account deletion, DM
    sending — returned True and rate-limited nothing at all from the day
    they were added (May-2026 audit; found 2026-08-15). They were wired
    up, invoked on every request, and inert.

    Attaching `throttle_scope` to a function-based `@api_view` is awkward
    (the decorator wraps it in a generated class), so the scope stays on
    the throttle, where the declaration already lived. Cache key mirrors
    DRF's: per user when authenticated, per IP otherwise.
    """

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
