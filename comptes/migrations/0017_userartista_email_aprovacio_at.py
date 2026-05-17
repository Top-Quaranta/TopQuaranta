"""Add `email_aprovacio_at` to UserArtista.

Stamp the moment the "you have been verified" email is dispatched so
the retroactive notifier (`notificar_gestors_retroactiu`) can skip
users already covered by the new normal flow.

Bumped to 0017 at merge time because the parallel PR landed first
as 0016_admin_pseudouser.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comptes", "0016_admin_pseudouser"),
    ]

    operations = [
        migrations.AddField(
            model_name="userartista",
            name="email_aprovacio_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
