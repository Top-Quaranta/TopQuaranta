"""Template filters for the weekly digest email.

Kept local to `analytics/` so the digest template renders without
enabling project-wide `USE_THOUSAND_SEPARATOR` (which would change
number formatting everywhere).
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def milers(value):
    """Group an int with Catalan thousands separators (4812 → 4.812).

    Non-int values (floats, strings, None) pass through untouched —
    Django's L10N already renders floats with the Catalan decimal comma,
    and pre-formatted strings (e.g. a "%" suffix carrier) stay as-is.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return value
    return f"{value:,}".replace(",", ".")
