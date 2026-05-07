"""Tiny Telegram Bot API client.

Auth: a bot token from @BotFather on Telegram (`/newbot`). The bot
must be added to the destination channel as an admin with "Post
messages" permission. `chat_id` accepts either the channel handle
(e.g. `@topquaranta_canal`) or the numeric supergroup ID.

Two send methods:
  * `send_photo(chat_id, image_url, caption)` — single image.
  * `send_media_group(chat_id, image_urls, caption)` — up to 10
    images grouped in one notification (Telegram caps at 10). The
    caption attaches to the *first* item; the rest are silent.

We pass URLs (not multipart uploads) so Telegram's CDN fetches the
PNGs directly from our Caddy `/static/social/*` endpoint — same
flow as Meta's media fetcher.
"""

from __future__ import annotations

import json
import logging

import requests

from social.constants import HTTP_TIMEOUT_S as TIMEOUT_S
from social.models import TelegramAuth

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
MEDIA_GROUP_MAX = 10
CAPTION_MAX = 1024


def _row() -> TelegramAuth | None:
    return TelegramAuth.load()


def is_dry_run() -> bool:
    row = _row()
    return not (row and row.bot_token and row.chat_id)


def _bot_url(method: str) -> str:
    return f"{API_BASE}/bot{_row().bot_token}/{method}"


def _post(method: str, body: dict) -> dict:
    r = requests.post(_bot_url(method), json=body, timeout=TIMEOUT_S)
    if not r.ok:
        raise RuntimeError(f"Telegram /{method} {r.status_code}: {r.text[:300]}")
    payload = r.json()
    if not payload.get("ok"):
        raise RuntimeError(
            f"Telegram /{method} not ok: {payload.get('description', '')[:300]}"
        )
    return payload["result"]


def send_photo(image_url: str, caption: str = "") -> str:
    """Single-photo post. Returns the message URL (best-effort)."""
    if is_dry_run():
        logger.info("[DRY] telegram send_photo %s", image_url)
        return f"https://t.me/dry/{abs(hash(image_url)) & 0xffff:04x}"
    body = {
        "chat_id": _row().chat_id,
        "photo": image_url,
        "caption": caption[:CAPTION_MAX],
        "parse_mode": "HTML",
    }
    res = _post("sendPhoto", body)
    return _message_url(res)


def send_media_group(image_urls: list[str], caption: str = "") -> str:
    """Up to 10 photos in one message. Caption attaches to the first
    photo. Returns the URL of the first message (Telegram returns a
    list of Message objects, one per photo)."""
    if not image_urls:
        return ""
    if len(image_urls) == 1:
        return send_photo(image_urls[0], caption)
    if is_dry_run():
        logger.info("[DRY] telegram send_media_group n=%d", len(image_urls))
        return f"https://t.me/dry/{abs(hash(image_urls[0])) & 0xffff:04x}"
    media = []
    for i, url in enumerate(image_urls[:MEDIA_GROUP_MAX]):
        item = {"type": "photo", "media": url}
        if i == 0 and caption:
            item["caption"] = caption[:CAPTION_MAX]
            item["parse_mode"] = "HTML"
        media.append(item)
    body = {
        "chat_id": _row().chat_id,
        "media": json.dumps(media),
    }
    res = _post("sendMediaGroup", body)
    # `res` is a list of messages — one per photo. Take the first.
    if isinstance(res, list) and res:
        return _message_url(res[0])
    return ""


def send_media_group_full(image_urls: list[str], caption: str = "") -> dict:
    """Same as `send_media_group` but returns full `{url, message_ids}`.

    Needed by the staff "esborrar" button so we can later delete
    *every* message in the group (Telegram has no group-level delete;
    the bot must DELETE each message_id individually via
    `deleteMessages`).
    """
    if not image_urls:
        return {"url": "", "message_ids": []}
    if len(image_urls) == 1:
        url = send_photo(image_urls[0], caption)
        # send_photo returns a URL but not the id; parse trailing int.
        msg_id = url.rsplit("/", 1)[-1]
        return {"url": url, "message_ids": [int(msg_id)] if msg_id.isdigit() else []}
    if is_dry_run():
        logger.info("[DRY] telegram send_media_group n=%d", len(image_urls))
        return {
            "url": f"https://t.me/dry/{abs(hash(image_urls[0])) & 0xffff:04x}",
            "message_ids": [],
        }
    media = []
    for i, url in enumerate(image_urls[:MEDIA_GROUP_MAX]):
        item = {"type": "photo", "media": url}
        if i == 0 and caption:
            item["caption"] = caption[:CAPTION_MAX]
            item["parse_mode"] = "HTML"
        media.append(item)
    body = {"chat_id": _row().chat_id, "media": json.dumps(media)}
    res = _post("sendMediaGroup", body)
    if isinstance(res, list) and res:
        return {
            "url": _message_url(res[0]),
            "message_ids": [m.get("message_id") for m in res if m.get("message_id")],
        }
    return {"url": "", "message_ids": []}


def delete_messages(message_ids: list[int]) -> tuple[bool, str]:
    """Delete one or more messages by id from the configured chat.

    Uses `deleteMessages` (Bot API ≥ 7.4, accepts up to 100 ids in
    one call). Bots can only delete messages they themselves sent
    within the last 48h on most chat types; on channels where the
    bot is admin there's no time limit.
    """
    if is_dry_run():
        return True, "DRY-RUN: no es crida l'API de Telegram"
    if not message_ids:
        return False, "cap message_id per esborrar"
    body = {
        "chat_id": _row().chat_id,
        "message_ids": [int(m) for m in message_ids[:100]],
    }
    try:
        _post("deleteMessages", body)
    except RuntimeError as exc:
        return False, str(exc)
    return True, f"deleteMessages n={len(message_ids)} → OK"


def whoami() -> dict:
    """Return the bot's own info via /getMe.

    Useful for credential test: confirms the token is valid and
    surfaces the bot's username so the operator can verify they
    pasted the right one.
    """
    if is_dry_run():
        return {"dry_run": True}
    return _post("getMe", {})


def chat_info() -> dict:
    """Resolve the destination chat. Confirms the bot has access
    to the channel + returns the resolved title/username."""
    if is_dry_run():
        return {"dry_run": True}
    return _post("getChat", {"chat_id": _row().chat_id})


def get_post_metrics(message_id) -> dict:
    """Engagement metrics for a Telegram channel post.

    The Bot API does **not** expose per-message view counters or
    reaction counts — those are only readable via the user-facing
    MTProto API (Telethon / Pyrogram). Rather than add a heavy
    extra dependency for a single counter, we return zeros and
    flag `not_supported` in `raw` so the dashboard can hide
    Telegram engagement instead of charting fake silence.

    `chat_info()` does expose `members_count` for channels — that
    feeds `MetricaSocialPlatform(platform=telegram, metric=members)`
    via `get_account_stats()` below.
    """
    return {
        "likes": 0,
        "replies": 0,
        "shares": 0,
        "raw": {"not_supported": "telegram_bot_api_lacks_post_views"},
    }


def get_account_stats() -> dict:
    """Channel member count + posts-total (when retrievable)."""
    if is_dry_run():
        return {"members": 0, "raw": {"dry_run": True}}
    try:
        chat = chat_info()
    except RuntimeError as exc:
        return {"members": 0, "raw": {"error": str(exc)[:300]}}
    members = 0
    try:
        # `_post` already unwraps `{"ok": true, "result": …}`, so for
        # `getChatMemberCount` we get the plain integer back.
        body = _post("getChatMemberCount", {"chat_id": _row().chat_id})
        members = int(body or 0)
    except (RuntimeError, TypeError, ValueError) as exc:
        return {"members": 0, "raw": {"error": str(exc)[:300], "chat": chat}}
    return {"members": members, "raw": {"chat": chat}}


def _message_url(msg: dict) -> str:
    """Best-effort permalink. Public channels expose
    `https://t.me/<username>/<message_id>`; private chats don't."""
    chat = msg.get("chat") or {}
    msg_id = msg.get("message_id")
    username = chat.get("username")
    if username and msg_id:
        return f"https://t.me/{username}/{msg_id}"
    return f"telegram-msg-{msg_id}" if msg_id else ""
