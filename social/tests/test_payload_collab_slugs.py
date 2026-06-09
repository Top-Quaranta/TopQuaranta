"""Slice 2 — `build_top` exposes `artistes_slugs` (additive).

NO-REGRESSION pin: the payload the social engine consumes is identical
except for the new `artistes_slugs` field; every legacy field keeps its
exact value and the names list is untouched.
"""

from __future__ import annotations

import datetime

import pytest

from music.models import Album, Artista, Canco
from ranking.models import TopSetmanal
from social import payload

SETMANA = datetime.date(2026, 6, 1)

# Every key `build_top` emitted per entry BEFORE Slice 2. The social
# engine reads from this set; the only allowed addition is `artistes_slugs`.
LEGACY_ENTRY_KEYS = {
    "posicio",
    "posicio_anterior",
    "canco_nom",
    "canco_slug",
    "artistes_noms",
    "artista_nom",
    "artista_slug",
    "artista_instagram_url",
    "artistes_instagram_urls",
    "cover_url",
    "album_deezer_id",
}


@pytest.fixture
def top_with_collab(db):
    principal = Artista.objects.create(nom="Ouineta", slug="ouineta", aprovat=True)
    collab = Artista.objects.create(nom="Mushkaa", slug="mushkaa", aprovat=True)
    album = Album.objects.create(nom="Alb", slug="alb", artista=principal)
    canco = Canco.objects.create(
        nom="Nois", slug="nois", artista=principal, album=album
    )
    canco.artistes_col.add(collab)
    TopSetmanal.objects.create(
        canco=canco, territori="PPCC", setmana=SETMANA, posicio=1, score_setmanal=10.0
    )
    return canco


@pytest.mark.django_db
def test_build_top_adds_parallel_slugs(top_with_collab):
    data = payload.build_top("PPCC", SETMANA)
    entry = data["entries"][0]
    # Additive: names list unchanged, slugs parallel (principal first).
    assert entry["artistes_noms"] == ["Ouineta", "Mushkaa"]
    assert entry["artistes_slugs"] == ["ouineta", "mushkaa"]
    assert len(entry["artistes_slugs"]) == len(entry["artistes_noms"])


@pytest.mark.django_db
def test_build_top_no_regression_on_legacy_keys(top_with_collab):
    data = payload.build_top("PPCC", SETMANA)
    entry = data["entries"][0]
    # The ONLY new key is `artistes_slugs`; everything else is the legacy set.
    assert set(entry) == LEGACY_ENTRY_KEYS | {"artistes_slugs"}
    # Legacy fields keep their exact values (social engine contract).
    assert entry["artista_nom"] == "Ouineta"
    assert entry["artista_slug"] == "ouineta"
    assert entry["canco_nom"] == "Nois"
    assert entry["canco_slug"] == "nois"
