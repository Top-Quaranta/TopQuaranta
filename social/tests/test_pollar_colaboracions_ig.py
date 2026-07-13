"""Expiry cron (`pollar_colaboracions_ig`) — ADR-0015 §5.5.

Definitive cycle (2026-07-13): the command calls no Graph API. It
expires stale pending invites to `caducada` and refreshes the
acceptance-rate metric from registry state. Acceptances are marked
manually from the staff panel (tested in
`web/tests/test_staff_social_invitacions.py`).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from analytics.models import MetricaPipeline
from music.models import Artista
from ranking.models import ConfiguracioGlobal
from social.management.commands.pollar_colaboracions_ig import METRICA_CLAU
from social.models import InvitacioColaboracioIG as Inv


def _artista(nom):
    return Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=True)


def _invite(artista, media, username, *, dies=1, estat=Inv.ESTAT_PENDENT):
    return Inv.objects.create(
        artista=artista,
        username_snapshot=username,
        ig_media_id=media,
        tipus_publicacio="top_ppcc",
        data_invitacio=timezone.now() - timedelta(days=dies),
        estat=estat,
    )


@pytest.mark.django_db
def test_poller_expires_old_pending_to_caducada():
    """Pending invites older than the 14-day window become `caducada`
    (with data_resolucio); fresh pending is untouched."""
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    old = _invite(a, "m1", "u_old", dies=20)  # > 14d
    fresh = _invite(a, "m2", "u_fresh", dies=2)  # < 14d
    call_command("pollar_colaboracions_ig")
    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.estat == Inv.ESTAT_CADUCADA and old.data_resolucio is not None
    assert fresh.estat == Inv.ESTAT_PENDENT and fresh.data_resolucio is None
    # caducada counts as a non-acceptance in the rate (0 acc / 1 no = 0.0).
    m = MetricaPipeline.objects.get(clau=METRICA_CLAU)
    assert m.valor_float == 0.0


@pytest.mark.django_db
def test_poller_caducada_is_idempotent():
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    old = _invite(a, "m1", "u_old", dies=20)
    call_command("pollar_colaboracions_ig")
    old.refresh_from_db()
    first_resolucio = old.data_resolucio
    call_command("pollar_colaboracions_ig")  # second run
    old.refresh_from_db()
    # Already caducada → not re-touched (the expiry pass filters on pendent).
    assert old.estat == Inv.ESTAT_CADUCADA
    assert old.data_resolucio == first_resolucio
    # One metric row per day (update_or_create), no double count.
    assert MetricaPipeline.objects.filter(clau=METRICA_CLAU).count() == 1


@pytest.mark.django_db
def test_noop_when_flag_off():
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = False
    cfg.save()
    a = _artista("EXEMPLE A")
    inv = _invite(a, "media1", "handle_a", dies=20)
    call_command("pollar_colaboracions_ig")
    inv.refresh_from_db()
    # Even an expired-by-age pendent is untouched while the flag is off.
    assert inv.estat == Inv.ESTAT_PENDENT
    assert not MetricaPipeline.objects.filter(clau=METRICA_CLAU).exists()


@pytest.mark.django_db
def test_metric_derived_from_registry_state():
    """The acceptance rate is acceptades / (acceptades + rebutjades +
    caducades), derived from the registry — a manually-marked
    acceptance shows up on the next tick without any API involved."""
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    _invite(a, "m1", "u_acc", dies=3, estat=Inv.ESTAT_ACCEPTADA)
    _invite(a, "m2", "u_old", dies=20)  # expires this run → caducada
    _invite(a, "m3", "u_fresh", dies=1)  # pendent — not in the denominator
    call_command("pollar_colaboracions_ig")
    m = MetricaPipeline.objects.get(clau=METRICA_CLAU)
    assert abs(m.valor_float - 0.5) < 1e-6  # 1 acc / (1 acc + 1 caducada)


@pytest.mark.django_db
def test_fresh_pending_untouched_and_no_graph_dependency():
    """A fresh pendent stays pendent forever under this command alone —
    resolution is manual (staff) or expiry. The command must not import
    the Instagram client at all (no Graph calls in the definitive
    cycle)."""
    import social.management.commands.pollar_colaboracions_ig as mod

    assert not hasattr(mod, "instagram_client")
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    inv = _invite(a, "m1", "u1", dies=13)  # still inside the window
    call_command("pollar_colaboracions_ig")
    inv.refresh_from_db()
    assert inv.estat == Inv.ESTAT_PENDENT and inv.data_resolucio is None
