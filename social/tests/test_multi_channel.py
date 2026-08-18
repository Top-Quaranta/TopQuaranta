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


@pytest.mark.django_db
def test_master_switch_blocks_newsletter_real_run():
    """The headline fix (2026-06-07): the master `distribucio_activa`
    now gates the newsletter, which the old IG-only pause never did."""
    cfg = ConfiguracioGlobal.load()
    cfg.distribucio_activa = False
    cfg.newsletter_actiu = True  # channel ON; master must still block it
    cfg.save()
    out = StringIO()
    call_command(
        "publicar_canal",
        "--channel",
        "newsletter",
        "--data",
        "2026-04-25",
        stdout=out,
    )
    assert "mestre" in out.getvalue().lower()
    assert not SocialPost.objects.filter(
        platform=SocialPost.PLATFORM_NEWSLETTER
    ).exists()


@pytest.mark.django_db
def test_master_switch_blocks_rss_feed(client):
    """Master off → RSS feeds 503 even with rss_actiu True."""
    cfg = ConfiguracioGlobal.load()
    cfg.distribucio_activa = False
    cfg.rss_actiu = True
    cfg.save()
    resp = client.get("/rss/top.xml")
    assert resp.status_code == 503
