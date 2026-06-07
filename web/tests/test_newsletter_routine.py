"""Guards for the newsletter cloud-routine endpoints (2026-06-07).

Token auth (valid passes / invalid 401), the not-ready brief guard, and
the draft upsert that can never mark approved/sent. VilaWeb RSS is mocked
so no network is hit.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from comptes.models import NewsletterDraft
from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal

TOKEN = "secret-routine-token"
BRIEF_URL = "/api/v1/newsletter-routine/brief/"
DRAFT_URL = "/api/v1/newsletter-routine/esborrany/"


def _monday():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _seed_top():
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
        canco=c, territori="PPCC", setmana=_monday(), posicio=1, score_setmanal=10.0
    )
    return c


@pytest.fixture
def client_with_token(settings):
    settings.NEWSLETTER_ROUTINE_TOKEN = TOKEN
    return APIClient()


def _auth(token=TOKEN):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


# ── token auth ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_valid_token_passes(client_with_token):
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200, r.content


@pytest.mark.django_db
def test_invalid_token_401(client_with_token):
    r = client_with_token.get(BRIEF_URL, **_auth("wrong"))
    assert r.status_code == 401


@pytest.mark.django_db
def test_missing_token_401(client_with_token):
    r = client_with_token.get(BRIEF_URL)
    assert r.status_code == 401


@pytest.mark.django_db
def test_blank_setting_denies_even_with_header(settings):
    settings.NEWSLETTER_ROUTINE_TOKEN = ""
    r = APIClient().get(BRIEF_URL, **{"HTTP_AUTHORIZATION": "Bearer "})
    assert r.status_code == 401
    r2 = APIClient().get(BRIEF_URL, **_auth("anything"))
    assert r2.status_code == 401


# ── brief ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_brief_not_ready_without_consolidated_top(client_with_token):
    with patch("comptes.newsletter_brief._fetch_vilaweb", return_value=[]):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200
    assert r.data["status"] == "not_ready"


@pytest.mark.django_db
def test_brief_ready_shape(client_with_token):
    _seed_top()
    with patch(
        "comptes.newsletter_brief._fetch_vilaweb",
        return_value=[{"titol": "Notícia", "font": "VilaWeb", "data": "x"}],
    ):
        r = client_with_token.get(BRIEF_URL, **_auth())
    assert r.status_code == 200
    d = r.data
    assert d["status"] == "ready"
    assert d["context"]["edicio"] == "Global"
    assert d["context"]["antiguitat_top_setmanes"] >= 1
    assert len(d["top10"]) == 1
    e = d["top10"][0]
    assert "can_call_new" in e and "moviment" in e
    assert "primera_aparicio" in e and "historial" in e
    assert d["fets_grup_top5"][0]["data_llancament"] == "2026-01-01"
    # Low-confidence section is separate from facts.
    assert "lastfm_tags_top5" in d["baixa_confianca"]
    assert d["actualitat"][0]["font"] == "VilaWeb"


# ── draft upsert ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_post_creates_draft_llm_pendent(client_with_token):
    _seed_top()
    r = client_with_token.post(
        DRAFT_URL,
        {"subject": "Subj", "narrative_html": "<p>n</p>"},
        format="json",
        **_auth(),
    )
    assert r.status_code == 201, r.content
    d = NewsletterDraft.objects.get(setmana=_monday())
    assert d.font == NewsletterDraft.FONT_LLM
    assert d.estat == NewsletterDraft.ESTAT_PENDENT
    assert d.subject == "Subj"


@pytest.mark.django_db
def test_post_idempotent_replaces(client_with_token):
    _seed_top()
    client_with_token.post(DRAFT_URL, {"subject": "A"}, format="json", **_auth())
    r = client_with_token.post(DRAFT_URL, {"subject": "B"}, format="json", **_auth())
    assert r.status_code == 200
    assert NewsletterDraft.objects.filter(setmana=_monday()).count() == 1
    assert NewsletterDraft.objects.get(setmana=_monday()).subject == "B"


@pytest.mark.django_db
def test_post_rejects_non_pendent_estat(client_with_token):
    _seed_top()
    r = client_with_token.post(
        DRAFT_URL, {"subject": "X", "estat": "enviat"}, format="json", **_auth()
    )
    assert r.status_code == 400
    assert not NewsletterDraft.objects.exists()


@pytest.mark.django_db
def test_post_requires_subject(client_with_token):
    _seed_top()
    r = client_with_token.post(
        DRAFT_URL, {"narrative_html": "<p>x</p>"}, format="json", **_auth()
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_post_terminal_draft_is_409(client_with_token):
    _seed_top()
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=_monday(),
        subject="s",
        estat=NewsletterDraft.ESTAT_ENVIAT,
    )
    r = client_with_token.post(DRAFT_URL, {"subject": "X"}, format="json", **_auth())
    assert r.status_code == 409


# ── engine fallback does not overwrite a routine draft ───────────────


@pytest.mark.django_db
@patch("comptes.management.commands.generar_esborrany_newsletter.mail_admins")
@patch("comptes.management.commands.generar_esborrany_newsletter.build_draft_text")
def test_engine_fallback_does_not_overwrite_routine_draft(mock_build, mock_mail):
    from io import StringIO

    from django.core.management import call_command

    _seed_top()
    # Routine already left an LLM draft for the week.
    NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=_monday(),
        subject="LLM subject",
        narrative_html="<p>llm</p>",
        font=NewsletterDraft.FONT_LLM,
    )
    mock_build.return_value = ("ENGINE subject", "<p>engine</p>")
    call_command("generar_esborrany_newsletter", stdout=StringIO())
    d = NewsletterDraft.objects.get(setmana=_monday())
    assert d.font == NewsletterDraft.FONT_LLM  # untouched
    assert d.subject == "LLM subject"
    assert not mock_build.called  # never even composed
