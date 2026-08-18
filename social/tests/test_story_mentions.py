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
import logging
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


_STORY_BUILDERS = (
    "_story_intro_ppcc",
    "_story_top_mosaic",
    "_story_top_pairs",
    "_story_top_grid",
    "_story_podi",
    "_story_hero",
    "_story_novetats",
    "_story_outro_ppcc",
)


def _renderer_visible(monkeypatch, tmp_path, territori, entries, novetats):
    """Run the real story orchestrator with the slide builders spied on and
    return, per emitted slide, the set of IG usernames of the items the
    renderer actually passed to that slide's builder. This is the oracle:
    whatever the renderer draws on slide k is what slide k must tag."""
    from PIL import Image

    from social.captions import instagram_username

    seen: list[set[str]] = []

    def _spy(*args, **kwargs):
        names: set[str] = set()
        for arg in args:
            items = arg if isinstance(arg, list) else [arg]
            for it in items:
                if isinstance(it, dict):
                    for u in it.get("artistes_instagram_urls") or []:
                        names.add(instagram_username(u))
        seen.append(names)
        return Image.new("RGB", (1, 1))

    for attr in _STORY_BUILDERS:
        monkeypatch.setattr(renderer, attr, _spy)
    monkeypatch.setattr(
        renderer,
        "_path",
        lambda tipus, territori, setmana, idx, story=False: tmp_path / f"{idx}.jpg",
    )
    if territori == "PPCC":
        paths = renderer.render_stories_ppcc(SETMANA, entries, novetats_items=novetats)
    else:
        paths = renderer.render_stories_territorial(
            territori, SETMANA, entries, novetats_items=novetats
        )
    assert len(paths) == len(seen)
    return seen


@pytest.mark.parametrize(
    "territori,n,n_nov",
    [
        ("PPCC", 40, 2),  # full set incl. novetats
        ("PPCC", 2, 0),  # short top: PPCC still emits every tier
        ("BAL", 8, 0),  # territorial degraded tiers (no mosaic, no pairs)
    ],
)
def test_story_tags_match_renderer_visible_songs(
    monkeypatch, tmp_path, territori, n, n_nov
):
    """Each story tags exactly the songs visible on it — no more, no less —
    and there is one tag set per rendered slide.

    Property asserted now (rewrite 2026-08-18; merges the former
    test_ppcc_full_set_composition, test_ppcc_tiers_emitted_even_when_short
    and test_territorial_degraded_tiers_alignment): the expected per-slide
    handle sets are DERIVED from the real orchestrator (builders spied),
    so no slide count, tier index or draw order is pinned here; each tag
    set is compared as a set and stays within Meta's 20-tag cap. The
    within-slide draw order is a separate promise (feed tagger tests)."""
    entries = _entries(n)
    novetats = _novetats(n_nov) if n_nov else None
    visible = _renderer_visible(monkeypatch, tmp_path, territori, entries, novetats)
    tags = PubCmd._story_tags(territori, entries, novetats)
    assert len(tags) == len(visible), (len(tags), len(visible))
    assert tags[0] == [] and tags[-1] == []  # intro/outro: no songs → no tags
    for k, (slide, expected) in enumerate(zip(tags, visible)):
        assert set(_usernames(slide)) == expected, (k, _usernames(slide), expected)
        assert len(slide) <= 20
    # …and the tags do reach the songs: with 40 entries every handle appears.
    if n == 40:
        assert set().union(*map(set, map(_usernames, tags))) >= {
            f"p{i}" for i in range(1, 41)
        }


def test_ppcc_collaborator_included_on_the_same_story():
    tags = PubCmd._story_tags("PPCC", _entries(5, collabs_on=(2,)), None)
    # Podi story carries #3, #2 AND #2's collaborator; nobody else.
    podi = _usernames(tags[4])
    assert set(podi) == {"p3", "p2", "c2"}
    hero = _usernames(tags[5])
    assert hero == ["p1"]


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
        cid, dropped = cmd._create_story_with_guard("https://x/s1.jpg", tags)
    assert cid == "story-cid"
    assert dropped == ["dolent"]
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
        cid, dropped = cmd._create_story_with_guard("https://x/s1.jpg", tags)
    assert cid == "story-cid"
    assert sorted(dropped) == ["a", "b"]
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


def _run_story(upload_story_fake, n_paths=7):
    """Run the Saturday PPCC STORY slot with renderer + client mocked.
    7 fake paths = the no-novetats PPCC set, aligned with the tagger."""
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
    """Wiring: the per-story tags computed by `_story_tags` reach
    `upload_story` (one upload per rendered story), intro/outro go out
    untagged, and the slot records how many mentions it sent.

    Property asserted now (rewrite 2026-08-18): the union of usernames
    across all uploads is exactly the top's handle set (every artist
    mentioned once, nobody invented), first/last uploads carry no tags,
    and `n_mencions` equals the number of tags actually sent — no
    per-index call lists, no literal 4."""
    fake = _CapturingUpload()
    _out, err = _run_story(fake)
    assert err is None
    post = SocialPost.objects.get(platform="instagram_story", tipus="top_ppcc")
    assert post.status == SocialPost.STATUS_PUBLICAT
    n_paths = 7  # `_run_story` default: the no-novetats PPCC set
    assert len(post.metadata["story_ids"]) == n_paths == len(fake.calls)
    # intro (first) and outro (last) untagged.
    assert fake.calls[0][1] == [] and fake.calls[-1][1] == []
    sent = [u for _url, names in fake.calls for u in names]
    expected = {f"p{i}" for i in range(1, 5)}  # the 4 cançons of the fixture
    assert set(sent) == expected and len(sent) == len(expected)  # each once
    assert post.metadata["n_mencions"] == len(sent)


def test_one_failed_story_never_blocks_the_rest(top_ppcc):
    # Page 3 (grid) dies even untagged → guard exhausts, page is skipped,
    # the other 6 publish. The set is incomplete so the slot is ERROR
    # (resumable: tq-run's retry backfills the gap) and the run exits
    # non-zero — the 6 that went out are NOT rolled back.
    fake = _CapturingUpload(fail_url="story_3.jpg")
    _out, err = _run_story(fake)
    assert err is not None  # CommandError → exit non-zero
    post = SocialPost.objects.get(platform="instagram_story", tipus="top_ppcc")
    assert post.status == SocialPost.STATUS_ERROR
    assert len(post.metadata["story_ids"]) == 6
    assert {d["idx"] for d in post.metadata["published_slides"]} == {0, 1, 2, 4, 5, 6}
    fallides = post.metadata["stories_fallides"]
    assert len(fallides) == 1 and fallides[0]["story"] == "story_3.jpg"
    assert "pendents" in post.error_msg


def test_tag_slide_mismatch_publishes_untagged(top_ppcc):
    # 9 fake paths ≠ 7 tag sets → defensive fallback: everything
    # publishes with NO mentions rather than mis-anchored ones.
    fake = _CapturingUpload()
    _out, err = _run_story(fake, n_paths=9)
    assert err is None
    post = SocialPost.objects.get(platform="instagram_story", tipus="top_ppcc")
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert len(post.metadata["story_ids"]) == 9
    assert all(names == [] for _url, names in fake.calls)
