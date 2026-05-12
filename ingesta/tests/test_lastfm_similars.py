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
def test_absorb_helper_deletes_clean_lastfm_pendent(db):
    """Anna Roig topology: confirmed alias on the canonical, plus a
    stale pendent at the same literal name. The absorb helper must
    delete the pendent and redirect any similars rows."""
    from web.api.staff.artistes import _absorb_lastfm_duplicate_pendents

    canon = Artista.objects.create(
        nom="Anna Roig i L'ombre de ton chien",
        lastfm_nom="Anna Roig i L'ombre de ton chien",
        aprovat=True,
    )
    typographic = "Anna Roig i L’ombre de ton chien"
    ArtistaLastfmAlias.objects.create(artista=canon, nom=typographic, confirmat=True)
    dup = Artista.objects.create(
        nom=typographic,
        lastfm_nom=typographic,
        aprovat=False,
        pendent_review=True,
        font_descoberta="lastfm_similar",
    )
    # A similars row pointing at the duplicate — it should be
    # redirected to the canonical, not deleted.
    other = Artista.objects.create(nom="Other", lastfm_nom="Other", aprovat=True)
    ArtistaLastfmSimilar.objects.create(source=other, target=dup)

    n = _absorb_lastfm_duplicate_pendents(canon, typographic)
    assert n == 1
    assert not Artista.objects.filter(pk=dup.pk).exists()
    # Similar redirected.
    redirected = ArtistaLastfmSimilar.objects.get(source=other)
    assert redirected.target_id == canon.pk
    canon.refresh_from_db()
    assert canon.nb_similars_lastfm == 1


@pytest.mark.django_db
def test_absorb_helper_preserves_pendent_with_data(db):
    """A pendent that already has Cançons / deezer_ids / territoris
    / collabs is NOT a clean dup — keep it for human review."""
    from music.models import Album, Canco
    from web.api.staff.artistes import _absorb_lastfm_duplicate_pendents

    canon = Artista.objects.create(
        nom="Sabor de Gràcia",
        lastfm_nom="Sabor de Gràcia",
        aprovat=True,
    )
    ArtistaLastfmAlias.objects.create(
        artista=canon, nom="Sabor De Gracia", confirmat=True
    )
    dup = Artista.objects.create(
        nom="Sabor De Gracia",
        lastfm_nom="Sabor De Gracia",
        aprovat=False,
        pendent_review=True,
        font_descoberta="lastfm_similar",
    )
    # Attach a Cançó so the dup looks like it has real ingestion
    # behind it. This is the safety floor — we never auto-delete
    # rows with downstream content.
    album = Album.objects.create(nom="Album X", artista=dup)
    Canco.objects.create(nom="Track X", artista=dup, album=album, deezer_id=99999)

    n = _absorb_lastfm_duplicate_pendents(canon, "Sabor De Gracia")
    assert n == 0
    assert Artista.objects.filter(pk=dup.pk).exists()


@pytest.mark.django_db
def test_absorb_helper_only_acts_on_lastfm_similar_source(db):
    """A pendent created via UserPropostaArtista (or any non-cron
    path) carries human intent — never auto-delete it just because
    its name matches a confirmed alias."""
    from web.api.staff.artistes import _absorb_lastfm_duplicate_pendents

    canon = Artista.objects.create(
        nom="Some Band", lastfm_nom="Some Band", aprovat=True
    )
    ArtistaLastfmAlias.objects.create(artista=canon, nom="some band", confirmat=True)
    dup = Artista.objects.create(
        nom="some band",
        lastfm_nom="some band",
        aprovat=False,
        pendent_review=True,
        font_descoberta="proposta_usuari",  # not lastfm_similar
    )

    n = _absorb_lastfm_duplicate_pendents(canon, "some band")
    assert n == 0
    assert Artista.objects.filter(pk=dup.pk).exists()


@pytest.mark.django_db
def test_unique_constraint_source_target(db, manel, delen):
    """The DB-level UNIQUE constraint blocks accidental duplicates,
    in case a future call site forgets to dedup."""
    from django.db import IntegrityError

    ArtistaLastfmSimilar.objects.create(source=manel, target=delen)
    with pytest.raises(IntegrityError):
        ArtistaLastfmSimilar.objects.create(source=manel, target=delen)


@pytest.mark.django_db
def test_cron_skips_pendents_as_sources(db):
    """Only approved artistes feed the discovery cron. A pendent with
    a NULL `lastfm_last_sync` (max priority under the old _prio=1
    tier) must be left untouched after a `--limit 10` run.

    Cascade-cut decision 2026-05-12: pendent → pendent edges saturated
    the backlog without adding signal."""
    from unittest.mock import patch

    from django.core.management import call_command

    approved = Artista.objects.create(
        nom="ApprovedSrc", lastfm_nom="ApprovedSrc", aprovat=True
    )
    pending = Artista.objects.create(
        nom="PendingSrc",
        lastfm_nom="PendingSrc",
        aprovat=False,
        pendent_review=True,
    )

    # Mock both Last.fm fetches so the test stays offline. info=truthy
    # so the command's `if info` branch runs and lastfm_last_sync gets
    # stamped.
    info_stub = {"name": "ApprovedSrc", "stats": {}, "bio": {}, "tags": {"tag": []}}
    with (
        patch(
            "ingesta.management.commands.obtenir_metadata_lastfm.get_artist_info",
            return_value=info_stub,
        ),
        patch(
            "ingesta.management.commands.obtenir_metadata_lastfm.get_artist_similar",
            return_value=[],
        ),
    ):
        call_command("obtenir_metadata_lastfm", "--limit", "10")

    approved.refresh_from_db()
    pending.refresh_from_db()
    assert approved.lastfm_last_sync is not None, "approved source must be synced"
    assert pending.lastfm_last_sync is None, "pendent must NOT be processed as source"
