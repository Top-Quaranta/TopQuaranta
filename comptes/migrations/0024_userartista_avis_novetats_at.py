from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comptes", "0023_perfilusuari_busca_perfilusuari_generes_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userartista",
            name="avis_novetats_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Last time this gestor was emailed about new pending "
                    "songs of the artist (avisar_gestors_novetats). Songs "
                    "created after this stamp are the next mail."
                ),
                null=True,
            ),
        ),
    ]
