"""Staff endpoints to monitor + control the social distribution.

  GET  /api/v1/staff/social/                — list of SocialPost rows
  POST /api/v1/staff/social/preview/        — render dry-run for a slot,
                                              returns the URLs of the
                                              freshly generated PNGs
  POST /api/v1/staff/social/publicar-ara/   — force-run publicar_social
                                              for a (data, tipus, platform)
                                              triple
  POST /api/v1/staff/social/toggle/         — flip ConfiguracioGlobal
                                              .instagram_actiu
  POST /api/v1/staff/social/fase/           — set ConfiguracioGlobal
                                              .fase_distribucio
  POST /api/v1/staff/social/story-cap/      — set ConfiguracioGlobal
                                              .story_max_cancons_ppcc
  GET  /api/v1/staff/social/token-status/   — days until token expires

All require IsStaff (the existing permission that the rest of the
staff endpoints already use, mounted by `staff_views`).
"""

from __future__ import annotations

import datetime
import io
from contextlib import redirect_stdout

from django.core.management import call_command
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from ingesta.social.instagram_client import days_until_expiry, is_dry_run
from ranking.models import ConfiguracioGlobal
from social.models import SocialPost
from web.api.staff._common import IsStaff


def _serialize(post: SocialPost) -> dict:
    return {
        "pk": post.pk,
        "platform": post.platform,
        "tipus": post.tipus,
        "territori": post.territori,
        "setmana": post.setmana.isoformat(),
        "status": post.status,
        "instagram_media_id": post.instagram_media_id or "",
        "error_msg": post.error_msg or "",
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "metadata": post.metadata or {},
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


@api_view(["GET"])
@permission_classes([IsStaff])
def social_list(request: Request) -> Response:
    qs = SocialPost.objects.all().order_by("-setmana", "-created_at")[:200]
    cfg = ConfiguracioGlobal.load()
    return Response(
        {
            "results": [_serialize(p) for p in qs],
            "config": {
                "instagram_actiu": cfg.instagram_actiu,
                "fase_distribucio": cfg.fase_distribucio,
                "story_max_cancons_ppcc": cfg.story_max_cancons_ppcc,
                "dry_run": is_dry_run(),
                "token_days_left": days_until_expiry(),
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def social_preview(request: Request) -> Response:
    """Run publicar_social --dry-run for the requested date / tipus
    / platform. Returns the captured stdout so the staff page can
    show what was rendered. Always safe."""
    data = (request.data.get("data") or "").strip()
    tipus = (request.data.get("tipus") or "").strip()
    platform = (request.data.get("platform") or "").strip()
    args = ["publicar_social", "--dry-run"]
    if data:
        args += ["--data", data]
    if tipus:
        args += ["--tipus", tipus]
    if platform:
        args += ["--platform", platform]
    buf = io.StringIO()
    with redirect_stdout(buf):
        call_command(*args)
    return Response({"output": buf.getvalue()})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_publicar_ara(request: Request) -> Response:
    """Force-run publicar_social for the requested triple. Bypasses
    the existing-publicat short-circuit via --force."""
    data = (request.data.get("data") or "").strip() or datetime.date.today().isoformat()
    tipus = (request.data.get("tipus") or "").strip()
    platform = (request.data.get("platform") or "").strip()
    if not tipus:
        return Response({"error": "tipus required"}, status=400)
    args = ["publicar_social", "--data", data, "--tipus", tipus, "--force"]
    if platform:
        args += ["--platform", platform]
    buf = io.StringIO()
    with redirect_stdout(buf):
        call_command(*args)
    return Response({"output": buf.getvalue()})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_toggle(request: Request) -> Response:
    cfg = ConfiguracioGlobal.load()
    cfg.instagram_actiu = bool(request.data.get("actiu", not cfg.instagram_actiu))
    cfg.save(update_fields=["instagram_actiu"])
    return Response({"instagram_actiu": cfg.instagram_actiu})


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
