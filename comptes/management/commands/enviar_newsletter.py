"""Send the weekly newsletter from its review draft (opt-out flow).

Runs on Sunday. Reads the week's `NewsletterDraft`:
  - cancelled  → do not send;
  - otherwise  → send the (possibly edited) `subject` + `narrative_html`,
    rebuilding the rest of the context (podi, entries, covers) from the
    FINAL top at send time, then mark the draft `enviat`.

Gated by `ConfiguracioGlobal.pot_publicar_tipus("newsletter", "top_ppcc")`
— the three distribution gates: master + per-channel + the
(newsletter × top_ppcc) matrix cell.
Writes a `SocialPost` row + audit (`newsletter_publicat`) so the
per-channel "last send" traceability stays consistent with the other
channels. Idempotent: an already-`enviat` week is skipped unless
`--force`.

# Spec: docs/architecture/comptes.md
"""

from __future__ import annotations

import datetime
import logging

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from comptes.models import NewsletterDraft
from comptes.newsletter import send_top_newsletter
from music.audit import log_staff_action
from ranking.models import ConfiguracioGlobal, TopSetmanal
from social.models import SocialPost

logger = logging.getLogger(__name__)

TIPUS = "top_ppcc"
TERRITORI = "PPCC"


class Command(BaseCommand):
    help = "Envia la newsletter setmanal des de l'esborrany de revisió (flux opt-out)."

    def add_arguments(self, parser):
        from music.management_helpers import add_dry_run

        add_dry_run(parser)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reenvia encara que l'esborrany ja estigui marcat enviat.",
        )

    def handle(self, *args, **opts):
        dry_run = bool(opts.get("dry_run"))
        force = bool(opts.get("force"))

        cfg = ConfiguracioGlobal.load()
        # Three gates: master (`distribucio_activa`), per-channel
        # (`newsletter_actiu`), and the distribution-matrix cell
        # (newsletter × top_ppcc). Any one off → the newsletter is NOT
        # sent.
        if not cfg.pot_publicar_tipus("newsletter", TIPUS) and not dry_run:
            if not cfg.distribucio_activa:
                self.stdout.write("Distribució pausada (mestre). Surt.")
            elif not cfg.newsletter_actiu:
                self.stdout.write("Kill switch tancat (newsletter_actiu=False). Surt.")
            else:
                self.stdout.write("Matriu desactivada (newsletter × top_ppcc). Surt.")
            return

        setmana = TopSetmanal.objects.filter(territori=TERRITORI).aggregate(
            m=Max("setmana")
        )["m"]
        if setmana is None:
            self.stdout.write("Cap TopSetmanal PPCC consolidat. Surt.")
            return

        draft = NewsletterDraft.objects.filter(
            tipus=TIPUS, territori=TERRITORI, setmana=setmana
        ).first()
        if draft is None:
            # The draft is the source of truth: no draft → nothing
            # reviewed to send (the Saturday generation step didn't run).
            self.stdout.write(
                f"Cap esborrany per a {setmana}; no envio (cal generar-lo dissabte)."
            )
            return
        if draft.estat == NewsletterDraft.ESTAT_CANCELLAT:
            self.stdout.write(f"Esborrany {setmana} cancel·lat. No envio.")
            return
        if draft.estat == NewsletterDraft.ESTAT_ENVIAT and not force:
            self.stdout.write(
                f"Esborrany {setmana} ja enviat. Surt (--force per re-enviar)."
            )
            return

        # Rebuild the list from the FINAL top at send time.
        from social import payload

        publish_date = setmana + datetime.timedelta(days=5)
        data = payload.build_top(TERRITORI, setmana)
        entries = (data or {}).get("entries") or []

        if dry_run:
            self.stdout.write(
                f"DRY-RUN: enviaria newsletter {setmana} "
                f"(editat={draft.editat})\n  subject: {draft.subject}"
            )
            return

        summary = send_top_newsletter(
            TIPUS,
            TERRITORI,
            setmana,
            publish_date,
            entries,
            subject_override=draft.subject,
            narrative_html_override=draft.narrative_html,
        )

        # Traceability: SocialPost row + audit, same shape as
        # publicar_canal so "last send per channel" stays consistent.
        post, _ = SocialPost.objects.get_or_create(
            platform=SocialPost.PLATFORM_NEWSLETTER,
            tipus=TIPUS,
            territori=TERRITORI,
            setmana=setmana,
            defaults={
                "status": SocialPost.STATUS_PENDENT,
                "scheduled_at": timezone.now(),
            },
        )
        post.status = SocialPost.STATUS_PUBLICAT
        post.published_at = timezone.now()
        post.metadata = {
            "channel": "newsletter",
            "summary": summary,
            "editat": draft.editat,
        }
        post.save()
        log_staff_action(None, "newsletter_publicat", target=post, tipus=TIPUS)
        try:
            from analytics.events import register as _register_event

            _register_event("social_publicat", dim1="newsletter", dim2=TIPUS)
        except Exception:  # noqa: BLE001
            logger.exception("enviar_newsletter: analytics register failed")

        draft.estat = NewsletterDraft.ESTAT_ENVIAT
        draft.enviat_at = timezone.now()
        draft.save(update_fields=["estat", "enviat_at", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f"Newsletter enviada: {summary}"))
