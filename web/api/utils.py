"""Shared utilities for the public REST surface.

Currently houses the page-cache helper for anonymous reads. Use it
on hot, mostly-static read endpoints (ranking, directory, map) so a
public traffic spike doesn't translate 1:1 into Postgres queries.

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
from django.http import HttpResponse


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
