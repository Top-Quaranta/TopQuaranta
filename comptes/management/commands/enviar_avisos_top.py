"""Email verified managers when their artist NEWLY enters the weekly top.

Fase 2 D1. SEPARATE from scoring: this command only READS the already
computed `TopSetmanal` (PPCC / Global) and never touches ranking. A
"new entry" is a cançó in this week's top whose `canco_id` was NOT in
last week's top (same derivation as the public top arrows, reusing
`web.api.top_views._prev_week_positions`).

Safety:
  * DRY-RUN BY DEFAULT. Nothing is sent and no ledger row is written
    unless `--send` is passed.
  * Idempotent: one `AvisTopEnviat(artista, setmana)` row gates each
    artist+week, so re-runs never double-email.
  * Only verified+approved managers (`UserArtista` verificat + aprovat)
    with an email and `PerfilUsuari.vol_avis_top=True` receive it.

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

import datetime
import logging

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from comptes.models import AvisTopEnviat, UserArtista
from ranking.models import TopSetmanal
from web.api.top_views import _prev_week_positions

logger = logging.getLogger(__name__)

TERRITORI = "PPCC"  # the Global top is the canonical "entered the top" signal
FROM_EMAIL = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@topquaranta.cat")


def _unsub_url(user) -> str:
    token = signing.dumps({"u": user.pk}, salt="avis-top-baixa")
    return f"{settings.SITE_URL}/api/v1/compte/baixa-avis-top/?token={token}"


class Command(BaseCommand):
    help = (
        "Avisa per email els gestors verificats quan el seu artista entra "
        "nou al top setmanal (Global). DRY-RUN per defecte; --send per enviar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--setmana",
            type=str,
            default="",
            help="ISO Monday (YYYY-MM-DD) de la setmana del top. Per defecte, "
            "l'última setmana amb TopSetmanal de PPCC.",
        )
        parser.add_argument(
            "--send",
            action="store_true",
            help="Envia de debò. Sense aquest flag, només informa (dry-run).",
        )

    def _resolve_setmana(self, raw: str) -> datetime.date:
        if raw:
            try:
                d = datetime.date.fromisoformat(raw)
            except ValueError as e:
                raise CommandError(f"Data invàlida: {raw} ({e})")
            if d.weekday() != 0:
                raise CommandError(f"{d} no és dilluns (weekday={d.weekday()}).")
            return d
        latest = (
            TopSetmanal.objects.filter(territori=TERRITORI)
            .order_by("-setmana")
            .values_list("setmana", flat=True)
            .first()
        )
        if latest is None:
            raise CommandError("No hi ha cap TopSetmanal de PPCC.")
        return latest

    def handle(self, *args, **opts):
        send = bool(opts["send"])
        setmana = self._resolve_setmana(opts["setmana"])
        prev = _prev_week_positions(TERRITORI, setmana)

        # New entries this week = cançons in the top whose canco_id was
        # absent last week. Map to their principal artista.
        entries = (
            TopSetmanal.objects.filter(territori=TERRITORI, setmana=setmana)
            .select_related("canco__artista")
            .order_by("posicio")
        )
        new_artistes: dict[int, object] = {}
        for e in entries:
            if e.canco_id in prev:
                continue
            a = e.canco.artista if e.canco_id else None
            if a is not None:
                new_artistes.setdefault(a.id, a)

        self.stdout.write(
            f"Setmana {setmana}: {len(new_artistes)} artistes amb entrada nova al top."
        )

        sent = skipped_done = skipped_no_gestor = 0
        for artista in new_artistes.values():
            if AvisTopEnviat.objects.filter(artista=artista, setmana=setmana).exists():
                skipped_done += 1
                continue
            gestors = list(
                UserArtista.objects.filter(
                    artista=artista,
                    verificat=True,
                    estat="aprovat",
                    usuari__is_active=True,
                    usuari__perfil__vol_avis_top=True,
                )
                .exclude(usuari__email="")
                .select_related("usuari", "usuari__perfil")
            )
            if not gestors:
                skipped_no_gestor += 1
                continue

            if not send:
                for ua in gestors:
                    self.stdout.write(
                        f"  DRY-RUN: avisaria {ua.usuari.email} de «{artista.nom}»."
                    )
                sent += len(gestors)
                continue

            with transaction.atomic():
                # Create the ledger row first; the unique constraint makes
                # a concurrent re-run fail closed rather than double-send.
                AvisTopEnviat.objects.create(artista=artista, setmana=setmana)
                for ua in gestors:
                    self._send_one(ua.usuari, artista)
                    sent += 1

        verb = "enviats" if send else "(dry-run) s'enviarien"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb}: {sent} avisos | ja-avisats: {skipped_done} | "
                f"sense gestor verificat: {skipped_no_gestor}"
            )
        )
        if not send:
            self.stdout.write(
                self.style.NOTICE("DRY-RUN: cap email enviat. Usa --send.")
            )

    def _send_one(self, user, artista) -> None:
        url = f"{settings.SITE_URL}/artista/{artista.slug}"
        unsub = _unsub_url(user)
        subject = f"«{artista.nom}» ha entrat al Top de TopQuaranta"
        text = (
            f"Hola,\n\n{artista.nom} ha entrat aquesta setmana al Top de música "
            f"en català de TopQuaranta.\n\nMira'l aquí: {url}\n\n"
            f"Per deixar de rebre aquests avisos: {unsub}\n"
        )
        html = (
            f"<p>Hola,</p><p><strong>{artista.nom}</strong> ha entrat aquesta "
            f'setmana al <a href="{url}">Top de música en català de '
            f"TopQuaranta</a>.</p>"
            f'<p style="font-size:12px;color:#666">'
            f'<a href="{unsub}">Deixar de rebre aquests avisos</a></p>'
        )
        msg = EmailMultiAlternatives(
            subject=subject, body=text, from_email=FROM_EMAIL, to=[user.email]
        )
        msg.attach_alternative(html, "text/html")
        msg.extra_headers["List-Unsubscribe"] = f"<{unsub}>"
        msg.extra_headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        try:
            msg.send(fail_silently=False)
        except Exception:
            logger.exception("avis_top send failed for user %s", user.pk)
