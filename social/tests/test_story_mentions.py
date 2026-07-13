"""Per-story `user_tags` on the pipeline story sets (PPCC + territorial).

Covers the pure tagger (`_story_tags`): slide alignment with the
renderer's emission (including the territorial degraded tiers), the
visible-songs-only rule, coordinate clamping and the 20-tag cap; the
non-blocking guard reuse (`_create_story_with_guard`); and the
publish-loop isolation (one failed story never blocks the rest).
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
from social import renderer
from social.management.commands.publicar_social import Command as PubCmd
from social.models import SocialPost

SETMANA = datetime.date(2026, 4, 20)
SATURDAY = "2026-04-25"


def _entries(n=40, *, with_handles=True, collabs_on=()):
    """Payload-shaped top entries. `collabs_on` = posicions (1-based)
    that carry one extra collaborator handle."""
    out = []
    for i in range(n):
        pos = i + 1
        urls = [f"https://instagram.com/p{pos}/"] if with_handles else []
        if pos in collabs_on:
            urls.append(f"https://instagram.com/c{pos}/")
        out.append(
            {
                "posicio": pos,
                "canco_nom": f"Cançó {pos}",
                "artista_nom": f"Artista {pos}",
                "artistes_noms": [f"Artista {pos}"],
                "artistes_instagram_urls": urls,
                "cover_url": None,
                "album_deezer_id": None,
            }
        )
    return out


def _novetats(n=2):
    return [
        {
            "nom": f"Novetat {i + 1}",
            "slug": f"novetat-{i + 1}",
            "artista_nom": f"Banda {i + 1}",
            "artistes_instagram_urls": [f"https://instagram.com/nov{i + 1}/"],
            "cover_url": None,
            "album_deezer_id": None,
            "dies": i,
        }
        for i in range(n)
    ]


def _usernames(tags):
    return [t["username"] for t in tags]


# ── _story_tags: composition ─────────────────────────────────────────


def test_ppcc_full_set_composition():
    tags = PubCmd._story_tags("PPCC", _entries(40), _novetats(2))
    # intro, mosaic, grid, podi, hero, novetats, outro
    assert len(tags) == 7
    assert tags[0] == [] and tags[6] == []  # intro/outro: no songs → no tags
    # Mosaic = entries 11-40 in draw order (40 first), capped at 20.
    assert len(tags[1]) == 20
    assert tags[1][0]["username"] == "p40"
    # Grid = entries 4-10, drawn 10→4.
    assert _usernames(tags[2]) == ["p10", "p9", "p8", "p7", "p6", "p5", "p4"]
    # Podi = #3 then #2 (draw order).
    assert _usernames(tags[3]) == ["p3", "p2"]
    # Hero = #1 only.
    assert _usernames(tags[4]) == ["p1"]
    # Novetats slide mentions only the visible releases.
    assert _usernames(tags[5]) == ["nov1", "nov2"]


def test_ppcc_collaborator_included_on_the_same_story():
    tags = PubCmd._story_tags("PPCC", _entries(5, collabs_on=(2,)), None)
    # Podi story carries #3, #2 AND #2's collaborator; nobody else.
    podi = _usernames(tags[3])
    assert set(podi) == {"p3", "p2", "c2"}
    hero = _usernames(tags[4])
    assert hero == ["p1"]


def test_ppcc_tiers_emitted_even_when_short():
    """PPCC emits every tier unconditionally (mirrors
    `render_stories_ppcc`) — short slices give empty tag sets, and the
    count still matches the 6-slide no-novetats set."""
    tags = PubCmd._story_tags("PPCC", _entries(2), None)
    assert len(tags) == 6  # intro, mosaic, grid, podi, hero, outro
    assert tags[1] == [] and tags[2] == []  # empty slices → no tags
    assert _usernames(tags[3]) == ["p2"]  # podi holds only #2
    assert _usernames(tags[4]) == ["p1"]


def test_territorial_degraded_tiers_alignment():
    # n=8: no mosaic (needs n>10); grid, podi, hero present.
    tags = PubCmd._story_tags("BAL", _entries(8), None)
    assert len(tags) == 5  # intro, grid, podi, hero, outro
    assert _usernames(tags[1]) == ["p8", "p7", "p6", "p5", "p4"]
    assert _usernames(tags[2]) == ["p3", "p2"]
    assert _usernames(tags[3]) == ["p1"]


def test_territorial_alignment_against_real_renderer(monkeypatch, tmp_path):
    """The tag sets must line up 1:1 with the actually rendered slides —
    for the degraded territorial set AND the full PPCC set."""
    monkeypatch.setattr(
        renderer,
        "_path",
        lambda tipus, territori, setmana, idx, story=False: tmp_path
        / f"{tipus}_{territori}_{idx}.jpg",
    )
    entries = _entries(8)
    paths = renderer.render_stories_territorial("BAL", SETMANA, entries)
    assert len(PubCmd._story_tags("BAL", entries, None)) == len(paths)

    full = _entries(40)
    nov = _novetats(2)
    paths = renderer.render_stories_ppcc(SETMANA, full, novetats_items=nov)
    assert len(PubCmd._story_tags("PPCC", full, nov)) == len(paths)


def test_coordinates_clamped_and_capped():
    tags = PubCmd._story_tags("PPCC", _entries(40, collabs_on=range(1, 41)), None)
    for slide in tags:
        assert len(slide) <= 20
        for t in slide:
            assert 0.05 <= t["x"] <= 0.95
            assert 0.05 <= t["y"] <= 0.95


def test_no_handles_means_no_tags():
    tags = PubCmd._story_tags("PPCC", _entries(40, with_handles=False), None)
    assert all(slide == [] for slide in tags)


# ── guard reuse ──────────────────────────────────────────────────────


class _FakeUploadStory:
    """Captures upload_story calls; raises on any `bad` username in the
    user_tags payload (simulating Meta rejecting a mention)."""

    def __init__(self, bad=frozenset()):
        self.bad = set(bad)
        self.calls: list[list[str]] = []

    def __call__(self, image_url, *, user_tags=None):
        names = [t["username"] for t in (user_tags or [])]
        self.calls.append(names)
        for u in names:
            if u in self.bad:
                raise RuntimeError(f"IG API 400: invalid user {u}")
        return "story-cid"


def test_guard_drops_bad_mention_and_story_survives():
    fake = _FakeUploadStory(bad={"dolent"})
    cmd = PubCmd()
    cmd.stdout = io.StringIO()
    tags = [
        {"username": "bo", "x": 0.5, "y": 0.5},
        {"username": "dolent", "x": 0.5, "y": 0.6},
    ]
    with (
        patch(
            "social.management.commands.publicar_social.instagram_client.upload_story",
            new=fake,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.wait_until_finished",
            return_value=None,
        ),
    ):
        cid = cmd._create_story_with_guard("https://x/s1.jpg", tags)
    assert cid == "story-cid"
    assert fake.calls[-1] == ["bo"]  # retried without the offender


def test_guard_last_resort_publishes_untagged():
    fake = _FakeUploadStory(bad={"a", "b"})
    cmd = PubCmd()
    cmd.stdout = io.StringIO()
    tags = [
        {"username": "a", "x": 0.5, "y": 0.5},
        {"username": "b", "x": 0.5, "y": 0.6},
    ]
    with (
        patch(
            "social.management.commands.publicar_social.instagram_client.upload_story",
            new=fake,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.wait_until_finished",
            return_value=None,
        ),
    ):
        cid = cmd._create_story_with_guard("https://x/s1.jpg", tags)
    assert cid == "story-cid"
    assert fake.calls[-1] == []  # empty set = untagged story


# ── publish loop: wiring + isolation ─────────────────────────────────


@pytest.fixture
def top_ppcc(db):
    """Minimal consolidated PPCC top of 4 cançons with IG handles."""
    arts = []
    for i in range(1, 5):
        arts.append(
            Artista.objects.create(
                nom=f"P{i}",
                slug=f"p{i}",
                aprovat=True,
                instagram_url=f"https://instagram.com/p{i}/",
            )
        )
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
            canco=c,
            territori="PPCC",
            setmana=SETMANA,
            posicio=i,
            score_setmanal=10 - i,
        )
    cfg = ConfiguracioGlobal.load()
    cfg.instagram_actiu = True
    cfg.save()
    return arts


def _run_story(upload_story_fake, n_paths=6):
    """Run the Saturday PPCC STORY slot with renderer + client mocked.
    6 fake paths = the no-novetats PPCC set, aligned with the tagger."""
    paths = [pathlib.Path(f"story_{i}.jpg") for i in range(n_paths)]
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
            new=upload_story_fake,
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
                call_command(
                    "publicar_social",
                    "--data",
                    SATURDAY,
                    "--platform",
                    "instagram_story",
                    "--tipus",
                    "top_ppcc",
                    stdout=out,
                )
        except CommandError as exc:
            err = exc
    return out.getvalue(), err


class _CapturingUpload:
    """Records (image_url, usernames) per call; optionally always fails
    for a given URL (a whole-story failure, tags or not)."""

    def __init__(self, fail_url=None):
        self.fail_url = fail_url
        self.calls: list[tuple[str, list[str]]] = []
        self._n = 0

    def __call__(self, image_url, *, user_tags=None):
        self.calls.append((image_url, [t["username"] for t in (user_tags or [])]))
        if self.fail_url and image_url.endswith(self.fail_url):
            raise RuntimeError("IG API 500: transient")
        self._n += 1
        return f"cid-{self._n}"


def test_story_slot_sends_per_story_tags(top_ppcc):
    fake = _CapturingUpload()
    _out, err = _run_story(fake)
    assert err is None
    post = SocialPost.objects.get(platform="instagram_story", tipus="top_ppcc")
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert len(post.metadata["story_ids"]) == 6
    # 6 stories uploaded; intro (first) and outro (last) untagged.
    assert len(fake.calls) == 6
    assert fake.calls[0][1] == [] and fake.calls[-1][1] == []
    # n=4 top: mosaic + grid slides carry no handles; podi = #3,#2;
    # grid = #4 only; hero = #1.
    assert fake.calls[1][1] == []  # mosaic (entries 11-40 empty)
    assert fake.calls[2][1] == ["p4"]  # grid (drawn 10→4 → only #4)
    assert fake.calls[3][1] == ["p3", "p2"]  # podi
    assert fake.calls[4][1] == ["p1"]  # hero
    assert post.metadata["n_mencions"] == 4


def test_one_failed_story_never_blocks_the_rest(top_ppcc):
    # Page 3 (podi) dies even untagged → guard exhausts, page is
    # skipped, the other 5 publish; slot stays publicat but the run
    # exits non-zero (partial failure is reported, not rolled back).
    fake = _CapturingUpload(fail_url="story_3.jpg")
    _out, err = _run_story(fake)
    assert err is not None  # CommandError → exit non-zero
    post = SocialPost.objects.get(platform="instagram_story", tipus="top_ppcc")
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert len(post.metadata["story_ids"]) == 5
    fallides = post.metadata["stories_fallides"]
    assert len(fallides) == 1 and fallides[0]["story"] == "story_3.jpg"
    assert "stories han fallat" in post.error_msg


def test_tag_slide_mismatch_publishes_untagged(top_ppcc):
    # 9 fake paths ≠ 6 tag sets → defensive fallback: everything
    # publishes with NO mentions rather than mis-anchored ones.
    fake = _CapturingUpload()
    _out, err = _run_story(fake, n_paths=9)
    assert err is None
    post = SocialPost.objects.get(platform="instagram_story", tipus="top_ppcc")
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert len(post.metadata["story_ids"]) == 9
    assert all(names == [] for _url, names in fake.calls)
