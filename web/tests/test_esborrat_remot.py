"""Remote delete of a published post, per platform.

The audit of 2026-08-15 found zero coverage here: the only two tests
near it mock `_delete_remote_and_reset` wholesale, so nothing exercised
what it actually sends. The Telegram branch is the one that bites — the
API has no group-level delete, so a carousel is N separate messages, and
getting the id list wrong silently leaves most of the post published
while the panel reports success and drops the evidence.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from social.models import SocialPost
from web.api.staff.social.posts import _delete_remote_and_reset


def _post(**kw):
    base = dict(
        platform="telegram",
        tipus="top_ppcc",
        territori="PPCC",
        setmana="2026-08-10",
        status=SocialPost.STATUS_PUBLICAT,
        instagram_media_id="https://t.me/topquaranta/1234",
    )
    base.update(kw)
    return SocialPost.objects.create(**base)


@pytest.mark.django_db
def test_a_telegram_carousel_deletes_every_message():
    """One conceptual post, ten messages. Deleting the first only would
    leave nine of them published."""
    ids = list(range(1234, 1244))
    p = _post(metadata={"message_ids": ids})

    with patch(
        "social.telegram_client.delete_messages", return_value=(True, "OK")
    ) as m:
        ok, _ = _delete_remote_and_reset(p)

    assert ok
    m.assert_called_once_with(ids)


@pytest.mark.django_db
def test_a_partial_delete_says_so_instead_of_reporting_plain_success():
    """Posts published before `message_ids` was captured only leave the
    URL, whose tail is the FIRST message. We still try, but the operator
    must not read it as "the post is gone"."""
    p = _post(metadata={})

    with patch(
        "social.telegram_client.delete_messages", return_value=(True, "OK")
    ) as m:
        ok, msg = _delete_remote_and_reset(p)

    assert ok
    m.assert_called_once_with([1234])
    assert "ATENCIÓ" in msg and "a mà" in msg


@pytest.mark.django_db
def test_a_failed_remote_delete_leaves_the_row_untouched():
    """The local reset mirrors the remote state. Resetting after a failed
    delete would strand the post: published remotely, pendent locally,
    and the next cron would publish it a second time."""
    ids = [1234, 1235]
    p = _post(metadata={"message_ids": ids})

    with patch("social.telegram_client.delete_messages", return_value=(False, "boom")):
        ok, _ = _delete_remote_and_reset(p)

    assert not ok
    p.refresh_from_db()
    assert p.status == SocialPost.STATUS_PUBLICAT
    assert p.instagram_media_id == "https://t.me/topquaranta/1234"
    assert (p.metadata or {}).get("message_ids") == ids


@pytest.mark.django_db
def test_a_successful_delete_resets_the_row_for_republishing():
    p = _post(metadata={"message_ids": [1234]})

    with patch("social.telegram_client.delete_messages", return_value=(True, "OK")):
        ok, _ = _delete_remote_and_reset(p)

    assert ok
    p.refresh_from_db()
    assert p.status == SocialPost.STATUS_PENDENT
    assert p.instagram_media_id == ""
    assert p.published_at is None


@pytest.mark.django_db
def test_a_post_with_no_remote_id_is_refused():
    p = _post(instagram_media_id="", metadata={})
    ok, msg = _delete_remote_and_reset(p)
    assert not ok and "no té id remota" in msg
