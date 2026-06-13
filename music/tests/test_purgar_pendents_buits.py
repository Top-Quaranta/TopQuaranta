"""purgar_pendents_buits — the casc-buit hard-delete command.

Pins:
  - dry-run (default) deletes nothing.
  - --execute deletes the 0/0/0 pending cohort.
  - --pks restricts to the given pks, intersected with the cohort (a pk
    outside the cohort is ignored — never deleted).
  - artists with a Cançó / anchor / signal are never in the cohort.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command

from music.models import Album, Artista, ArtistaDeezer, Canco


@pytest.fixture
def cohort_and_safe(db):
    # Three empty pending artists (in the cohort).
    a = Artista.objects.create(
        nom="Empty A", slug="empty-a", aprovat=False, pendent_review=True
    )
    b = Artista.objects.create(
        nom="Empty B", slug="empty-b", aprovat=False, pendent_review=True
    )
    c = Artista.objects.create(
        nom="Empty C", slug="empty-c", aprovat=False, pendent_review=True
    )
    # Not in cohort: has an anchor.
    anchored = Artista.objects.create(
        nom="Anchored", slug="anchored", aprovat=False, pendent_review=True
    )
    ArtistaDeezer.objects.create(artista=anchored, deezer_id=999001, principal=True)
    # Not in cohort: has a Cançó.
    with_song = Artista.objects.create(
        nom="WithSong", slug="withsong", aprovat=False, pendent_review=True
    )
    alb = Album.objects.create(nom="Alb", slug="alb-x", artista=with_song)
    Canco.objects.create(nom="C", slug="c-x", artista=with_song, album=alb)
    # Not in cohort: descartat (terminal).
    descartat = Artista.objects.create(
        nom="Descartat", slug="descartat-x", aprovat=False, pendent_review=False
    )
    return a, b, c, anchored, with_song, descartat


@pytest.mark.django_db
def test_dry_run_deletes_nothing(cohort_and_safe):
    before = Artista.objects.count()
    call_command("purgar_pendents_buits")  # no --execute
    assert Artista.objects.count() == before


@pytest.mark.django_db
def test_pks_restriction_only_deletes_listed_cohort(cohort_and_safe):
    a, b, c, anchored, with_song, descartat = cohort_and_safe
    call_command("purgar_pendents_buits", "--execute", f"--pks={a.pk},{b.pk}")
    assert not Artista.objects.filter(pk__in=[a.pk, b.pk]).exists()
    # c (cohort, not listed) survives; safe rows survive.
    for art in (c, anchored, with_song, descartat):
        assert Artista.objects.filter(pk=art.pk).exists()


@pytest.mark.django_db
def test_pks_outside_cohort_are_ignored(cohort_and_safe):
    a, b, c, anchored, with_song, descartat = cohort_and_safe
    # Pass anchored/with_song/descartat pks: none is in the 0/0/0 cohort.
    call_command(
        "purgar_pendents_buits",
        "--execute",
        f"--pks={anchored.pk},{with_song.pk},{descartat.pk}",
    )
    for art in (anchored, with_song, descartat):
        assert Artista.objects.filter(pk=art.pk).exists()


@pytest.mark.django_db
def test_execute_no_pks_deletes_whole_cohort(cohort_and_safe):
    a, b, c, anchored, with_song, descartat = cohort_and_safe
    call_command("purgar_pendents_buits", "--execute")
    assert not Artista.objects.filter(pk__in=[a.pk, b.pk, c.pk]).exists()
    for art in (anchored, with_song, descartat):
        assert Artista.objects.filter(pk=art.pk).exists()
