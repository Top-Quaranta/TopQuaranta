"""Guards for on-demand newsletter generation (distribution llesca 3).

- brief `?setmana=` optional (default = this week, production path).
- staff `POST /staff/newsletter/esborrany/generar/` — engine draft for a
  chosen consolidated week; no-clobber on terminal/edited drafts; NEVER
  sends.
- staff `GET /staff/newsletter/setmanes/` — consolidated-week selector +
  live can-generate status.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from django.core import mail
from rest_framework.test import APIClient

from comptes.models import NewsletterDraft
from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal

TOKEN = "secret-routine-token"
BRIEF_URL = "/api/v1/newsletter-routine/brief/"
GENERAR_URL = "/api/v1/staff/newsletter/esborrany/generar/"
SETMANES_URL = "/api/v1/staff/newsletter/setmanes/"


def _monday():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _seed_top(setmana=None):
    setmana = setmana or _monday()
    a = Artista.objects.create(nom="Art X", lastfm_nom="Art X", aprovat=True)
    al = Album.objects.create(
        artista=a, nom="Al X", data_llancament=datetime.date(2026, 1, 1)
    )
    c = Canco.objects.create(
        artista=a,
        album=al,
        nom="Tema X",
        verificada=True,
        activa=True,
        data_llancament=datetime.date(2026, 1, 1),
    )
    TopSetmanal.objects.create(
        canco=c, territori="PPCC", setmana=setmana, posicio=1, score_setmanal=10.0
    )
    return c


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="nl_ondemand_tester",
        email="nl@example.com",
        password="x",
        is_staff=True,
    )
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def token_client(settings):
    settings.NEWSLETTER_ROUTINE_TOKEN = TOKEN
    return APIClient()


def _auth():
    return {"HTTP_AUTHORIZATION": f"Bearer {TOKEN}"}


# ── brief ?setmana= optional ─────────────────────────────────────────


@pytest.mark.django_db
def test_brief_without_param_is_current_week(token_client):
    # Production path unchanged: no param → current week (not consolidated
    # here) → not_ready.
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = token_client.get(BRIEF_URL, **_auth())
    assert r.status_code == 200
    assert r.data["status"] == "not_ready"


@pytest.mark.django_db
def test_brief_with_consolidated_setmana_param(token_client):
    past = _monday() - datetime.timedelta(weeks=3)
    _seed_top(setmana=past)
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = token_client.get(f"{BRIEF_URL}?setmana={past.isoformat()}", **_auth())
    assert r.status_code == 200
    assert r.data["status"] == "ready"
    assert r.data["context"]["setmana"] == past.isoformat()


@pytest.mark.django_db
def test_brief_with_unconsolidated_setmana_param_not_ready(token_client):
    past = _monday() - datetime.timedelta(weeks=5)  # no TopSetmanal seeded
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = token_client.get(f"{BRIEF_URL}?setmana={past.isoformat()}", **_auth())
    assert r.status_code == 200
    assert r.data["status"] == "not_ready"


# ── staff generate on demand ─────────────────────────────────────────


@pytest.mark.django_db
@patch(
    "comptes.newsletter.build_draft_text",
    return_value=("ENGINE subj", "<p>engine</p>"),
)
def test_generar_creates_motor_draft_and_never_sends(mock_build, staff_client):
    _seed_top()
    r = staff_client.post(GENERAR_URL)
    assert r.status_code == 201, r.content
    d = NewsletterDraft.objects.get(setmana=_monday())
    assert d.font == NewsletterDraft.FONT_MOTOR
    assert d.estat == NewsletterDraft.ESTAT_PENDENT
    assert d.editat is False
    assert d.subject == "ENGINE subj"
    # Never sends: no email, draft is not 'enviat'.
    assert len(mail.outbox) == 0
    assert d.enviat_at is None


@pytest.mark.django_db
def test_generar_unconsolidated_week_is_409(staff_client):
    past = _monday() - datetime.timedelta(weeks=7)
    r = staff_client.post(f"{GENERAR_URL}?setmana={past.isoformat()}")
    assert r.status_code == 409
    assert not NewsletterDraft.objects.exists()


@pytest.mark.django_db
@patch(
    "comptes.newsletter.build_draft_text",
    return_value=("ENGINE subj", "<p>engine</p>"),
)
def test_generar_does_not_clobber_edited_draft(mock_build, staff_client):
    _seed_top()
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=_monday(),
        subject="Editat per staff",
        narrative_html="<p>humà</p>",
        estat=NewsletterDraft.ESTAT_PENDENT,
        editat=True,
    )
    r = staff_client.post(GENERAR_URL)
    assert r.status_code == 409
    d = NewsletterDraft.objects.get(setmana=_monday())
    assert d.subject == "Editat per staff"
    assert not mock_build.called


@pytest.mark.django_db
@patch(
    "comptes.newsletter.build_draft_text",
    return_value=("ENGINE subj", "<p>engine</p>"),
)
def test_generar_does_not_clobber_terminal_draft(mock_build, staff_client):
    _seed_top()
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=_monday(),
        subject="ja cancel·lat",
        estat=NewsletterDraft.ESTAT_CANCELLAT,
    )
    r = staff_client.post(GENERAR_URL)
    assert r.status_code == 409
    assert NewsletterDraft.objects.get(setmana=_monday()).estat == "cancellat"
    assert not mock_build.called


@pytest.mark.django_db
@patch(
    "comptes.newsletter.build_draft_text",
    return_value=("REGEN subj", "<p>regen</p>"),
)
def test_generar_regenerates_pendent_engine_draft(mock_build, staff_client):
    _seed_top()
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=_monday(),
        subject="vell",
        estat=NewsletterDraft.ESTAT_PENDENT,
        font=NewsletterDraft.FONT_MOTOR,
        editat=False,
    )
    r = staff_client.post(GENERAR_URL)
    assert r.status_code == 200, r.content
    assert NewsletterDraft.objects.filter(setmana=_monday()).count() == 1
    assert NewsletterDraft.objects.get(setmana=_monday()).subject == "REGEN subj"


@pytest.mark.django_db
def test_generar_requires_staff(client):
    # Anonymous (no staff session) must be rejected.
    r = client.post(GENERAR_URL)
    assert r.status_code in (401, 403)


# ── staff week selector ──────────────────────────────────────────────


@pytest.mark.django_db
def test_setmanes_lists_consolidated_weeks_and_draft_state(staff_client):
    w1 = _monday() - datetime.timedelta(weeks=1)
    w2 = _monday() - datetime.timedelta(weeks=2)
    _seed_top(setmana=w1)
    _seed_top(setmana=w2)
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=w1,
        subject="s",
        estat=NewsletterDraft.ESTAT_PENDENT,
    )
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = staff_client.get(SETMANES_URL)
    assert r.status_code == 200, r.content
    weeks = {row["setmana"]: row for row in r.data["setmanes"]}
    assert w1.isoformat() in weeks and w2.isoformat() in weeks
    assert weeks[w1.isoformat()]["has_draft"] is True
    assert weeks[w1.isoformat()]["estat"] == "pendent"
    assert weeks[w2.isoformat()]["has_draft"] is False
    # current-week live indicator present.
    assert "current" in r.data and "status" in r.data["current"]


@pytest.mark.django_db
def test_setmanes_current_status_ready_when_consolidated(staff_client):
    _seed_top()  # current week consolidated
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = staff_client.get(SETMANES_URL)
    assert r.data["current"]["status"] == "ready"
