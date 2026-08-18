"""Tests for the redesigned weekly digest (Setmanari)."""

from __future__ import annotations

import datetime
import re
from io import StringIO

import pytest
from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from analytics import incidents
from analytics.management.commands.enviar_digest_setmanal import (
    _CANALS,
    _delta,
    build_context,
)
from analytics.models import (
    MetricaBingLinks,
    MetricaCWV,
    MetricaEsdeveniment,
    MetricaPipeline,
    MetricaSEOQuery,
    MetricaSocialPlatform,
)
from music.models import StaffAuditLog
from ranking.models import TopSetmanal
from social.models import SocialPost


def _setmana_reportada(today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """The Monday→Sunday the digest reports on a given send date.

    Mirrors `build_context`; the fixtures have to land INSIDE that
    window, which is why they can't use `analytics.events.register()`
    (it always stamps today, and today is no longer in the window).
    """
    dilluns = today - datetime.timedelta(days=today.weekday() + 7)
    return dilluns, dilluns + datetime.timedelta(days=6)


def _event(data: datetime.date, clau: str, *, dim1="", dim2="", n=1) -> None:
    MetricaEsdeveniment.objects.create(
        data=data, clau=clau, dimensio_1=dim1, dimensio_2=dim2, comptador=n
    )


def _seed(today: datetime.date) -> None:
    dilluns, diumenge = _setmana_reportada(today)
    # Audiència: humans + bots + acquisition + registres
    _event(dilluns, "pageview", dim1="/top", dim2="human", n=42)
    _event(dilluns, "pageview", dim1="/mapa", dim2="bot", n=120)
    _event(diumenge, "registre_complet", n=3)
    _event(diumenge, "referrer", dim1="cerca_organica", n=18)
    _event(diumenge, "referrer", dim1="social", n=7)
    # Pipeline gauges — dated on the last day of the reported week, which
    # is the snapshot the digest compares against the week before.
    for clau, val in [
        ("cancons_verificades", 2500),
        ("cancons_pendents", 1843),
        ("artistes_aprovats", 1958),
        ("newsletter_subscriptors", 312),
    ]:
        MetricaPipeline.objects.create(data=diumenge, clau=clau, valor_int=val)
    MetricaPipeline.objects.create(
        data=diumenge, clau="cobertura_whisper", valor_float=92.4
    )
    MetricaPipeline.objects.create(data=diumenge, clau="cobertura_mb", valor_float=88.1)
    # Moderation decisions — `created_at` is auto_now_add, so it has to
    # be pushed into the window after the fact.
    for action in [
        "canco_aprovar",
        "canco_aprovar",
        "canco_rebutjar",
        "artista_aprovar",
    ]:
        StaffAuditLog.objects.create(action=action, target_type="Canco")
    StaffAuditLog.objects.update(
        created_at=timezone.make_aware(
            datetime.datetime.combine(diumenge, datetime.time(12, 0))
        )
    )
    # Ranking entries
    for terr, n in [("CAT", 3), ("VAL", 2)]:
        for pos in range(1, n + 1):
            TopSetmanal.objects.create(
                territori=terr, setmana=diumenge, posicio=pos, score_setmanal=1.0
            )
    # SEO + Bing
    MetricaSEOQuery.objects.create(
        data=diumenge,
        query="música en català",
        page="/",
        impressions=900,
        clicks=40,
        ctr=0.044,
        position=12.3,
    )
    MetricaBingLinks.objects.create(
        data=diumenge, inbound_links=142, linking_domains=37
    )
    MetricaCWV.objects.create(
        data=diumenge,
        url="https://www.topquaranta.cat/",
        category="mobile",
        score=86,
        lcp_ms=1900,
        inp_ms=110,
        cls=0.05,
    )
    # Followers
    MetricaSocialPlatform.objects.create(
        data=diumenge, platform="instagram", metric="followers", valor=1245
    )


@pytest.mark.django_db
def test_digest_dry_run_renders_sections():
    """The dry-run text carries every seeded figure under its label.

    Property asserted: label → number pairs (whitespace-tolerant), not
    the column alignment of the plain-text renderer.
    """
    today = timezone.localdate()
    _seed(today)
    out = StringIO()
    call_command("enviar_digest_setmanal", "--dry-run", stdout=out)
    body = out.getvalue()
    assert "SETMANARI TOPQUARANTA" in body

    def figure(label: str, value: int) -> bool:
        return re.search(rf"{re.escape(label)}\s+{value}\b", body) is not None

    assert figure("Visites humanes", 42)
    assert "Cerca orgànica" in body
    assert figure("Decisions moderació", 4)  # 3 canço + 1 artista
    assert "CAT" in body and "VAL" in body
    assert figure("Enllaços entrants", 142)
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


def test_delta_reports_small_moves_instead_of_rounding_them_to_zero():
    """3.905 → 3.912 is +7, not "= 0%".

    The old code rounded the percentage first and then read that 0 as
    "flat", so a week of real moderation work was reported as a metric
    that hadn't moved — which is what made the KPI grid untrustworthy.
    """
    puja = _delta(3912, 3905)
    assert puja["moved"] == "up"
    assert puja["text"] == "+7"

    # Tiny bases: "+1" beats a technically-correct "▲ 100%".
    assert _delta(2, 1)["text"] == "+1"
    assert _delta(0, 4)["text"] == "−4"

    # Genuinely unchanged → the arrow alone, no phantom percentage.
    igual = _delta(404, 404)
    assert igual["moved"] == "flat"
    assert igual["text"] == ""

    # Big enough to be worth a percentage.
    assert _delta(150, 100)["text"] == "50%"


@pytest.mark.django_db
def test_calendari_situa_cada_publicacio_al_seu_dia(monkeypatch, tmp_path):
    monkeypatch.setattr(incidents, "LOG_DIR", tmp_path)
    monkeypatch.setattr(incidents, "STATUS_DIR", tmp_path / "cap")
    today = timezone.localdate()
    dilluns, diumenge = _setmana_reportada(today)
    dissabte = dilluns + datetime.timedelta(days=5)
    SocialPost.objects.create(
        platform="mastodon",
        tipus="top_ppcc",
        setmana=dilluns,
        status=SocialPost.STATUS_PUBLICAT,
        published_at=timezone.make_aware(
            datetime.datetime.combine(dissabte, datetime.time(9, 40))
        ),
    )
    fallada = SocialPost.objects.create(
        platform="instagram_story",
        tipus="top_territorial",
        territori="BAL",
        setmana=dilluns,
        status=SocialPost.STATUS_ERROR,
        error_msg="Graph API 9004: media not accepted\nsegona línia",
    )
    # A failed slot has no `published_at`; it is dated by when the
    # attempt was recorded, so push `updated_at` (auto_now) into the week.
    SocialPost.objects.filter(pk=fallada.pk).update(
        updated_at=timezone.make_aware(
            datetime.datetime.combine(dissabte, datetime.time(9, 31))
        )
    )

    ctx = build_context(today)
    cal = ctx["social"]["calendari"]

    # Property asserted: each post lands in its own channel's row on the
    # day it went out, a failure stays visible on the grid AND in the
    # incidents list, and every channel gets a row even when silent —
    # not the exact cell dict shape nor the copy of the cell label.
    # Columns run dilluns → diumenge over the last complete week.
    assert [d["data"] for d in cal["dies"]] == [
        dilluns + datetime.timedelta(days=i) for i in range(7)
    ]
    assert ctx["period"] == {"since": dilluns, "until": diumenge}
    # One published slot → headline and grid agree.
    assert ctx["social"]["publicacions"] == 1
    assert cal["cap"] is False

    dia_idx = (dissabte - dilluns).days
    mastodon = next(f for f in cal["files"] if f["platform"] == "mastodon")
    cel = mastodon["cel_les"][dia_idx]
    assert cel["estat"] == "publicat" and cel["count"] == 1 and not cel["fallats"]
    # Every other Mastodon day is empty, and every channel has a row even
    # when it published nothing — silence is the signal.
    assert [i for i, c in enumerate(mastodon["cel_les"]) if c["estat"] != "buit"] == [
        dia_idx
    ]
    assert {f["platform"] for f in cal["files"]} == {p for p, _ in _CANALS}
    assert all(len(f["cel_les"]) == 7 for f in cal["files"])

    # The failure shows up both on the grid and in the incidents list.
    stories = next(f for f in cal["files"] if f["platform"] == "instagram_story")
    assert stories["cel_les"][dia_idx]["estat"] == "error"
    assert all(
        c["estat"] == "buit" for i, c in enumerate(stories["cel_les"]) if i != dia_idx
    )
    # …and a day that both published and failed keeps both facts.
    SocialPost.objects.create(
        platform="instagram_story",
        tipus="top_territorial",
        territori="CAT",
        setmana=dilluns,
        status=SocialPost.STATUS_PUBLICAT,
        published_at=timezone.make_aware(
            datetime.datetime.combine(dissabte, datetime.time(9, 32))
        ),
    )
    cel = next(
        f
        for f in build_context(today)["social"]["calendari"]["files"]
        if f["platform"] == "instagram_story"
    )["cel_les"][dia_idx]
    assert cel["estat"] == "publicat" and cel["count"] == 1
    assert cel["fallats"] == 1
    inc = ctx["incidencies"]
    assert inc["total"] == 1
    assert "Graph API 9004" in inc["social_fallades"][0]["error"]
    assert "segona línia" not in inc["social_fallades"][0]["error"]  # first line only
    assert "BAL" in inc["social_fallades"][0]["label"]


@pytest.mark.django_db
def test_digest_reports_a_clean_week_as_clean(monkeypatch, tmp_path):
    monkeypatch.setattr(incidents, "LOG_DIR", tmp_path)
    monkeypatch.setattr(incidents, "STATUS_DIR", tmp_path / "cap")
    today = timezone.localdate()
    _seed(today)
    out = StringIO()
    call_command("enviar_digest_setmanal", "--dry-run", stdout=out)
    body = out.getvalue()
    # Property asserted: a week without failures says "cap incidència"
    # (the column-heading copy is the renderer's business, not ours).
    assert "CALENDARI DE PUBLICACIONS" in body
    assert "Cap incidència" in body


@pytest.mark.django_db
def test_digest_html_out_writes_file(tmp_path):
    today = timezone.localdate()
    _seed(today)
    target = tmp_path / "preview.html"
    call_command("enviar_digest_setmanal", "--html-out", str(target))
    assert target.exists()
    assert "Setmanari" in target.read_text(encoding="utf-8")
    assert len(mail.outbox) == 0  # html-out must not send
