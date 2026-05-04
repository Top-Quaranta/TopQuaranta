"""Per-channel credential save/test/clear endpoints.

Instagram (Meta Graph), Mastodon, Bluesky, Telegram. Each platform has
the same triple: persist creds → live read-only verification call →
wipe. Test endpoints never publish."""

from __future__ import annotations

import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from social.models import (
    BlueskyAuth,
    InstagramAuth,
    MastodonAuth,
    TelegramAuth,
)
from web.api.staff._common import IsStaff

from ._common import (
    _bluesky_payload,
    _credentials_payload,
    _mastodon_payload,
    _telegram_payload,
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


# ── Mastodon credentials ─────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsStaff])
def social_mastodon_save(request: Request) -> Response:
    """Persist Mastodon credentials. Caller passes:
        instance_url   — e.g. "https://mastodont.cat"
        access_token   — long-lived app token (scopes: write:media,
                         write:statuses)
        handle         — user-facing label (e.g. "topquaranta")
    The handle is auto-resolved from `whoami()` if blank.
    """
    instance = (request.data.get("instance_url") or "").strip().rstrip("/")
    token = (request.data.get("access_token") or "").strip()
    handle = (request.data.get("handle") or "").strip()
    if not instance or not token:
        return Response(
            {"error": "instance_url + access_token obligatoris"}, status=400
        )
    if not instance.startswith(("http://", "https://")):
        return Response(
            {"error": "instance_url ha de començar amb http(s)://"}, status=400
        )
    user = request.user if request.user.is_authenticated else None
    MastodonAuth.objects.update_or_create(
        pk=1,
        defaults={
            "instance_url": instance,
            "access_token": token,
            "handle": handle,
            "updated_by": user,
        },
    )
    # Best-effort: try to resolve the handle if the operator left
    # it blank. Failure here is non-fatal — we keep the row, just
    # without the auto-filled label.
    if not handle:
        try:
            from social import mastodon_client

            who = mastodon_client.whoami()
            if isinstance(who, dict) and who.get("username"):
                MastodonAuth.objects.filter(pk=1).update(handle=who["username"][:80])
        except Exception:  # noqa: BLE001
            logger = __import__("logging").getLogger(__name__)
            logger.exception("mastodon whoami after save failed")
    return Response({"ok": True, "mastodon": _mastodon_payload()})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_mastodon_test(request: Request) -> Response:
    """Hit `/api/v1/accounts/verify_credentials` and return the
    verified handle so the operator can confirm the right account."""
    try:
        from social import mastodon_client

        who = mastodon_client.whoami()
    except Exception as exc:  # noqa: BLE001
        return Response({"ok": False, "error": str(exc)[:300]}, status=502)
    return Response({"ok": True, "whoami": who})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_mastodon_clear(request: Request) -> Response:
    MastodonAuth.objects.filter(pk=1).delete()
    return Response({"ok": True, "mastodon": _mastodon_payload()})


# ── Bluesky credentials ──────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsStaff])
def social_bluesky_save(request: Request) -> Response:
    """Persist Bluesky credentials. Caller passes:
        handle        — e.g. "topquaranta.bsky.social"
        app_password  — created at bsky.app/settings/app-passwords
                        (NOT the account password)
    DID is resolved + stored on first authenticated request.
    """
    handle = (request.data.get("handle") or "").strip().lstrip("@")
    app_password = (request.data.get("app_password") or "").strip()
    if not handle or not app_password:
        return Response({"error": "handle + app_password obligatoris"}, status=400)
    user = request.user if request.user.is_authenticated else None
    BlueskyAuth.objects.update_or_create(
        pk=1,
        defaults={
            "handle": handle,
            "app_password": app_password,
            "did": "",  # cleared; bluesky_client._session() refills it
            "updated_by": user,
        },
    )
    # Reset cached session so the next call re-authenticates.
    try:
        from social import bluesky_client

        bluesky_client._SESSIONS.clear()
    except Exception:  # noqa: BLE001
        pass
    return Response({"ok": True, "bluesky": _bluesky_payload()})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_bluesky_test(request: Request) -> Response:
    """Run createSession against bsky.social and return the resolved
    DID. Confirms the app-password is valid."""
    try:
        from social import bluesky_client

        # Force re-auth so a stale cached session can't mask a
        # broken password.
        bluesky_client._SESSIONS.clear()
        who = bluesky_client.whoami()
    except Exception as exc:  # noqa: BLE001
        return Response({"ok": False, "error": str(exc)[:300]}, status=502)
    return Response({"ok": True, "whoami": who, "bluesky": _bluesky_payload()})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_bluesky_clear(request: Request) -> Response:
    BlueskyAuth.objects.filter(pk=1).delete()
    try:
        from social import bluesky_client

        bluesky_client._SESSIONS.clear()
    except Exception:  # noqa: BLE001
        pass
    return Response({"ok": True, "bluesky": _bluesky_payload()})


# ── Telegram credentials ─────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsStaff])
def social_telegram_save(request: Request) -> Response:
    """Persist Telegram bot credentials. Caller passes:
        bot_token  — the long token from @BotFather (`/newbot`)
        chat_id    — destination channel: handle (`@topquaranta`)
                     or numeric supergroup ID
    The bot must already be added as admin of the destination
    channel with "Post messages" permission — the test endpoint
    confirms this via `/getChat`.
    """
    bot_token = (request.data.get("bot_token") or "").strip()
    chat_id = (request.data.get("chat_id") or "").strip()
    if not bot_token or not chat_id:
        return Response({"error": "bot_token + chat_id obligatoris"}, status=400)
    if not bot_token.count(":") == 1:
        return Response(
            {"error": "bot_token sembla mal format (ha de ser '<id>:<hash>')"},
            status=400,
        )
    user = request.user if request.user.is_authenticated else None
    TelegramAuth.objects.update_or_create(
        pk=1,
        defaults={
            "bot_token": bot_token,
            "chat_id": chat_id,
            "bot_username": "",
            "updated_by": user,
        },
    )
    # Best-effort: resolve the bot's own username for display.
    try:
        from social import telegram_client

        info = telegram_client.whoami()
        if isinstance(info, dict) and info.get("username"):
            TelegramAuth.objects.filter(pk=1).update(bot_username=info["username"][:80])
    except Exception:  # noqa: BLE001
        logger = __import__("logging").getLogger(__name__)
        logger.exception("telegram whoami after save failed")
    return Response({"ok": True, "telegram": _telegram_payload()})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_telegram_test(request: Request) -> Response:
    """Run /getMe + /getChat to confirm the bot token is valid AND
    has access to the destination channel. Returns both payloads."""
    try:
        from social import telegram_client

        bot = telegram_client.whoami()
        chat = telegram_client.chat_info()
    except Exception as exc:  # noqa: BLE001
        return Response({"ok": False, "error": str(exc)[:300]}, status=502)
    return Response({"ok": True, "bot": bot, "chat": chat})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_telegram_clear(request: Request) -> Response:
    TelegramAuth.objects.filter(pk=1).delete()
    return Response({"ok": True, "telegram": _telegram_payload()})
