"""A stale Instagram handle must cost a tag, never the post.

On 2026-08-03 Suu's renamed account (`tontaca13`) — she was a
*collaborator* on one track, not even a chart entry — raised code 110 and
took down the entire Catalan weekly top, which was never published. The
docstring at the time assumed Meta would "reject invalid handles silently
(untagged) or raise". It raised.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from social import instagram_client as ig

_ERR = json.dumps(
    {
        "error": {
            "message": "Invalid user id",
            "type": "OAuthException",
            "code": 110,
            "error_subcode": 2207018,
            "error_user_title": "Cannot load user with a private profile",
            "error_user_msg": ("The following user(s) cannot be accessed: tontaca13"),
        }
    }
)

TAGS = [
    {"username": "tontaca13", "x": 0.1, "y": 0.1},
    {"username": "laludwigband", "x": 0.5, "y": 0.5},
]


class TestParseig:
    def test_reads_the_refused_handles_out_of_the_message(self):
        exc = ig.IGError(400, _ERR)
        assert exc.code == 110
        assert ig.handles_rebutjats(exc) == {"tontaca13"}

    def test_reads_several(self):
        text = _ERR.replace("tontaca13", "tontaca13, altrecompte")
        assert ig.handles_rebutjats(ig.IGError(400, text)) == {
            "tontaca13",
            "altrecompte",
        }

    def test_an_unrelated_error_yields_nothing(self):
        text = json.dumps({"error": {"code": 4, "message": "rate limit"}})
        assert ig.handles_rebutjats(ig.IGError(400, text)) == set()


@pytest.mark.django_db
class TestDegradacio:
    def _client(self, respostes):
        it = iter(respostes)

        def fake_post(path, body):
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return r

        return fake_post

    def test_drops_the_bad_tag_and_publishes(self, settings):
        settings.SOCIAL_DRY_RUN = False
        enviats = []

        def fake_post(path, body):
            enviats.append(body)
            if len(enviats) == 1:
                raise ig.IGError(400, _ERR)
            return {"id": "container-1"}

        dropped = []
        with (
            patch.object(ig, "_post", side_effect=fake_post),
            patch.object(ig, "_user_id", return_value="1"),
            patch.object(ig, "is_dry_run", return_value=False),
        ):
            cid = ig.upload_carousel_item(
                "https://x/img.jpg", user_tags=TAGS, dropped=dropped
            )

        assert cid == "container-1"
        assert dropped == ["tontaca13"]
        # The good tag survives; only the refused one is gone.
        restants = json.loads(enviats[1]["user_tags"])
        assert [t["username"] for t in restants] == ["laludwigband"]

    def test_publishes_untagged_when_every_handle_is_refused(self, settings):
        enviats = []

        def fake_post(path, body):
            enviats.append(body)
            if len(enviats) == 1:
                raise ig.IGError(400, _ERR)
            return {"id": "c2"}

        with (
            patch.object(ig, "_post", side_effect=fake_post),
            patch.object(ig, "_user_id", return_value="1"),
            patch.object(ig, "is_dry_run", return_value=False),
        ):
            cid = ig.upload_carousel_item("https://x/img.jpg", user_tags=[TAGS[0]])

        assert cid == "c2"
        assert "user_tags" not in enviats[1]

    def test_an_unrelated_failure_still_raises(self, settings):
        text = json.dumps({"error": {"code": 4, "message": "rate limit"}})
        with (
            patch.object(ig, "_post", side_effect=ig.IGError(400, text)),
            patch.object(ig, "_user_id", return_value="1"),
            patch.object(ig, "is_dry_run", return_value=False),
        ):
            with pytest.raises(ig.IGError):
                ig.upload_carousel_item("https://x/img.jpg", user_tags=TAGS)
