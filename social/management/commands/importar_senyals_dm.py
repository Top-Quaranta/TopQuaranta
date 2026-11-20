"""Load per-artist Instagram inbox counts produced by
`scripts/senyals_dm_instagram.py`.

    python manage.py importar_senyals_dm senyals.json [--dry-run]

The file is a JSON list of `[nom, missatges, mencions, reaccions, ultim]`.
An account is matched to an artist by normalised name, and only when
exactly one approved artist carries it: an inbox name is not an identity,
so anything ambiguous is reported and skipped rather than guessed.

# Spec: docs/architecture/social.md
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db import transaction

from music.models import Artista, normalitza_nom_homonim
from social.models import SenyalDM


class Command(BaseCommand):
    help = "Importa els comptadors de missatges directes d'Instagram per artista."

    def add_arguments(self, parser):
        parser.add_argument("fitxer")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts) -> None:
        with open(opts["fitxer"], encoding="utf-8") as f:
            files = json.load(f)
        desats, sense = 0, []
        with transaction.atomic():
            for nom, missatges, mencions, reaccions, ultim in files:
                candidats = list(
                    Artista.objects.filter(
                        aprovat=True, nom_normalitzat=normalitza_nom_homonim(nom)
                    )[:2]
                )
                if len(candidats) != 1:
                    sense.append(nom)
                    continue
                desats += 1
                if opts["dry_run"]:
                    continue
                SenyalDM.objects.update_or_create(
                    artista=candidats[0],
                    defaults={
                        "missatges": missatges,
                        "mencions": mencions,
                        "reaccions": reaccions,
                        "ultim": ultim or None,
                    },
                )
        self.stdout.write(f"{desats} artistes amb senyal; {len(sense)} sense casar")
        for nom in sense:
            self.stdout.write(f"  · {nom}")
