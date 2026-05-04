"""Tests for enviar_digest_setmanal."""

from __future__ import annotations

import datetime
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from analytics.events import register
from analytics.models import MetricaPipeline


@pytest.mark.django_db
def test_digest_dry_run_renders_all_sections():
    register("pageview", dim1="/top", n=42)
    register("registre_complet", n=3)
    register("utm_landing", dim1="mastodon", dim2="top_ppcc", n=5)
    today = timezone.localdate()
    MetricaPipeline.objects.create(
        data=today, clau="cancons_verificades", valor_int=2500
    )
    MetricaPipeline.objects.create(
        data=today, clau="cobertura_whisper", valor_float=72.3
    )
    out = StringIO()
    call_command("enviar_digest_setmanal", "--dry-run", stdout=out)
    body = out.getvalue()
    assert "DIGEST SETMANAL" in body
    assert "Pageviews" in body
    assert "/top" in body  # appears in Top 5 pages
    assert "mastodon" in body  # UTM source
    assert "2500" in body  # cancons_verificades
    assert "72.3 %" in body  # cobertura whisper
    assert "Dashboard complet" in body


@pytest.mark.django_db
def test_digest_sends_email():
    register("pageview", dim1="/")
    call_command("enviar_digest_setmanal")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "Digest setmanal" in msg.subject
    assert "Pageviews" in msg.body


@pytest.mark.django_db
def test_digest_handles_zero_data_gracefully():
    """Empty DB must not crash the digest — show '(sense dades)' lines."""
    out = StringIO()
    call_command("enviar_digest_setmanal", "--dry-run", stdout=out)
    body = out.getvalue()
    assert "(sense dades)" in body
