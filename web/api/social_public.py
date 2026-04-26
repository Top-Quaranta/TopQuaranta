"""Public render endpoint for Meta's image fetcher.

When `publicar_social` calls the Instagram Graph API, Meta needs to
download the rendered PNG by HTTP. The PNG lives at
`<SOCIAL_CACHE_DIR>/renders/`. Two ways we can expose it:

  a) A `handle_path /static/social/*` block in the Caddyfile —
     cleanest, but needs ops access to the server config.
  b) This Django view, mounted at `/api/v1/social/render/<file>`.
     No auth (Meta has no credentials with us), but the URL pattern
     is restricted to literal PNG filenames written by the renderer
     and the file is read from the controlled cache dir only.

We use (b) until (a) is in place; switching is one settings flip
(`SOCIAL_PUBLIC_BASE`).

The contents being served are by definition the same PNGs we'd
publish to Instagram immediately after — no privacy concern.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request

from web.api.staff.social import _serve_png


@api_view(["GET"])
@permission_classes([AllowAny])
def render_public(request: Request, filename: str):
    return _serve_png(filename)
