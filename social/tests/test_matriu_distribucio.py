"""Guards for the distribution matrix (`MatriuPublicacio`) — the third
gate (canal × tipus) over the master switch and the per-channel switches.

NEVER triggers a real publication or newsletter send: the newsletter
guard mocks `send_top_newsletter` and asserts it is not called; the
publish-command guards run with `--dry-run`.
"""

from __future__ import annotations

import datetime
import io
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from music.models import Album, Artista, Canco, StaffAuditLog
from ranking.models import ConfiguracioGlobal, MatriuPublicacio, TopSetmanal
from social.models import SocialPost

SETMANA = datetime.date(2026, 4, 20)  # Monday of the TQ week (Sat 2026-04-25)
SATURDAY = "2026-04-25"


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def cfg_all_on(db):
    cfg = ConfiguracioGlobal.load()
    cfg.distribucio_activa = True
    cfg.instagram_actiu = True
    cfg.mastodon_actiu = True
    cfg.bluesky_actiu = True
    cfg.telegram_actiu = True
    cfg.newsletter_actiu = True
    cfg.story_max_cancons_ppcc = 5
    cfg.save()
    return cfg


@pytest.fixture
def top_ppcc(db):
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
            canco=c, territori="PPCC", setmana=SETMANA, posicio=i, score_setmanal=10 - i
        )
    return SETMANA


# ── model + predicate ────────────────────────────────────────────────


def test_seed_creates_todays_combos(db):
    """The migration seeds the 17 combos published today, all on."""
    rows = {(m.canal, m.tipus): m.actiu for m in MatriuPublicacio.objects.all()}
    assert len(rows) == 17
    for canal in ("instagram", "mastodon", "bluesky", "telegram"):
        for tipus in ("top_ppcc", "top_territorial", "nous_singles", "nous_albums"):
            assert rows[(canal, tipus)] is True
    assert rows[("newsletter", "top_ppcc")] is True
    assert ("newsletter", "nous_albums") not in rows  # never published today


def test_actiu_per_default_and_off(db):
    assert MatriuPublicacio.actiu_per("mastodon", "top_ppcc") is True
    # Non-seeded combo → fail-open to the pre-matrix world.
    assert MatriuPublicacio.actiu_per("newsletter", "nous_albums") is True
    MatriuPublicacio.objects.filter(canal="mastodon", tipus="top_ppcc").update(
        actiu=False
    )
    assert MatriuPublicacio.actiu_per("mastodon", "top_ppcc") is False


def test_pot_publicar_tipus_combines_three_gates(cfg_all_on):
    cfg = cfg_all_on
    assert cfg.pot_publicar_tipus("mastodon", "top_ppcc") is True
    # Matrix off → blocked even though master + channel are on.
    MatriuPublicacio.objects.filter(canal="mastodon", tipus="top_ppcc").update(
        actiu=False
    )
    assert cfg.pot_publicar_tipus("mastodon", "top_ppcc") is False
    # Channel off → blocked regardless of the matrix.
    MatriuPublicacio.objects.filter(canal="mastodon", tipus="top_ppcc").update(
        actiu=True
    )
    cfg.mastodon_actiu = False
    cfg.save()
    assert cfg.pot_publicar_tipus("mastodon", "top_ppcc") is False


# ── guard (a): full matrix → identical to today ──────────────────────


def test_full_matrix_publishes_saturday_as_before(cfg_all_on, top_ppcc):
    """With the default (all-on) matrix, Saturday still produces the IG
    top_ppcc feed + story posts — identical to the pre-matrix world."""
    out = io.StringIO()
    with redirect_stdout(out):
        call_command("publicar_social", "--data", SATURDAY, "--dry-run")
    posts = SocialPost.objects.filter(setmana=top_ppcc, tipus="top_ppcc")
    feed = posts.get(platform=SocialPost.PLATFORM_INSTAGRAM_FEED)
    assert feed.status != SocialPost.STATUS_OMES
    assert "matriu" not in out.getvalue().lower()


# ── guard (b): one cell off blocks exactly that combo ────────────────


def test_one_cell_off_blocks_only_that_combo(cfg_all_on, top_ppcc):
    MatriuPublicacio.objects.filter(canal="instagram", tipus="top_ppcc").update(
        actiu=False
    )
    out = io.StringIO()
    with redirect_stdout(out):
        call_command("publicar_social", "--data", SATURDAY, "--dry-run")
    feed = SocialPost.objects.get(
        setmana=top_ppcc,
        platform=SocialPost.PLATFORM_INSTAGRAM_FEED,
        tipus="top_ppcc",
    )
    assert feed.status == SocialPost.STATUS_OMES
    assert "matriu" in feed.error_msg.lower()
    # A different channel's cell is untouched (mastodon × top_ppcc still on).
    assert MatriuPublicacio.actiu_per("mastodon", "top_ppcc") is True


def test_publicar_canal_respects_matrix(cfg_all_on, top_ppcc):
    MatriuPublicacio.objects.filter(canal="mastodon", tipus="top_ppcc").update(
        actiu=False
    )
    out = io.StringIO()
    with redirect_stdout(out):
        call_command(
            "publicar_canal", "--channel", "mastodon", "--data", SATURDAY, "--dry-run"
        )
    post = SocialPost.objects.get(
        setmana=top_ppcc, platform=SocialPost.PLATFORM_MASTODON, tipus="top_ppcc"
    )
    assert post.status == SocialPost.STATUS_OMES
    assert "matriu" in post.error_msg.lower()


# ── guard (c): newsletter gate — NEVER sends ─────────────────────────


def _seed_draft(setmana):
    from comptes.models import NewsletterDraft

    return NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=setmana,
        estat=NewsletterDraft.ESTAT_PENDENT,
        subject="Subj",
        narrative_html="<p>x</p>",
    )


@pytest.mark.django_db
def test_newsletter_matrix_off_does_not_send(cfg_all_on, top_ppcc):
    """(newsletter × top_ppcc) off → enviar_newsletter exits without ever
    calling the real send."""
    _seed_draft(top_ppcc)
    MatriuPublicacio.objects.filter(canal="newsletter", tipus="top_ppcc").update(
        actiu=False
    )
    with patch(
        "comptes.management.commands.enviar_newsletter.send_top_newsletter"
    ) as mock_send:
        out = io.StringIO()
        with redirect_stdout(out):
            call_command("enviar_newsletter")  # NO --dry-run: the real gate path
    mock_send.assert_not_called()
    assert "matriu" in out.getvalue().lower()


@pytest.mark.django_db
def test_newsletter_matrix_on_reaches_send(cfg_all_on, top_ppcc):
    """Default (on) matrix → the gate passes and the send is reached
    (mocked, never real)."""
    _seed_draft(top_ppcc)
    with patch(
        "comptes.management.commands.enviar_newsletter.send_top_newsletter",
        return_value="sent=0 fail=0",
    ) as mock_send:
        out = io.StringIO()
        with redirect_stdout(out):
            call_command("enviar_newsletter")
    mock_send.assert_called_once()
    assert "matriu" not in out.getvalue().lower()


# ── guard (d): web + RSS never gated by the matrix ───────────────────


def test_matrix_does_not_bypass_channel_gate(cfg_all_on, top_ppcc):
    """The matrix is an ADDITIONAL gate, never a bypass. Full matrix
    active + per-channel OFF → publicar_social still short-circuits at the
    channel gate, no real publish. (No --dry-run; the gate blocks before
    any side effect.)"""
    cfg_all_on.instagram_actiu = False
    cfg_all_on.save()
    out = io.StringIO()
    with redirect_stdout(out):
        call_command("publicar_social", "--data", SATURDAY)
    assert not SocialPost.objects.filter(setmana=top_ppcc).exists()
    assert "kill switch" in out.getvalue().lower()


def test_matrix_does_not_bypass_master_gate(cfg_all_on, top_ppcc):
    """Full matrix active + master OFF → still globally paused."""
    cfg_all_on.distribucio_activa = False
    cfg_all_on.save()
    out = io.StringIO()
    with redirect_stdout(out):
        call_command("publicar_social", "--data", SATURDAY)
    assert not SocialPost.objects.filter(setmana=top_ppcc).exists()
    assert "pausada" in out.getvalue().lower()


@pytest.mark.django_db
def test_toggle_writes_staff_audit(db, django_user_model):
    """The toggle changes what gets distributed, so it must be audited
    (who/when/what)."""
    user = django_user_model.objects.create_user(
        username="matriu_auditor", email="ma@example.com", password="x", is_staff=True
    )
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.post(
        "/api/v1/staff/social/matriu/toggle/",
        {"canal": "newsletter", "tipus": "top_ppcc", "actiu": False},
        format="json",
    )
    assert r.status_code == 200
    row = StaffAuditLog.objects.filter(action="config_update").order_by("-id").first()
    assert row is not None
    assert row.actor == user  # who
    assert row.created_at is not None  # when
    assert row.metadata.get("camp") == "matriu_distribucio"
    assert row.metadata.get("canal") == "newsletter"
    assert row.metadata.get("tipus") == "top_ppcc"
    # `nou`/`anterior` now carry both the switch and the weekday (5a).
    assert row.metadata.get("nou") == {"actiu": False, "dia_setmana": None}


def test_matrix_excludes_web_and_rss(cfg_all_on):
    canals = {c for c, _ in MatriuPublicacio.CANALS}
    assert canals == {"instagram", "mastodon", "bluesky", "telegram", "newsletter"}
    assert "rss" not in canals and "web" not in canals
    # RSS stays governed by its own per-channel switch, never the matrix.
    cfg_all_on.rss_actiu = True
    cfg_all_on.save()
    assert cfg_all_on.pot_publicar("rss") is True
