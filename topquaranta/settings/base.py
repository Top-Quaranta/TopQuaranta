from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    # Django
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",  # F3: /sitemap.xml generation
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "axes",  # S4: brute-force login protection
    "django_otp",  # S11: TOTP 2FA base
    "django_otp.plugins.otp_totp",  # S11: TOTP devices (Google Auth / Authy)
    "django_otp.plugins.otp_static",  # S11: single-use backup codes
    # Project apps
    "music",
    "ingesta",
    "ranking",
    "web",
    "comptes",
    "social",
    "analytics",
]

# Public-facing canonical URL for the SPA + API. Single source of
# truth for code that needs to build absolute URLs (newsletter
# unsubscribe links, JSON-LD `sameAs`, PSI URL probes, OG image
# defaults, etc.). May-2026 audit: was hardcoded across 12+ Python
# callsites — see web/seo/jsonld.py, comptes/newsletter.py,
# analytics/.../recollir_metrics_psi.py.
SITE_URL = "https://www.topquaranta.cat"

# Brand-owned profiles on third-party platforms. Consumed by the
# JSON-LD `Organization.sameAs` block (web/seo/jsonld.py) and any
# future "About / Contact" page that needs to surface them.
# Keep order stable: it determines the JSON output order (and any
# downstream caches that key on it).
SOCIAL_PROFILES = (
    "https://mastodont.cat/@topquaranta",
    "https://bsky.app/profile/topquaranta.bsky.social",
    "https://www.instagram.com/topquaranta/",
    "https://t.me/topquaranta",
)

# Sprint I — Instagram + cache directory for generated social
# assets. Persistent (survives reboots, unlike /tmp); falls back
# automatically to /tmp/tq_social if the path is unwriteable.
SOCIAL_CACHE_DIR = "/var/cache/topquaranta/social"

# Instagram credentials. Empty/test value forces DRY_RUN in the
# client (no real API calls; PNGs still rendered).
INSTAGRAM_ACCESS_TOKEN = ""
INSTAGRAM_USER_ID = ""
INSTAGRAM_TOKEN_EXPIRES_AT = ""

AUTH_USER_MODEL = "comptes.Usuari"

# Pseudo-user that fronts the staff inbox for community DMs. Any
# logged-in user can DM this account to reach the moderation team
# without having to find a specific staff user in the directory.
# Messages addressed to this username are fanned out by email to
# every active staff user (see `_enviar_notificacio_missatge`).
# The user itself is seeded by migration `comptes.0016_admin_pseudouser`
# with `is_staff=False` (a proxy, not a real admin), `is_active=True`,
# and a `PerfilUsuari` visible to the directory.
ADMIN_INBOX_USERNAME = "admin"

# S10: Argon2 is preferred; PBKDF2 variants retained so existing hashes
# continue to verify. Django rehashes to Argon2 on next successful login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# S4: django-axes authentication backend intercepts failed login attempts.
# Must be first in the list. ModelBackend stays after it for actual auth.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # S11: django-otp's middleware annotates request.user with .is_verified()
    # (True iff the user has successfully completed a 2FA challenge in this
    # session). Must be AFTER AuthenticationMiddleware.
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # S4: must come AFTER AuthenticationMiddleware so request.user is set.
    "axes.middleware.AxesMiddleware",
    # A8: stamp /api/vN/* responses with X-API-Version.
    "web.api.middleware.ApiVersionHeaderMiddleware",
    # K1: ethical aggregate analytics — pageviews + UTM landings.
    # No PII, no IP, no fingerprinting. Fail-open if anything raises.
    "analytics.middleware.AnalyticsMiddleware",
]

# S11: TOTP issuer shown in the user's authenticator app.
OTP_TOTP_ISSUER = "TopQuaranta"

# S4: django-axes configuration. Lock out after 5 failed attempts per
# (username, IP) tuple for 1 hour; after 10 attempts, lock for 24 hours.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hours for the first-tier lockout
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "web/403.html"

# S9: rate-limit public API. DRF applies these to every @api_view handler
# under /api/v1/*. Anonymous traffic is keyed by client IP; authenticated
# traffic by user ID. A scraper hammering /api/v1/mapa/artistes/ or the
# location endpoints now gets HTTP 429 after 60 requests in a minute.
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
        # ScopedRateThrottle scopes (May-2026 audit). Apply per
        # endpoint with `throttle_scope = "<scope>"` on the view.
        # Defends sensitive primitives from online guessing within
        # the axes brute-force window — axes only catches login
        # itself; 2FA-verify, unsubscribe and data-export weren't
        # protected against repeated requests from the same IP.
        "auth_login": "5/min",
        "auth_2fa": "10/min",
        "newsletter_unsubscribe": "10/min",
        "data_export": "3/hour",  # heavy email-generating endpoint
        # May-2026 audit follow-up. Protects authenticated mail-bombing
        # vectors and the registration mail-bomb (Brevo free tier is
        # 300/day; an attacker spraying registrations can burn it in
        # minutes). All scopes per-IP via ScopedRateThrottle.
        "registre": "5/hour",  # public, anti-mail-bomb on Brevo budget
        "feedback_crear": "30/hour",  # auth, anti-spam
        "account_delete": "3/hour",  # auth, anti-mail-bomb-the-user
        "dm_send": "20/hour",  # auth, anti-DM-flood + email-flood
    },
}

# DRF throttling stores counters in Django's cache. With 2 gunicorn
# workers a per-process LocMemCache would split the rate limit per
# worker (effectively doubling it). Use a PostgreSQL-backed cache so
# the counter is coherent across workers. Table created via
# `manage.py createcachetable django_cache`.
#
# P1: a SEPARATE `pagecache` alias (LocMem, per-worker) is used for
# HTML page caching of anonymous hits. Per-worker is fine here — a
# brief spike of cold requests hitting different workers merely warms
# the cache independently. Splitting the DB cache across workers for
# this would multiply DB writes unnecessarily.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    },
    "pagecache": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "topquaranta-pagecache",
        "TIMEOUT": 600,  # 10 minutes default; @cache_page overrides per view
    },
}

ROOT_URLCONF = "topquaranta.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "topquaranta.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ca"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    # A10: mm-design tokens are vendored into the repo at `vendor/mm-design/`
    # (committed). Previously this pointed to `node_modules/mm-design` which
    # was populated by `npm install` from a git dependency on
    # `github:miquelmatoses/mm-design` — fragile (deploys fail if the source
    # repo is unreachable). The vendored copy is frozen; refresh by copying
    # a new snapshot into vendor/ and committing.
    ("mm-design", BASE_DIR / "vendor" / "mm-design"),
]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django 6 accepts both `[(name, addr)]` and `[addr]`; Django 7
# drops the tuple form (RemovedInDjango70Warning). Use plain
# strings now so the future bump is a no-op.
ADMINS = ["admin@topquaranta.cat"]
DEFAULT_FROM_EMAIL = "noreply@topquaranta.cat"
SERVER_EMAIL = "noreply@topquaranta.cat"

_LOG_DIR = Path("/var/log/topquaranta")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        # All ERROR / CRITICAL log records across the project are appended to
        # a single file. Consumed by bin/tq-health.sh and the ops dashboard;
        # see docs/architecture/pipeline.md (monitoring section).
        "errors_file": {
            "class": "logging.FileHandler",
            "filename": str(_LOG_DIR / "errors.log"),
            "formatter": "verbose",
            "level": "ERROR",
            # delay=True means the file is not opened until first use; avoids
            # startup failures in environments where /var/log/topquaranta is
            # not writable (e.g. tests, CI).
            "delay": True,
        },
    },
    "root": {
        "handlers": ["console", "errors_file"],
        "level": "INFO",
    },
    "loggers": {
        "ingesta": {"level": "INFO"},
        "ranking": {"level": "INFO"},
    },
}
