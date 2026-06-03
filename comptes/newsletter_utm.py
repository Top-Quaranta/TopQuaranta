"""UTM helper for the weekly newsletter (Step 2).

Every link in the email body goes through `build_newsletter_url` so the
analytics dashboard can attribute landings to a specific block
(`utm_content`). The campaign is the project-week-based global campaign
(one newsletter per week, Global edition — no territorial versions).

    utm_source   = newsletter
    utm_medium   = email
    utm_campaign = top_<setmana>_global
    utm_content  = <block>  (podi_1, top_4, cta_top, territorial_cat,
                             novetat_1, compartir_telegram, …)
"""

from __future__ import annotations

from urllib.parse import urlencode, urlparse


def build_newsletter_url(base_url: str, content: str, setmana: int) -> str:
    """Append the four newsletter UTM params to `base_url`.

    `setmana` is the project-week number; `content` is the block slug
    that fired the click. The separator is `?` when the base already has
    a path and `/?` for a bare host, mirroring `social.captions.utm_url`
    so the trailing slash on the home route stays clean."""
    params = urlencode(
        {
            "utm_source": "newsletter",
            "utm_medium": "email",
            "utm_campaign": f"top_{setmana}_global",
            "utm_content": content,
        }
    )
    parsed = urlparse(base_url)
    sep = "?" if parsed.path and parsed.path != "/" else "/?"
    return f"{base_url.rstrip('/')}{sep}{params}"
