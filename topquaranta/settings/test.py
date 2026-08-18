from .base import *  # noqa: F401,F403

DEBUG = True
SECRET_KEY = "django-insecure-test-key-do-not-use-in-production"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

ALLOWED_HOSTS = ["*"]

# API keys for tests (mocked, never called for real)
SPOTIFY_CLIENT_ID = "test-spotify-id"
SPOTIFY_CLIENT_SECRET = "test-spotify-secret"
SPOTIFY_REDIRECT_URI = "http://testserver/staff/social/spotify/callback"
YOUTUBE_API_KEY = "test-youtube-key"
LASTFM_API_KEY = "test-lastfm-key"
LASTFM_API_SECRET = "test-lastfm-secret"

# Keep ERROR records out of /var/log/topquaranta/errors.log during tests —
# that file is consumed by the ops health check (tq-health).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"], "level": "CRITICAL"},
}
