"""Central transactional-email layer for moderation lifecycle events.

Until 2026-05-17 every user-facing email at TopQuaranta was dispatched
inline from the view that triggered it. That worked for the
registration / password / RGPD flows (one-off, simple), but left an
inventory gap: staff-moderated events (sol·licituds de gestió,
propostes d'artista, feedback) had no notification path — neither to
the staff who should review them nor to the user once they're
resolved. Fase 1.5.A introduces this module as the single point where
those six emails are constructed.

Design:
- Six public functions, paired by lifecycle: `notify_admins_new_*`
  (fires when a user submits) and `notify_user_*_resolta` (fires when
  staff approves / rejects).
- Every function is best-effort: it logs and swallows exceptions so a
  mail-server hiccup never blocks the business action that triggered
  it. The audit row still records what happened.
- Templates are placeholders for now. Fase 1.5.C will replace them
  with the full walkthrough + FAQ content.
- Staff recipients = `Usuari.objects.filter(is_staff=True)` excluding
  users without an email or with `is_active=False`. Same query used
  for every admin-side notification — kept local so future changes
  (e.g. honour a `notify_*_moderation` opt-out on PerfilUsuari) only
  touch this module.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _site_url() -> str:
    """Absolute base URL for links inside email bodies."""
    return getattr(settings, "SITE_URL", "https://www.topquaranta.cat")


def _staff_emails() -> list[str]:
    """Active staff users with a non-empty email. Centralised so the
    rule is one-line to tune (e.g. add an opt-out flag later)."""
    User = get_user_model()
    return list(
        User.objects.filter(is_staff=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )


def _send(
    subject: str,
    template: str,
    context: dict,
    *,
    to: Iterable[str],
) -> None:
    """Render the placeholder template + send. Logs + swallows on
    failure — never propagates so the business action stays
    successful even if Brevo/Resend is briefly down."""
    recipients = [addr for addr in to if addr]
    if not recipients:
        return
    try:
        html_body = render_to_string(template, {**context, "subject": subject})
        text_body = (
            f"{subject}\n\n"
            f"Consulta {_site_url()} per als detalls. "
            f"(Aquest correu té versió HTML; el teu client no la mostra.)"
        )
        msg = EmailMultiAlternatives(subject, text_body, None, recipients)
        msg.attach_alternative(html_body, "text/html")
        msg.send()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Notification send failed: template=%s recipients=%s",
            template,
            recipients,
        )


# ── Admin notifications (new user-submitted item) ───────────────────


def notify_admins_nova_solicitud_gestio(user_artista) -> None:
    """A user has just opened a gestió request. Pings staff."""
    _send(
        subject=f"TopQuaranta · nova sol·licitud de gestió: {user_artista.artista.nom}",
        template="comptes/email_admin_nova_solicitud.html",
        context={
            "artista_nom": user_artista.artista.nom,
            "usuari_email": user_artista.usuari.email,
            "missatge": user_artista.sollicitud_text,
            "staff_url": f"{_site_url()}/staff/solicituds",
        },
        to=_staff_emails(),
    )


def notify_admins_nova_proposta(proposta) -> None:
    """A user has proposed a new artist. Pings staff."""
    _send(
        subject=f"TopQuaranta · nova proposta d'artista: {proposta.nom}",
        template="comptes/email_admin_nova_proposta.html",
        context={
            "artista_nom": proposta.nom,
            "usuari_email": proposta.usuari.email,
            "justificacio": proposta.justificacio,
            "staff_url": f"{_site_url()}/staff/propostes",
        },
        to=_staff_emails(),
    )


def notify_admins_nou_feedback(feedback) -> None:
    """A user filed a Feedback (correction request). Pings staff."""
    _send(
        subject=f"TopQuaranta · nou feedback: {feedback.target_label or feedback.target_type}",
        template="comptes/email_admin_nou_feedback.html",
        context={
            "target_label": feedback.target_label or feedback.target_type,
            "target_type": feedback.target_type,
            "usuari_email": feedback.usuari.email,
            "missatge": feedback.missatge,
            "url": feedback.url,
            "staff_url": f"{_site_url()}/staff/feedback",
        },
        to=_staff_emails(),
    )


# ── User notifications (staff resolved their submission) ────────────


def notify_user_solicitud_resolta(user_artista, accio: str) -> None:
    """Staff resolved a gestió request. `accio` is 'aprovada' or
    'rebutjada'. Placeholder template; Fase 1.5.C will replace it
    with the walkthrough + FAQ."""
    if accio not in ("aprovada", "rebutjada"):
        raise ValueError(f"accio must be 'aprovada' or 'rebutjada', got {accio!r}")
    suffix = "verificada" if accio == "aprovada" else "no acceptada"
    _send(
        subject=f"TopQuaranta · sol·licitud de gestió {suffix}: {user_artista.artista.nom}",
        template="comptes/email_user_solicitud_resolta.html",
        context={
            "accio": accio,
            "artista_nom": user_artista.artista.nom,
            "motiu_rebuig": user_artista.motiu_rebuig,
            "compte_url": f"{_site_url()}/compte",
        },
        to=[user_artista.usuari.email],
    )


def notify_user_proposta_resolta(proposta, accio: str) -> None:
    """Staff resolved a new-artist proposal."""
    if accio not in ("aprovada", "rebutjada"):
        raise ValueError(f"accio must be 'aprovada' or 'rebutjada', got {accio!r}")
    suffix = "acceptada" if accio == "aprovada" else "no acceptada"
    _send(
        subject=f"TopQuaranta · proposta d'artista {suffix}: {proposta.nom}",
        template="comptes/email_user_proposta_resolta.html",
        context={
            "accio": accio,
            "artista_nom": proposta.nom,
            "compte_url": f"{_site_url()}/compte",
        },
        to=[proposta.usuari.email],
    )


def notify_user_feedback_resolt(feedback) -> None:
    """Staff resolved a Feedback. Sends a thank-you with optional
    notes for the reporter."""
    _send(
        subject=f"TopQuaranta · feedback resolt: {feedback.target_label or feedback.target_type}",
        template="comptes/email_user_feedback_resolt.html",
        context={
            "target_label": feedback.target_label or feedback.target_type,
            "notes_staff": feedback.notes_staff,
            "site_url": _site_url(),
        },
        to=[feedback.usuari.email],
    )
