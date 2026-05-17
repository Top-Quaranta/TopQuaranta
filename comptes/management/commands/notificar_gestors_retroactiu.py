"""One-shot retroactive notifier for verified gestors.

After the Fase 1.5.A notification layer landed (PR #24), only NEW
sol·licitud approvals trigger an email. Users approved before that
date never got a notification — most notably Jordi Sarrà Moyano
(verified 2026-05-15, never logged in since).

This command walks every `UserArtista(verificat=True, estat='aprovat')`
that lacks an `email_aprovacio_at` stamp and sends the
"verified, here's what you can do" email. The stamp is set on success
so the command is idempotent: re-runs only hit rows that genuinely
haven't been emailed.

Usage:
    ./manage.py notificar_gestors_retroactiu --dry-run
    ./manage.py notificar_gestors_retroactiu
    ./manage.py notificar_gestors_retroactiu --exclude-user-id 42

`--exclude-user-id` accepts the Usuari PK. Useful for skipping a
manager who has already been contacted out-of-band (e.g. via a
manual DM during testing). Repeat the flag to exclude several PKs.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from comptes.models import UserArtista


class Command(BaseCommand):
    help = (
        "Send the 'verified gestor' walkthrough to UserArtista rows "
        "approved before the notification layer existed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be sent without emailing.",
        )
        parser.add_argument(
            "--exclude-user-id",
            type=int,
            action="append",
            default=[],
            help="Usuari PK to skip. Repeat the flag for several PKs.",
        )

    def handle(self, *args, **opts):
        from comptes.notifications import notify_user_solicitud_resolta

        dry_run = opts["dry_run"]
        exclude_pks = set(opts["exclude_user_id"] or [])

        qs = (
            UserArtista.objects.filter(
                verificat=True,
                estat=UserArtista.ESTAT_APROVAT,
                email_aprovacio_at__isnull=True,
            )
            .select_related("usuari", "artista")
            .order_by("pk")
        )

        total = qs.count()
        self.stdout.write(f"Candidats a notificar: {total}")
        if exclude_pks:
            self.stdout.write(f"Excloent Usuari PKs: {sorted(exclude_pks)}")
        if dry_run:
            self.stdout.write(self.style.NOTICE("--dry-run: no s'envia res."))

        sent = 0
        skipped = 0
        for ua in qs:
            if ua.usuari_id in exclude_pks:
                self.stdout.write(
                    f"  · skip pk={ua.pk} usuari={ua.usuari.email} (excluded)"
                )
                skipped += 1
                continue
            if not ua.usuari.email:
                self.stdout.write(
                    f"  · skip pk={ua.pk} usuari={ua.usuari_id} (no email on file)"
                )
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(
                    f"  · would send to {ua.usuari.email} for artista "
                    f"«{ua.artista.nom}» (UA pk={ua.pk})"
                )
                continue
            # `notify_user_solicitud_resolta` stamps email_aprovacio_at on
            # success (when accio='aprovada'), so re-runs auto-skip
            # this row via the QS filter above.
            notify_user_solicitud_resolta(ua, "aprovada")
            self.stdout.write(
                self.style.SUCCESS(
                    f"  · sent to {ua.usuari.email} for «{ua.artista.nom}»"
                )
            )
            sent += 1

        if dry_run:
            self.stdout.write(
                f"DRY-RUN: {total - skipped} rows would have been notified."
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Done. sent={sent} skipped={skipped}")
            )
