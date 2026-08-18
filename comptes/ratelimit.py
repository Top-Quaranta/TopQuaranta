"""A rate limiter for plain Django views.

DRF's throttles only reach DRF views. The 2FA challenge
(`comptes.views.dos_fa_verificar`) is a plain Django view, so the
`auth_2fa` rate configured back in the May-2026 audit could never apply
to it — the one screen that accepts **single-use backup codes in a loop**
was the one with no limit on guessing (found 2026-08-15).

Fixed window, per identity, counted in the shared cache. The `default`
cache is PostgreSQL-backed precisely so the counter is coherent across
gunicorn workers; a per-process cache would multiply every limit by the
worker count.

Rates are read from the same `DEFAULT_THROTTLE_RATES` map the DRF
throttles use, so there is one place to change a number.

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_PERIODS = {"s": 1, "min": 60, "hour": 3600, "day": 86400}


def _rate(scope: str) -> tuple[int, int] | None:
    """`("10/min")` → `(10, 60)`. None when the scope has no rate, which
    means "don't limit" rather than "limit to zero"."""
    raw = (settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES") or {}).get(scope)
    if not raw:
        return None
    try:
        num, _, period = raw.partition("/")
        return int(num), _PERIODS[period]
    except (ValueError, KeyError):
        logger.error("Rate mal format per a l'scope %s: %r", scope, raw)
        return None


def _ident(request) -> str:
    """Who we are counting.

    For 2FA the session already exists — the whole point of the screen is
    that the person has passed the password and not the second factor —
    so the user is the meaningful identity: someone with a stolen cookie
    is one user however many IPs they rotate through. Falls back to the
    IP when there is no user.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return f"u{user.pk}"
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")
    return f"ip{ip}"


def excedeix_limit(request, scope: str) -> bool:
    """True when this request is over the limit and must be refused.

    Fails **open** on a cache error: a broken cache must not lock people
    out of their own account. That is the right trade here — the password
    is still required to reach this screen at all — but it does mean the
    limiter is only as available as the cache.
    """
    conf = _rate(scope)
    if conf is None:
        return False
    limit, finestra = conf
    clau = f"tq-rl:{scope}:{_ident(request)}"
    try:
        cache.add(clau, 0, timeout=finestra)
        n = cache.incr(clau)
    except ValueError:
        # The window expired between `add` and `incr`; start a new one.
        cache.set(clau, 1, timeout=finestra)
        n = 1
    except Exception:  # pragma: no cover — cache backend down
        logger.exception("Limitador %s inoperant; deixe passar la petició", scope)
        return False
    if n > limit:
        logger.warning("Límit %s superat per %s (%d)", scope, _ident(request), n)
        return True
    return False
