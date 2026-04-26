import dj_database_url
from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = config("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())

DATABASES = {
    # P6: persistent connections. Without pooling, every request opens a
    # fresh psycopg2 connection (~5ms on localhost). `conn_max_age=600`
    # keeps the connection alive for up to 10 minutes per worker, and
    # `conn_health_checks=True` pings before reuse so a recycled-by-the-
    # server connection doesn't raise InterfaceError mid-request.
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
    ),
}

# Security
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Last.fm
LASTFM_API_KEY = config("LASTFM_API_KEY")
LASTFM_API_SECRET = config("LASTFM_API_SECRET", default="")

# Spotify. The client-credentials ingesta flow has been blocked since
# 2024, but playlist management via user OAuth still works fine (no
# Premium required). Used by the `actualitzar_playlists_spotify` cron
# to sync the public top-40 + novetats playlists.
SPOTIFY_CLIENT_ID = config("SPOTIFY_CLIENT_ID", default="")
SPOTIFY_CLIENT_SECRET = config("SPOTIFY_CLIENT_SECRET", default="")
# OAuth callback URL. The React SPA serves a tiny page at
# /spotify/callback that displays the `code` query param so the admin
# can copy it back into the `autoritzar_spotify` command. The URL
# must be registered exactly in the Spotify app dashboard's
# "Redirect URIs" list.
SPOTIFY_REDIRECT_URI = config(
    "SPOTIFY_REDIRECT_URI",
    default="https://www.topquaranta.cat/spotify/callback",
)

# SMTP via cdmon's Micropla (smtp.topquaranta.cat). Falls back to a
# file-based backend if EMAIL_HOST_PASSWORD is not set in .env, so dev
# or a freshly-cloned server doesn't raise on mail_admins().
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
if EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = config("EMAIL_HOST", default="smtp.topquaranta.cat")
    EMAIL_PORT = config("EMAIL_PORT", default=465, cast=int)
    EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=True, cast=bool)
    EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
    EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="noreply@topquaranta.cat")
    EMAIL_TIMEOUT = 20
else:
    EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    EMAIL_FILE_PATH = "/var/log/topquaranta/admin_mail"

# ── Sprint I: Instagram credentials ─────────────────────────────────────
# Empty token forces DRY_RUN in `ingesta.social.instagram_client`.
INSTAGRAM_ACCESS_TOKEN = config("INSTAGRAM_ACCESS_TOKEN", default="")
INSTAGRAM_USER_ID = config("INSTAGRAM_USER_ID", default="")
INSTAGRAM_TOKEN_EXPIRES_AT = config("INSTAGRAM_TOKEN_EXPIRES_AT", default="")
