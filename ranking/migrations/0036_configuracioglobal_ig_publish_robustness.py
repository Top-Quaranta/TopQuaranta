from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ranking", "0035_configuracioglobal_feed_artwork_actiu_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioglobal",
            name="ig_retry_9007_actiu",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Reintenta `publish_container` quan la Graph API respon amb "
                    "codi 9007/subcode 2207027 («Media ID is not available»), una "
                    "carrera d'async-processing: re-polleja l'estat del contenidor "
                    "i reintenta. Apagat = comportament actual (una sola crida)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="configuracioglobal",
            name="ig_retry_9007_intents",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text=(
                    "Nombre de reintents de publicació després del primer 9007 "
                    "(només si `ig_retry_9007_actiu`). 0 = cap reintent."
                ),
            ),
        ),
        migrations.AddField(
            model_name="configuracioglobal",
            name="ig_retry_9007_backoff_s",
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text="Segons d'espera entre reintents 9007 (backoff curt fix).",
            ),
        ),
        migrations.AddField(
            model_name="configuracioglobal",
            name="ig_stories_resumibles_actiu",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Story sets resumibles: en un fallo parcial, la fila queda en "
                    "ERROR (no PUBLICAT) amb les slides ja publicades desades a "
                    "`metadata.published_slides`; el reintent de tq-run reentra i "
                    "publica només les que falten, marcant PUBLICAT quan el set és "
                    "complet. Apagat = comportament actual (partial → PUBLICAT)."
                ),
            ),
        ),
    ]
