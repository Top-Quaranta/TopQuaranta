"""Tests for the daily YouTube report."""

from __future__ import annotations

import re
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from music.models import Album, Artista, Canco
from ranking.models import SenyalYouTube


def _canco(nom, *, artista, video="", dies=10):
    alb, _ = Album.objects.get_or_create(
        artista=artista, nom="X", defaults={"data_llancament": date.today()}
    )
    return Canco.objects.create(
        artista=artista,
        album=alb,
        nom=nom,
        data_llancament=date.today() - timedelta(days=dies),
        verificada=True,
        activa=True,
        youtube_video_id=video,
    )


@pytest.mark.django_db
def test_report_counts_coverage_and_the_blind_spot():
    a = Artista.objects.create(
        nom="A", lastfm_nom="A", aprovat=True, youtube_channel_id="UC1"
    )
    a.youtube_checked_at = timezone.now()
    a.save()
    _canco("amb video", artista=a, video="v1")
    _canco("sense video", artista=a)

    out = StringIO()
    call_command("enviar_informe_youtube", "--dry-run", stdout=out)
    body = out.getvalue()

    # Property asserted: the coverage figures 1/2 and 50% appear under
    # their labels — whitespace-tolerant, column alignment is not the
    # promise.
    assert "DESCOBRIMENT" in body
    assert re.search(r"Cançons connectades\s+1/2\b", body)
    # Neither track has Last.fm signal, so both are blind spot; one covered.
    assert re.search(r"Ja tenen YouTube\s+1/2\b.*50%", body)


@pytest.mark.django_db
def test_report_sends_html_and_survives_an_empty_catalogue():
    call_command("enviar_informe_youtube")
    assert len(mail.outbox) == 1
    html, mimetype = mail.outbox[0].alternatives[0]
    assert mimetype == "text/html"
    assert "Connexió amb YouTube" in html
    assert "facc15" in html


@pytest.mark.django_db
def test_snapshot_errors_surface_as_incidents():
    a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
    c = _canco("t", artista=a, video="v1")
    SenyalYouTube.objects.create(
        canco=c,
        data=date.today(),
        video_id="v1",
        error=True,
        error_msg="vídeo esborrat",
    )

    out = StringIO()
    call_command("enviar_informe_youtube", "--dry-run", stdout=out)

    assert "INCIDÈNCIES" in out.getvalue()
    assert "vídeo esborrat" in out.getvalue()


@pytest.mark.django_db
def test_eta_uses_capacity_until_there_is_real_history():
    """Day one has run once, so the 7-day average says "145 days" when the
    budget actually covers it in a week. Projecting from capacity — and
    saying so — beats a precise-looking wrong number."""
    for i in range(30):
        a = Artista.objects.create(nom=f"a{i}", lastfm_nom=f"a{i}", aprovat=True)
        _canco(f"t{i}", artista=a)
        if i < 3:
            a.youtube_checked_at = timezone.now()
            a.youtube_channel_id = "UC1"
            a.save()

    out = StringIO()
    call_command("enviar_informe_youtube", "--dry-run", stdout=out)

    assert "capacitat diària" in out.getvalue()
    assert "ritme actual" not in out.getvalue()
