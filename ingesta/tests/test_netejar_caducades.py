# Spec: docs/architecture/pipeline.md
"""Minimal coverage for the destructive caducitat purge.

`netejar_caducades` hard-deletes unverified, active tracks past
DIES_CADUCITAT. Until now it had no test at all. This pins the survivor
set — especially that NULL-dated pendents are KEPT (the `__lt` filter
never matches NULL). That matters because the enrich side is now blinded
to caducats via `exclude_caducats`, but the two must stay mirror images:
if the roadmap NULL-escape fix changes the purge filter (e.g. to also
delete NULL-dated rows) without updating `exclude_caducats`, the
survivor-mirror invariant breaks silently — this test catches it.

See test_caducitat_guard for the queryset-level mirror, and
test_enriquir_spotify for the enrich-pending guard.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command

from ingesta.caducitat import caducitat_cutoff
from music.models import Album, Artista, Canco


@pytest.mark.django_db
def test_netejar_caducades_survivor_set():
    """Only the caducat, unverified, ACTIVE track is deleted. Kept:
    NULL-dated (unknown → not caducat), recent, verified-caducat (the
    purge only sweeps verificada=False), and the activa=False rejection
    tombstone."""
    a = Artista.objects.create(nom="A", lastfm_nom="A")
    al = Album.objects.create(artista=a, nom="Al")
    cutoff = caducitat_cutoff()

    def mk(dz, *, data, verificada=False, activa=True):
        return Canco.objects.create(
            artista=a,
            album=al,
            nom=f"c{dz}",
            deezer_id=dz,
            isrc="",
            data_llancament=data,
            verificada=verificada,
            activa=activa,
        )

    caducat = mk(201, data=cutoff - timedelta(days=1))  # → deleted
    null_date = mk(202, data=None)  # → kept (NULL never matches __lt)
    recent = mk(203, data=cutoff + timedelta(days=1))  # → kept
    verificat_caducat = mk(204, data=cutoff - timedelta(days=1), verificada=True)
    tombstone = mk(205, data=cutoff - timedelta(days=1), activa=False)

    call_command("netejar_caducades")

    alive = set(Canco.objects.values_list("pk", flat=True))
    assert caducat.pk not in alive  # the only deletion
    assert null_date.pk in alive  # NULL kept — mirror of the __lt filter
    assert recent.pk in alive
    assert verificat_caducat.pk in alive  # purge only sweeps verificada=False
    assert tombstone.pk in alive  # activa=False rejection trail preserved
