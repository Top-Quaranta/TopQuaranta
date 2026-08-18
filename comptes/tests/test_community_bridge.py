"""Newsletter → Community bridge: gate, idempotency, safety pins.

The bridge is additive and OFF by default. These pins assert it (a) refuses
while the gate is off, (b) when on, creates exactly one public Publicació
authored by the admin pseudo-user, (c) is idempotent, (d) stores plain text
(no raw HTML) and (e) never sends an email or triggers a send.
"""

from __future__ import annotations

import datetime

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APIClient

from comptes import community_bridge
from comptes.models import NewsletterDraft, Publicacio
from ranking.models import ConfiguracioGlobal

SET = datetime.date(2026, 6, 1)
HTML = "<h1>Hola</h1><p>Primera <strong>línia</strong>.</p><p>Segona &amp; final.</p>"


@pytest.fixture
def admin_user(db):
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        username=getattr(settings, "ADMIN_INBOX_USERNAME", "admin"),
        defaults={"email": "admin@topquaranta.cat"},
    )
    return u


@pytest.fixture
def draft(db):
    return NewsletterDraft.objects.create(
        tipus="top_ppcc",
        territori="PPCC",
        setmana=SET,
        subject="El top d'aquesta setmana",
        narrative_html=HTML,
    )


def _set_gate(value: bool):
    cfg = ConfiguracioGlobal.load()
    cfg.newsletter_publicacio_pont_actiu = value
    cfg.save(update_fields=["newsletter_publicacio_pont_actiu"])


# ── gate ─────────────────────────────────────────────────────────────


def test_flag_defaults_off(db):
    assert ConfiguracioGlobal.load().newsletter_publicacio_pont_actiu is False


def test_refuses_when_gate_off(admin_user, draft):
    _set_gate(False)
    with pytest.raises(community_bridge.PontDesactivat):
        community_bridge.publicar_draft_a_comunitat(draft)
    assert Publicacio.objects.count() == 0
    draft.refresh_from_db()
    assert draft.publicacio_id is None


# ── happy path ───────────────────────────────────────────────────────


def test_creates_public_post_authored_by_admin(admin_user, draft):
    _set_gate(True)
    pub = community_bridge.publicar_draft_a_comunitat(draft)
    assert pub.autor_id == admin_user.id
    assert pub.visibilitat == Publicacio.VISIBILITAT_PUBLICA
    assert pub.estat == Publicacio.ESTAT_PUBLICAT
    assert pub.publicat_at is not None
    assert pub.titol == draft.subject
    draft.refresh_from_db()
    assert draft.publicacio_id == pub.id


def test_body_is_markdown_without_raw_html(admin_user, draft):
    _set_gate(True)
    pub = community_bridge.publicar_draft_a_comunitat(draft)
    # No raw HTML tags survive → safe + clean for both stripMarkdown (preview)
    # and react-markdown (full render, which never emits raw HTML anyway).
    # (The JS renderers can't run in pytest; this asserts their invariant.)
    import re

    assert not re.search(r"<[a-zA-Z/][^>]*>", pub.cos)
    # Markdown formatting is preserved, not flattened to plain text.
    assert "**línia**" in pub.cos
    assert "# Hola" in pub.cos
    assert "Segona & final" in pub.cos  # entity unescaped


def test_idempotent(admin_user, draft):
    _set_gate(True)
    a = community_bridge.publicar_draft_a_comunitat(draft)
    b = community_bridge.publicar_draft_a_comunitat(draft)
    assert a.id == b.id
    assert Publicacio.objects.count() == 1


def test_never_sends_email(admin_user, draft):
    _set_gate(True)
    mail.outbox.clear()
    community_bridge.publicar_draft_a_comunitat(draft)
    assert mail.outbox == []


def test_html_to_markdown_cleans_ugly_cases():
    import re

    html = (
        "<h2>Top</h2>"
        '<p>Lidera <strong><a href="/artista/x">X</a></strong> i '
        '<em><a href="https://topquaranta.cat/t">el top</a></em>.</p>'
        '<img src="https://brevo.cdn/c.png" alt="cover">'
        '<img src="/static/portada.png" alt="portada">'
        "<table><tr><th>P</th></tr><tr><td>1</td></tr></table>"
    )
    out = community_bridge._html_to_markdown(html)
    # No raw HTML anywhere.
    assert not re.search(r"<[a-zA-Z/][^>]*>", out)
    # Markdown link/emphasis preserved; relative link absolutised.
    assert "[X](https://www.topquaranta.cat/artista/x)" in out
    assert "https://topquaranta.cat/t" in out  # already-absolute kept
    # Images PRESERVED now (Slice newsletter-imatges); absolute kept,
    # relative image absolutised to the public site.
    assert "![cover](https://brevo.cdn/c.png)" in out
    assert "![portada](https://www.topquaranta.cat/static/portada.png)" in out
    # GFM table survives as markdown (react-markdown has remark-gfm).
    assert "| P |" in out or "|P|" in out.replace(" ", "")


# ── endpoint ─────────────────────────────────────────────────────────


@pytest.fixture
def staff_client(db):
    User = get_user_model()
    staff = User.objects.create_user(
        username="staffer", email="s@x.cat", password="x", is_staff=True
    )
    c = APIClient()
    c.force_authenticate(staff)
    return c


def test_endpoint_409_when_gate_off(staff_client, admin_user, draft):
    _set_gate(False)
    r = staff_client.post(
        "/api/v1/staff/newsletter/esborrany/publicar-comunitat/",
        {"setmana": SET.isoformat()},
    )
    assert r.status_code == 409
    assert Publicacio.objects.count() == 0


def test_endpoint_200_when_gate_on(staff_client, admin_user, draft):
    _set_gate(True)
    r = staff_client.post(
        "/api/v1/staff/newsletter/esborrany/publicar-comunitat/",
        {"setmana": SET.isoformat()},
    )
    assert r.status_code == 200
    assert r.json()["publicacio_id"]
    assert (
        Publicacio.objects.filter(visibilitat="publica", estat="publicat").count() == 1
    )
