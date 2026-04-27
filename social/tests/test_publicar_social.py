"""Sprint I — `publicar_social` command + companion modules.

Covers:
  - Phase gating (kill switch + min_fase per slot)
  - Idempotency: a publicat row isn't re-published unless --force
  - DRY_RUN: full pipeline (renderer + client) but no real API
  - Calendari resolution (territorial rotation)
  - Captions: hashtag composition, mention extraction, length cap
"""

from __future__ import annotations

import datetime
import io
from contextlib import redirect_stdout

import pytest
from django.core.management import call_command

from ingesta.social import calendari, captions
from music.models import Album, Artista, Canco
from ranking.models import ConfiguracioGlobal, TopSetmanal
from social.models import SocialPost

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
def cfg_phase_1(db):
    cfg = ConfiguracioGlobal.load()
    cfg.fase_distribucio = 1
    cfg.instagram_actiu = True
    cfg.story_max_cancons_ppcc = 5  # keep tests fast
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


def test_phase_gate_blocks_above_min_fase(db, cfg_phase_1, setmana_with_top):
    cfg_phase_1.fase_distribucio = 1
    cfg_phase_1.save()
    # Wednesday entries need fase ≥ 2 → must be omès.
    out = io.StringIO()
    with redirect_stdout(out):
        call_command(
            "publicar_social", "--data", "2026-04-22", "--dry-run"  # Wednesday
        )
    text = out.getvalue()
    assert "omès" in text or "omes" in text or "min_fase" in text


def test_phase_1_publishes_saturday_dryrun(db, cfg_phase_1, setmana_with_top):
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


def test_kill_switch_short_circuits(db, cfg_phase_1, setmana_with_top):
    # Disable globally; even live mode wouldn't publish.
    cfg_phase_1.instagram_actiu = False
    cfg_phase_1.save()
    out = io.StringIO()
    with redirect_stdout(out):
        # NO --dry-run on purpose: kill switch should stop before any side effect.
        call_command("publicar_social", "--data", "2026-04-25")
    assert "Kill switch" in out.getvalue()


def test_idempotent_does_not_repost_when_already_publicat(
    db, cfg_phase_1, setmana_with_top
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


def test_force_republishes_even_if_publicat(db, cfg_phase_1, setmana_with_top):
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
    text = out.getvalue()
    assert "renderitzades" in text


def test_no_data_marks_omes(db, cfg_phase_1):
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
