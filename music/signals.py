"""Signals for the music app — auto-sync territories from ArtistaLocalitat
and bidirectional sync between `Artista.lastfm_nom` and
`ArtistaLastfmAlias.prioritari` (Sprint Portal Artista A.7).

R12: the signal is wrapped in `transaction.on_commit()` so the territory
M2M is recomputed once, after the surrounding transaction commits, instead
of N times in the middle of an `atomic()` block (one per ArtistaLocalitat
row inserted/updated). The previous behaviour produced inconsistent
intermediate states visible to concurrent readers.

D5: a Canco must not list its own main Artista as a collaborator. The
`m2m_changed` guard below rejects `canco.artistes_col.add(...)` calls
that would create a self-collab. Migration 0034 cleaned up pre-existing
rows; this signal prevents the same class of bug from re-entering the
data via the Deezer contributor parser.
"""

import threading

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from music.models import (
    Artista,
    ArtistaDeezer,
    ArtistaLastfmAlias,
    ArtistaLocalitat,
    Canco,
)

# Thread-local re-entrancy guard for the bidirectional
# `Artista.lastfm_nom` ⇄ `ArtistaLastfmAlias.prioritari` sync.
# Set inside whichever direction wrote the field so the opposite-
# direction signal short-circuits and avoids an infinite loop.
_lastfm_sync_state = threading.local()


def _in_lastfm_sync() -> bool:
    return getattr(_lastfm_sync_state, "active", False)


class _LastfmSyncGuard:
    """Context manager that suppresses re-entrancy on the
    Artista⇄ArtistaLastfmAlias mirrors. Stacks safely if it
    happens to nest."""

    def __enter__(self):
        self._prev = getattr(_lastfm_sync_state, "active", False)
        _lastfm_sync_state.active = True
        return self

    def __exit__(self, *exc):
        _lastfm_sync_state.active = self._prev
        return False


def _resync(artista_id: int) -> None:
    """Resolve the artist by id and resync its territories.

    Defensive lookup: if the artist (or the localitat that triggered us)
    has been cascade-deleted between the signal firing and the on_commit
    callback running, do nothing.
    """
    from music.models import Artista

    artista = Artista.objects.filter(pk=artista_id).first()
    if artista is not None:
        artista.sync_territoris_from_localitats()


@receiver(post_save, sender=ArtistaLocalitat)
def sync_territoris_on_localitat_save(sender, instance, **kwargs):
    """Recompute artist territories when a location is added or changed."""
    artista_id = instance.artista_id
    transaction.on_commit(lambda: _resync(artista_id))


@receiver(post_delete, sender=ArtistaLocalitat)
def sync_territoris_on_localitat_delete(sender, instance, **kwargs):
    """Recompute artist territories when a location is removed."""
    artista_id = instance.artista_id
    transaction.on_commit(lambda: _resync(artista_id))


@receiver(m2m_changed, sender=Canco.artistes_col.through)
def prevent_self_collab(sender, instance, action, pk_set, reverse, **kwargs):
    """D5: reject `canco.artistes_col.add(main_artista)`.

    Only fires on the forward direction (Canco.artistes_col.add/set). The
    reverse direction (Artista.participacions.add) is rarely used; the
    check is symmetric anyway because we compare by ID.
    """
    if action not in {"pre_add", "pre_set"} or not pk_set:
        return
    if reverse:
        # `instance` is the Artista; pk_set is Canco IDs. Reject any Canco
        # whose main artista is `instance`.
        if Canco.objects.filter(pk__in=pk_set, artista=instance).exists():
            raise ValidationError(
                "D5: an artist cannot be listed as a collaborator on "
                "their own track."
            )
    else:
        # `instance` is the Canco; pk_set is Artista IDs.
        if instance.artista_id in pk_set:
            raise ValidationError(
                "D5: an artist cannot be listed as a collaborator on "
                "their own track."
            )


@receiver(post_delete, sender=ArtistaDeezer)
def unapprove_on_last_deezer_removed(sender, instance, **kwargs):
    """Invariant: `aprovat=True` ⇒ at least one external ID
    (Deezer OR MusicBrainz).

    When the last Deezer ID is removed, the Deezer pipeline can no
    longer ingest material for the artist — but if we have an MBID we
    can still rely on the MusicBrainz sync, so keep them aprovat.

    Only desaprova'l if the artist lost BOTH external anchors
    (Deezer + MBID).

    Motivation: Crim-style collisions. Two Catalan artists share a
    single Deezer ID (347962). Only one can own it per the DB unique
    constraint; the other stays Deezer-less but MusicBrainz-backed.
    """
    artista_id = instance.artista_id
    if not artista_id:
        return
    # If any other Deezer ID still references this artist, nothing to do.
    if ArtistaDeezer.objects.filter(artista_id=artista_id).exists():
        return
    from music.models import Artista

    # Still has an MBID → the MB pipeline is enough to keep them live.
    if (
        Artista.objects.filter(pk=artista_id)
        .exclude(musicbrainz_id="")
        .exclude(musicbrainz_id__isnull=True)
        .exists()
    ):
        return

    # No Deezer + no MBID → desaprova'l. The `update()` path skips
    # Artista.save() so we don't retrigger the territori sync.
    Artista.objects.filter(pk=artista_id, aprovat=True).update(
        aprovat=False,
        pendent_review=False,
    )


# ─── Last.fm alias prioritari → mirror to Artista.lastfm_nom ─────────


def _mirror_lastfm_nom(artista_id: int) -> None:
    """Read the current `prioritari` alias for `artista_id` and copy
    its name to `Artista.lastfm_nom`. If no prioritari row exists,
    clear the field.

    Used as a deferred callback (on_commit) so the mirror runs once
    after the surrounding transaction settles — no half-state visible
    to concurrent readers when the gestor flips prioritari from one
    alias to another in a single PATCH.

    The save is wrapped in `_LastfmSyncGuard` so the Artista
    post_save handler — which would otherwise run the *reverse*
    direction (artista → alias) — short-circuits."""
    from music.models import Artista, ArtistaLastfmAlias

    artista = Artista.objects.filter(pk=artista_id).first()
    if artista is None:
        return
    new_nom = (
        ArtistaLastfmAlias.objects.filter(artista_id=artista_id, prioritari=True)
        .values_list("nom", flat=True)
        .first()
        or ""
    )
    if artista.lastfm_nom != new_nom:
        artista.lastfm_nom = new_nom
        with _LastfmSyncGuard():
            artista.save(update_fields=["lastfm_nom"])


@receiver(post_save, sender=ArtistaLastfmAlias)
def mirror_lastfm_nom_on_alias_save(sender, instance, **kwargs):
    """Sprint Portal Artista (2026-05-19): keep `Artista.lastfm_nom`
    aligned with the current `prioritari=True` alias.

    Fires on every alias save; the resolver inside `_mirror_lastfm_nom`
    finds the current prioritari and copies its name (or clears the
    field if none). Cheap because the table is small (one row per
    confirmed alias per artista; most artistes have 1, a handful have
    2-3 after the Boira/Böira-style audits).

    Skipped when the alias write itself originated inside the
    reverse-sync path (Artista → alias). Without this short-circuit
    the two mirrors would re-fire each other forever on every
    `Artista.lastfm_nom` write."""
    if _in_lastfm_sync():
        return
    transaction.on_commit(lambda: _mirror_lastfm_nom(instance.artista_id))


@receiver(post_delete, sender=ArtistaLastfmAlias)
def mirror_lastfm_nom_on_alias_delete(sender, instance, **kwargs):
    """Same as the post_save handler — re-evaluate the prioritari
    after a row is removed. If the deleted row was the prioritari,
    the artist's `lastfm_nom` is cleared (or set to whatever other
    row carries prioritari=True, but the unique constraint forbids
    two prioritaris so the only legitimate next state is empty)."""
    if _in_lastfm_sync():
        return
    transaction.on_commit(lambda: _mirror_lastfm_nom(instance.artista_id))


# ─── Artista.lastfm_nom → ArtistaLastfmAlias prioritari (reverse) ────


def _sync_alias_from_artista(artista_id: int, new_nom: str) -> None:
    """Reconcile `ArtistaLastfmAlias.prioritari` so it matches the
    canonical `Artista.lastfm_nom` written by an external caller
    (admin form, staff PATCH, MB sync, services helper, etc.).

    Rules:
      * `new_nom == ""` → demote every alias for this artista
        (`prioritari=False`). No deletions: the rows stay as
        confirmed history.
      * `new_nom != ""` → look up an alias with the same `nom`
        (case-sensitive — matches the forward direction):
          - found → promote it to `prioritari=True` after demoting
            any other prioritari for the artista (the partial unique
            constraint forbids two at once);
          - not found → create a new row `confirmat=True,
            prioritari=True, rebutjat=False, confirmat_at=now`.

    All writes happen inside `_LastfmSyncGuard` so the forward-
    direction mirror (`mirror_lastfm_nom_on_alias_save`) doesn't
    fire, which would otherwise schedule a redundant on_commit
    callback for the same artista on every PATCH."""
    from music.models import ArtistaLastfmAlias

    with _LastfmSyncGuard():
        if not new_nom:
            ArtistaLastfmAlias.objects.filter(
                artista_id=artista_id, prioritari=True
            ).update(prioritari=False)
            return

        # Drop any *other* prioritari for this artista before
        # promoting the target row — partial unique
        # `uniq_artista_lastfm_prioritari` allows only one True.
        ArtistaLastfmAlias.objects.filter(
            artista_id=artista_id, prioritari=True
        ).exclude(nom=new_nom).update(prioritari=False)

        target = ArtistaLastfmAlias.objects.filter(
            artista_id=artista_id, nom=new_nom
        ).first()
        now = timezone.now()
        if target is None:
            ArtistaLastfmAlias.objects.create(
                artista_id=artista_id,
                nom=new_nom,
                confirmat=True,
                rebutjat=False,
                prioritari=True,
                confirmat_at=now,
            )
            return

        changed_fields = []
        if not target.prioritari:
            target.prioritari = True
            changed_fields.append("prioritari")
        if not target.confirmat:
            target.confirmat = True
            changed_fields.append("confirmat")
            if target.confirmat_at is None:
                target.confirmat_at = now
                changed_fields.append("confirmat_at")
        if target.rebutjat:
            target.rebutjat = False
            changed_fields.append("rebutjat")
        if changed_fields:
            target.save(update_fields=changed_fields)


@receiver(post_save, sender=Artista)
def sync_alias_on_artista_save(sender, instance, created, update_fields, **kwargs):
    """Sprint Portal Artista A.7 (2026-05-20): reverse sync.

    When an external caller writes `Artista.lastfm_nom` directly —
    via `services.py`, the staff PATCH endpoints, the MB cron, or
    the legacy Last.fm metadata command — keep the alias table
    consistent so the canonical `prioritari` row matches.

    Short-circuits:
      * `_in_lastfm_sync()`: we're inside the forward mirror —
        the alias is already the source of truth, nothing to do.
      * `update_fields` was supplied and doesn't mention
        `lastfm_nom`: cheap exit on the very common path
        (territory sync, image upload, etc.).
    """
    if _in_lastfm_sync():
        return
    if update_fields is not None and "lastfm_nom" not in update_fields:
        return

    artista_id = instance.pk
    new_nom = instance.lastfm_nom or ""
    transaction.on_commit(lambda: _sync_alias_from_artista(artista_id, new_nom))
