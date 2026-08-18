"""Sprint I — `publicar_social` command + companion modules.

Covers:
  - Kill switch (master + per-channel) short-circuit
  - Idempotency: a publicat row isn't re-published unless --force
  - DRY_RUN: full pipeline (renderer + client) but no real API
  - Calendari resolution (territorial rotation)
  - Captions: hashtag composition, mention extraction, length cap
"""

from __future__ import annotations

import datetime
import io
import re
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest
from django.core.management import call_command

from music.models import Album, Artista, Canco
from ranking.models import ConfiguracioGlobal, TopSetmanal
from social import calendari, captions
from social.models import SocialPost

# ── Public media URL (Caddy static vs Django fallback) ────────────────


def test_public_url_for_uses_caddy_static_not_django_fallback():
    """Regression (2026-06-03): the social publish commands run under
    `production` settings. `SOCIAL_PUBLIC_BASE` must be inherited there
    — it now lives in `base.py` — so `_public_url_for` builds the Caddy
    `/static/social/` URL. If it slips back to `web_server`-only, the
    commands fall through to the header-laden Django
    `/api/v1/social/render` view, which Meta rejects with code 9004 and
    Telegram with WEBPAGE_MEDIA_EMPTY. The publish-flow tests below MOCK
    `_public_url_for`, so they never caught this — this calls it for
    real."""
    from pathlib import Path

    from social.management.commands.publicar_social import _public_url_for

    name = "feed_top_territorial_BAL_2026-05-25_00.jpg"
    url = _public_url_for(Path(name))
    assert url == f"https://www.topquaranta.cat/static/social/{name}"
    assert "/api/v1/social/render" not in url


# ── Calendari ─────────────────────────────────────────────────────────


def test_calendari_saturday_returns_ppcc_slots(db):
    sat = datetime.date(2026, 4, 25)  # a Saturday
    slots = calendari.slots_for(sat)
    assert any(s[0].tipus == SocialPost.TIPUS_TOP_PPCC for s in slots)
    assert all(s[1] == "PPCC" for s in slots)


def test_calendari_wednesday_rotates_territoris(db):
    # Three consecutive Wednesdays → three different territoris.
    seen = set()
    for d in (
        datetime.date(2026, 4, 1),
        datetime.date(2026, 4, 8),
        datetime.date(2026, 4, 15),
    ):
        for s, ter in calendari.slots_for(d):
            if s.tipus == SocialPost.TIPUS_TOP_TERRITORIAL:
                seen.add(ter)
    assert seen.issubset({"CAT", "VAL", "BAL"}) and len(seen) == 3


def test_calendari_monday_uses_different_territori_than_wednesday(db):
    monday = datetime.date(2026, 4, 27)
    wed = monday + datetime.timedelta(days=2)
    mon_terrs = {
        ter
        for s, ter in calendari.slots_for(monday)
        if s.tipus == SocialPost.TIPUS_TOP_TERRITORIAL
    }
    wed_terrs = {
        ter
        for s, ter in calendari.slots_for(wed)
        if s.tipus == SocialPost.TIPUS_TOP_TERRITORIAL
    }
    assert mon_terrs and wed_terrs and mon_terrs.isdisjoint(wed_terrs)


# ── Captions ──────────────────────────────────────────────────────────


def test_caption_top_includes_hashtags_and_mentions():
    setmana = datetime.date(2026, 4, 20)
    entries = [
        {
            "posicio": 1,
            "canco_nom": "Alba",
            "artista_nom": "Suc i Sopes",
            "artista_instagram_url": "https://instagram.com/sucisopes/",
        }
    ]
    text = captions.caption_top("top_ppcc", "PPCC", setmana, entries)
    assert "#topquaranta" in text
    assert "Països Catalans" not in text
    assert "PaïsosCatalans" not in text
    # When we have an IG handle the caption uses it *instead* of the
    # display name (autolinks + notifies the artist on publish).
    assert "@sucisopes" in text
    assert "Suc i Sopes" not in text


def test_caption_truncates_to_2200_chars():
    setmana = datetime.date(2026, 4, 20)
    entries = [
        {
            "posicio": i,
            "canco_nom": f"Cançó {i} amb un nom moltíssim llarg",
            "artista_nom": f"Artista {i}",
            "artista_instagram_url": "",
        }
        for i in range(1, 100)
    ]
    text = captions.caption_top("top_ppcc", "PPCC", setmana, entries)
    assert len(text) <= 2200


def test_caption_drops_malformed_handle():
    setmana = datetime.date(2026, 4, 20)
    entries = [
        {
            "posicio": 1,
            "canco_nom": "X",
            "artista_nom": "Y",
            "artista_instagram_url": "https://example.com/foo?bar=baz",
        }
    ]
    text = captions.caption_top("top_ppcc", "PPCC", setmana, entries)
    # Malformed URL → no @handle extractable, fall back to the display
    # name. Body line should contain "Y" and zero @ mentions.
    body = text.split("\n\n")[1]
    assert "@" not in body
    assert "Y" in body


# ── publicar_social: real DB → render → DRY publish ──────────────────


@pytest.fixture
def cfg_ig_on(db):
    cfg = ConfiguracioGlobal.load()
    cfg.instagram_actiu = True
    cfg.save()
    return cfg


@pytest.fixture
def setmana_with_top(db):
    """Create the minimum data the publicar_social command needs to
    actually render: 5 ranked tracks under PPCC for a saturday."""
    setmana = datetime.date(2026, 4, 20)  # Monday of week 17
    artista = Artista.objects.create(nom="A", slug="a", aprovat=True)
    album = Album.objects.create(nom="Alb", slug="alb", artista=artista)
    for i in range(1, 6):
        c = Canco.objects.create(
            nom=f"Cançó {i}",
            slug=f"canco-{i}",
            artista=artista,
            album=album,
            verificada=True,
            activa=True,
        )
        TopSetmanal.objects.create(
            canco=c,
            territori="PPCC",
            setmana=setmana,
            posicio=i,
            score_setmanal=10 - i,
        )
    return setmana


def test_phase_1_publishes_saturday_dryrun(db, cfg_ig_on, setmana_with_top):
    out = io.StringIO()
    with redirect_stdout(out):
        call_command("publicar_social", "--data", "2026-04-25", "--dry-run")  # Saturday
    text = out.getvalue()
    assert "renderitzades" in text
    posts = SocialPost.objects.filter(setmana=setmana_with_top)
    assert posts.filter(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED, tipus=SocialPost.TIPUS_TOP_PPCC
    ).exists()
    assert posts.filter(
        platform=SocialPost.PLATFORM_INSTAGRAM_STORY, tipus=SocialPost.TIPUS_TOP_PPCC
    ).exists()


def test_kill_switch_short_circuits(db, cfg_ig_on, setmana_with_top):
    # Disable globally; even live mode wouldn't publish.
    # Property: with the channel switch off (and NO --dry-run) the run has
    # no side effect at all — no SocialPost row is created and neither the
    # renderer nor the Instagram client is ever touched.
    cfg_ig_on.instagram_actiu = False
    cfg_ig_on.save()
    with (
        patch("social.management.commands.publicar_social.renderer") as renderer_mod,
        patch("social.management.commands.publicar_social.instagram_client") as ig_mod,
    ):
        # NO --dry-run on purpose: kill switch should stop before any side effect.
        call_command("publicar_social", "--data", "2026-04-25")
    assert not SocialPost.objects.filter(setmana=setmana_with_top).exists()
    assert not renderer_mod.mock_calls
    assert not ig_mod.mock_calls


def test_idempotent_does_not_repost_when_already_publicat(
    db, cfg_ig_on, setmana_with_top
):
    setmana = setmana_with_top
    # Pretend a post is already published.
    p = SocialPost.objects.create(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="PPCC",
        setmana=setmana,
        status=SocialPost.STATUS_PUBLICAT,
        instagram_media_id="manual-test",
    )
    out = io.StringIO()
    with redirect_stdout(out):
        call_command(
            "publicar_social",
            "--data",
            "2026-04-25",
            "--platform",
            "instagram_feed",
            "--dry-run",
        )
    p.refresh_from_db()
    assert "ja publicat" in out.getvalue()
    assert p.instagram_media_id == "manual-test"


def test_force_republishes_even_if_publicat(db, cfg_ig_on, setmana_with_top):
    # Property: --force re-processes a row that is already `publicat`
    # (the idempotency skip does not apply): the pipeline runs again and
    # the same row is re-marked with freshly rendered slides.
    setmana = setmana_with_top
    p = SocialPost.objects.create(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
        tipus=SocialPost.TIPUS_TOP_PPCC,
        territori="PPCC",
        setmana=setmana,
        status=SocialPost.STATUS_PUBLICAT,
        instagram_media_id="manual-test",
    )
    out = io.StringIO()
    with redirect_stdout(out):
        call_command(
            "publicar_social",
            "--data",
            "2026-04-25",
            "--platform",
            "instagram_feed",
            "--force",
            "--dry-run",
        )
    p.refresh_from_db()
    assert p.metadata.get("dry_run") is True  # the row was re-processed
    assert p.metadata.get("slides")  # ≥1 slide re-rendered
    assert (
        SocialPost.objects.filter(
            platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
            tipus=SocialPost.TIPUS_TOP_PPCC,
            setmana=setmana,
        ).count()
        == 1
    )  # same row, no duplicate


def test_no_data_marks_omes(db, cfg_ig_on):
    """Saturday with no TopSetmanal rows → marks omes."""
    out = io.StringIO()
    with redirect_stdout(out):
        call_command(
            "publicar_social",
            "--data",
            "2026-04-25",
            "--platform",
            "instagram_feed",
            "--dry-run",
        )
    p = SocialPost.objects.filter(
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
        tipus=SocialPost.TIPUS_TOP_PPCC,
    ).first()
    assert p is not None
    assert p.status == SocialPost.STATUS_OMES


# ── slide_alts (a11y) ──────────────────────────────────────────────


def test_slide_alts_top_portada_mentions_territory_and_week():
    setmana = datetime.date(2026, 4, 27)
    alts = captions.slide_alts(
        "top_territorial",
        "CAT",
        setmana,
        [{"posicio": 1, "canco_nom": "X", "artista_nom": "Y"}],
        n_slides=2,
    )
    assert "Catalunya" in alts[0]
    assert "Portada" in alts[0]


def test_slide_alts_top_list_lists_entries_with_positions():
    # Property: the list-slide alt names EVERY entry on that slide
    # (song + artist), and states the position range covered — first and
    # last positions appear — without pinning the exact copy.
    setmana = datetime.date(2026, 4, 27)
    entries = [
        {"posicio": i, "canco_nom": f"Cançó {i}", "artista_nom": f"Artista {i}"}
        for i in range(1, 11)
    ]
    alts = captions.slide_alts("top_territorial", "CAT", setmana, entries, n_slides=2)
    assert len(alts) == 2
    alt = alts[1]
    for e in entries:
        assert e["canco_nom"] in alt
        assert e["artista_nom"] in alt
    # The song and its artist are named together (song before artist).
    assert re.search(r"Cançó 7\b[^\d]*Artista 7\b", alt)
    # The position range covered (1..10) is stated in the header, i.e.
    # before the first entry is listed.
    header = alt[: alt.index("Cançó 1")]
    assert re.search(r"\b1\b", header) and re.search(r"\b10\b", header)


def test_slide_alts_novetats_albums_one_per_slide():
    setmana = datetime.date(2026, 4, 27)
    items = [
        {"nom": "Àlbum A", "artista_nom": "Artista A"},
        {"nom": "Àlbum B", "artista_nom": "Artista B"},
    ]
    alts = captions.slide_alts("nous_albums", "", setmana, items, n_slides=3)
    assert "Nous àlbums" in alts[0]
    assert "Àlbum A" in alts[1] and "Artista A" in alts[1]
    assert "Àlbum B" in alts[2] and "Artista B" in alts[2]


def test_slide_alts_novetats_singles_bin_packs():
    setmana = datetime.date(2026, 4, 27)
    items = [{"nom": f"Single {i}", "artista_nom": f"Art {i}"} for i in range(1, 13)]
    # 12 singles, 2 list slides + portada → 6 per slide
    alts = captions.slide_alts("nous_singles", "", setmana, items, n_slides=3)
    assert "Single 1" in alts[1]
    assert "Single 12" in alts[2]


def test_slide_alts_pads_to_n_slides():
    setmana = datetime.date(2026, 4, 27)
    out = captions.slide_alts("top_territorial", "CAT", setmana, [], n_slides=4)
    assert len(out) == 4


# ── _slide_tags coordinate dispersion ──────────────────────────────


def test_slide_tags_top_spreads_y_per_row():
    from social.management.commands.publicar_social import Command

    entries = [
        {"posicio": i, "artista_instagram_url": f"https://instagram.com/a{i}"}
        for i in range(1, 11)
    ]
    out = Command._slide_tags("top_ppcc", n_slides=2, data={"entries": entries})
    list_slide_tags = out[1]
    ys = [t["y"] for t in list_slide_tags]
    assert len(set(ys)) == len(ys), "every row should land at a different Y"
    assert all(0.05 <= y <= 0.95 for y in ys), "Y must be within Meta's bounds"


def test_slide_tags_album_slide_tags_principal():
    from social.management.commands.publicar_social import Command

    items = [{"artista_instagram_url": "https://instagram.com/banda"}]
    out = Command._slide_tags("nous_albums", n_slides=2, data={"items": items})
    # One album slide, one tag for the album artist, placed within the
    # canvas (exact bubble coords are cosmetic — see `_row_xy`).
    assert len(out[1]) == 1
    tag = out[1][0]
    assert tag["username"] == "banda"
    assert 0.05 <= tag["x"] <= 0.95 and 0.05 <= tag["y"] <= 0.95


def test_slide_tags_cover_slide_has_no_tags():
    from social.management.commands.publicar_social import Command

    entries = [
        {"posicio": 1, "artista_instagram_url": "https://instagram.com/a"},
    ]
    out = Command._slide_tags("top_ppcc", n_slides=2, data={"entries": entries})
    assert out[0] == []


def test_story_set_counts_as_one_publication(db, cfg_ig_on, setmana_with_top):
    """Bug 2 of Fase 3 audit (2026-05-18): a story-set is ONE
    publication conceptually, regardless of how many slides it
    carries. Same treatment as an IG feed carousel (1 publication
    with N images). The previous `n=len(story_ids)` over-counted by
    42× for a top story-set."""
    import pathlib
    from unittest.mock import patch

    register_calls = []

    def _capture_register(clau, dim1="", dim2="", n=1, **kwargs):
        register_calls.append({"clau": clau, "dim1": dim1, "dim2": dim2, "n": n})

    fake_paths = [pathlib.Path(f"/tmp/story_{i}.png") for i in range(5)]

    with (
        patch(
            # Saturday → PPCC, which renders the 7-slide editorial set
            # via render_stories_ppcc (Step 3b). Patched to fixed paths
            # so the counter assertion stays decoupled from slide count.
            "social.management.commands.publicar_social.renderer.render_stories_ppcc",
            return_value=fake_paths,
        ),
        patch(
            "social.management.commands.publicar_social._public_url_for",
            side_effect=lambda p: f"https://www.topquaranta.cat/static/social/{p.name}",
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.upload_story",
            return_value="container-xyz",
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.wait_until_finished",
            return_value=None,
        ),
        patch(
            "social.management.commands.publicar_social.instagram_client.publish_container",
            side_effect=[f"sid-{i}" for i in range(5)],
        ),
        patch("analytics.events.register", side_effect=_capture_register),
    ):
        call_command(
            "publicar_social",
            "--data",
            "2026-04-25",  # Saturday: Saturday slots include instagram_story
            "--platform",
            "instagram_story",
        )

    # Among all register() calls, the social_publicat row for
    # instagram_story must have n=1, not 5.
    story_calls = [
        c
        for c in register_calls
        if c["clau"] == "social_publicat" and c["dim1"] == "instagram_story"
    ]
    assert len(story_calls) >= 1, register_calls
    for call in story_calls:
        assert call["n"] == 1, (
            f"Story-set incremented counter by {call['n']}, expected 1. "
            "Bug 2 of Fase 3 reintroduced."
        )


# ── Exit non-zero on partial failure (2026-07 invisible-outage fix) ────


def test_publicar_social_partial_failure_exits_nonzero(db, cfg_ig_on, setmana_with_top):
    """A per-slot publish failure marks the SocialPost ERROR AND makes the
    command exit non-zero (CommandError) so tq-run records status=FAIL —
    the bug that hid the IG outage. Already-attempted slots stay recorded."""
    from unittest.mock import patch

    from django.core.management.base import CommandError

    from social.management.commands.publicar_social import Command

    with (
        patch.object(Command, "_publish_feed", side_effect=RuntimeError("boom")),
        patch.object(Command, "_publish_story", side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(CommandError):
            call_command("publicar_social", "--data", "2026-04-25")  # Saturday
    errs = SocialPost.objects.filter(
        setmana=setmana_with_top, status=SocialPost.STATUS_ERROR
    )
    assert errs.count() == 2  # feed + story, both recorded as ERROR


def test_publicar_social_all_ok_exits_zero(db, cfg_ig_on, setmana_with_top):
    """No slot failure → no CommandError (exit 0), unchanged behaviour."""
    from unittest.mock import patch

    from social.management.commands.publicar_social import Command

    with (
        patch.object(Command, "_publish_feed"),
        patch.object(Command, "_publish_story"),
    ):
        call_command("publicar_social", "--data", "2026-04-25")  # must NOT raise


def test_publicar_canal_channel_failure_exits_nonzero(db, cfg_ig_on, setmana_with_top):
    """Same guarantee on the multi-channel command: a failing channel
    exits non-zero + leaves the SocialPost ERROR."""
    from unittest.mock import patch

    from django.core.management.base import CommandError

    from ranking.models import MatriuPublicacio
    from social.management.commands.publicar_canal import Command

    cfg_ig_on.distribucio_activa = True
    cfg_ig_on.mastodon_actiu = True
    cfg_ig_on.save()
    with (
        patch.object(MatriuPublicacio, "actiu_per", return_value=True),
        patch.object(Command, "_publish_mastodon", side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(CommandError):
            call_command(
                "publicar_canal", "--channel", "mastodon", "--data", "2026-04-25"
            )
    assert SocialPost.objects.filter(
        setmana=setmana_with_top,
        platform="mastodon",
        status=SocialPost.STATUS_ERROR,
    ).exists()
