"""Deactivate orphan pendent cançons left in the verification queue.

Auditoria 2026-06-07, informe 2a. A pendent canço (`verificada=False,
activa=True`) is only reviewable if it has at least one approved artist —
the main `artista` or an `artistes_col` collaborator. The verify queue
(`Canco.objects.pendents()`) never filtered on artist approval, so songs
whose main and every collaborator were pendent/rejected piled up there.
At audit time 149 such orphans existed (28% of the 537-row queue), the
canonical case being "Love Me (Slowed)" (Irokz): created from a legacy
pendent artist's album, then left with every artist pendent after the
album owner was rejected.

This backfill sets `activa=False` on those rows so they leave the queue.
It is the historical counterpart of the runtime fixes shipped in the
same change: `music.services.has_approved_artist` /
`orphan_pendents_qs` (the canonical predicate) and the de-approval hook
in `rebutjar_artista`.

SPARED (the explicit caveat): songs whose `contributors_raw` is NOT
empty still await deferred-collaborator resolution and may yet gain an
approved artist on approval — they keep `activa=True`. The predicate
below mirrors `orphan_pendents_qs` but is written against the historical
model per Django convention (no import of runtime model code).

Reversible and non-destructive: forward sets `activa=False`, reverse
sets the same rows back to `activa=True`. No row is ever deleted.
"""

from __future__ import annotations

from django.db import migrations


def _orphan_pendents(Canco):
    """Mirror of music.services.orphan_pendents_qs against the historical
    model: pendent, active, no approved artist (main or collab), and no
    pending deferred contributors."""
    return (
        Canco.objects.filter(verificada=False, activa=True, contributors_raw=[])
        .exclude(artista__aprovat=True)
        .exclude(artistes_col__aprovat=True)
        .distinct()
    )


def forwards(apps, schema_editor):
    Canco = apps.get_model("music", "Canco")
    ids = list(_orphan_pendents(Canco).values_list("id", flat=True))
    if ids:
        Canco.objects.filter(id__in=ids).update(activa=False)


def backwards(apps, schema_editor):
    # Best-effort reverse: re-activate the rows this migration would
    # match if they were active. Since forward set them inactive, we
    # re-activate every pendent row that is currently orphan + inactive
    # with no pending contributors. This may re-activate a row that was
    # independently deactivated, but never deletes data.
    Canco = apps.get_model("music", "Canco")
    ids = list(
        Canco.objects.filter(verificada=False, activa=False, contributors_raw=[])
        .exclude(artista__aprovat=True)
        .exclude(artistes_col__aprovat=True)
        .distinct()
        .values_list("id", flat=True)
    )
    if ids:
        Canco.objects.filter(id__in=ids).update(activa=True)


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0089_repurpose_no_verif_7_as_novetats_per_verificar"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
