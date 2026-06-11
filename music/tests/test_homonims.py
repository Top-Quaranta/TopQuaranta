"""Homonym marker: normalised name key + `Artista.homonims()`.

The key ignores accents AND punctuation so same-name different-bands (the Crim
case) are flagged for the staff verifier. Aggressive on purpose — it's a
heads-up, not an auto-block.
"""

from __future__ import annotations

import pytest

from music.models import Artista, normalitza_nom_homonim


@pytest.mark.parametrize(
    "nom,key",
    [
        ("Crim", "crim"),
        ("Crïm.", "crim"),
        ("Sr. À", "sra"),
        ("L'Atzar", "latzar"),
        ("El Carxe", "elcarxe"),
        ("EL CÀRXE", "elcarxe"),
        ("", ""),
    ],
)
def test_normalitza_nom_homonim(nom, key):
    assert normalitza_nom_homonim(nom) == key


@pytest.mark.django_db
def test_save_populates_nom_normalitzat():
    a = Artista.objects.create(nom="El Càrxe!")
    assert a.nom_normalitzat == "elcarxe"
    a.nom = "Un Altre"
    a.save()
    assert a.nom_normalitzat == "unaltre"


@pytest.mark.django_db
def test_homonims_match_modulo_accents_and_punctuation():
    a = Artista.objects.create(nom="Crim")
    b = Artista.objects.create(nom="Crïm.")  # same key
    c = Artista.objects.create(nom="Crim", aprovat=False)  # same key
    other = Artista.objects.create(nom="Manel")  # different

    keys = set(a.homonims().values_list("pk", flat=True))
    assert keys == {b.pk, c.pk}
    assert other.pk not in keys
    # symmetric + self excluded
    assert a.pk not in set(a.homonims().values_list("pk", flat=True))
    assert other.homonims().count() == 0


@pytest.mark.django_db
def test_blank_key_has_no_homonims():
    a = Artista.objects.create(nom="!!!")  # normalises to ""
    Artista.objects.create(nom="???")  # also ""
    assert a.nom_normalitzat == ""
    assert a.homonims().count() == 0  # blank key never matches


@pytest.mark.django_db
def test_artista_detail_exposes_homonims():
    from rest_framework.test import APIClient

    from comptes.models import Usuari

    aprovat = Artista.objects.create(nom="Crim", aprovat=True)
    pendent = Artista.objects.create(nom="Crïm", aprovat=False)
    u = Usuari.objects.create_user(
        username="hx", email="hx@example.com", password="x", is_staff=True
    )
    c = APIClient()
    c.force_authenticate(user=u)

    r = c.get(f"/api/v1/staff/artistes/{pendent.pk}/")
    assert r.status_code == 200
    homs = r.data["homonims"]
    assert len(homs) == 1
    h = homs[0]
    assert h["pk"] == aprovat.pk
    assert h["aprovat"] is True
    assert set(h.keys()) >= {
        "pk",
        "nom",
        "slug",
        "aprovat",
        "localitats",
        "deezer_ids",
        "n_cancons_verificades",
    }
