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
    # Unified publications table (distribution-views llesca 2). Filters
    # + search + sort via query params (same shape as the cançons /
    # artistes staff lists), paginated through the shared `_paginate`
    # (default 50, cap 200) so the response never scales with rows.
    # The cockpit + channel views call this without filter params and
    # ignore `results` (they consume `config`/`credentials`/...); the
    # publications table calls it with `?canal=...&page=...&...`.
    from django.db.models import F, Q
    from django.utils.dateparse import parse_date

    from web.api.staff._common import _paginate

    qs = SocialPost.objects.all()

    # `canal` maps a friendly channel key to its SocialPost platforms
    # (Instagram spans feed + story); reuse the single source of truth.
    canal = (request.GET.get("canal") or "").strip()
    if canal in _CHANNEL_ESTAT:
        platforms = _CHANNEL_ESTAT[canal][1]
        if platforms:
            qs = qs.filter(platform__in=platforms)
    estat = (request.GET.get("estat") or "").strip()
    if estat in {s for s, _ in SocialPost.STATUS_CHOICES}:
        qs = qs.filter(status=estat)
    tipus = (request.GET.get("tipus") or "").strip()
    if tipus in {t for t, _ in SocialPost.TIPUS_CHOICES}:
        qs = qs.filter(tipus=tipus)
    setmana_raw = (request.GET.get("setmana") or "").strip()
    if setmana_raw:
        d = parse_date(setmana_raw)
        if d is not None:
            qs = qs.filter(setmana=d)
    # Free-text over the human-meaningful char fields on the row. Small
    # table; a plain icontains is enough (no unaccent machinery needed).
    cerca = (request.GET.get("q") or "").strip()
    if cerca:
        qs = qs.filter(
            Q(platform__icontains=cerca)
            | Q(tipus__icontains=cerca)
            | Q(territori__icontains=cerca)
        )

    # Sort. `data` (default) keeps the legacy activity order: published
    # first (nulls last), freshest created among the still-pending.
    sort_raw = (request.GET.get("sort") or "-data").strip()
    direction = "-" if sort_raw.startswith("-") else ""
    key = sort_raw[1:] if sort_raw.startswith("-") else sort_raw
    sort_map = {
        "data": "published_at",
        "setmana": "setmana",
        "canal": "platform",
        "estat": "status",
    }
    if key not in sort_map:
        direction, key = "-", "data"
    if key == "data":
        if direction == "-":
            qs = qs.order_by(F("published_at").desc(nulls_last=True), "-created_at")
        else:
            qs = qs.order_by(F("published_at").asc(nulls_first=True), "created_at")
    else:
        qs = qs.order_by(f"{direction}{sort_map[key]}", "-created_at")

    page, meta = _paginate(qs, request)
    cfg = ConfiguracioGlobal.load()
    return Response(
        {
            "results": [_serialize(p) for p in page.object_list],
            **meta,
            "config": {
                "distribucio_activa": cfg.distribucio_activa,
                "instagram_actiu": cfg.instagram_actiu,
                "mastodon_actiu": cfg.mastodon_actiu,
                "bluesky_actiu": cfg.bluesky_actiu,
                "telegram_actiu": cfg.telegram_actiu,
                "newsletter_actiu": cfg.newsletter_actiu,
                "rss_actiu": cfg.rss_actiu,
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


# Channel → (per-channel switch field, SocialPost platforms for the
# last-send timestamp, StaffAuditLog *_publicat action for the
# reset-proof fallback). RSS is pull-based (no SocialPost, no audit).
_CHANNEL_ESTAT = {
    "instagram": (
        "instagram_actiu",
        [SocialPost.PLATFORM_INSTAGRAM_FEED, SocialPost.PLATFORM_INSTAGRAM_STORY],
        "social_publicat",
    ),
    "mastodon": ("mastodon_actiu", [SocialPost.PLATFORM_MASTODON], "mastodon_publicat"),
    "bluesky": ("bluesky_actiu", [SocialPost.PLATFORM_BLUESKY], "bluesky_publicat"),
    "telegram": ("telegram_actiu", [SocialPost.PLATFORM_TELEGRAM], "telegram_publicat"),
    "newsletter": (
        "newsletter_actiu",
        [SocialPost.PLATFORM_NEWSLETTER],
        "newsletter_publicat",
    ),
    "rss": ("rss_actiu", [], None),
}


@api_view(["GET"])
@permission_classes([IsStaff])
def social_estat_canals(request: Request) -> Response:
    """Honest per-channel distribution state for the staff view.

    For each of the six channels returns:
      - `efectiu`: actiu | pausat_global (master off) | pausat_canal
        (this channel's switch off, master on)
      - `mestre_actiu` / `canal_actiu`: the raw booleans so the UI can
        show "pausat pel mestre" AND "pausat pel canal" independently
      - `ultim_enviament`: max(SocialPost.published_at) where
        status=publicat, with StaffAuditLog `*_publicat` (max
        created_at) as a reset-proof fallback (republicar/reset NULLs
        published_at). `font` = socialpost | audit | none."""
    from django.db.models import Max

    from music.models import StaffAuditLog

    cfg = ConfiguracioGlobal.load()
    master = cfg.distribucio_activa
    out = {}
    for canal, (field, platforms, audit_action) in _CHANNEL_ESTAT.items():
        canal_actiu = bool(getattr(cfg, field))
        if not master:
            efectiu = "pausat_global"
        elif not canal_actiu:
            efectiu = "pausat_canal"
        else:
            efectiu = "actiu"

        last_iso = None
        font = "none"
        if platforms:
            last_dt = SocialPost.objects.filter(
                platform__in=platforms, status=SocialPost.STATUS_PUBLICAT
            ).aggregate(m=Max("published_at"))["m"]
            if last_dt is not None:
                last_iso = last_dt.isoformat()
                font = "socialpost"
            elif audit_action:
                # Fallback: published_at was reset/republicat → NULL.
                audit_dt = StaffAuditLog.objects.filter(action=audit_action).aggregate(
                    m=Max("created_at")
                )["m"]
                if audit_dt is not None:
                    last_iso = audit_dt.isoformat()
                    font = "audit"

        entry = {
            "efectiu": efectiu,
            "mestre_actiu": master,
            "canal_actiu": canal_actiu,
            "ultim_enviament": last_iso,
            "font": font,
        }
        out[canal] = entry

    return Response({"mestre_actiu": master, "canals": out})


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


@api_view(["GET"])
@permission_classes([IsStaff])
def social_metrics_summary(request: Request) -> Response:
    """Per-platform engagement totals for the publications table.

    Sums the LATEST `MetricaSocialPost` snapshot of every post, grouped
    by `SocialPost.platform`. Read-only and additive: it never touches
    the row list / `_serialize`, so the table query stays cheap. Returns
    `{"per_platform": [{platform, n_posts, likes, replies, shares, reach,
    impressions, clicks}, ...]}` sorted by platform. Posts with no metric
    snapshot yet (freshly published, the daily cron hasn't run) simply
    don't contribute."""
    from collections import defaultdict

    from analytics.models import MetricaSocialPost

    fields = ("likes", "replies", "shares", "reach", "impressions", "clicks")

    # Latest snapshot per post: ordering by (post, data) ascending means
    # the last row written into the dict per post is its max-data one.
    latest: dict[int, MetricaSocialPost] = {}
    for m in MetricaSocialPost.objects.select_related("socialpost").order_by(
        "socialpost_id", "data"
    ):
        latest[m.socialpost_id] = m

    agg: dict[str, dict] = defaultdict(lambda: {"n_posts": 0, **{f: 0 for f in fields}})
    for m in latest.values():
        sp = m.socialpost
        if sp is None:
            continue
        row = agg[sp.platform]
        row["n_posts"] += 1
        for f in fields:
            row[f] += getattr(m, f) or 0

    out = [{"platform": plat, **vals} for plat, vals in sorted(agg.items())]
    return Response({"per_platform": out})
