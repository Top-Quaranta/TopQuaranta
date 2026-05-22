"""Full-DB recalc of Artista.spotify_artist_dispersio.

Useful after a bulk enrichment run, after a migration that adds new
fields, or when an operator suspects the dispersion cache has
drifted (no auto-invalidation today).

# Spec: music/spotify_dispersio.py
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from music.spotify_dispersio import recalcular_dispersio


class Command(BaseCommand):
    help = "Recompute spotify_artist_dispersio for every Artista."

    def handle(self, *args, **opts):
        result = recalcular_dispersio()  # None means: all artistas
        self.stdout.write(
            f"[recalcular_dispersio_spotify] "
            f"inspected={result['inspected']} changed={result['changed']}"
        )
