"""IG publish-robustness — the default, unconditional behaviour
(2026-07-20 story-3 post-mortem; gating flags retired once prod ran on
them):

  1. `publish_container` re-polls + retries on the Graph API media-
     readiness race (code 9007 / subcode 2207027), up to the
     `ig_retry_9007_intents` tunable (0 = single-shot).
  2. A partially-published story set stays ERROR (not PUBLICAT) with the
     sent slides persisted, so tq-run's retry re-enters and backfills
     only the gap.

Every test mocks the Instagram client — no real API calls.
"""

from __future__ import annotations

import datetime
import io
import pathlib
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from music.models import Album, Artista, Canco
from ranking.models import ConfiguracioGlobal, TopSetmanal
from social import instagram_client as ic
from social.management.commands.publicar_social import Command as PubCmd
from social.models import SocialPost

SETMANA = datetime.date(2026, 4, 20)
SATURDAY = "2026-04-25"

_9007 = 'IG API 400: {"error":{"code":9007,"error_subcode":2207027,"message":"x"}}'


# ── Fix 1: publish_container 9007 retry ──────────────────────────────


class _FakePost:
    """Stand-in for `instagram_client._post`: fails the first
    `fail_times` media_publish calls with `err`, then returns an id."""

    def __init__(self, *, err: str, fail_times: int):
        self.err = err
        self.fail_times = fail_times
        self.calls = 0

    def __call__(self, path, params):
        assert "media_publish" in path
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(self.err)
        return {"id": "media-final"}


@pytest.fixture
def _live(monkeypatch):
    """Force the client out of dry-run and neutralise sleeps/polls."""
    monkeypatch.setattr(ic, "is_dry_run", lambda: False)
    monkeypatch.setattr(ic, "wait_until_finished", lambda cid: None)
    monkeypatch.setattr(ic.time, "sleep", lambda s: None)


def _cfg_retry(*, intents=2):
    cfg = ConfiguracioGlobal.load()
    cfg.ig_retry_9007_intents = intents
    cfg.ig_retry_9007_backoff_s = 0
    cfg.save()
    return cfg


def test_9007_transient_recovers_with_retry(db, _live, monkeypatch):
    _cfg_retry(intents=2)
    fake = _FakePost(err=_9007, fail_times=1)
    monkeypatch.setattr(ic, "_post", fake)
    assert ic.publish_container("cid-1") == "media-final"
    assert fake.calls == 2  # first 9007, retry succeeds


def test_9007_gives_up_after_intents(db, _live, monkeypatch):
    _cfg_retry(intents=2)
    fake = _FakePost(err=_9007, fail_times=99)  # never recovers
    monkeypatch.setattr(ic, "_post", fake)
    with pytest.raises(RuntimeError):
        ic.publish_container("cid-1")
    assert fake.calls == 3  # 1 initial + 2 retries


def test_9007_intents_zero_is_single_shot(db, _live, monkeypatch):
    # The retry is default behaviour, but `intents=0` still degrades to a
    # single publish attempt (the tunable, not a removed on/off flag).
    _cfg_retry(intents=0)
    fake = _FakePost(err=_9007, fail_times=99)
    monkeypatch.setattr(ic, "_post", fake)
    with pytest.raises(RuntimeError):
        ic.publish_container("cid-1")
    assert fake.calls == 1  # no retry


def test_non_9007_error_not_retried(db, _live, monkeypatch):
    _cfg_retry(intents=3)
    fake = _FakePost(err="IG API 400: some other permanent error", fail_times=99)
    monkeypatch.setattr(ic, "_post", fake)
    with pytest.raises(RuntimeError):
        ic.publish_container("cid-1")
    assert fake.calls == 1  # only 9007/2207027 is retried


# ── Fix 2: resumable story sets ──────────────────────────────────────


@pytest.fixture
def top_ppcc(db):
    """Minimal consolidated PPCC top of 4 cançons with IG handles."""
    arts = [
        Artista.objects.create(
            nom=f"P{i}",
            slug=f"p{i}",
            aprovat=True,
            instagram_url=f"https://instagram.com/p{i}/",
        )
        for i in range(1, 5)
    ]
    alb = Album.objects.create(nom="Alb", slug="alb", artista=arts[0])
    for i, art in enumerate(arts, start=1):
        c = Canco.objects.create(
            nom=f"Cançó {i}",
            slug=f"canco-{i}",
            artista=art,
            album=alb,
            verificada=True,
            activa=True,
        )
        TopSetmanal.objects.create(
            canco=c, territori="PPCC", setmana=SETMANA, posicio=i, score_setmanal=10 - i
        )
    cfg = ConfiguracioGlobal.load()
    cfg.instagram_actiu = True
    cfg.save()
    return arts


class _StoryUpload:
    """Fake `upload_story`: records calls; raises for any url whose name
    is in `fail_names` (a whole-story failure, mirroring a transient)."""

    def __init__(self, fail_names=(), tag="a"):
        self.fail_names = set(fail_names)
        self.tag = tag  # namespaces cids so a re-run yields globally-unique ids
        self.calls: list[str] = []
        self._n = 0

    def __call__(self, image_url, *, user_tags=None):
        self.calls.append(image_url)
        if any(image_url.endswith(name) for name in self.fail_names):
            raise RuntimeError("IG API 500: transient")
        self._n += 1
        return f"cid-{self.tag}-{self._n}"


def _run_story(upload_fake, *, force=False, n_paths=7):
    """Run the Saturday PPCC story slot with renderer + client mocked."""
    paths = [pathlib.Path(f"story_{i}.jpg") for i in range(n_paths)]
    argv = [
        "publicar_social",
        "--data",
        SATURDAY,
        "--platform",
        "instagram_story",
        "--tipus",
        "top_ppcc",
    ]
    if force:
        argv.append("--force")
    with (
        patch(
            "social.management.commands.publicar_social.renderer.render_stories_ppcc",
            return_value=paths,
        ),
        patch.object(PubCmd, "_story_novetats_items", return_value=[]),
        patch(
            "social.management.commands.publicar_social._public_url_for",
            side_effect=lambda p: f"https://x/{p.name}",
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.upload_story",
            new=upload_fake,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.wait_until_finished",
            return_value=None,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.publish_container",
            side_effect=lambda cid: f"pub-{cid}",
        ),
    ):
        out = io.StringIO()
        err = None
        try:
            with redirect_stdout(out):
                call_command(*argv, stdout=out)
        except CommandError as exc:
            err = exc
    return out.getvalue(), err


def _post():
    return SocialPost.objects.get(platform="instagram_story", tipus="top_ppcc")


def test_resumable_partial_leaves_error_and_exits_nonzero(top_ppcc):
    # Slide index 3 (story_3.jpg) fails → set incomplete. The row is ERROR
    # (not PUBLICAT) and the run exits non-zero.
    fake = _StoryUpload(fail_names={"story_3.jpg"})
    _out, err = _run_story(fake)
    assert err is not None  # CommandError → tq-run retries
    post = _post()
    assert post.status == SocialPost.STATUS_ERROR
    done = {d["idx"] for d in post.metadata["published_slides"]}
    assert done == {0, 1, 2, 4, 5, 6}  # the gap (idx 3) is not recorded
    assert len(post.metadata["story_ids"]) == 6


def test_resumable_reentry_backfills_only_the_gap(top_ppcc):
    # Run 1: idx 3 fails. Run 2: everything works → only idx 3 retried,
    # the other 6 skipped (no duplicate publish), set completes.
    _out, err = _run_story(_StoryUpload(fail_names={"story_3.jpg"}))
    assert err is not None and _post().status == SocialPost.STATUS_ERROR

    fake2 = _StoryUpload(tag="b")  # healthy, distinct id namespace
    _out2, err2 = _run_story(fake2)
    assert err2 is None
    post = _post()
    assert post.status == SocialPost.STATUS_PUBLICAT
    # Only the missing slide was re-uploaded.
    assert fake2.calls == ["https://x/story_3.jpg"]
    story_ids = post.metadata["story_ids"]
    assert len(story_ids) == 7
    assert len(set(story_ids)) == 7  # no duplicate publishes
    # The 6 originals kept their run-1 ids; only idx 3 got a fresh one.
    assert story_ids[3] == "pub-cid-b-1"
    assert story_ids[0] == "pub-cid-a-1"
    assert {d["idx"] for d in post.metadata["published_slides"]} == set(range(7))


def test_resumable_full_success_marks_publicat(top_ppcc):
    fake = _StoryUpload()  # all healthy
    _out, err = _run_story(fake)
    assert err is None
    post = _post()
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert len(fake.calls) == 7
    assert len(post.metadata["published_slides"]) == 7


def test_resumable_force_republishes_all_without_skipping(top_ppcc):
    # A completed set re-run with --force must NOT read the resume state
    # and skip slides: it re-publishes the whole set (legacy --force).
    _out, err = _run_story(_StoryUpload())
    assert err is None and _post().status == SocialPost.STATUS_PUBLICAT

    fake2 = _StoryUpload()
    _out2, err2 = _run_story(fake2, force=True)
    assert err2 is None
    assert len(fake2.calls) == 7  # all seven re-published, none skipped
