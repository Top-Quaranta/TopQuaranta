"""Analytics app — ethical, aggregate-only metrics.

See docs/architecture/analytics.md for the design and what we
deliberately don't measure (no per-user tracking, no IP storage,
no third-party JS, no fingerprinting).
"""

from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    name = "analytics"
    default_auto_field = "django.db.models.BigAutoField"
