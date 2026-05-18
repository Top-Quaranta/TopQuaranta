"""Anti-repetition ledger for the narrative engine (Fase 4 PR 1)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("social", "0005_alter_socialpost_platform_alter_socialpost_tipus"),
    ]

    operations = [
        migrations.CreateModel(
            name="NarrativePhraseUsage",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("phrase_id", models.CharField(db_index=True, max_length=80)),
                ("territori", models.CharField(max_length=4)),
                ("setmana", models.DateField()),
                ("channel", models.CharField(max_length=20)),
                ("used_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Ús de frase narrativa",
                "verbose_name_plural": "Usos de frases narratives",
                "ordering": ["-used_at"],
            },
        ),
        migrations.AddIndex(
            model_name="narrativephraseusage",
            index=models.Index(
                fields=["channel", "territori", "-setmana"],
                name="social_narr_channel_837bb1_idx",
            ),
        ),
    ]
