"""purgar_pendents_post_seed — keep the seed, delete post-seed pendents
with no verified Cançó (hard delete, no rebuig)."""

from __future__ import annotations

import datetime

import pytest
from django.core.management import call_command

from comptes.models import UserArtista
from music.models import Album, Artista, Canco

BOUND = "2026-05-01"
SEED_DATE = datetime.datetime(2026, 4, 10, tzinfo=datetime.timezone.utc)
POST_DATE = datetime.datetime(2026, 5, 15, tzinfo=datetime.timezone.utc)


def _pend(nom, slug, when):
    a = Artista.objects.create(nom=nom, slug=slug, aprovat=False, pendent_review=True)
    Artista.objects.filter(pk=a.pk).update(created_at=when)
    return Artista.objects.get(pk=a.pk)


@pytest.fixture
def scenario(db, django_user_model):
    seed = _pend("Seed Band", "seed-band", SEED_DATE)  # April → keep
    post_empty = _pend("Post Empty", "post-empty", POST_DATE)  # delete
    post_unverified = _pend("Post Unverified", "post-unverified", POST_DATE)
    alb1 = Album.objects.create(nom="A1", slug="a1", artista=post_unverified)
    Canco.objects.create(
        nom="c1", slug="c1", artista=post_unverified, album=alb1, verificada=False
    )  # unverified canço → still delete
    post_verified = _pend("Post Verified", "post-verified", POST_DATE)
    alb2 = Album.objects.create(nom="A2", slug="a2", artista=post_verified)
    Canco.objects.create(
        nom="c2", slug="c2", artista=post_verified, album=alb2, verificada=True
    )  # verified canço → keep
    post_claimed = _pend("Post Claimed", "post-claimed", POST_DATE)
    u = django_user_model.objects.create_user(
        username="u1", email="u1@x.cat", password="x"
    )
    UserArtista.objects.create(usuari=u, artista=post_claimed)  # user link → keep
    return locals()


@pytest.mark.django_db
def test_dry_run_deletes_nothing(scenario):
    before = Artista.objects.count()
    call_command("purgar_pendents_post_seed", f"--keep-before={BOUND}")
    assert Artista.objects.count() == before


@pytest.mark.django_db
def test_execute_keeps_seed_verified_claimed_deletes_rest(scenario):
    s = scenario
    call_command("purgar_pendents_post_seed", "--execute", f"--keep-before={BOUND}")
    # Deleted: post_empty + post_unverified.
    assert not Artista.objects.filter(pk=s["post_empty"].pk).exists()
    assert not Artista.objects.filter(pk=s["post_unverified"].pk).exists()
    # Kept: seed (April), post_verified (verified canço), post_claimed (user link).
    assert Artista.objects.filter(pk=s["seed"].pk).exists()
    assert Artista.objects.filter(pk=s["post_verified"].pk).exists()
    assert Artista.objects.filter(pk=s["post_claimed"].pk).exists()


@pytest.mark.django_db
def test_no_rebuig_record_written(scenario):
    """Hard delete must not create a HistorialRevisio rejection (so the
    artist can re-enter later)."""
    from music.models import HistorialRevisio

    before = HistorialRevisio.objects.count()
    call_command("purgar_pendents_post_seed", "--execute", f"--keep-before={BOUND}")
    assert HistorialRevisio.objects.count() == before
