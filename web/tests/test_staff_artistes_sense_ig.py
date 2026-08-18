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


def _canco(artista, album, nom, isrc, *, verificada=True, activa=True):
    return Canco.objects.create(
        artista=artista,
        album=album,
        nom=nom,
        isrc=isrc,
        verificada=verificada,
        activa=activa,
    )


@pytest.mark.django_db
def test_cancons_vives_counts_principal_or_collaborator(staff_client):
    """`n_cancons_vives` = distinct live (verificada+activa) cançons the
    artist takes part in, as principal OR collaborator. Dead/unverified
    tracks don't count."""
    Artista.objects.all().delete()
    a = Artista.objects.create(nom="EXEMPLE Viu", aprovat=True)
    lead = Artista.objects.create(nom="EXEMPLE Amfitrio", aprovat=True)
    al = Album.objects.create(artista=a, nom="EXEMPLE Al")
    al2 = Album.objects.create(artista=lead, nom="EXEMPLE Al2")
    # 2 live as principal.
    _canco(a, al, "EXEMPLE P1", "ZZ00VIU000001")
    _canco(a, al, "EXEMPLE P2", "ZZ00VIU000002")
    # 1 live as collaborator.
    feat = _canco(lead, al2, "EXEMPLE Feat", "ZZ00VIU000003")
    feat.artistes_col.add(a)
    # 1 NON-live as principal (unverified) + 1 inactive → excluded.
    _canco(a, al, "EXEMPLE Dead1", "ZZ00VIU000004", verificada=False)
    _canco(a, al, "EXEMPLE Dead2", "ZZ00VIU000005", activa=False)

    r = staff_client.get("/api/v1/staff/artistes/?include_n_top=1&sort=-n_top")
    by_nom = {row["nom"]: row for row in r.json()["results"]}
    assert by_nom["EXEMPLE Viu"]["n_cancons_vives"] == 3  # 2 principal + 1 collab


@pytest.mark.django_db
def test_ordering_three_keys_novetats_surface(staff_client):
    """Full ordering: n_top DESC, then n_cancons_vives DESC, then
    alphabetical. A novetats-style collaborator (0 tops, 1 live song as
    collaborator — the Trapella case) surfaces above the 0-top silence,
    and equal (0-top, equal-vives) artists fall back to alphabetical.

    Since 2026-08-12 the endpoint (`sort=-n_top`) breaks the
    tops/vives tie by NEWEST live song before the alphabetical
    stabiliser (see `test_staff_instagram_revisat.py::
    test_ties_break_by_newest_song`). This test therefore asserts:
    tops > vives > collaborator-only surfaces, and — with fixtures whose
    dates and names disagree — that recency, not the alphabet, decides
    an equal-tops/equal-vives tie. No alphabetical order is pinned."""
    from datetime import timedelta

    Artista.objects.all().delete()
    today = date.today()
    # 1 top appearance — must lead regardless of live-song counts.
    topper = Artista.objects.create(nom="EXEMPLE Topper", aprovat=True)
    al_t = Album.objects.create(artista=topper, nom="EXEMPLE AlT")
    c_t = _canco(topper, al_t, "EXEMPLE T", "ZZ00ORD000001")
    TopSetmanal.objects.create(
        canco=c_t,
        territori="CAT",
        setmana=date(2026, 5, 19),
        posicio=5,
        score_setmanal=0.5,
    )
    # 0 tops, 5 live songs.
    z5 = Artista.objects.create(nom="EXEMPLE Zulu Cinc", aprovat=True)
    al_z = Album.objects.create(artista=z5, nom="EXEMPLE AlZ")
    for i in range(5):
        _canco(z5, al_z, f"EXEMPLE Z{i}", f"ZZ00ORD00010{i}")
    # 0 tops, 2 live songs — two of them. Names and dates DISAGREE:
    # "Equal A" is alphabetically first but released long ago; "Equal B"
    # is alphabetically last but released this week.
    eq_b = Artista.objects.create(nom="EXEMPLE Equal B", aprovat=True)
    eq_a = Artista.objects.create(nom="EXEMPLE Equal A", aprovat=True)
    for art, tag, dies in ((eq_b, "B", 2), (eq_a, "A", 300)):
        al = Album.objects.create(artista=art, nom=f"EXEMPLE AlEq{tag}")
        for k in (1, 2):
            c = _canco(art, al, f"EXEMPLE Eq{tag}{k}", f"ZZ00ORDEQ{tag}0{k}")
            c.data_llancament = today - timedelta(days=dies + k)
            c.save(update_fields=["data_llancament"])
    # 0 tops, 1 live song as COLLABORATOR only (the Trapella case).
    trapella = Artista.objects.create(nom="EXEMPLE Trapella", aprovat=True)
    host = Artista.objects.create(nom="EXEMPLE Zzz Host", aprovat=True)
    al_h = Album.objects.create(artista=host, nom="EXEMPLE AlH")
    feat = _canco(host, al_h, "EXEMPLE HostTrack", "ZZ00ORD000200")
    feat.artistes_col.add(trapella)

    r = staff_client.get(
        "/api/v1/staff/artistes/?aprovat=1&instagram=no&include_n_top=1&sort=-n_top"
    )
    rows = r.json()["results"]
    order = [row["nom"] for row in rows]
    # Topper (1 top) first.
    assert order[0] == "EXEMPLE Topper"

    def pos(nom):
        return order.index(nom)

    # Within the 0-top block: 5 vives > 2 vives > 1 vive (collaborator).
    assert pos("EXEMPLE Zulu Cinc") < pos("EXEMPLE Equal A")
    assert pos("EXEMPLE Zulu Cinc") < pos("EXEMPLE Equal B")
    assert pos("EXEMPLE Equal A") < pos("EXEMPLE Trapella")
    assert pos("EXEMPLE Equal B") < pos("EXEMPLE Trapella")
    # Equal tops + equal vives → the NEWEST release wins, whatever the
    # alphabet says: "Equal B" (this week) before "Equal A" (long ago).
    assert pos("EXEMPLE Equal B") < pos("EXEMPLE Equal A")
    # The collaborator-only novetats artist surfaces in the queue at all
    # (that is the Trapella promise) and reports its counts honestly.
    by_nom = {row["nom"]: row for row in rows}
    assert "EXEMPLE Trapella" in by_nom
    assert by_nom["EXEMPLE Trapella"]["n_cancons_vives"] == 1
    assert by_nom["EXEMPLE Trapella"]["n_top"] == 0


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
