"""Add aprovat_at / aprovat_per / motiu_rebuig to UserArtista.

Fase 1.5.A — make the model self-describing instead of relying on
StaffAuditLog rows to know when/who approved a management request.

The schema migration is automatic. The data backfill walks every
existing approved UserArtista row and tries to populate the new
fields from a matching StaffAuditLog entry. If no audit row exists
(the approval predates the audit log or was applied manually), the
fields stay NULL — that's acceptable; consumers must handle absent
values anyway.
"""

from django.db import migrations, models
from django.db.models.deletion import SET_NULL


def _backfill_audit_fields(apps, schema_editor):
    UserArtista = apps.get_model("comptes", "UserArtista")
    StaffAuditLog = apps.get_model("music", "StaffAuditLog")

    approved = UserArtista.objects.filter(verificat=True, estat="aprovat")
    for ua in approved:
        # StaffAuditLog stores target as (target_type, target_id); for
        # UserArtista approvals target_type is the model_name
        # ("userartista") and target_id is the row pk.
        log = (
            StaffAuditLog.objects.filter(
                action="sollicitud_aprovar",
                target_type="userartista",
                target_id=ua.pk,
            )
            .order_by("-created_at")
            .first()
        )
        if log is None:
            continue
        ua.aprovat_at = log.created_at
        ua.aprovat_per_id = log.actor_id
        ua.save(update_fields=["aprovat_at", "aprovat_per"])


def _noop_reverse(apps, schema_editor):
    """Reverse leaves the column drop to the schema part; data is gone
    by then anyway."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("comptes", "0014_userartista_comptes_use_usuari__b271f8_idx"),
        ("music", "0071_alter_historialrevisio_artista_territori"),
    ]

    operations = [
        migrations.AddField(
            model_name="userartista",
            name="aprovat_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userartista",
            name="aprovat_per",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=SET_NULL,
                related_name="+",
                to="comptes.usuari",
            ),
        ),
        migrations.AddField(
            model_name="userartista",
            name="motiu_rebuig",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(_backfill_audit_fields, _noop_reverse),
    ]
