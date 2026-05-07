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


_DELAY_CHANNELS = ("instagram", "mastodon", "bluesky", "telegram", "newsletter")


@api_view(["POST"])
@permission_classes([IsStaff])
def social_delay(request: Request) -> Response:
    """Set per-channel publish delay in minutes (Sprint Distribució v2
    lot B). Cron fires the channel at its base time; each command
    sleeps `delay_<channel>_min` before doing work, letting staff
    spread the schedule wider without editing crontab. Capped at
    180 min (a worker holds a slot idle for the duration).
    """
    channel = (request.data.get("channel") or "").strip()
    if channel not in _DELAY_CHANNELS:
        return Response(
            {
                "error": f"unknown channel '{channel}'; expected one of {_DELAY_CHANNELS}"
            },
            status=400,
        )
    try:
        n = int(request.data.get("min"))
    except (TypeError, ValueError):
        return Response({"error": "min must be int 0-180"}, status=400)
    if n < 0 or n > 180:
        return Response({"error": "min must be in [0, 180]"}, status=400)
    cfg = ConfiguracioGlobal.load()
    field = f"delay_{channel}_min"
    setattr(cfg, field, n)
    cfg.save(update_fields=[field])
    return Response({field: n})
