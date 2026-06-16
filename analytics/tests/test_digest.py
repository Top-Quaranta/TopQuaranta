"""Tests for the redesigned weekly digest (Setmanari)."""

from __future__ import annotations

import datetime
from io import StringIO

import pytest
from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from analytics.events import register
from analytics.models import (
    MetricaBingLinks,
    MetricaCWV,
    MetricaPipeline,
    MetricaSEOQuery,
    MetricaSocialPlatform,
)
from music.models import StaffAuditLog
from ranking.models import TopSetmanal


def _seed(today: datetime.date) -> None:
    # Audiència: humans + bots + acquisition + registres
    register("pageview", dim1="/top", dim2="human", n=42)
    register("pageview", dim1="/mapa", dim2="bot", n=120)
    register("registre_complet", n=3)
    register("referrer", dim1="cerca_organica", n=18)
    register("referrer", dim1="social", n=7)
    # Pipeline gauges
    for clau, val in [
        ("cancons_verificades", 2500),
        ("cancons_pendents", 1843),
        ("artistes_aprovats", 1958),
        ("newsletter_subscriptors", 312),
    ]:
        MetricaPipeline.objects.create(data=today, clau=clau, valor_int=val)
    MetricaPipeline.objects.create(
        data=today, clau="cobertura_whisper", valor_float=92.4
    )
    MetricaPipeline.objects.create(data=today, clau="cobertura_mb", valor_float=88.1)
    # Moderation decisions
    for action in [
        "canco_aprovar",
        "canco_aprovar",
        "canco_rebutjar",
        "artista_aprovar",
    ]:
        StaffAuditLog.objects.create(action=action, target_type="Canco")
    # Ranking entries
    for terr, n in [("CAT", 3), ("VAL", 2)]:
        for pos in range(1, n + 1):
            TopSetmanal.objects.create(
                territori=terr, setmana=today, posicio=pos, score_setmanal=1.0
            )
    # SEO + Bing
    MetricaSEOQuery.objects.create(
        data=today,
        query="música en català",
        page="/",
        impressions=900,
        clicks=40,
        ctr=0.044,
        position=12.3,
    )
    MetricaBingLinks.objects.create(data=today, inbound_links=142, linking_domains=37)
    MetricaCWV.objects.create(
        data=today,
        url="https://www.topquaranta.cat/",
        category="mobile",
        score=86,
        lcp_ms=1900,
        inp_ms=110,
        cls=0.05,
    )
    # Followers
    MetricaSocialPlatform.objects.create(
        data=today, platform="instagram", metric="followers", valor=1245
    )


@pytest.mark.django_db
def test_digest_dry_run_renders_sections():
    today = timezone.localdate()
    _seed(today)
    out = StringIO()
    call_command("enviar_digest_setmanal", "--dry-run", stdout=out)
    body = out.getvalue()
    assert "SETMANARI TOPQUARANTA" in body
    assert "Visites humanes   42" in body
    assert "Cerca orgànica" in body
    assert "Decisions moderació 4" in body  # 3 canço + 1 artista
    assert "CAT" in body and "VAL" in body
    assert "Enllaços entrants 142" in body
    assert "instagram" in body


@pytest.mark.django_db
def test_digest_sends_multipart_email_from_server_email():
    today = timezone.localdate()
    _seed(today)
    call_command("enviar_digest_setmanal")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "Setmanari" in msg.subject
    assert msg.from_email == settings.SERVER_EMAIL
    # HTML alternative carries the brand markup.
    assert msg.alternatives, "expected an HTML alternative"
    html, mimetype = msg.alternatives[0]
    assert mimetype == "text/html"
    assert "Audiència humana" in html
    assert "facc15" in html  # brand yellow present


@pytest.mark.django_db
def test_digest_handles_zero_data_gracefully():
    out = StringIO()
    call_command("enviar_digest_setmanal", "--dry-run", stdout=out)
    body = out.getvalue()
    assert "SETMANARI TOPQUARANTA" in body  # renders without crashing


@pytest.mark.django_db
def test_digest_html_out_writes_file(tmp_path):
    today = timezone.localdate()
    _seed(today)
    target = tmp_path / "preview.html"
    call_command("enviar_digest_setmanal", "--html-out", str(target))
    assert target.exists()
    assert "Setmanari" in target.read_text(encoding="utf-8")
    assert len(mail.outbox) == 0  # html-out must not send
