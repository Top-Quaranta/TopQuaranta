"""Acceptance poller (`pollar_colaboracions_ig`) — ADR-0015 §5.5.

Graph responses mocked; covers reconciliation of each state,
idempotency, the flag-off no-op, and the best-effort/skip behaviour.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from analytics.models import MetricaPipeline
from music.models import Artista
from ranking.models import ConfiguracioGlobal
from social import instagram_client
from social.management.commands.pollar_colaboracions_ig import (
    METRICA_CLAU,
    reconcile_estat,
)
from social.models import InvitacioColaboracioIG as Inv


def test_reconcile_estat_mapping():
    assert reconcile_estat("accepted") == Inv.ESTAT_ACCEPTADA
    assert reconcile_estat("ACTIVE") == Inv.ESTAT_ACCEPTADA
    assert reconcile_estat("pending") is None
    assert reconcile_estat("requested") is None
    assert reconcile_estat("declined") == Inv.ESTAT_REBUTJADA
    assert reconcile_estat("removed") == Inv.ESTAT_REBUTJADA
    # Absent from a successful fetch → rejected.
    assert reconcile_estat(None) == Inv.ESTAT_REBUTJADA


def _artista(nom):
    return Artista.objects.create(nom=nom, lastfm_nom=nom, aprovat=True)


def _invite(artista, media, username, *, dies=1):
    return Inv.objects.create(
        artista=artista,
        username_snapshot=username,
        ig_media_id=media,
        tipus_publicacio="top_ppcc",
        data_invitacio=timezone.now() - timedelta(days=dies),
        estat=Inv.ESTAT_PENDENT,
    )


@pytest.mark.django_db
def test_poller_expires_old_pending_to_caducada(monkeypatch):
    """Pending invites older than the 14-day window become `caducada`
    (with data_resolucio), closing the eternal-pending hole. Fresh
    pending is untouched by this pass."""
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    old = _invite(a, "m1", "u_old", dies=20)  # > 14d
    fresh = _invite(a, "m2", "u_fresh", dies=2)  # < 14d
    # API unknown → fresh stays pending; only the expiry pass acts.
    monkeypatch.setattr(instagram_client, "get_collaborators", lambda m: None)
    call_command("pollar_colaboracions_ig")
    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.estat == Inv.ESTAT_CADUCADA and old.data_resolucio is not None
    assert fresh.estat == Inv.ESTAT_PENDENT and fresh.data_resolucio is None
    # caducada counts as a non-acceptance in the rate (0 acc / 1 no = 0.0).
    m = MetricaPipeline.objects.get(clau=METRICA_CLAU)
    assert m.valor_float == 0.0


@pytest.mark.django_db
def test_poller_caducada_is_idempotent(monkeypatch):
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    old = _invite(a, "m1", "u_old", dies=20)
    monkeypatch.setattr(instagram_client, "get_collaborators", lambda m: None)
    call_command("pollar_colaboracions_ig")
    old.refresh_from_db()
    first_resolucio = old.data_resolucio
    call_command("pollar_colaboracions_ig")  # second run
    old.refresh_from_db()
    # Already caducada → not re-touched (the expiry pass filters on pendent).
    assert old.estat == Inv.ESTAT_CADUCADA
    assert old.data_resolucio == first_resolucio
    assert MetricaPipeline.objects.filter(clau=METRICA_CLAU).count() == 1


@pytest.mark.django_db
def test_noop_when_flag_off():
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = False
    cfg.save()
    a = _artista("EXEMPLE A")
    inv = _invite(a, "media1", "handle_a")
    called = []
    # Even if the API were reachable it must not be touched.
    import social.management.commands.pollar_colaboracions_ig as mod

    orig = instagram_client.get_collaborators
    instagram_client.get_collaborators = lambda m: called.append(m)  # noqa: E731
    try:
        call_command("pollar_colaboracions_ig")
    finally:
        instagram_client.get_collaborators = orig
    inv.refresh_from_db()
    assert inv.estat == Inv.ESTAT_PENDENT
    assert called == []  # no API call
    assert not MetricaPipeline.objects.filter(clau=METRICA_CLAU).exists()
    assert mod  # imported


@pytest.mark.django_db
def test_poller_reconciles_states(monkeypatch):
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a1, a2, a3, a4 = (_artista(f"EXEMPLE {x}") for x in "ABCD")
    # All on the same media so one GET reconciles all four.
    i_acc = _invite(a1, "m1", "u_accept")
    i_pend = _invite(a2, "m1", "u_pending")
    i_dec = _invite(a3, "m1", "u_declined")
    i_absent = _invite(a4, "m1", "u_absent")

    def fake(media_id):
        assert media_id == "m1"
        return {
            "u_accept": "accepted",
            "u_pending": "pending",
            "u_declined": "declined",
            # u_absent intentionally missing → rejected
        }

    monkeypatch.setattr(instagram_client, "get_collaborators", fake)
    call_command("pollar_colaboracions_ig")

    i_acc.refresh_from_db()
    i_pend.refresh_from_db()
    i_dec.refresh_from_db()
    i_absent.refresh_from_db()
    assert i_acc.estat == Inv.ESTAT_ACCEPTADA and i_acc.data_resolucio is not None
    assert i_pend.estat == Inv.ESTAT_PENDENT and i_pend.data_resolucio is None
    assert i_dec.estat == Inv.ESTAT_REBUTJADA
    assert i_absent.estat == Inv.ESTAT_REBUTJADA

    # Acceptance rate = 1 accepted / (1 accepted + 2 rejected) = 0.333…
    m = MetricaPipeline.objects.get(clau=METRICA_CLAU)
    assert abs(m.valor_float - (1 / 3)) < 1e-6


@pytest.mark.django_db
def test_poller_idempotent(monkeypatch):
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    _invite(a, "m1", "u_accept")
    monkeypatch.setattr(
        instagram_client, "get_collaborators", lambda m: {"u_accept": "accepted"}
    )
    call_command("pollar_colaboracions_ig")
    call_command("pollar_colaboracions_ig")  # second run
    # One metric row (update_or_create), rate still 1.0, no double count.
    rows = MetricaPipeline.objects.filter(clau=METRICA_CLAU)
    assert rows.count() == 1
    assert rows.first().valor_float == 1.0
    assert Inv.objects.filter(estat=Inv.ESTAT_ACCEPTADA).count() == 1


@pytest.mark.django_db
def test_poller_leaves_pending_on_api_error(monkeypatch):
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    inv = _invite(a, "m1", "u1")

    def boom(media_id):
        raise RuntimeError("IG API 500")

    monkeypatch.setattr(instagram_client, "get_collaborators", boom)
    call_command("pollar_colaboracions_ig")  # must not raise
    inv.refresh_from_db()
    assert inv.estat == Inv.ESTAT_PENDENT  # untouched


@pytest.mark.django_db
def test_poller_old_pending_expires_not_api_queried(monkeypatch):
    """A pending invite older than the window is expired to `caducada`
    by the local pass — its media is never queried against the API."""
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    old = _invite(a, "m1", "u1", dies=20)  # older than 14-day window
    seen = []
    monkeypatch.setattr(
        instagram_client, "get_collaborators", lambda m: seen.append(m) or {}
    )
    call_command("pollar_colaboracions_ig")
    old.refresh_from_db()
    assert old.estat == Inv.ESTAT_CADUCADA  # expired, not left pending
    assert seen == []  # its media never queried (only fresh pending hit the API)


@pytest.mark.django_db
def test_poller_none_statuses_leaves_pending(monkeypatch):
    """DRY_RUN / unknown (get_collaborators → None) must not misread
    silence as rejection."""
    cfg = ConfiguracioGlobal.load()
    cfg.ig_collaboradors_actiu = True
    cfg.save()
    a = _artista("EXEMPLE A")
    inv = _invite(a, "m1", "u1")
    monkeypatch.setattr(instagram_client, "get_collaborators", lambda m: None)
    call_command("pollar_colaboracions_ig")
    inv.refresh_from_db()
    assert inv.estat == Inv.ESTAT_PENDENT
