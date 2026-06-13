"""Guards for the newsletter opt-out review flow (2026-06-07).

Generation (Saturday) → review/edit → send (Sunday) unless cancelled.
External engine + email are mocked; these tests pin the orchestration:
idempotency, the override wiring, the list rebuild at send time, and the
estat machine (pendent sends, cancelled doesn't, edited ships edited).
"""

from __future__ import annotations

import datetime
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from comptes.models import NewsletterDraft
from music.models import Album, Artista, Canco
from ranking.models import ConfiguracioGlobal, TopSetmanal
from social.models import SocialPost

SETMANA = datetime.date(2026, 6, 1)  # a Monday


def _enable_newsletter():
    cfg = ConfiguracioGlobal.load()
    cfg.distribucio_activa = True
    cfg.newsletter_actiu = True
    cfg.save()


def _current_monday():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _seed_top(posicio=1, nom="Cançó A", setmana=SETMANA):
    a = Artista.objects.create(nom=f"Art {nom}", lastfm_nom=f"Art {nom}", aprovat=True)
    al = Album.objects.create(artista=a, nom=f"Al {nom}")
    c = Canco.objects.create(artista=a, album=al, nom=nom, verificada=True, activa=True)
    TopSetmanal.objects.create(
        canco=c, territori="PPCC", setmana=setmana, posicio=posicio, score_setmanal=10.0
    )
    return c


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="nl_draft_tester", email="nd@example.com", password="x", is_staff=True
    )
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ── generation ───────────────────────────────────────────────────────


@pytest.mark.django_db
@patch(
    "comptes.management.commands.generar_esborrany_newsletter.notify_staff_draft_ready"
)
@patch("comptes.management.commands.generar_esborrany_newsletter.build_draft_text")
def test_generation_creates_draft_when_current_week_consolidated(
    mock_build, mock_notify
):
    monday = _current_monday()
    _seed_top(setmana=monday)  # THIS week's top exists
    mock_build.return_value = ("Subjecte motor", "<p>narrativa</p>")
    call_command("generar_esborrany_newsletter", stdout=StringIO())
    d = NewsletterDraft.objects.get(setmana=monday)
    assert d.estat == NewsletterDraft.ESTAT_PENDENT
    assert d.font == NewsletterDraft.FONT_MOTOR
    assert d.subject == "Subjecte motor"
    assert d.editat is False
    assert mock_notify.called


@pytest.mark.django_db
@patch(
    "comptes.management.commands.generar_esborrany_newsletter.notify_staff_draft_ready"
)
@patch("comptes.management.commands.generar_esborrany_newsletter.build_draft_text")
def test_generation_skips_when_current_week_top_missing(mock_build, mock_notify):
    """Anti-stale guard: only a STALE (previous-week) top exists →
    calcular_top hasn't consolidated this week yet → do NOT generate
    (never build the draft from last week's top)."""
    stale = _current_monday() - datetime.timedelta(days=7)
    _seed_top(setmana=stale)
    mock_build.return_value = ("X", "<p>x</p>")
    call_command("generar_esborrany_newsletter", stdout=StringIO())
    assert NewsletterDraft.objects.count() == 0
    assert not mock_build.called  # never even composed
    assert not mock_notify.called


@pytest.mark.django_db
@patch(
    "comptes.management.commands.generar_esborrany_newsletter.notify_staff_draft_ready"
)
@patch("comptes.management.commands.generar_esborrany_newsletter.build_draft_text")
def test_generation_idempotent_does_not_overwrite(mock_build, mock_notify):
    monday = _current_monday()
    _seed_top(setmana=monday)
    mock_build.return_value = ("Subjecte 1", "<p>1</p>")
    call_command("generar_esborrany_newsletter", stdout=StringIO())
    # Staff edits it.
    d = NewsletterDraft.objects.get(setmana=monday)
    d.subject = "Editat per staff"
    d.editat = True
    d.save()
    # Second run must NOT overwrite.
    mock_build.return_value = ("Subjecte 2", "<p>2</p>")
    call_command("generar_esborrany_newsletter", stdout=StringIO())
    d.refresh_from_db()
    assert d.subject == "Editat per staff"
    assert NewsletterDraft.objects.filter(setmana=monday).count() == 1


# ── send ─────────────────────────────────────────────────────────────


def _draft(estat=NewsletterDraft.ESTAT_PENDENT, **kw):
    return NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=SETMANA,
        subject=kw.get("subject", "Subj"),
        narrative_html=kw.get("narrative_html", "<p>n</p>"),
        estat=estat,
        editat=kw.get("editat", False),
    )


@pytest.mark.django_db
@patch("social.payload.build_top")
@patch("comptes.management.commands.enviar_newsletter.send_top_newsletter")
def test_send_pendent_ships_and_marks(mock_send, mock_top):
    _seed_top()
    _enable_newsletter()
    _draft()
    mock_top.return_value = {"entries": [{"posicio": 1, "canco_nom": "X"}]}
    mock_send.return_value = "sent=3 fail=0"
    call_command("enviar_newsletter", stdout=StringIO())
    assert mock_send.called
    d = NewsletterDraft.objects.get(setmana=SETMANA)
    assert d.estat == NewsletterDraft.ESTAT_ENVIAT
    assert d.enviat_at is not None
    post = SocialPost.objects.get(
        platform=SocialPost.PLATFORM_NEWSLETTER, setmana=SETMANA
    )
    assert post.status == SocialPost.STATUS_PUBLICAT
    assert post.published_at is not None


@pytest.mark.django_db
@patch("social.payload.build_top")
@patch("comptes.management.commands.enviar_newsletter.send_top_newsletter")
def test_send_uses_edited_text_and_rebuilds_list(mock_send, mock_top):
    _seed_top()
    _enable_newsletter()
    _draft(subject="EDITAT", narrative_html="<p>editat</p>", editat=True)
    # Final top at send time (rebuilt fresh, not stored on the draft).
    final_entries = [
        {"posicio": 1, "canco_nom": "Final"},
        {"posicio": 2, "canco_nom": "B"},
    ]
    mock_top.return_value = {"entries": final_entries}
    mock_send.return_value = "sent=1 fail=0"
    call_command("enviar_newsletter", stdout=StringIO())
    _, kwargs = mock_send.call_args
    args = mock_send.call_args.args
    assert kwargs["subject_override"] == "EDITAT"
    assert kwargs["narrative_html_override"] == "<p>editat</p>"
    # entries (positional arg 5) rebuilt from build_top at send time.
    assert args[4] == final_entries


@pytest.mark.django_db
@patch("comptes.management.commands.enviar_newsletter.send_top_newsletter")
def test_send_cancelled_does_not_send(mock_send):
    _seed_top()
    _enable_newsletter()
    _draft(estat=NewsletterDraft.ESTAT_CANCELLAT)
    call_command("enviar_newsletter", stdout=StringIO())
    assert not mock_send.called
    assert not SocialPost.objects.filter(
        platform=SocialPost.PLATFORM_NEWSLETTER
    ).exists()


@pytest.mark.django_db
@patch("comptes.management.commands.enviar_newsletter.send_top_newsletter")
def test_send_blocked_by_master_switch(mock_send):
    _seed_top()
    _draft()
    cfg = ConfiguracioGlobal.load()
    cfg.distribucio_activa = False
    cfg.newsletter_actiu = True
    cfg.save()
    call_command("enviar_newsletter", stdout=StringIO())
    assert not mock_send.called
    assert (
        NewsletterDraft.objects.get(setmana=SETMANA).estat
        == NewsletterDraft.ESTAT_PENDENT
    )


@pytest.mark.django_db
@patch("comptes.management.commands.enviar_newsletter.send_top_newsletter")
def test_send_already_sent_is_idempotent(mock_send):
    _seed_top()
    _enable_newsletter()
    _draft(estat=NewsletterDraft.ESTAT_ENVIAT)
    call_command("enviar_newsletter", stdout=StringIO())
    assert not mock_send.called


# ── endpoints ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_endpoint_get_returns_draft_and_entries(staff_client):
    _seed_top(posicio=1, nom="Tema 1")
    _draft()
    r = staff_client.get("/api/v1/staff/newsletter/esborrany/")
    assert r.status_code == 200, r.content
    assert r.data["estat"] == "pendent"
    assert r.data["send_date"] == (SETMANA + datetime.timedelta(days=6)).isoformat()
    assert isinstance(r.data["entries"], list)


@pytest.mark.django_db
def test_endpoint_patch_sets_editat(staff_client):
    _seed_top()
    _draft()
    r = staff_client.patch(
        "/api/v1/staff/newsletter/esborrany/",
        {"subject": "Nou assumpte", "narrative_html": "<p>nou</p>"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["editat"] is True
    d = NewsletterDraft.objects.get(setmana=SETMANA)
    assert d.subject == "Nou assumpte"
    assert d.editat is True


@pytest.mark.django_db
def test_endpoint_cancel(staff_client):
    _seed_top()
    _draft()
    r = staff_client.post(
        "/api/v1/staff/newsletter/esborrany/cancellar/", {}, format="json"
    )
    assert r.status_code == 200, r.content
    assert r.data["estat"] == "cancellat"


@pytest.mark.django_db
def test_endpoint_patch_blocked_when_not_pendent(staff_client):
    _seed_top()
    _draft(estat=NewsletterDraft.ESTAT_CANCELLAT)
    r = staff_client.patch(
        "/api/v1/staff/newsletter/esborrany/", {"subject": "x"}, format="json"
    )
    assert r.status_code == 409


# ── preview endpoint (render-only, honours editor overrides) ─────────

PREVIEW_URL = "/api/v1/staff/newsletter/esborrany/preview/"


@pytest.mark.django_db
def test_preview_renders_override_and_list(staff_client):
    _seed_top(nom="Cançó Preview")
    r = staff_client.post(
        PREVIEW_URL,
        {
            "subject": "Assumpte preview",
            "narrative_html": "<p>MARCA_OVERRIDE_XYZ</p>",
        },
        format="json",
    )
    assert r.status_code == 200, r.content
    html = r.data["html"]
    # Editorial override is in the rendered email...
    assert "MARCA_OVERRIDE_XYZ" in html
    # ...and the list is rebuilt from the consolidated top.
    assert "Cançó Preview" in html


@pytest.mark.django_db
def test_preview_has_no_side_effects(staff_client):
    _seed_top()
    _draft(subject="Original", narrative_html="<p>orig</p>")
    before = NewsletterDraft.objects.get(setmana=SETMANA)
    r = staff_client.post(
        PREVIEW_URL,
        {"subject": "Edit no desat", "narrative_html": "<p>edit</p>"},
        format="json",
    )
    assert r.status_code == 200, r.content
    after = NewsletterDraft.objects.get(setmana=SETMANA)
    # The draft row is untouched by a preview render.
    assert after.subject == before.subject == "Original"
    assert after.narrative_html == before.narrative_html
    assert after.estat == before.estat
    assert NewsletterDraft.objects.count() == 1


@pytest.mark.django_db
def test_preview_refuses_without_consolidated_top(staff_client):
    # No TopSetmanal seeded → no week resolves (400) / no data (409);
    # either way the preview refuses rather than rendering an empty email.
    r = staff_client.post(
        PREVIEW_URL, {"subject": "x", "narrative_html": "<p>x</p>"}, format="json"
    )
    assert r.status_code in (400, 409)
