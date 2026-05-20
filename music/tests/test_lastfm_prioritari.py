"""Tests for the `ArtistaLastfmAlias.prioritari` flag and the
post_save mirror to `Artista.lastfm_nom` (Sprint Portal Artista,
2026-05-19, FASE A).

Coverage:
  * The unique partial constraint forbids two `prioritari=True` rows
    per artista.
  * post_save mirror copies the prioritari name to `Artista.lastfm_nom`.
  * Flipping prioritari from one alias to another updates the mirror.
  * Deleting the prioritari clears the mirror.
  * The data migration is covered by a separate test that exercises
    the same logic end-to-end (creating an Artista with `lastfm_nom`
    set BEFORE any alias, then running the migration via direct
    function call)."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from music.models import Artista, ArtistaLastfmAlias


@pytest.mark.django_db(transaction=True)
def test_unique_constraint_forbids_two_prioritaris_per_artista():
    """The partial unique index `uniq_artista_lastfm_prioritari`
    must reject a second `prioritari=True` row for the same artista."""
    # Create with empty `lastfm_nom` so the reverse-sync signal
    # (A.7) doesn't auto-create a prioritari before we get to write
    # the two we're testing.
    art = Artista.objects.create(nom="A", lastfm_nom="", aprovat=True)
    ArtistaLastfmAlias.objects.create(
        artista=art, nom="A1", confirmat=True, prioritari=True
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ArtistaLastfmAlias.objects.create(
                artista=art, nom="A2", confirmat=True, prioritari=True
            )


@pytest.mark.django_db(transaction=True)
def test_prioritari_save_mirrors_to_artista_lastfm_nom():
    """Creating a prioritari alias propagates its `nom` to the
    artista's `lastfm_nom` (post_save → transaction.on_commit)."""
    art = Artista.objects.create(nom="Boira", lastfm_nom="", aprovat=True)
    ArtistaLastfmAlias.objects.create(
        artista=art, nom="Böira", confirmat=True, prioritari=True
    )
    art.refresh_from_db()
    assert art.lastfm_nom == "Böira"


@pytest.mark.django_db(transaction=True)
def test_flipping_prioritari_between_aliases_updates_mirror():
    """Move the prioritari flag from one alias to another. The
    mirror should reflect the new prioritari name."""
    art = Artista.objects.create(nom="X", lastfm_nom="", aprovat=True)
    a1 = ArtistaLastfmAlias.objects.create(
        artista=art, nom="X-one", confirmat=True, prioritari=True
    )
    art.refresh_from_db()
    assert art.lastfm_nom == "X-one"

    a2 = ArtistaLastfmAlias.objects.create(
        artista=art, nom="X-two", confirmat=True, prioritari=False
    )
    # Flip: drop prioritari from a1 first (partial unique forbids
    # two prioritaris at once), then promote a2.
    a1.prioritari = False
    a1.save(update_fields=["prioritari"])
    a2.prioritari = True
    a2.save(update_fields=["prioritari"])

    art.refresh_from_db()
    assert art.lastfm_nom == "X-two"


@pytest.mark.django_db(transaction=True)
def test_deleting_prioritari_clears_mirror():
    """Removing the prioritari alias leaves the artista without a
    canonical name — the mirror clears the field."""
    art = Artista.objects.create(nom="Y", lastfm_nom="", aprovat=True)
    a = ArtistaLastfmAlias.objects.create(
        artista=art, nom="Y-canon", confirmat=True, prioritari=True
    )
    art.refresh_from_db()
    assert art.lastfm_nom == "Y-canon"

    a.delete()
    art.refresh_from_db()
    assert art.lastfm_nom == ""


@pytest.mark.django_db(transaction=True)
def test_non_prioritari_save_does_not_touch_mirror():
    """A confirmed-but-not-prioritari alias shouldn't change the
    artista's canonical name — the mirror is driven exclusively by
    the prioritari row."""
    # Setting `lastfm_nom` at create-time triggers the A.7 reverse
    # sync, which creates the prioritari row for us.
    art = Artista.objects.create(nom="Z", lastfm_nom="Z-already", aprovat=True)
    assert (
        ArtistaLastfmAlias.objects.get(artista=art, nom="Z-already").prioritari is True
    )
    # Add a non-prioritari (e.g. typographic variant).
    ArtistaLastfmAlias.objects.create(
        artista=art, nom="Z-variant", confirmat=True, prioritari=False
    )
    art.refresh_from_db()
    assert art.lastfm_nom == "Z-already"


# ─── Data migration A.4: backfill function ────────────────────────


@pytest.mark.django_db(transaction=True)
def test_data_migration_idempotent():
    """Running the data backfill twice produces the same end state.

    Test simulates the actual production sequence: legacy rows exist
    (`Artista.lastfm_nom` set, alias table not yet populated), then
    the migration runs. The migration creates a prioritari alias.
    Running again is a no-op (idempotent)."""
    from music.migrations._test_helpers import run_backfill_lastfm_prioritari

    # Same trick as `test_data_migration_creates_row_when_absent`:
    # `.update()` simulates the legacy state by bypassing A.7.
    art_w = Artista.objects.create(nom="W", lastfm_nom="", aprovat=True)
    Artista.objects.filter(pk=art_w.pk).update(lastfm_nom="W-canon")
    # No alias rows yet — production state before the sprint.

    run_backfill_lastfm_prioritari()
    a = ArtistaLastfmAlias.objects.get(artista__nom="W", nom="W-canon")
    assert a.confirmat is True
    assert a.prioritari is True
    assert a.rebutjat is False

    # Re-run: same state, no new rows.
    run_backfill_lastfm_prioritari()
    assert ArtistaLastfmAlias.objects.filter(artista__nom="W").count() == 1
    a.refresh_from_db()
    assert a.confirmat is True
    assert a.prioritari is True


# ─── FASE A.7: reverse sync Artista → ArtistaLastfmAlias ─────────


@pytest.mark.django_db(transaction=True)
def test_reverse_sync_writes_create_prioritari_alias():
    """Writing `Artista.lastfm_nom` directly (without touching aliases)
    creates a matching prioritari row. This covers the 6 legacy call
    sites that update `lastfm_nom` via `artista.save()` — they must
    not need to be aware of the alias table."""
    art = Artista.objects.create(nom="P", lastfm_nom="", aprovat=True)
    assert not ArtistaLastfmAlias.objects.filter(artista=art).exists()

    art.lastfm_nom = "P-canon"
    art.save(update_fields=["lastfm_nom"])

    a = ArtistaLastfmAlias.objects.get(artista=art, nom="P-canon")
    assert a.prioritari is True
    assert a.confirmat is True
    assert a.rebutjat is False
    assert a.confirmat_at is not None


@pytest.mark.django_db(transaction=True)
def test_reverse_sync_promotes_existing_alias():
    """If a confirmed-but-not-prioritari alias already carries the
    same name, the reverse sync promotes it rather than creating a
    duplicate row (the unique (artista, nom) constraint would block
    a duplicate anyway, but we want a clean promotion path)."""
    art = Artista.objects.create(nom="Q", lastfm_nom="", aprovat=True)
    ArtistaLastfmAlias.objects.create(
        artista=art, nom="Q-name", confirmat=True, prioritari=False
    )

    art.lastfm_nom = "Q-name"
    art.save(update_fields=["lastfm_nom"])

    aliases = ArtistaLastfmAlias.objects.filter(artista=art)
    assert aliases.count() == 1
    assert aliases.first().prioritari is True


@pytest.mark.django_db(transaction=True)
def test_reverse_sync_demotes_other_prioritaris():
    """Setting `lastfm_nom` to a *different* name than the current
    prioritari must demote the old row (partial unique forbids two
    True at once)."""
    art = Artista.objects.create(nom="R", lastfm_nom="", aprovat=True)
    old = ArtistaLastfmAlias.objects.create(
        artista=art, nom="R-old", confirmat=True, prioritari=True
    )

    art.lastfm_nom = "R-new"
    art.save(update_fields=["lastfm_nom"])

    old.refresh_from_db()
    assert old.prioritari is False
    new_row = ArtistaLastfmAlias.objects.get(artista=art, nom="R-new")
    assert new_row.prioritari is True


@pytest.mark.django_db(transaction=True)
def test_reverse_sync_clear_demotes_all():
    """Clearing `Artista.lastfm_nom` demotes every prioritari for the
    artist. Aliases stay in the table as confirmed history."""
    art = Artista.objects.create(nom="S", lastfm_nom="S-canon", aprovat=True)
    art.refresh_from_db()
    assert ArtistaLastfmAlias.objects.get(artista=art, nom="S-canon").prioritari

    art.lastfm_nom = ""
    art.save(update_fields=["lastfm_nom"])

    aliases = list(ArtistaLastfmAlias.objects.filter(artista=art))
    assert len(aliases) == 1
    assert aliases[0].prioritari is False


@pytest.mark.django_db(transaction=True)
def test_reverse_sync_no_loop_with_forward():
    """The thread-local guard must break the cycle: writing
    `Artista.lastfm_nom` → reverse sync writes alias → forward
    mirror MUST NOT re-write Artista. We verify by snapshotting the
    alias row count and confirming exactly one prioritari row
    exists after a write."""
    art = Artista.objects.create(nom="T", lastfm_nom="", aprovat=True)
    art.lastfm_nom = "T-canon"
    art.save(update_fields=["lastfm_nom"])

    # Re-saving with the same value is a no-op for the alias table.
    art.lastfm_nom = "T-canon"
    art.save(update_fields=["lastfm_nom"])

    aliases = ArtistaLastfmAlias.objects.filter(artista=art, prioritari=True)
    assert aliases.count() == 1


@pytest.mark.django_db(transaction=True)
def test_reverse_sync_skipped_when_update_fields_excludes_lastfm_nom():
    """An `artista.save(update_fields=["nom"])` call must NOT
    touch the alias table — the reverse sync's cheap-exit branch."""
    art = Artista.objects.create(nom="U", lastfm_nom="", aprovat=True)
    art.nom = "U-renamed"
    art.save(update_fields=["nom"])
    assert not ArtistaLastfmAlias.objects.filter(artista=art).exists()


@pytest.mark.django_db(transaction=True)
def test_data_migration_creates_row_when_absent():
    """An artista with `lastfm_nom` set but NO alias rows gets a new
    alias created with prioritari=True."""
    from music.migrations._test_helpers import run_backfill_lastfm_prioritari

    # Simulate the legacy production state via a QuerySet `.update()`
    # — bypasses model signals so A.7's reverse sync doesn't auto-
    # create the alias the migration is supposed to backfill.
    art = Artista.objects.create(nom="V", lastfm_nom="", aprovat=True)
    Artista.objects.filter(pk=art.pk).update(lastfm_nom="V-canon")
    assert not ArtistaLastfmAlias.objects.filter(artista=art).exists()

    run_backfill_lastfm_prioritari()
    a = ArtistaLastfmAlias.objects.get(artista=art, nom="V-canon")
    assert a.confirmat is True
    assert a.prioritari is True
    assert a.confirmat_at is not None
