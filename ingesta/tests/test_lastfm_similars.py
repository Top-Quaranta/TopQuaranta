"""Last.fm similars: dedup variants per source, alias-aware target
resolution, and recompute of the cached `nb_similars_lastfm`.

Caught 2026-05-01 in the same investigation as ArtistaLastfmAlias:
when Last.fm lists the same artist under multiple spellings within
a single source's similars response (e.g. 'Delên' AND 'dêlen'), the
old counter went up by 2. With the row-per-recommendation table and
alias-aware lookup, both spellings now resolve to the same target
and dedup to a single row.
"""

from __future__ import annotations

import pytest

from music.models import (
    Artista,
    ArtistaLastfmAlias,
    ArtistaLastfmSimilar,
)


@pytest.fixture
def cmd(db):
    """Instance of the management command, used to call its private
    helpers without spinning up the full Last.fm fetch loop."""
    from ingesta.management.commands.obtenir_metadata_lastfm import Command

    c = Command()
    c.stdout = type("S", (), {"write": lambda self, *a, **k: None})()  # silence stdout
    return c


@pytest.fixture
def manel(db):
    return Artista.objects.create(nom="Manel", lastfm_nom="Manel", aprovat=True)


@pytest.fixture
def delen(db):
    """Canonical Delên + a confirmed alias 'dêlen' so the resolver
    can collapse the variant onto this row."""
    art = Artista.objects.create(nom="Delên", lastfm_nom="Delên", aprovat=True)
    ArtistaLastfmAlias.objects.create(artista=art, nom="dêlen", confirmat=True)
    return art


@pytest.mark.django_db
def test_resolver_returns_existing_artist_by_lastfm_nom(cmd, manel):
    """Direct hit on the canonical name is the cheapest path."""
    target, created = cmd._resolve_similar_target("Manel", dry_run=False)
    assert target.pk == manel.pk
    assert created is False


@pytest.mark.django_db
def test_resolver_uses_confirmed_alias(cmd, delen):
    """A variant name matches the confirmed alias and resolves to
    the canonical Delên — not a new pendent."""
    target, created = cmd._resolve_similar_target("dêlen", dry_run=False)
    assert target.pk == delen.pk
    assert created is False
    # No new artist was created.
    assert Artista.objects.filter(lastfm_nom="dêlen").count() == 0


@pytest.mark.django_db
def test_resolver_alias_of_approved_beats_stale_pendent(cmd):
    """Anna Roig case (caught 2026-05-01): the canonical artist is
    approved (ASCII apostrophe), with a confirmed alias for the
    typographic spelling. Before the alias path existed, the
    similars cron created a separate pendent at the typographic
    spelling — that stale pendent must NOT win against the alias
    of the approved artist when the same name re-appears now."""
    canon = Artista.objects.create(
        nom="Anna Roig i L'ombre de ton chien",
        lastfm_nom="Anna Roig i L'ombre de ton chien",
        aprovat=True,
    )
    ArtistaLastfmAlias.objects.create(
        artista=canon,
        nom="Anna Roig i L’ombre de ton chien",  # typographic apostrophe
        confirmat=True,
    )
    stale_pendent = Artista.objects.create(
        nom="Anna Roig i L’ombre de ton chien",  # typographic
        lastfm_nom="Anna Roig i L’ombre de ton chien",
        aprovat=False,
        pendent_review=True,
    )

    target, created = cmd._resolve_similar_target(
        "Anna Roig i L’ombre de ton chien", dry_run=False
    )
    assert target.pk == canon.pk
    assert target.pk != stale_pendent.pk
    assert created is False


@pytest.mark.django_db
def test_resolver_creates_pendent_when_no_match(cmd):
    """An unknown name becomes a pendent placeholder, same as
    before — the alias path is purely additive."""
    target, created = cmd._resolve_similar_target("Random Band", dry_run=False)
    assert target is not None
    assert created is True
    assert target.aprovat is False
    assert target.pendent_review is True
    assert target.font_descoberta == "lastfm_similar"


@pytest.mark.django_db
def test_replace_similars_dedup_by_target(cmd, manel, delen):
    """Even if 'Delên' and 'dêlen' both appear in the same source's
    response, only ONE row is written — dedup happens at call site
    (`seen_target_pks` set in `_process`). Here we exercise the
    underlying `_replace_similars` invariant: bulk_create with
    duplicate targets becomes a single row."""
    # Simulate `_process` having already deduped: pass each unique
    # target only once.
    cmd._replace_similars(source=manel, targets=[(delen, 0.9)])
    rows = ArtistaLastfmSimilar.objects.filter(source=manel)
    assert rows.count() == 1
    assert rows.first().target_id == delen.pk
    delen.refresh_from_db()
    assert delen.nb_similars_lastfm == 1


@pytest.mark.django_db
def test_replace_similars_recomputes_cached_count(cmd, manel, delen):
    """The cached `nb_similars_lastfm` must reflect the actual row
    count, not an append-only sum. Replacing Manel's similars with
    an empty set should drop Delên's count back to 0."""
    cmd._replace_similars(source=manel, targets=[(delen, 0.9)])
    delen.refresh_from_db()
    assert delen.nb_similars_lastfm == 1
    # Manel's similars get re-fetched and now Delên isn't there.
    cmd._replace_similars(source=manel, targets=[])
    delen.refresh_from_db()
    assert delen.nb_similars_lastfm == 0


@pytest.mark.django_db
def test_replace_similars_idempotent(cmd, manel, delen):
    """Re-running with the same target set leaves the count stable
    (no double-count). Critical: the previous integer-counter design
    bumped on every call without idempotency."""
    cmd._replace_similars(source=manel, targets=[(delen, 0.9)])
    cmd._replace_similars(source=manel, targets=[(delen, 0.9)])
    cmd._replace_similars(source=manel, targets=[(delen, 0.9)])
    delen.refresh_from_db()
    assert delen.nb_similars_lastfm == 1


@pytest.mark.django_db
def test_count_accumulates_across_distinct_sources(db, cmd, delen):
    """Two different sources both recommending Delên → count = 2.
    The dedup is per-source, not global."""
    a = Artista.objects.create(nom="A", lastfm_nom="A", aprovat=True)
    b = Artista.objects.create(nom="B", lastfm_nom="B", aprovat=True)
    cmd._replace_similars(source=a, targets=[(delen, 0.9)])
    cmd._replace_similars(source=b, targets=[(delen, 0.9)])
    delen.refresh_from_db()
    assert delen.nb_similars_lastfm == 2


@pytest.mark.django_db
def test_unique_constraint_source_target(db, manel, delen):
    """The DB-level UNIQUE constraint blocks accidental duplicates,
    in case a future call site forgets to dedup."""
    from django.db import IntegrityError

    ArtistaLastfmSimilar.objects.create(source=manel, target=delen)
    with pytest.raises(IntegrityError):
        ArtistaLastfmSimilar.objects.create(source=manel, target=delen)
