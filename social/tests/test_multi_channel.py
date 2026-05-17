"""Sprint I bis — RSS feeds, short captions, publicar_canal command.

Covers the non-Instagram surfaces. Each test is self-contained
(creates its own minimal fixtures) so a failure points cleanly at
which channel broke.
"""

from __future__ import annotations

import datetime
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from ranking.models import ConfiguracioGlobal
from social import captions
from social.models import SocialPost

# ── caption_short ─────────────────────────────────────────────────────


def test_caption_short_top_fits_under_500_chars():
    setmana = datetime.date(2026, 4, 20)
    entries = [
        {
            "posicio": i,
            "canco_nom": f"Cançó número {i}",
            "artista_nom": f"Artista {i}",
            "artista_instagram_url": "",
        }
        for i in range(1, 11)
    ]
    text = captions.caption_short("top_ppcc", "PPCC", setmana, entries, max_chars=480)
    assert len(text) <= 480
    assert "topquaranta.cat" in text
    assert "Setmana" in text


def test_caption_short_uses_plain_name_not_handle():
    """Per the 2026-05-16 decision, caption_short emits the plain
    artist name on Mastodon/Bluesky/Telegram/Newsletter. The IG
    `@handle` only autolinks on Instagram; on the other networks it
    rendered as broken-looking literal text. caption_top keeps the
    handle (covered separately in test_captions.py)."""
    setmana = datetime.date(2026, 4, 20)
    entries = [
        {
            "posicio": 1,
            "canco_nom": "X",
            "artista_nom": "Y",
            "artista_instagram_url": "https://instagram.com/yhandle/",
        }
    ]
    text = captions.caption_short("top_ppcc", "PPCC", setmana, entries)
    assert "@yhandle" not in text
    assert "Y" in text


def test_caption_short_bluesky_300_char_cap():
    setmana = datetime.date(2026, 4, 20)
    entries = [
        {
            "posicio": i,
            "canco_nom": f"Una cançó molt llarga número {i}",
            "artista_nom": f"Un Nom Llarguíssim {i}",
            "artista_instagram_url": "",
        }
        for i in range(1, 11)
    ]
    text = captions.caption_short("top_ppcc", "PPCC", setmana, entries, max_chars=280)
    assert len(text) <= 280


# ── RSS feeds ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_rss_top_returns_atom(client):
    cfg = ConfiguracioGlobal.load()
    cfg.rss_actiu = True
    cfg.save()
    r = client.get("/rss/top.xml")
    assert r.status_code == 200
    assert "atom+xml" in r["content-type"]


@pytest.mark.django_db
def test_rss_kill_switch_returns_503(client):
    cfg = ConfiguracioGlobal.load()
    cfg.rss_actiu = False
    cfg.save()
    try:
        r = client.get("/rss/top.xml")
        assert r.status_code == 503
    finally:
        cfg.rss_actiu = True
        cfg.save()


# ── publicar_canal ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_publicar_canal_dry_run_creates_pendent_row():
    """Dry-run should populate a SocialPost row even if the relevant
    auth singleton is empty — that's the whole point of dry-run."""
    cfg = ConfiguracioGlobal.load()
    cfg.mastodon_actiu = True
    cfg.save()

    with patch("social.payload.build_top") as fake_top:
        fake_top.return_value = {
            "entries": [
                {
                    "posicio": 1,
                    "canco_nom": "Demo",
                    "artista_nom": "Artista",
                    "artista_instagram_url": "",
                    "cover_url": None,
                }
            ],
            "hero_cover_url": None,
        }
        out = StringIO()
        call_command(
            "publicar_canal",
            "--channel",
            "mastodon",
            "--data",
            "2026-04-25",  # Saturday → top_ppcc slot
            "--dry-run",
            "--force",
            stdout=out,
        )
    assert SocialPost.objects.filter(
        platform=SocialPost.PLATFORM_MASTODON,
        tipus=SocialPost.TIPUS_TOP_PPCC,
    ).exists()


@pytest.mark.django_db
def test_publicar_canal_telegram_dry_run():
    """Telegram should accept the same flow and create a SocialPost
    row with platform=telegram in dry-run mode."""
    cfg = ConfiguracioGlobal.load()
    cfg.telegram_actiu = True
    cfg.save()
    with patch("social.payload.build_top") as fake_top:
        fake_top.return_value = {
            "entries": [
                {
                    "posicio": 1,
                    "canco_nom": "Demo",
                    "artista_nom": "X",
                    "artista_instagram_url": "",
                    "cover_url": None,
                }
            ],
            "hero_cover_url": None,
        }
        out = StringIO()
        call_command(
            "publicar_canal",
            "--channel",
            "telegram",
            "--data",
            "2026-04-25",
            "--dry-run",
            "--force",
            stdout=out,
        )
    assert SocialPost.objects.filter(
        platform=SocialPost.PLATFORM_TELEGRAM,
        tipus=SocialPost.TIPUS_TOP_PPCC,
    ).exists()


@pytest.mark.django_db
def test_publicar_canal_kill_switch_blocks_real_run():
    cfg = ConfiguracioGlobal.load()
    cfg.bluesky_actiu = False
    cfg.save()
    out = StringIO()
    call_command(
        "publicar_canal",
        "--channel",
        "bluesky",
        "--data",
        "2026-04-25",
        stdout=out,
    )
    assert "Kill switch" in out.getvalue()
    assert not SocialPost.objects.filter(platform=SocialPost.PLATFORM_BLUESKY).exists()
