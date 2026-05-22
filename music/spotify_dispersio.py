"""Artist dispersion signal derived from Spotify enrichment.

For every Artista, count the DISTINCT principal Spotify artist IDs
across that artist's enriched Cançons. dispersion=1 means a clean
mapping (all the artist's tracks resolve to the same Spotify artist);
dispersion>1 is the canonical signature of a Deezer name-collapse
collision (Crim-style), and the staff triage workbench surfaces it
as a "possible barreja" badge so reviewers split the artist before
approving more tracks under the wrong identity.

Design notes:
  * Only the PRINCIPAL spotify_artist_id counts. Collaborations
    inflate the list otherwise (a featuring on someone else's track
    would make every soloist look dispersed).
  * Cançons with enrichment_status != found are ignored (no signal).
  * We write the artist row only when the value actually changes, so
    repeated calls don't churn `updated_at`.

# Spec: docs/architecture/playlists.md (Process B section)
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction

from music.models import Artista, SpotifyMetadata


def recalcular_dispersio(artista_ids: Iterable[int] | None = None) -> dict:
    """Recompute dispersion for the given artistes, or all of them.

    Returns a dict with totals for operator visibility: how many
    artistes were inspected and how many had their dispersion
    actually changed. Cheap O(n) over the enriched-found rows.
    """
    qs = SpotifyMetadata.objects.filter(
        enrichment_status=SpotifyMetadata.STATUS_FOUND
    ).exclude(spotify_artist_id="")
    if artista_ids is not None:
        # The OneToOne canco -> artista relationship is two hops away;
        # we filter via canco__artista_id which is indexed.
        qs = qs.filter(canco__artista_id__in=list(artista_ids))
        target_artistas = Artista.objects.filter(pk__in=list(artista_ids))
    else:
        target_artistas = Artista.objects.all()

    # Build artista_id -> set(spotify_artist_id) in one pass.
    by_artist: dict[int, set[str]] = {}
    for row in qs.values_list("canco__artista_id", "spotify_artist_id"):
        artista_id, sp_id = row
        if not sp_id:
            continue
        by_artist.setdefault(artista_id, set()).add(sp_id)

    changed = 0
    inspected = 0
    with transaction.atomic():
        for a in target_artistas.only(
            "pk", "spotify_artist_dispersio", "spotify_artist_ids_distints"
        ):
            inspected += 1
            ids = sorted(by_artist.get(a.pk, set()))
            disp = len(ids) if ids else None  # None = no signal yet
            if (
                a.spotify_artist_dispersio != disp
                or list(a.spotify_artist_ids_distints or []) != ids
            ):
                a.spotify_artist_dispersio = disp
                a.spotify_artist_ids_distints = ids
                a.save(
                    update_fields=[
                        "spotify_artist_dispersio",
                        "spotify_artist_ids_distints",
                    ]
                )
                changed += 1

    return {"inspected": inspected, "changed": changed}
