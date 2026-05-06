"""Template tags for SEO templates."""

import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="safe_json")
def safe_json(value):
    """Render a Python dict as a JSON string safe to embed inside
    a `<script type="application/ml+json">` tag — escapes the
    closing `</script>` sequence so a malicious string field can't
    break out, escapes `<` and `>` as Unicode escapes which JSON
    parsers accept fine.

    Equivalent to Django's built-in `json_script` but inline (no
    wrapper element) since the schema.org spec wants the JSON
    inside a typed script tag we emit ourselves.
    """
    txt = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    txt = txt.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(txt)


@register.filter(name="rel_url")
def rel_url(absolute_url):
    """Strip protocol+host from a canonical absolute URL — used in
    breadcrumbs etc. when we want the path-only form."""
    if not absolute_url:
        return ""
    for prefix in ("https://www.topquaranta.cat", "http://www.topquaranta.cat"):
        if absolute_url.startswith(prefix):
            return absolute_url[len(prefix) :] or "/"
    return absolute_url
