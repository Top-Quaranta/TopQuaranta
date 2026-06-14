"""Tests for the "artistes sense Instagram" queue ordering.

PART C of the 2026-05-23 Sprint Triple: a collaborator-heavy artist
must rank as high as a principal-heavy one in the queue, because
tagging them on Instagram is just as valuable. The endpoint counts
both `cancons__rankings` and `participacions__rankings`.
"""

from __future__ import annotations

from datetime import date

import pytest
from rest_framework.test import APIClient

from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal


@pytest.fixture
def staff_client(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="ig_queue_tester",
        email="iq@example.com",
        password="x",
        is_staff=True,
    )
    if hasattr(user, "is_verified"):
        try:
            del user.is_verified
        except (AttributeError, TypeError):
            pass
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
def test_n_top_sums_principal_and_collaborator_appearances(staff_client):
    """Artist A is principal on 1 TopSetmanal cançó.
    Artist B is principal on 0 cançons but collaborator on 3.
    With the new logic, B's n_top = 3, A's = 1, so B ranks higher."""
    Artista.objects.all().delete()  # tests own the universe
    a = Artista.objects.create(
        nom="EXEMPLE Solo A", lastfm_nom="EXEMPLE Solo A", aprovat=True
    )
    b = Artista.objects.create(
        nom="EXEMPLE Featured B", lastfm_nom="EXEMPLE Featured B", aprovat=True
    )
    other_principal = Artista.objects.create(
        nom="EXEMPLE Lead", lastfm_nom="EXEMPLE Lead", aprovat=True
    )

    # A as principal on 1 cançó with one chart row.
    al_a = Album.objects.create(artista=a, nom="EXEMPLE Al A")
    c_a = Canco.objects.create(
        artista=a,
        album=al_a,
        nom="EXEMPLE A track",
        isrc="ZZ00IGQ0000001",
        verificada=True,
        activa=True,
    )
    TopSetmanal.objects.create(
        canco=c_a,
        territori="CAT",
        setmana=date(2026, 5, 19),
        posicio=10,
        score_setmanal=0.5,
    )

    # B as collaborator on 3 cançons, each with one chart row.
    al_b = Album.objects.create(artista=other_principal, nom="EXEMPLE Al Lead")
    for i in range(3):
        c = Canco.objects.create(
            artista=other_principal,
            album=al_b,
            nom=f"EXEMPLE Lead-{i}",
            isrc=f"ZZ00IGQ000010{i}",
            verificada=True,
            activa=True,
        )
        c.artistes_col.add(b)
        TopSetmanal.objects.create(
            canco=c,
            territori="CAT",
            setmana=date(2026, 5, 19),
            posicio=20 + i,
            score_setmanal=0.3,
        )

    r = staff_client.get("/api/v1/staff/artistes/?include_n_top=1&sort=-n_top")
    assert r.status_code == 200, r.content
    rows = r.json()["results"]
    by_nom = {row["nom"]: row for row in rows}
    assert by_nom["EXEMPLE Featured B"]["n_top"] == 3
    assert by_nom["EXEMPLE Solo A"]["n_top"] == 1
    # And B sorts above A (the queue prioritises by descending n_top).
    nom_order = [row["nom"] for row in rows]
    assert nom_order.index("EXEMPLE Featured B") < nom_order.index("EXEMPLE Solo A")


@pytest.mark.django_db
def test_n_top_no_double_counting_when_principal_and_collab(staff_client):
    """An artist who appears as both principal AND collaborator on
    the same chart row should count once per path (so 2 here, NOT
    a Cartesian inflation of N*M)."""
    Artista.objects.all().delete()
    a = Artista.objects.create(
        nom="EXEMPLE Both", lastfm_nom="EXEMPLE Both", aprovat=True
    )

    # As principal on its own track (chart row).
    al = Album.objects.create(artista=a, nom="EXEMPLE Both Al")
    own = Canco.objects.create(
        artista=a,
        album=al,
        nom="EXEMPLE Own",
        isrc="ZZ00IGQ0000200",
        verificada=True,
        activa=True,
    )
    TopSetmanal.objects.create(
        canco=own,
        territori="CAT",
        setmana=date(2026, 5, 19),
        posicio=1,
        score_setmanal=1.0,
    )

    # Collab on a different artist's track (chart row).
    other = Artista.objects.create(
        nom="EXEMPLE Other", lastfm_nom="EXEMPLE Other", aprovat=True
    )
    al2 = Album.objects.create(artista=other, nom="EXEMPLE Other Al")
    feat = Canco.objects.create(
        artista=other,
        album=al2,
        nom="EXEMPLE Feat",
        isrc="ZZ00IGQ0000201",
        verificada=True,
        activa=True,
    )
    feat.artistes_col.add(a)
    TopSetmanal.objects.create(
        canco=feat,
        territori="CAT",
        setmana=date(2026, 5, 19),
        posicio=2,
        score_setmanal=0.9,
    )

    r = staff_client.get("/api/v1/staff/artistes/?include_n_top=1&sort=-n_top")
    by_nom = {row["nom"]: row for row in r.json()["results"]}
    # 1 principal chart row + 1 collab chart row = 2. No Cartesian.
    assert by_nom["EXEMPLE Both"]["n_top"] == 2


@pytest.mark.django_db
def test_al_top_filter_and_gestor_email_flag(staff_client, django_user_model):
    """Fase 2 D2: ?al_top=1 lists artistes in the latest PPCC week and
    flags whether they have a reachable verified-manager email."""
    from comptes.models import PerfilUsuari, UserArtista

    Artista.objects.all().delete()
    setmana = date(2026, 6, 8)
    setmana -= __import__("datetime").timedelta(days=setmana.weekday())

    charting = Artista.objects.create(nom="EXEMPLE Charting", aprovat=True)
    offchart = Artista.objects.create(nom="EXEMPLE OffChart", aprovat=True)
    al = Album.objects.create(artista=charting, nom="EXEMPLE Al")
    c = Canco.objects.create(
        artista=charting, album=al, nom="EXEMPLE C", verificada=True, activa=True
    )
    TopSetmanal.objects.create(
        canco=c, territori="PPCC", setmana=setmana, posicio=1, score_setmanal=1.0
    )

    # Give the charting artist a verified manager with an email.
    u = django_user_model.objects.create_user(
        username="mgr", email="mgr@example.com", password="x"
    )
    PerfilUsuari.objects.update_or_create(usuari=u, defaults={"vol_avis_top": True})
    UserArtista.objects.create(
        usuari=u, artista=charting, verificat=True, estat="aprovat"
    )

    r = staff_client.get("/api/v1/staff/artistes/?al_top=1")
    assert r.status_code == 200, r.content
    noms = {row["nom"]: row for row in r.json()["results"]}
    assert "EXEMPLE Charting" in noms
    assert "EXEMPLE OffChart" not in noms
    assert noms["EXEMPLE Charting"]["te_gestor_email"] is True
