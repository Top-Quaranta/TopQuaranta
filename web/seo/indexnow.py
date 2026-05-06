"""IndexNow protocol — push freshly published/updated URLs to Bing
and Yandex (and any participating engine) so they recrawl within
hours instead of days.

Spec: https://www.indexnow.org/documentation

Verification: a key file lives at `/<KEY>.txt` containing the same
key string. We commit the key + serve it via Django so search
engines can verify ownership. The file's URL must match the host
we're submitting URLs for.

Usage:
    from web.seo.indexnow import notify_url, notify_artista
    notify_artista(artista_instance)
    notify_url("https://www.topquaranta.cat/canco/foo")

Calls are fire-and-forget — failures are logged but never propagate.
A real outage at Bing won't block our `aprovar_artista` flow.
"""

from __future__ import annotations

import logging
from typing import Iterable

import requests

from music.models import Album, Artista, Canco

logger = logging.getLogger(__name__)

# 32-char hex key. Generated 2026-05-06 — committed at
# `web/static/seo/<KEY>.txt` (and `staticfiles/seo/...` after
# collectstatic) so Bing/Yandex can verify ownership.
INDEXNOW_KEY = "8f4c2e5b3a9d7c1f6e0b8a5d4c2e9f7b"

HOST = "www.topquaranta.cat"

# Bing's endpoint accepts a single URL (GET) or a batch (POST).
# Yandex / Naver / Seznam pull from Bing's endpoint via the
# IndexNow consortium.
SUBMIT_ENDPOINT = "https://api.indexnow.org/indexnow"
TIMEOUT = 10


def _submit(urls: list[str]) -> None:
    """POST one batch up to 10 000 URLs. Always called fire-and-forget."""
    if not urls:
        return
    payload = {
        "host": HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{HOST}/{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }
    try:
        r = requests.post(SUBMIT_ENDPOINT, json=payload, timeout=TIMEOUT)
        if r.status_code in (200, 202):
            logger.info(
                "indexnow: pushed %d URLs (status=%s)", len(urls), r.status_code
            )
        else:
            logger.warning(
                "indexnow: unexpected status %s for %d URLs (body: %s)",
                r.status_code,
                len(urls),
                r.text[:200],
            )
    except requests.RequestException as exc:
        # Network issues etc. Never blocks the calling flow.
        logger.warning("indexnow: submit failed: %s", exc)


def notify_url(url: str) -> None:
    """Push a single URL. Validates it points at our host."""
    if not url.startswith(f"https://{HOST}/"):
        logger.warning("indexnow: refusing to push foreign URL %s", url)
        return
    _submit([url])


def notify_urls(urls: Iterable[str]) -> None:
    """Batch push (deduped + filtered to our host)."""
    seen = set()
    out = []
    for u in urls:
        if u.startswith(f"https://{HOST}/") and u not in seen:
            seen.add(u)
            out.append(u)
    if out:
        _submit(out)


# ── Convenience wrappers per entity ────────────────────────────────


def notify_artista(a: Artista) -> None:
    """Called from the staff approval flow + the Artista save signal
    when `aprovat` flips to True. Pushes both the artist page and
    every page that links to it (their albums + recent cançons)
    so Google's link graph sees the freshness."""
    if not a.aprovat:
        return
    urls = [f"https://{HOST}/artista/{a.slug}"]
    urls += [
        f"https://{HOST}/album/{al.slug}"
        for al in Album.objects.filter(artista=a, descartat=False).only("slug")[:25]
    ]
    urls += [
        f"https://{HOST}/canco/{c.slug}"
        for c in Canco.objects.filter(artista=a, verificada=True, activa=True).only(
            "slug"
        )[:25]
    ]
    notify_urls(urls)


def notify_album(al: Album) -> None:
    if al.descartat or not al.artista.aprovat:
        return
    notify_url(f"https://{HOST}/album/{al.slug}")


def notify_canco(c: Canco) -> None:
    if not (c.verificada and c.activa):
        return
    notify_url(f"https://{HOST}/canco/{c.slug}")
