"""Tell each verified gestor when their artist got new pending songs.

Songs arrive from Deezer every hour as `Canco(verificada=False,
activa=True)` and wait for the staff. Until 2026-10-23 the gestor
learned about them only by opening the portal, so nobody asked for a
review and nobody noticed when Deezer had merged their profile with a
homonym (SAMU: 101 foreign albums in a day). One mail per gestor and
artist with the songs created since the last mail; the stamp
`UserArtista.avis_novetats_at` moves only when the mail is sent, so a
re-run never repeats and a failed send retries tomorrow.

Daily cron at 07:30 (`--send`); without the flag it only reports.

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from comptes.models import UserArtista
from music.models import Canco


def cancons_noves(user_artista) -> list[Canco]:
    """Pending songs of the gestor's artist created after the stamp
    (all of them when there is no stamp yet)."""
    qs = Canco.objects.filter(
        artista=user_artista.artista, verificada=False, activa=True
    )
    if user_artista.avis_novetats_at:
        qs = qs.filter(created_at__gt=user_artista.avis_novetats_at)
    return list(qs.select_related("album").order_by("-data_llancament", "nom"))


class Command(BaseCommand):
    help = "Avisa els gestors verificats de les cançons noves pendents del seu artista."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send",
            action="store_true",
            help="Envia de debò. Sense aquest flag, només informa (dry-run).",
        )

    def handle(self, *args, **opts):
        from comptes.notifications import notify_gestor_novetats

        send = bool(opts["send"])
        qs = (
            UserArtista.objects.filter(
                verificat=True,
                estat=UserArtista.ESTAT_APROVAT,
                usuari__is_active=True,
            )
            .exclude(usuari__email="")
            .select_related("usuari", "artista")
            .order_by("pk")
        )
        if not send:
            self.stdout.write(self.style.NOTICE("Sense --send: no s'envia res."))
        enviats = 0
        for ua in qs:
            noves = cancons_noves(ua)
            if not noves:
                continue
            self.stdout.write(
                f"  · {ua.usuari.email} ← {ua.artista.nom}: {len(noves)} noves "
                f"({', '.join(c.nom for c in noves[:5])}{'…' if len(noves) > 5 else ''})"
            )
            if not send:
                continue
            with transaction.atomic():
                notify_gestor_novetats(ua, noves)
                ua.avis_novetats_at = timezone.now()
                ua.save(update_fields=["avis_novetats_at"])
            enviats += 1
        self.stdout.write(self.style.SUCCESS(f"Correus enviats: {enviats}"))
