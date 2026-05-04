"""
Settings for the public web server (port 8083).
Inherits production settings without FORCE_SCRIPT_NAME.
"""

from .production import *  # noqa: F401,F403

# Caddy terminates TLS and proxies HTTP internally to gunicorn :8083.
# We trust Caddy's `X-Forwarded-Proto` header so Django knows the
# original scheme — without this, `request.is_secure()` would be
# False and `*_COOKIE_SECURE` would refuse to set the cookies.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # Caddy already redirects http→https on the apex

# Cookies: now safe to require Secure because we know the original
# request was HTTPS. Closes the May-2026 audit critical (a downgraded
# HTTP request could otherwise capture session/CSRF cookies).
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS at the Django layer too (1 year, preload-eligible). Caddy
# already sets it on the apex; this duplicates on every API response
# so a sub-resource path can't slip past.
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

ALLOWED_HOSTS = ["www.topquaranta.cat", "topquaranta.cat", "127.0.0.1"]

STATIC_URL = "/static/"

# Public URL prefix used when handing PNG paths to Meta's media
# fetcher (carousel item upload). Caddy serves `/static/social/*`
# from `/var/cache/topquaranta/social/renders/` as plain static
# files — bypassing Django avoids the CSP/COOP/Vary headers that
# Meta's fetcher rejects with code 9004 ("Only photo or video can
# be accepted as media type"). Switch back to the Django view at
# `/api/v1/social/render` only if Caddy is unavailable.
SOCIAL_PUBLIC_BASE = "https://www.topquaranta.cat/static/social"
