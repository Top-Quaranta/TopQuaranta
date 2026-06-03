"""Requeue Artistas that the previous `desvincular_artista` behaviour
left in limbo (no Deezer, no MBID, aprovat=False, pendent_review=False).

Before 2026-05-25 the post_delete signal on `ArtistaDeezer` set
`aprovat=False, pendent_review=False` when the last Deezer link was
removed without an MBID anchor. That left the artista invisible to
the pendents queue, which meant the operator had no place to come
back to it and rediscover the correct Deezer profile. The new
`rebutjar_artista` (and the single-profile path of
`_try_auto_unlink_homonym_deezer`) explicitly forces
`pendent_review=True, aprovat=False`. This migration backfills the
historical victims so they show up in pendents now.

Recovery criteria (verified on 2026-05-25):
  - 0 ArtistaDeezer rows;
  - aprovat=False;
  - pendent_review=False;
  - at least one `HistorialRevisio` row whose `motiu` is
    `desvincular_artista` or its legacy alias `artista_incorrecte`.

The fourth criterion is the disambiguator: 4 304 total limbo
artistas exist, but only 63 of them carry HR evidence of a
`desvincular_artista` decision. The remaining 4 241 (limbo without
HR rows) came from other prune paths (auto-discovered collaborators
that staff removed silently, contributor materialisations that got
cleaned up) and must stay where they are.

The 63 include 3 cases that also have non-desvincular HR rejections
(Cavallo, Twin Diplomacy, MC Cwsp). Bringing them to pendents is
still safe: pendent_review=True only means "operator may revisit";
nothing destructive. If the operator decides they should stay out,
one click removes the flag.

Reverse migration: best-effort. It moves the same artistas back to
limbo (aprovat=False, pendent_review=False) without trying to
restore any Deezer links (we never had them; they were deleted in
the original action and we cannot recover them here).
"""

from django.db import migrations
from django.db.models import Count

REJECT_MOTIUS = ("desvincular_artista", "artista_incorrecte")


def forwards(apps, schema_editor):
    Artista = apps.get_model("music", "Artista")
    HistorialRevisio = apps.get_model("music", "HistorialRevisio")

    limbo = (
        Artista.objects.filter(aprovat=False, pendent_review=False)
        .annotate(n_dz=Count("deezer_ids"))
        .filter(n_dz=0)
    )
    victim_names = set(
        HistorialRevisio.objects.filter(
            decisio="rebutjada", motiu__in=REJECT_MOTIUS
        ).values_list("artista_nom", flat=True)
    )
    n = limbo.filter(nom__in=victim_names).update(pendent_review=True)
    print(
        f"  [music.0084] requeued {n} Artistas to pendent_review "
        f"(previously in desvincular_artista limbo)"
    )


def backwards(apps, schema_editor):
    Artista = apps.get_model("music", "Artista")
    HistorialRevisio = apps.get_model("music", "HistorialRevisio")

    candidates = (
        Artista.objects.filter(aprovat=False, pendent_review=True)
        .annotate(n_dz=Count("deezer_ids"))
        .filter(n_dz=0)
    )
    victim_names = set(
        HistorialRevisio.objects.filter(
            decisio="rebutjada", motiu__in=REJECT_MOTIUS
        ).values_list("artista_nom", flat=True)
    )
    candidates.filter(nom__in=victim_names).update(pendent_review=False)


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0083_rename_motius_to_actions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        # `HistorialRevisio.MOTIUS` labels were tightened to action-
        # only on 2026-05-25 (the previous labels carried the cause,
        # which brought back the very ambiguity the rename killed).
        # Values unchanged; only the display strings move.
        migrations.AlterField(
            model_name="historialrevisio",
            name="motiu",
            field=__import__("django").db.models.CharField(
                choices=[
                    ("ok", "Aprovada"),
                    ("auto_ml", "Aprovada per ML"),
                    ("desvincular_canco", "Desvincular la cançó"),
                    ("desvincular_album", "Desvincular l'àlbum"),
                    ("desvincular_artista", "Desvincular l'artista"),
                ],
                max_length=50,
            ),
        ),
    ]
