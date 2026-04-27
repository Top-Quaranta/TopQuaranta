"""
Settings for the public web server (port 8083).
Inherits production settings without FORCE_SCRIPT_NAME.
"""

from .production import *  # noqa: F401,F403

# Caddy terminates TLS and proxies HTTP internally
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

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
