"""Seed the `admin` pseudo-user that fronts the staff inbox for DMs.

This is NOT a real admin account (`is_staff=False`); it's a proxy
that any logged-in user can DM to reach the moderation team without
having to identify a specific staff user in the community directory.
Messages sent to this user are fanned out by email to every active
staff member (see `_enviar_notificacio_missatge`).

Idempotent: if a user with this email already exists, the migration
leaves it untouched. The associated `PerfilUsuari` is created or
upserted to the canonical state (`visible_directori=True` so it shows
in the directory, biographical text explaining what the account is).
"""

from django.db import migrations


ADMIN_EMAIL = "admin@topquaranta.cat"
ADMIN_USERNAME = "admin"
ADMIN_NOM_PUBLIC = "Admin TopQuaranta"
ADMIN_BIO = (
    "Compte oficial de TopQuaranta. Per a qualsevol pregunta, "
    "suggeriment o problema, escriu-nos per aquí. Et respondrem el staff."
)


def _seed(apps, schema_editor):
    Usuari = apps.get_model("comptes", "Usuari")
    PerfilUsuari = apps.get_model("comptes", "PerfilUsuari")

    user = Usuari.objects.filter(email=ADMIN_EMAIL).first()
    if user is None:
        user = Usuari.objects.create(
            username=ADMIN_USERNAME,
            email=ADMIN_EMAIL,
            first_name="Admin",
            last_name="TopQuaranta",
            is_active=True,
            is_staff=False,
        )
        # `set_unusable_password` exists on the real Usuari class but
        # the historical-model proxy lacks it; emulate by writing the
        # literal "!" prefix Django uses internally for unusable
        # passwords. This also blocks any login attempt.
        user.password = "!unusable"
        user.save(update_fields=["password"])

    # The PerfilUsuari may already exist via the post_save signal that
    # fires on Usuari creation. Update_or_create so the canonical
    # text is set either way.
    PerfilUsuari.objects.update_or_create(
        usuari=user,
        defaults={
            "nom_public": ADMIN_NOM_PUBLIC,
            "bio": ADMIN_BIO,
            "visible_directori": True,
            "rol_musical": "escoltador",
        },
    )


def _unseed(apps, schema_editor):
    """Reverse: delete the seeded user + perfil. Safe because no real
    user data hangs off this account."""
    Usuari = apps.get_model("comptes", "Usuari")
    Usuari.objects.filter(email=ADMIN_EMAIL, username=ADMIN_USERNAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("comptes", "0015_userartista_audit_fields"),
    ]

    operations = [
        migrations.RunPython(_seed, _unseed),
    ]
