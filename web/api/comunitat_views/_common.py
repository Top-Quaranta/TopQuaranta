"""Shared helpers + constants for the comunitat_views package.

Helpers used by 2+ sibling modules live here. Constants used by a single
module stay in that module.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.template.loader import render_to_string

from comptes.models import (
    HTTP_ONLY_URL,
    PerfilUsuari,
    Publicacio,
)

# ─── PerfilUsuari ────────────────────────────────────────────────────────


def _serialize_perfil(p: PerfilUsuari, *, include_private: bool = False) -> dict:
    """Return a JSON-safe snapshot of a PerfilUsuari.

    `include_private` adds fields the owner (or staff) can see but which
    aren't safe to surface in the public directori — e.g. raw email or
    onboarding state.
    """
    loc = p.localitat
    row = {
        "usuari_id": p.usuari_id,
        "username": p.usuari.username,
        "nom_public": p.nom_public,
        "imatge_url": p.imatge_url or "",
        "bio": p.bio or "",
        "rol_musical": p.rol_musical,
        "instruments": p.instruments or "",
        "visible_directori": p.visible_directori,
        "obert_colaboracions": p.obert_colaboracions,
        "notificar_missatges_email": p.notificar_missatges_email,
        "notificar_comentaris_email": p.notificar_comentaris_email,
        "social": {f: getattr(p, f) or "" for f, _ in PerfilUsuari.SOCIAL_FIELDS},
        "localitat": (
            {
                "pk": loc.pk,
                "nom": loc.nom,
                "comarca": loc.comarca,
                "territori": loc.territori_id,
            }
            if loc
            else None
        ),
        "social_fields": list(PerfilUsuari.SOCIAL_FIELDS),
        "rol_choices": list(PerfilUsuari.ROL_CHOICES),
    }
    if include_private:
        row["email"] = p.usuari.email
        row["onboarding_complet"] = p.onboarding_complet
    return row


def _clean_url(raw: str) -> tuple[str, str | None]:
    raw = (raw or "").strip()
    if not raw:
        return "", None
    try:
        HTTP_ONLY_URL(raw)
    except ValidationError:
        return raw, "URL no vàlida (només http/https)."
    return raw, None


# ─── Publicacions ────────────────────────────────────────────────────────


def _serialize_publicacio(pub: Publicacio, *, for_staff: bool = False) -> dict:
    row = {
        "pk": pub.pk,
        "titol": pub.titol,
        "cos": pub.cos,
        "visibilitat": pub.visibilitat,
        "estat": pub.estat,
        "created_at": pub.created_at.isoformat() if pub.created_at else None,
        "publicat_at": pub.publicat_at.isoformat() if pub.publicat_at else None,
        "updated_at": pub.updated_at.isoformat() if pub.updated_at else None,
        "autor": {
            "username": pub.autor.username,
            "nom_public": getattr(getattr(pub.autor, "perfil", None), "nom_public", "")
            or pub.autor.username,
            "is_staff": pub.autor.is_staff,
        },
    }
    if for_staff:
        row["notes_staff"] = pub.notes_staff or ""
    return row


def _validate_publicacio_body(data: dict) -> tuple[dict, dict]:
    """Common validation for create + edit. Returns (cleaned, errors)."""
    errors: dict[str, str] = {}
    titol = (data.get("titol") or "").strip()
    if not titol:
        errors["titol"] = "Obligatori."
    elif len(titol) > 200:
        errors["titol"] = "Massa llarg (màxim 200)."
    cos = (data.get("cos") or "").strip()
    if not cos:
        errors["cos"] = "El cos no pot ser buit."
    elif len(cos) > 20000:
        errors["cos"] = "Massa llarg (màxim 20 000 caràcters)."
    visibilitat = data.get("visibilitat", Publicacio.VISIBILITAT_INTERNA)
    if visibilitat not in {k for k, _ in Publicacio.VISIBILITAT_CHOICES}:
        errors["visibilitat"] = "Valor no vàlid."
    return {"titol": titol, "cos": cos, "visibilitat": visibilitat}, errors


# ─── Missatgeria ─────────────────────────────────────────────────────────


def _serialize_missatge(m, viewer) -> dict:
    """Compact shape for inbox lists / thread views."""
    other = m.remitent if m.destinatari_id == viewer.pk else m.destinatari
    return {
        "pk": m.pk,
        "remitent": (
            {
                "pk": m.remitent.pk,
                "username": m.remitent.username,
                "nom_public": getattr(
                    getattr(m.remitent, "perfil", None), "nom_public", ""
                ),
            }
            if m.remitent_id
            else None
        ),
        "destinatari": {
            "pk": m.destinatari.pk,
            "username": m.destinatari.username,
        },
        "altre": (
            {
                "pk": other.pk,
                "username": other.username,
                "nom_public": getattr(getattr(other, "perfil", None), "nom_public", ""),
            }
            if other is not None
            else None
        ),
        "assumpte": m.assumpte,
        "cos": m.cos,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "llegit_at": m.llegit_at.isoformat() if m.llegit_at else None,
        "meu": m.remitent_id == viewer.pk,
    }


def _enviar_notificacio_missatge(request, msg) -> None:
    """Email the recipient a "you have a new message" heads-up.

    Skipped silently if the recipient opted out or doesn't have an
    email configured. Failures never block the message itself.

    Special case: when the destinatari is the `admin` pseudo-user
    (settings.ADMIN_INBOX_USERNAME), the notification is fanned out
    to every active staff member in addition to the admin mailbox.
    This lets any logged-in user reach the moderation team with a DM
    without having to identify a specific staff user in the directory.
    The pseudo-user's own `notificar_missatges_email` opt-out is
    ignored in this case — the staff alert is the whole point.
    """
    from django.conf import settings as _settings
    from django.contrib.auth import get_user_model

    logger = logging.getLogger(__name__)
    dest = msg.destinatari
    admin_username = getattr(_settings, "ADMIN_INBOX_USERNAME", "admin")
    is_admin_inbox = dest.username == admin_username

    if is_admin_inbox:
        # Fan out to admin mailbox + every active staff member.
        User = get_user_model()
        recipients = set()
        if dest.email:
            recipients.add(dest.email)
        recipients.update(
            User.objects.filter(is_staff=True, is_active=True)
            .exclude(email="")
            .values_list("email", flat=True)
        )
        recipients = sorted(recipients)
        if not recipients:
            return
    else:
        if not dest.email:
            return
        perfil = getattr(dest, "perfil", None)
        if perfil and not perfil.notificar_missatges_email:
            return
        recipients = [dest.email]

    remitent_nom = (
        (getattr(getattr(msg.remitent, "perfil", None), "nom_public", None) or "")
        if msg.remitent_id
        else ""
    ) or (msg.remitent.username if msg.remitent_id else "un usuari")
    host = request.get_host()
    scheme = "https" if request.is_secure() else "http"
    link = f"{scheme}://{host}/compte/missatges"
    ctx = {
        "remitent_nom": remitent_nom,
        "assumpte": msg.assumpte or "(sense assumpte)",
        "preview": (msg.cos or "")[:300],
        "link": link,
        "subject": f"TopQuaranta · missatge de {remitent_nom}",
    }
    html = render_to_string("comptes/email_missatge.html", ctx)
    text = (
        f"Hola,\n\n"
        f"{remitent_nom} t'ha enviat un missatge a TopQuaranta.\n\n"
        f"Assumpte: {ctx['assumpte']}\n\n"
        f"{ctx['preview']}\n\n"
        f"Llegeix-lo aquí:\n{link}\n"
    )
    try:
        send_mail(ctx["subject"], text, None, recipients, html_message=html)
    except Exception:
        logger.exception("Failed to send message notification to %s", recipients)


# ─── Comentaris ──────────────────────────────────────────────────────────


def _serialize_comentari(c) -> dict:
    autor = c.autor
    perfil = getattr(autor, "perfil", None) if autor else None
    return {
        "pk": c.pk,
        "cos": c.cos,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "autor": (
            {
                "pk": autor.pk,
                "username": autor.username,
                "nom_public": getattr(perfil, "nom_public", "") or autor.username,
                "imatge_url": getattr(perfil, "imatge_url", "") or "",
                "is_staff": autor.is_staff,
            }
            if autor is not None
            else None
        ),
    }


def _enviar_notificacio_comentari(request, comentari) -> None:
    """Tell the post author someone commented on their publication.

    Skipped if the commenter IS the author (no self-pings), if the
    author opted out or lacks an email.
    """
    logger = logging.getLogger(__name__)
    pub = comentari.publicacio
    if not pub.autor_id or pub.autor_id == comentari.autor_id:
        return
    autor_post = pub.autor
    if not autor_post.email:
        return
    perfil = getattr(autor_post, "perfil", None)
    if perfil and not perfil.notificar_comentaris_email:
        return

    commenter_nom = (
        getattr(getattr(comentari.autor, "perfil", None), "nom_public", None)
        or comentari.autor.username
    )
    host = request.get_host()
    scheme = "https" if request.is_secure() else "http"
    link = f"{scheme}://{host}/comunitat/{pub.pk}"
    ctx = {
        "commenter_nom": commenter_nom,
        "titol_post": pub.titol,
        "preview": (comentari.cos or "")[:300],
        "link": link,
        "subject": f"TopQuaranta · nou comentari a «{pub.titol}»",
    }
    html = render_to_string("comptes/email_comentari.html", ctx)
    text = (
        f"Hola,\n\n"
        f"{commenter_nom} ha comentat a la teva publicació "
        f"«{pub.titol}»:\n\n{ctx['preview']}\n\nRespon aquí:\n{link}\n"
    )
    try:
        send_mail(ctx["subject"], text, None, [autor_post.email], html_message=html)
    except Exception:
        logger.exception("Failed to send comment notification to %s", autor_post.email)
