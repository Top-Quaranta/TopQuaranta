"""SocialPost CRUD-ish endpoints: list, slide preview, render serving,
dry-run + real publish, local reset, and remote-delete dispatch."""

from __future__ import annotations

import datetime
import io
from contextlib import redirect_stdout

from django.core.management import call_command
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from ranking.models import ConfiguracioGlobal
from social.calendari import publication_date_for, upcoming_week
from social.instagram_client import days_until_expiry, is_dry_run
from social.models import SocialPost
from web.api.staff._common import IsStaff

from ._common import (
    _bluesky_payload,
    _calendari_payload,
    _credentials_payload,
    _mastodon_payload,
    _serialize,
    _serve_png,
    _telegram_payload,
)


@api_view(["GET"])
@permission_classes([IsStaff])
def social_list(request: Request) -> Response:
    # Sort by activity date (when it was published, falling back to
    # when it was created) so the staff list matches what a human
    # would expect when scanning "what's new". `F('published_at')`
    # with `nulls_last` sends pending rows to the bottom; among
    # them the secondary `-created_at` keeps the freshest scheduled
    # ones on top.
    from django.db.models import F

    qs = SocialPost.objects.all().order_by(
        F("published_at").desc(nulls_last=True), "-created_at"
    )[:200]
    cfg = ConfiguracioGlobal.load()
    return Response(
        {
            "results": [_serialize(p) for p in qs],
            "config": {
                "instagram_actiu": cfg.instagram_actiu,
                "mastodon_actiu": cfg.mastodon_actiu,
                "bluesky_actiu": cfg.bluesky_actiu,
                "telegram_actiu": cfg.telegram_actiu,
                "newsletter_actiu": cfg.newsletter_actiu,
                "rss_actiu": cfg.rss_actiu,
                "fase_distribucio": cfg.fase_distribucio,
                "story_max_cancons_ppcc": cfg.story_max_cancons_ppcc,
                "delay_instagram_min": cfg.delay_instagram_min,
                "delay_mastodon_min": cfg.delay_mastodon_min,
                "delay_bluesky_min": cfg.delay_bluesky_min,
                "delay_telegram_min": cfg.delay_telegram_min,
                "delay_newsletter_min": cfg.delay_newsletter_min,
                "dry_run": is_dry_run(),
                "token_days_left": days_until_expiry(),
            },
            "credentials": _credentials_payload(),
            "mastodon": _mastodon_payload(),
            "bluesky": _bluesky_payload(),
            "telegram": _telegram_payload(),
            "calendari": _calendari_payload(),
        }
    )


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
    # `platform` lets the caller scope the response to feed-only or
    # story-only PNGs. When omitted we return both (legacy callers).
    # The staff page passes `post.platform` so each row's "Veure
    # slides" only shows the slides that belong to that row.
    platform = (request.GET.get("platform") or "").strip()
    if not (tipus and setmana):
        return Response({"error": "tipus + setmana required"}, status=400)
    want_feed = platform in ("", SocialPost.PLATFORM_INSTAGRAM_FEED)
    want_story = platform in ("", SocialPost.PLATFORM_INSTAGRAM_STORY)

    base = Path(getattr(_s, "SOCIAL_CACHE_DIR", "/tmp/tq_social")) / "renders"
    if not base.exists():
        base = Path("/tmp/tq_social/renders")

    # Try the row's stored setmana first, then fall back to the setmana
    # the renderer would *actually* use (= ISO Monday of the TQ-week
    # containing the publication date). This covers the case where
    # legacy rows still carry the old buggy setmana value but the
    # rendered files live under the canonical one.
    candidates = {setmana}
    try:
        from music.dates import tq_week_start

        target = publication_date_for(tipus, datetime.date.fromisoformat(setmana))
        canonical_sat = tq_week_start(target)
        canonical_setmana = canonical_sat - datetime.timedelta(
            days=canonical_sat.weekday()
        )
        candidates.add(canonical_setmana.isoformat())
    except (ValueError, TypeError):
        pass

    feed_files: list = []
    story_files: list = []
    for s in candidates:
        if not base.exists():
            break
        if want_feed:
            feed_files.extend(base.glob(f"feed_{tipus}_{territori}_{s}_*.png"))
        if want_story:
            story_files.extend(base.glob(f"story_{tipus}_{territori}_{s}_*.png"))
    # De-dup + stable order.
    feed_files = sorted(set(feed_files), key=lambda p: p.name)
    story_files = sorted(set(story_files), key=lambda p: p.name)

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
def social_preview_all(request: Request) -> Response:
    """Render every calendar slot of the upcoming TQ week in dry-run.

    Used by the staff "Generar totes les slides" button so the
    operator can review the design across PPCC + territoris + novetats
    without waiting for each slot's calendar day to come round.

    For each slot we call `publicar_social --dry-run --force` with
    its own `--data` (the day that slot would naturally publish on),
    so the command's weekday filter matches and the slot actually
    fires. Returns concatenated stdout for the operator to inspect.
    """
    setmana_raw = (request.data.get("setmana") or "").strip()
    reference: datetime.date | None = None
    if setmana_raw:
        try:
            reference = datetime.date.fromisoformat(setmana_raw)
        except ValueError:
            return Response({"error": "setmana invàlida"}, status=400)
    slots = upcoming_week(reference)
    buf = io.StringIO()
    runs: list[dict] = []
    for slot, _territori, publish_date in slots:
        args = [
            "publicar_social",
            "--dry-run",
            "--force",
            "--data",
            publish_date.isoformat(),
            "--tipus",
            slot.tipus,
            "--platform",
            slot.platform,
        ]
        try:
            with redirect_stdout(buf):
                call_command(*args)
            runs.append({"args": args, "ok": True})
        except Exception as exc:  # noqa: BLE001
            runs.append(
                {
                    "args": args,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            buf.write(f"\n  · ERROR: {type(exc).__name__}: {exc}\n")
    return Response({"output": buf.getvalue(), "runs": runs})


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
def social_reset(request: Request) -> Response:
    """Clear a SocialPost's local state so the next `Publicar` runs
    fresh (status → pendent, instagram_media_id + error_msg cleared,
    metadata wiped). Does **not** touch the live IG post — for that
    use `eliminar-instagram` first.

    Used during testing when something goes wrong (e.g. wanted IG
    handles weren't filled in) and the operator wants to retry from
    a clean slate without spawning a duplicate IG post.
    """
    pk = request.data.get("pk")
    if not pk:
        return Response({"error": "pk required"}, status=400)
    try:
        post = SocialPost.objects.get(pk=int(pk))
    except (SocialPost.DoesNotExist, ValueError):
        return Response({"error": "post not found"}, status=404)
    previous = {
        "status": post.status,
        "instagram_media_id": post.instagram_media_id,
        "error_msg": post.error_msg,
    }
    post.status = SocialPost.STATUS_PENDENT
    post.instagram_media_id = ""
    post.error_msg = ""
    post.metadata = {}
    post.published_at = None
    post.save(
        update_fields=[
            "status",
            "instagram_media_id",
            "error_msg",
            "metadata",
            "published_at",
            "updated_at",
        ]
    )
    return Response({"ok": True, "post": _serialize(post), "previous": previous})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_eliminar_instagram(request: Request) -> Response:
    """Delete the live IG post via Meta's `DELETE /{media-id}` and
    clear the local row. Destructive — removes the post from the
    public feed. Use it when re-publishing a corrected version (so
    the feed doesn't end up with two copies).
    """
    pk = request.data.get("pk")
    if not pk:
        return Response({"error": "pk required"}, status=400)
    try:
        post = SocialPost.objects.get(pk=int(pk))
    except (SocialPost.DoesNotExist, ValueError):
        return Response({"error": "post not found"}, status=404)
    media_id = (post.instagram_media_id or "").strip()
    if not media_id:
        return Response(
            {"error": "el post no té media_id; no hi ha res a esborrar a IG"},
            status=400,
        )
    if is_dry_run():
        deleted = False
        msg = "DRY-RUN: no es crida l'API de Meta"
    else:
        # Meta accepts DELETE on the media ID for self-owned posts
        # within the standard retention window. Failures (post
        # already gone, permission denied, etc.) propagate so the
        # operator sees the cause in the captured stdout.
        import requests

        from social.instagram_client import GRAPH_BASE, _token

        r = requests.delete(
            f"{GRAPH_BASE}/{media_id}",
            params={"access_token": _token()},
            timeout=30,
        )
        deleted = r.ok
        msg = (
            f"DELETE /{media_id} → {r.status_code}: {r.text[:300]}"
            if not r.ok
            else f"DELETE /{media_id} → 200 OK"
        )
        if not r.ok:
            return Response({"ok": False, "msg": msg}, status=502)
    # Mirror the reset path: blank local state.
    post.status = SocialPost.STATUS_PENDENT
    post.instagram_media_id = ""
    post.error_msg = ""
    post.metadata = {}
    post.published_at = None
    post.save()
    return Response(
        {"ok": True, "deleted": deleted, "msg": msg, "post": _serialize(post)}
    )


def _delete_remote_and_reset(post: SocialPost) -> tuple[bool, str]:
    """Platform-aware remote delete + local reset. Returns
    (ok, msg). Extracted from `social_eliminar_remot` so
    `social_republicar` can call it as the first step of the
    delete → re-render → re-publish flow without HTTP-calling
    itself.
    """
    ext_id = (post.instagram_media_id or "").strip()
    if not ext_id:
        return False, "el post no té id remota; no hi ha res a esborrar"

    plat = post.platform
    ok = False
    msg = ""
    if plat in ("instagram_feed", "instagram_story"):
        if is_dry_run():
            ok, msg = True, "DRY-RUN: no es crida l'API de Meta"
        else:
            import requests as _req

            from social.instagram_client import GRAPH_BASE, _token

            r = _req.delete(
                f"{GRAPH_BASE}/{ext_id}",
                params={"access_token": _token()},
                timeout=30,
            )
            ok = r.ok
            msg = (
                f"DELETE /{ext_id} → {r.status_code}: {r.text[:300]}"
                if not r.ok
                else f"DELETE /{ext_id} → 200 OK"
            )
    elif plat == "mastodon":
        from social import mastodon_client

        ok, msg = mastodon_client.delete_status(ext_id)
    elif plat == "bluesky":
        from social import bluesky_client

        ok, msg = bluesky_client.delete_post(ext_id)
    elif plat == "telegram":
        from social import telegram_client

        mids = (post.metadata or {}).get("message_ids") or []
        if not mids:
            tail = ext_id.rstrip("/").rsplit("/", 1)[-1]
            if tail.isdigit():
                mids = [int(tail)]
        ok, msg = telegram_client.delete_messages(mids)
    else:
        return False, f"plataforma no suportada per esborrat remot: {plat}"

    if not ok:
        return False, msg

    # Remote delete succeeded → mirror the reset.
    post.status = SocialPost.STATUS_PENDENT
    post.instagram_media_id = ""
    post.error_msg = ""
    post.metadata = {}
    post.published_at = None
    post.save()
    return True, msg


def _publish_args_for(post: SocialPost) -> list[str]:
    """Build the `call_command` args that re-publish a post in its
    original platform + tipus + setmana slot. Used by
    `social_republicar` after the remote delete + local reset.
    """
    publish_date = publication_date_for(post.tipus, post.setmana)
    plat = post.platform
    if plat in ("instagram_feed", "instagram_story"):
        return [
            "publicar_social",
            "--data",
            publish_date.isoformat(),
            "--tipus",
            post.tipus,
            "--platform",
            plat,
            "--force",
        ]
    # Non-IG channels go through publicar_canal.
    channel = plat  # mastodon | bluesky | telegram | newsletter
    return [
        "publicar_canal",
        "--channel",
        channel,
        "--data",
        publish_date.isoformat(),
        "--tipus",
        post.tipus,
        "--force",
    ]


@api_view(["POST"])
@permission_classes([IsStaff])
def social_eliminar_remot(request: Request) -> Response:
    """Platform-aware delete: dispatch on `post.platform` and call
    the matching client's delete function. Mirrors the local-reset
    side-effects of `social_eliminar_instagram` once the remote call
    succeeds (or in dry-run).

    Supported platforms: instagram_feed, instagram_story (via Meta
    Graph), mastodon, bluesky, telegram. The external id lives in
    `post.instagram_media_id` (legacy field name, reused for every
    channel); Telegram additionally needs `post.metadata.message_ids`
    because a media-group expands into multiple Message rows on
    Telegram's side and each has to be deleted individually.
    """
    pk = request.data.get("pk")
    if not pk:
        return Response({"error": "pk required"}, status=400)
    try:
        post = SocialPost.objects.get(pk=int(pk))
    except (SocialPost.DoesNotExist, ValueError):
        return Response({"error": "post not found"}, status=404)

    try:
        ok, msg = _delete_remote_and_reset(post)
    except Exception as exc:  # noqa: BLE001
        return Response(
            {"ok": False, "msg": f"{type(exc).__name__}: {exc}"}, status=502
        )
    if not ok:
        # 400 vs 502 keeps the previous semantics (no ext_id → 400;
        # API failure → 502).
        status_code = 400 if "id remota" in msg else 502
        return Response({"ok": False, "msg": msg}, status=status_code)
    return Response({"ok": True, "msg": msg, "post": _serialize(post)})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_republicar(request: Request) -> Response:
    """Re-publish a post with the latest top contents.

    Use case: a cançó in a published top is rejected after publication
    (e.g. staff finds the artist is a homonym mismatch). The on-screen
    post still shows the wrong row. This endpoint:

      1. Deletes the remote post via `_delete_remote_and_reset` (the
         same dispatcher `social_eliminar_remot` uses).
      2. Re-runs the appropriate publish command with `--force`. The
         renderer now produces a corrected slide because TopSetmanal
         has been recomputed since the rebuig.

    Returns the captured stdout of both steps so the operator sees
    what happened. Lot C of Sprint Distribució v2 — replaces the
    manual three-click workflow (Esborrar → Reset → Publicar).
    """
    pk = request.data.get("pk")
    if not pk:
        return Response({"error": "pk required"}, status=400)
    try:
        post = SocialPost.objects.get(pk=int(pk))
    except (SocialPost.DoesNotExist, ValueError):
        return Response({"error": "post not found"}, status=404)

    if not (post.instagram_media_id or "").strip():
        return Response(
            {"error": "el post no està publicat (no hi ha id remota)"},
            status=400,
        )

    # Step 1: remote delete + local reset.
    try:
        ok, delete_msg = _delete_remote_and_reset(post)
    except Exception as exc:  # noqa: BLE001
        return Response(
            {"ok": False, "step": "delete", "msg": f"{type(exc).__name__}: {exc}"},
            status=502,
        )
    if not ok:
        return Response({"ok": False, "step": "delete", "msg": delete_msg}, status=502)

    # Step 2: re-publish via the appropriate command.
    args = _publish_args_for(post)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            call_command(*args)
    except Exception as exc:  # noqa: BLE001
        return Response(
            {
                "ok": False,
                "step": "publish",
                "msg": f"{type(exc).__name__}: {exc}",
                "delete_msg": delete_msg,
                "publish_output": buf.getvalue(),
            },
            status=500,
        )

    post.refresh_from_db()
    return Response(
        {
            "ok": True,
            "delete_msg": delete_msg,
            "publish_output": buf.getvalue() or f"(sense sortida) Args: {args}",
            "args": args,
            "post": _serialize(post),
        }
    )
