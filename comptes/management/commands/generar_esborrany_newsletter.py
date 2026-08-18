"""Generate the weekly newsletter review draft (opt-out flow).

Runs on Saturday, AFTER `calcular_top` has consolidated the official
weekly top. Builds the editorial text from the narrative engine
(side-effect-free), persists it as a `NewsletterDraft`, and emails staff
a link to review/edit it. `enviar_newsletter` sends it on Sunday unless
cancelled — review is opt-out (no approval step).

Idempotent: if a draft for the week already exists it is left untouched
(a re-run never overwrites staff edits).

# Spec: docs/architecture/comptes-newsletter.md
"""

from __future__ import annotations

import datetime
import logging

from django.conf import settings
from django.core.mail import mail_admins
from django.core.management.base import BaseCommand

from comptes.models import NewsletterDraft
from comptes.newsletter import build_draft_text
from ranking.models import TopSetmanal

logger = logging.getLogger(__name__)

# The public subscriber newsletter is the Global (PPCC) weekly top.
TIPUS = "top_ppcc"
TERRITORI = "PPCC"


class Command(BaseCommand):
    help = "Genera l'esborrany de revisió de la newsletter setmanal (flux opt-out)."

    def add_arguments(self, parser):
        from music.management_helpers import add_dry_run

        add_dry_run(parser)

    def handle(self, *args, **opts):
        dry_run = bool(opts.get("dry_run"))

        # The week we generate for is THIS week's Monday, computed exactly
        # like `calcular_top` (`date.today() - weekday`). Anti-stale guard
        # (2026-06-07): we require the TopSetmanal for THAT week to already
        # exist — NOT just any latest row. `calcular_top` runs Saturday and
        # can finish late (~10:30 observed), so if it hasn't consolidated
        # this week yet we exit cleanly rather than build the draft from
        # last week's stale top. The cron is scheduled with ample margin
        # (Saturday 12:00); this guard is the belt for a late ranking.
        today = datetime.date.today()
        setmana = today - datetime.timedelta(days=today.weekday())
        if not TopSetmanal.objects.filter(
            territori=TERRITORI, setmana=setmana
        ).exists():
            self.stdout.write(
                f"TopSetmanal {TERRITORI} de la setmana {setmana} encara no "
                "consolidat (calcular_top no ha acabat?). No genero per no "
                "construir des d'un top vell."
            )
            self.stdout.write("WORK_DONE=0")
            return

        existing = NewsletterDraft.objects.filter(
            tipus=TIPUS, territori=TERRITORI, setmana=setmana
        ).first()
        if existing is not None:
            self.stdout.write(
                f"Ja existeix esborrany per a {setmana} (estat={existing.estat}). "
                "Idempotent: no el sobreescric."
            )
            self.stdout.write("WORK_DONE=0")
            return

        # Side-effect-free engine compose. publish_date = Saturday of the
        # week (setmana is the ISO Monday) for the week-number + novetats
        # window, mirroring the live send.
        from social import payload

        publish_date = setmana + datetime.timedelta(days=5)
        data = payload.build_top(TERRITORI, setmana)
        entries = (data or {}).get("entries") or []
        subject, narrative_html = build_draft_text(
            TIPUS, TERRITORI, setmana, publish_date, entries
        )

        if dry_run:
            self.stdout.write(
                f"DRY-RUN: crearia esborrany {setmana}\n  subject: {subject}"
            )
            self.stdout.write("WORK_DONE=0")
            return

        draft = NewsletterDraft.objects.create(
            tipus=TIPUS,
            territori=TERRITORI,
            setmana=setmana,
            subject=subject,
            narrative_html=narrative_html,
            font=NewsletterDraft.FONT_MOTOR,
        )
        self._email_staff(draft)
        self._email_desti_prova(draft)
        self.stdout.write(
            self.style.SUCCESS(f"Esborrany creat (pk={draft.pk}, setmana={setmana}).")
        )
        self.stdout.write("WORK_DONE=1")

    def _email_staff(self, draft: NewsletterDraft) -> None:
        """Best-effort staff notification with the edit link."""
        site = settings.SITE_URL.rstrip("/")
        link = f"{site}/staff/social/esborrany?setmana={draft.setmana.isoformat()}"
        body = (
            "S'ha generat l'esborrany de la newsletter setmanal.\n\n"
            f"Setmana: {draft.setmana}\n"
            f"Assumpte: {draft.subject}\n\n"
            "S'enviarà DIUMENGE tret que el cancel·lis o el modifiquis.\n\n"
            f"Revisa'l i edita'l aquí:\n{link}\n"
        )
        try:
            mail_admins(
                f"[TopQuaranta] Esborrany newsletter setmana {draft.setmana}",
                body,
                fail_silently=False,
            )
        except Exception:  # noqa: BLE001
            logger.exception("generar_esborrany_newsletter: mail_admins failed")

    def _email_desti_prova(self, draft: NewsletterDraft) -> None:
        """Send the FULL rendered preview to the optional render-testing
        address (`ConfiguracioGlobal.newsletter_desti_prova`) ONLY. Empty
        field (the default) → no extra send, byte-identical behaviour.
        Never reaches subscribers: this is the draft-preview path."""
        from comptes.newsletter import (
            notify_admins_draft_preview,
            preview_extra_recipient,
        )

        extra = preview_extra_recipient()
        if not extra:
            return
        notify_admins_draft_preview(draft, recipients=[extra])
