"""ConfiguracioGlobal toggles for the social pipeline:
per-channel kill switches, distribution phase, story cap."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from ranking.models import ConfiguracioGlobal
from web.api.staff._common import IsStaff


@api_view(["POST"])
@permission_classes([IsStaff])
def social_toggle(request: Request) -> Response:
    """Flip a per-channel kill switch.

    Accepts an optional `channel` to target a specific switch
    (`instagram` | `mastodon` | `bluesky` | `newsletter` | `rss`).
    Default is `instagram` for backward-compat with the old UI
    button that didn't pass a channel.
    """
    field_map = {
        "instagram": "instagram_actiu",
        "mastodon": "mastodon_actiu",
        "bluesky": "bluesky_actiu",
        "telegram": "telegram_actiu",
        "newsletter": "newsletter_actiu",
        "rss": "rss_actiu",
    }
    channel = (request.data.get("channel") or "instagram").strip()
    field = field_map.get(channel)
    if field is None:
        return Response({"error": f"unknown channel '{channel}'"}, status=400)
    cfg = ConfiguracioGlobal.load()
    new_val = bool(request.data.get("actiu", not getattr(cfg, field)))
    setattr(cfg, field, new_val)
    cfg.save(update_fields=[field])
    return Response({channel + "_actiu": new_val})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_fase(request: Request) -> Response:
    try:
        fase = int(request.data.get("fase"))
    except (TypeError, ValueError):
        return Response({"error": "fase must be int 1-5"}, status=400)
    if fase < 1 or fase > 5:
        return Response({"error": "fase must be in [1, 5]"}, status=400)
    cfg = ConfiguracioGlobal.load()
    cfg.fase_distribucio = fase
    cfg.save(update_fields=["fase_distribucio"])
    return Response({"fase_distribucio": cfg.fase_distribucio})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_story_cap(request: Request) -> Response:
    try:
        n = int(request.data.get("n"))
    except (TypeError, ValueError):
        return Response({"error": "n must be int 1-40"}, status=400)
    if n < 1 or n > 40:
        return Response({"error": "n must be in [1, 40]"}, status=400)
    cfg = ConfiguracioGlobal.load()
    cfg.story_max_cancons_ppcc = n
    cfg.save(update_fields=["story_max_cancons_ppcc"])
    return Response({"story_max_cancons_ppcc": cfg.story_max_cancons_ppcc})
