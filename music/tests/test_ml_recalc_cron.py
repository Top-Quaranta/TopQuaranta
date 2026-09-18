"""Retraining and bulk rescoring belong to the cron, not to a web request.

Until 2026-09 `recalcular_ml_si_cal()` span a daemon thread inside the
gunicorn worker every time staff accumulated 5 decisions. Measured on prod
on 2026-09-18: the rebuild costs ~26 min, the "last recalc" marker is only
written at the end (so overlapping copies stacked with no lock), and a
worker recycle kills the thread silently. The last run that finished was
13-09; the 27 decisions over the next four days triggered nothing, leaving
15 % of pendents with a stale `ml_confianca` — the key the staff cançons
page sorts by.

These tests guard the promises, not the plumbing: no web path may start
the work or hand it to a thread, the command is singleton-guarded, it only
rescores what the panel reads, and a quiet night skips the rebuild.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from music.constants import MIN_NEW_DECISIONS
from music.models import Album, Artista, Canco

COMANDA = "music.management.commands.recalcular_ml"


@pytest.fixture
def artista(db):
    return Artista.objects.create(nom="Recalc Tester", aprovat=True)


@pytest.fixture
def album(db, artista):
    return Album.objects.create(nom="Recalc Album", artista=artista)


def _canco(artista, album, *, nom, deezer_id, activa):
    return Canco.objects.create(
        nom=nom,
        artista=artista,
        album=album,
        deezer_id=deezer_id,
        verificada=False,
        activa=activa,
        ml_classe="A",
        ml_confianca=0.99,
    )


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="recalc_cron_tester",
        email="rc@example.com",
        password="x",
        is_staff=True,
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ── The web must never start the work ─────────────────────────────────


def test_approving_from_the_panel_never_retrains(staff_client, artista, album):
    """The promise: deciding a song is a DB write, not a 26-minute job.

    Hooked on `entrenar_model` inside `music.ml` because every retrain
    path reaches it through that module global — so the guard holds
    however a future caller chooses to import the trigger.
    """
    c = _canco(artista, album, nom="Decidida", deezer_id=9001, activa=True)

    with patch("music.ml.entrenar_model") as entrenar:
        resp = staff_client.post(
            "/api/v1/staff/cancons/accio/",
            {"action": "aprovar", "ids": [c.pk]},
            format="json",
        )

    assert resp.status_code == 200, resp.content
    c.refresh_from_db()
    assert c.verificada is True
    entrenar.assert_not_called()


def test_a_staff_decision_spawns_no_background_thread(staff_client, artista, album):
    """The failure mode was invisibility.

    A daemon thread that dies takes its error with it: nothing in the
    status file, nothing for `tq-health` to see. Work that can fail must
    run in the foreground of a command whose exit code `tq-run` records.
    """
    c = _canco(artista, album, nom="Sense fil", deezer_id=9002, activa=True)

    with patch("threading.Thread") as fil:
        resp = staff_client.post(
            "/api/v1/staff/cancons/accio/",
            {"action": "aprovar", "ids": [c.pk]},
            format="json",
        )

    assert resp.status_code == 200, resp.content
    fil.assert_not_called()


# ── The command's contract ────────────────────────────────────────────


def test_command_runs_under_the_singleton_lock(db):
    """Two overlapping runs must not both rebuild the model."""
    vist = {}

    @contextmanager
    def _spy(name, *args, **kwargs):
        vist["name"] = name
        yield

    with patch("music.locks.SingletonLock", _spy), patch(f"{COMANDA}.recalcular_ml"):
        call_command("recalcular_ml", "--entrenar", "mai")

    assert vist.get("name") == "recalcular_ml"


def test_rescoring_skips_deactivated_songs(db, artista, album):
    """Scope is what the panel reads: verificada=False AND activa=True.

    A deactivated song is neither listed nor rankable; rescoring it was
    64 % of the nightly loop for no reader.
    """
    viva = _canco(artista, album, nom="Viva", deezer_id=9101, activa=True)
    morta = _canco(artista, album, nom="Morta", deezer_id=9102, activa=False)

    with patch(
        "music.ml.pre_classificar", return_value={"classe": "C", "confiança": 0.11}
    ):
        call_command("recalcular_ml", "--entrenar", "mai")

    viva.refresh_from_db()
    morta.refresh_from_db()
    assert (viva.ml_classe, viva.ml_confianca) == ("C", 0.11)
    assert (morta.ml_classe, morta.ml_confianca) == ("A", 0.99)


@pytest.mark.parametrize(
    "n_decisions, ha_d_entrenar",
    [(0, False), (MIN_NEW_DECISIONS - 1, False), (MIN_NEW_DECISIONS, True)],
)
def test_auto_mode_retrains_only_when_there_is_something_to_learn(
    db, n_decisions, ha_d_entrenar
):
    """A quiet night costs a rescore, not a rebuild."""
    with (
        patch("music.ml.entrenar_model") as entrenar,
        patch(f"{COMANDA}.decisions_des_de_l_ultim_recalc", return_value=n_decisions),
    ):
        call_command("recalcular_ml")

    assert entrenar.called is ha_d_entrenar


def test_sempre_and_mai_override_the_threshold(db):
    with (
        patch("music.ml.entrenar_model") as entrenar,
        patch(f"{COMANDA}.decisions_des_de_l_ultim_recalc", return_value=0),
    ):
        call_command("recalcular_ml", "--entrenar", "sempre")
    assert entrenar.called

    with (
        patch("music.ml.entrenar_model") as entrenar,
        patch(f"{COMANDA}.decisions_des_de_l_ultim_recalc", return_value=9999),
    ):
        call_command("recalcular_ml", "--entrenar", "mai")
    assert not entrenar.called
