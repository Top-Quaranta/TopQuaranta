from django.db import migrations, models


class Migration(migrations.Migration):
    """Retire the two gating flags: the 9007 publish retry and resumable
    story sets are now the unconditional default. Schema-only drop of two
    boolean config columns — no editorial-data implication. The retry
    tunables (`ig_retry_9007_intents`, `ig_retry_9007_backoff_s`) stay;
    the intents help_text loses its stale reference to the removed flag."""

    dependencies = [
        ("ranking", "0036_configuracioglobal_ig_publish_robustness"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="configuracioglobal",
            name="ig_retry_9007_actiu",
        ),
        migrations.RemoveField(
            model_name="configuracioglobal",
            name="ig_stories_resumibles_actiu",
        ),
        migrations.AlterField(
            model_name="configuracioglobal",
            name="ig_retry_9007_intents",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text=(
                    "Nombre de reintents de publicació després d'un 9007/2207027 "
                    "(«Media ID is not available»). 0 = cap reintent (una sola crida)."
                ),
            ),
        ),
    ]
