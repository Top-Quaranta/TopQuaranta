"""Guards for the matching fields + directory filters (Slice B)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from comptes.models import PerfilUsuari


def _user(django_user_model, name):
    return django_user_model.objects.create_user(
        username=name, email=f"{name}@example.com", password="x"
    )


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
def test_patch_sets_matching_fields_from_list_and_string(django_user_model):
    u = _user(django_user_model, "guitarrista")
    r = _client(u).patch(
        "/api/v1/compte/perfil-usuari/",
        {
            "busca": ["grup", "colaboradors", "INVALID"],
            "generes": "rock, pop",
            "nivell": "amateur",
            "instruments": "guitarra",
        },
        format="json",
    )
    assert r.status_code == 200, r.content
    # Property asserted (through the API, not the storage format): the
    # unknown `busca` token is dropped, every valid one is kept, and the
    # comma-string `generes` is tokenised — order and separator are not
    # pinned.
    body = r.json()

    def _toks(s):
        return {t.strip() for t in str(s or "").split(",") if t.strip()}

    assert _toks(body["busca"]) == {"grup", "colaboradors"}
    assert _toks(body["generes"]) == {"rock", "pop"}
    assert body["nivell"] == "amateur"
    # And it round-trips: a fresh GET says the same.
    again = _client(u).get("/api/v1/compte/perfil-usuari/").json()
    assert _toks(again["busca"]) == {"grup", "colaboradors"}
    # The directori filter sees the valid tokens and not the dropped one.
    PerfilUsuari.objects.filter(usuari=u).update(visible_directori=True)
    viewer = _client(_user(django_user_model, "viewer1"))
    hit = viewer.get("/api/v1/comunitat/directori/?busca=colaboradors").json()
    assert u.pk in [row["usuari_id"] for row in hit["results"]]
    miss = viewer.get("/api/v1/comunitat/directori/?busca=INVALID").json()
    assert u.pk not in [row["usuari_id"] for row in miss["results"]]


@pytest.mark.django_db
def test_patch_rejects_bad_nivell(django_user_model):
    u = _user(django_user_model, "u2")
    r = _client(u).patch(
        "/api/v1/compte/perfil-usuari/", {"nivell": "nope"}, format="json"
    )
    assert r.status_code == 400
    assert "nivell" in r.json().get("errors", {})


@pytest.mark.django_db
def test_directori_filters_by_instrument_genere_busca(django_user_model):
    viewer = _user(django_user_model, "viewer")
    # Target: a rock guitarist in VAL looking for a band, visible.
    target = _user(django_user_model, "match")
    PerfilUsuari.objects.filter(usuari=target).update(
        visible_directori=True,
        instruments="guitarra",
        generes="rock,pop",
        busca="grup",
        rol_musical="music",
    )
    # Decoy: visible but no match.
    decoy = _user(django_user_model, "decoy")
    PerfilUsuari.objects.filter(usuari=decoy).update(
        visible_directori=True, instruments="bateria", generes="jazz", busca="cantant"
    )

    c = _client(viewer)
    r = c.get("/api/v1/comunitat/directori/?instrument=guitarra&genere=rock&busca=grup")
    assert r.status_code == 200, r.content
    ids = [row["usuari_id"] for row in r.json()["results"]]
    assert target.pk in ids and decoy.pk not in ids
    # Choices exposed for the UI.
    assert "busca_choices" in r.json() and "nivell_choices" in r.json()
