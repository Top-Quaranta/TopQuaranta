from .base import *  # noqa: F401,F403

DEBUG = True
SECRET_KEY = "django-insecure-local-dev-key-do-not-use-in-production"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "topquaranta",
        "USER": "topquaranta",
        "PASSWORD": "topquaranta",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

ALLOWED_HOSTS = ["*"]

# Last.fm (for tests)
YOUTUBE_API_KEY = "test-key"
LASTFM_API_KEY = "test-key"
LASTFM_API_SECRET = ""

# Spotify (for tests)
SPOTIFY_CLIENT_ID = "test-client-id"
SPOTIFY_CLIENT_SECRET = "test-client-secret"
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8000/staff/social/spotify/callback"
