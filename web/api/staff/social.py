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

from ingesta.social.calendari import publication_date_for, upcoming_week
from ingesta.social.instagram_client import days_until_expiry, is_dry_run
from ranking.models import ConfiguracioGlobal
from social.models import InstagramAuth, SocialPost
from web.api.staff._common import IsStaff

# User-facing label map. PPCC is the legacy code; visitors see
# "Global". Mirrors the convention used everywhere in the public SPA.
TERRITORI_LABEL = {
    "PPCC": "Global",
    "CAT": "Catalunya",
    "VAL": "País Valencià",
    "BAL": "Illes Balears",
    "AND": "Andorra",
    "CNO": "Catalunya del Nord",
    "FRA": "Franja de Ponent",
    "ALG": "L'Alguer",
    "ALT": "Altres",
    "": "—",
}


def _serialize(post: SocialPost) -> dict:
    # The publication day for this slot's tipus (Saturday for PPCC,
    # Wednesday/Monday for territorial, etc.). Surfaces in the UI as
    # the human-meaningful date — the operator thinks about "the
    # post of dissabte", not "the Monday of the ISO week".
    pub_date = publication_date_for(post.tipus, post.setmana)
    return {
        "pk": post.pk,
        "platform": post.platform,
        "tipus": post.tipus,
        "territori": post.territori,
        "territori_label": TERRITORI_LABEL.get(post.territori, post.territori or "—"),
        "setmana": post.setmana.isoformat(),
        "publication_date": pub_date.isoformat(),
        "status": post.status,
        "instagram_media_id": post.instagram_media_id or "",
        "error_msg": post.error_msg or "",
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "metadata": post.metadata or {},
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
    }


_DAY_CA = [
    "dilluns",
    "dimarts",
    "dimecres",
    "dijous",
    "divendres",
    "dissabte",
    "diumenge",
]


def _calendari_payload() -> list[dict]:
    """One row per slot of the current ISO week, with the territori
    already resolved (so the operator knows ahead of time which top
    will go out)."""
    out = []
    for slot, ter, pub_date in upcoming_week():
        out.append(
            {
                "platform": slot.platform,
                "tipus": slot.tipus,
                "territori": ter,
                "territori_label": TERRITORI_LABEL.get(ter, ter or "—"),
                "min_fase": slot.min_fase,
                "weekday": slot.weekday,
                "weekday_name": _DAY_CA[slot.weekday],
                "publication_date": pub_date.isoformat(),
            }
        )
    return out


def _credentials_payload() -> dict:
    """Token info for the staff page. Never returns the full token
    string — only first/last 4 chars so an admin can verify which
    one is active without exposing it on screen."""
    row = InstagramAuth.load()
    if row and row.access_token:
        t = row.access_token
        return {
            "configured": True,
            "source": "db",
            "token_masked": f"{t[:4]}…{t[-4:]}",
            "instagram_user_id": row.instagram_user_id,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by.username if row.updated_by else None,
        }
    # Fallback: env-based credentials (dev / first-boot).
    from django.conf import settings as _s

    env_token = (getattr(_s, "INSTAGRAM_ACCESS_TOKEN", "") or "").strip()
    if env_token and env_token != "test":
        return {
            "configured": True,
            "source": "env",
            "token_masked": f"{env_token[:4]}…{env_token[-4:]}",
            "instagram_user_id": getattr(_s, "INSTAGRAM_USER_ID", "") or "",
            "expires_at": getattr(_s, "INSTAGRAM_TOKEN_EXPIRES_AT", "") or None,
            "updated_at": None,
            "updated_by": None,
        }
    return {
        "configured": False,
        "source": None,
        "token_masked": "",
        "instagram_user_id": "",
        "expires_at": None,
        "updated_at": None,
        "updated_by": None,
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
            "credentials": _credentials_payload(),
            "calendari": _calendari_payload(),
        }
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def social_credentials_save(request: Request) -> Response:
    """Persist the Instagram long-lived token to the `InstagramAuth`
    singleton. The Instagram user ID is **resolved automatically** via
    `GET https://graph.instagram.com/v19.0/me?access_token=...` so the
    operator only needs to paste the token. Returns 400 if the token
    can't be exchanged into a valid user_id (catches typos + revoked
    tokens before they cause cron failures).

    `expires_at` is set to `now + 60 days` — the default lifetime of
    a fresh long-lived token. `renovar_token_instagram` resets it
    every refresh.
    """
    import requests
    from django.utils import timezone as _tz

    token = (request.data.get("access_token") or "").strip()
    if not token:
        return Response({"error": "access_token obligatori"}, status=400)
    if len(token) < 20:
        return Response(
            {"error": "access_token sospitosament curt; revisa-ho"}, status=400
        )

    # Optional manual override for the user_id. Useful if Meta returns
    # a wrapper account ID instead of the IG numeric ID; rare, but
    # harmless to expose.
    forced_uid = (request.data.get("instagram_user_id") or "").strip()

    # Resolve user_id from the token.
    try:
        r = requests.get(
            "https://graph.instagram.com/v19.0/me",
            params={"fields": "id,username", "access_token": token},
            timeout=20,
        )
    except Exception as exc:  # noqa: BLE001
        return Response(
            {"error": f"No s'ha pogut contactar amb Meta: {exc}"}, status=502
        )
    if not r.ok:
        return Response(
            {"error": f"Token rebutjat per Meta ({r.status_code}): {r.text[:200]}"},
            status=400,
        )
    body = r.json()
    user_id = forced_uid or str(body.get("id") or "")
    username = body.get("username") or ""
    if not user_id:
        return Response({"error": "Meta no ha retornat user_id"}, status=400)

    row = InstagramAuth.load() or InstagramAuth(pk=1)
    row.access_token = token
    row.instagram_user_id = user_id
    row.expires_at = _tz.now() + datetime.timedelta(days=60)
    row.updated_by = request.user if request.user.is_authenticated else None
    row.save()
    return Response(
        {
            "ok": True,
            "resolved_username": username,
            "resolved_user_id": user_id,
            "credentials": _credentials_payload(),
        }
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def social_credentials_test(request: Request) -> Response:
    """Live read-only call to the Graph API: GET /<user_id>?fields=
    username,account_type,media_count. Confirms the token is valid
    without posting anything. Surfaces the response body verbatim."""
    import requests

    row = InstagramAuth.load()
    token = row.access_token if row else ""
    user_id = row.instagram_user_id if row else ""
    if not token:
        from django.conf import settings as _s

        token = (getattr(_s, "INSTAGRAM_ACCESS_TOKEN", "") or "").strip()
        user_id = (getattr(_s, "INSTAGRAM_USER_ID", "") or "").strip()
    if not token or not user_id:
        return Response(
            {"ok": False, "error": "Cap credencial configurada."}, status=400
        )
    try:
        r = requests.get(
            f"https://graph.instagram.com/v19.0/{user_id}",
            params={
                "fields": "username,account_type,media_count",
                "access_token": token,
            },
            timeout=20,
        )
        return Response(
            {
                "ok": r.ok,
                "status": r.status_code,
                "body": (
                    r.json()
                    if r.headers.get("content-type", "").startswith("application/json")
                    else r.text[:500]
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return Response({"ok": False, "error": str(exc)}, status=500)


@api_view(["POST"])
@permission_classes([IsStaff])
def social_credentials_clear(request: Request) -> Response:
    """Wipe the InstagramAuth row. Useful if you need to revoke +
    re-authorize without leaving stale credentials around."""
    InstagramAuth.objects.filter(pk=1).delete()
    return Response({"ok": True, "credentials": _credentials_payload()})


@api_view(["GET"])
@permission_classes([IsStaff])
def social_slides_for(request: Request) -> Response:
    """List rendered PNGs for a (tipus, territori, setmana) triple.

    Looks at `<SOCIAL_CACHE_DIR>/renders/` and returns every file
    whose name matches the pattern the renderer writes for this
    slot. Includes a `serve_url` per file pointing at the staff
    `social/render/<filename>/` endpoint that proxies the bytes."""
    from pathlib import Path

    from django.conf import settings as _s
    from django.urls import reverse

    tipus = (request.GET.get("tipus") or "").strip()
    territori = (request.GET.get("territori") or "").strip() or "general"
    setmana = (request.GET.get("setmana") or "").strip()
    if not (tipus and setmana):
        return Response({"error": "tipus + setmana required"}, status=400)

    base = Path(getattr(_s, "SOCIAL_CACHE_DIR", "/tmp/tq_social")) / "renders"
    if not base.exists():
        base = Path("/tmp/tq_social/renders")

    feed_pattern = f"feed_{tipus}_{territori}_{setmana}_*.png"
    story_pattern = f"story_{tipus}_{territori}_{setmana}_*.png"
    feed_files = sorted(base.glob(feed_pattern)) if base.exists() else []
    story_files = sorted(base.glob(story_pattern)) if base.exists() else []

    def _serve_url(p):
        return reverse("api:staff_social_render_serve", args=[p.name])

    return Response(
        {
            "feed": [
                {
                    "name": p.name,
                    "url": _serve_url(p),
                    "size_kb": round(p.stat().st_size / 1024),
                }
                for p in feed_files
            ],
            "stories": [
                {
                    "name": p.name,
                    "url": _serve_url(p),
                    "size_kb": round(p.stat().st_size / 1024),
                }
                for p in story_files
            ],
        }
    )


@api_view(["GET"])
@permission_classes([IsStaff])
def social_render_serve(request: Request, filename: str) -> Response:
    """Serves a single PNG out of the renders cache. Auth-gated so
    we don't have to expose `/static/social/` publicly until the
    Caddy block is in place. Restricts to PNGs to avoid path tricks."""
    return _serve_png(filename)


def _serve_png(filename: str):
    """Shared file-serving helper used by both the staff-only
    endpoint and the public one Meta needs to fetch PNGs from."""
    import re
    from pathlib import Path

    from django.conf import settings as _s
    from django.http import FileResponse, Http404

    if not re.fullmatch(r"[A-Za-z0-9_.\-]+\.png", filename):
        raise Http404()
    base = Path(getattr(_s, "SOCIAL_CACHE_DIR", "/tmp/tq_social")) / "renders"
    candidate = base / filename
    if not candidate.exists():
        candidate = Path("/tmp/tq_social/renders") / filename
    if not candidate.exists() or not candidate.is_file():
        raise Http404()
    resp = FileResponse(open(candidate, "rb"), content_type="image/png")
    # Tell intermediaries (and Meta's fetcher) it's safe to cache.
    resp["Cache-Control"] = "public, max-age=86400"
    return resp


@api_view(["POST"])
@permission_classes([IsStaff])
def social_preview(request: Request) -> Response:
    """Run publicar_social --dry-run for the requested slot.

    Caller passes `setmana` (Monday of the ISO week — what the
    SocialPost row stores) + tipus + platform. We translate the
    setmana into the *publication day* for that tipus before calling
    the command, otherwise calling with a Monday wouldn't match a
    Saturday slot in the calendari.
    """
    setmana_raw = (
        request.data.get("data") or request.data.get("setmana") or ""
    ).strip()
    tipus = (request.data.get("tipus") or "").strip()
    platform = (request.data.get("platform") or "").strip()

    # `--force` so a previously-publicat row still re-renders for
    # visual review (we never publish anyway because of --dry-run).
    args = ["publicar_social", "--dry-run", "--force"]
    if setmana_raw and tipus:
        try:
            setmana = datetime.date.fromisoformat(setmana_raw)
        except ValueError:
            return Response({"error": "data invàlida"}, status=400)
        target = publication_date_for(tipus, setmana)
        args += ["--data", target.isoformat()]
    elif setmana_raw:
        args += ["--data", setmana_raw]
    if tipus:
        args += ["--tipus", tipus]
    if platform:
        args += ["--platform", platform]
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            call_command(*args)
    except Exception as exc:  # noqa: BLE001
        return Response(
            {"output": buf.getvalue(), "error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )
    output = buf.getvalue() or f"(sense sortida) Args: {args}"
    return Response({"output": output, "args": args})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_publicar_ara(request: Request) -> Response:
    """Force-run publicar_social for the requested triple. Bypasses
    the existing-publicat short-circuit via --force.

    Same setmana → publication-date translation as `social_preview`.
    """
    setmana_raw = (
        request.data.get("data") or request.data.get("setmana") or ""
    ).strip()
    tipus = (request.data.get("tipus") or "").strip()
    platform = (request.data.get("platform") or "").strip()
    if not tipus:
        return Response({"error": "tipus required"}, status=400)
    if setmana_raw:
        try:
            setmana = datetime.date.fromisoformat(setmana_raw)
        except ValueError:
            return Response({"error": "data invàlida"}, status=400)
        target = publication_date_for(tipus, setmana)
    else:
        target = datetime.date.today()
    args = [
        "publicar_social",
        "--data",
        target.isoformat(),
        "--tipus",
        tipus,
        "--force",
    ]
    if platform:
        args += ["--platform", platform]
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            call_command(*args)
    except Exception as exc:  # noqa: BLE001
        return Response(
            {"output": buf.getvalue(), "error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )
    output = buf.getvalue() or f"(sense sortida) Args: {args}"
    return Response({"output": output, "args": args})


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
