"""Rename HistorialRevisio.motiu values from cause-based to action-based.

The previous codes described the cause of the rejection
(`no_catala`, `album_incorrecte`, `artista_incorrecte`,
`no_musica`) and kept getting misread (notably
`album_incorrecte`, which was assumed to mean "the album is wrong"
when the real meaning is "the album is from a homonym artist that
Deezer collapsed under the right Deezer profile"). The new codes
describe the concrete action each value triggers; see
`music.constants.MOTIUS_REBUIG` for the contract.

Rewrite is 1-to-1 except for `no_catala` + `no_musica` which both
collapse to `desvincular_canco` (they share the action: per-cançó
`rebutjar_canco` that flips verificada=False, activa=False). The
language/category provenance is preserved at canço level via
`Canco.whisper_*` features, so no information is lost for the
RF classifier.

Row counts at migration time (2026-05-25, all-time HR.motiu):
  album_incorrecte    9 164  ->  desvincular_album
  artista_incorrecte  1 567  ->  desvincular_artista
  no_catala           1 275  ->  desvincular_canco
  no_musica               4  ->  desvincular_canco
  ok                  2 991  unchanged (approvals)
  auto_ml             (TBD)  unchanged (ML auto-approvals)
"""

from django.db import migrations

RENAMES = {
    "artista_incorrecte": "desvincular_artista",
    "album_incorrecte": "desvincular_album",
    "no_catala": "desvincular_canco",
    "no_musica": "desvincular_canco",
}


def forwards(apps, schema_editor):
    HistorialRevisio = apps.get_model("music", "HistorialRevisio")
    for old, new in RENAMES.items():
        HistorialRevisio.objects.filter(motiu=old).update(motiu=new)


def backwards(apps, schema_editor):
    """Reverse migration. Approximate: `desvincular_canco` rows can
    have originated from either `no_catala` or `no_musica`; since
    no_musica was a vanishing 4-row tail (0.03% of HR), we collapse
    all of them back to `no_catala`. The 4 historical `no_musica`
    rows are not recoverable but the practical effect is null."""
    HistorialRevisio = apps.get_model("music", "HistorialRevisio")
    inverse = {
        "desvincular_artista": "artista_incorrecte",
        "desvincular_album": "album_incorrecte",
        "desvincular_canco": "no_catala",
    }
    for old, new in inverse.items():
        HistorialRevisio.objects.filter(motiu=old).update(motiu=new)


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0082_spotify_playlist_seed_weekly"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="historialrevisio",
            name="motiu",
            field=__import__("django").db.models.CharField(
                choices=[
                    ("ok", "Aprovada"),
                    ("auto_ml", "Aprovada per ML"),
                    ("desvincular_canco", "Descartar la cançó"),
                    ("desvincular_album", "Desvincular l'àlbum (homònim)"),
                    ("desvincular_artista", "Desvincular el perfil Deezer"),
                ],
                max_length=50,
            ),
        ),
    ]
