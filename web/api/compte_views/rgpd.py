"""Sprint J — RGPD endpoints (deletion request, data export, newsletter unsub)."""

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from ._common import (
    _AccountDeleteThrottle,
    _DataExportThrottle,
    _NewsletterUnsubThrottle,
)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([_AccountDeleteThrottle])
def compte_esborrar_sollicitar(request: Request) -> Response:
    """User requests self-deletion. Sends a signed confirmation email.

    We never delete on this call — the GET handler at
    /compte/esborrar/<uidb64>/<token>/ completes the action after the
    user clicks the email link. That keeps the audit trail clean and
    prevents a compromised session from nuking an account in one click.
    """
    import logging

    from django.contrib.auth.tokens import default_token_generator
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    logger = logging.getLogger(__name__)
    u = request.user
    if not u.email:
        return Response({"error": "El teu compte no té email."}, status=400)
    if u.is_staff:
        return Response(
            {
                "error": (
                    "Els comptes staff no es poden auto-esborrar. "
                    "Contacta amb un altre administrador."
                )
            },
            status=400,
        )

    uidb64 = urlsafe_base64_encode(force_bytes(u.pk))
    token = default_token_generator.make_token(u)
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    link = f"{scheme}://{host}/compte/esborrar/{uidb64}/{token}/"

    subject = "TopQuaranta · confirma l'eliminació del teu compte"
    ctx = {"link": link, "email": u.email, "subject": subject}
    html = render_to_string("comptes/email_esborrar_compte.html", ctx)
    text = (
        f"Hola,\n\n"
        f"Has demanat eliminar el teu compte de TopQuaranta ({u.email}).\n"
        f"Confirma obrint aquest enllaç (caduca a les 24 hores):\n\n"
        f"{link}\n\n"
        f"Si no has sigut tu, pots ignorar aquest missatge.\n"
    )
    try:
        send_mail(
            subject, text, None, [u.email], html_message=html, fail_silently=False
        )
    except Exception as e:
        logger.exception("Failed to send account-deletion email to %s", u.email)
        return Response({"error": f"No s'ha pogut enviar l'email: {e}"}, status=500)
    return Response({"ok": True, "email": u.email})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([_DataExportThrottle])
def exportar_dades(request: Request) -> Response:
    """Right to data portability (RGPD art. 20).

    Collects everything the system knows about the user across the
    domain models (perfil, gestió d'artistes, propostes, feedback,
    publicacions, comentaris, missatges) and emails it to the user
    as a JSON attachment. Inline only — never persisted to disk.
    """
    import json
    import logging

    from django.core.mail import EmailMessage
    from django.utils import timezone

    from comptes.models import (
        Comentari,
        Feedback,
        Missatge,
        PropostaArtista,
        Publicacio,
        UserArtista,
    )
    from music.models import StaffAuditLog

    # Optional dep: axes records login attempts. If the user disabled
    # axes (test settings), skip silently.
    try:
        from axes.models import AccessAttempt, AccessLog
    except ImportError:  # pragma: no cover
        AccessAttempt = AccessLog = None

    logger = logging.getLogger(__name__)
    u = request.user
    if not u.email:
        return Response({"error": "El teu compte no té email."}, status=400)

    perfil = getattr(u, "perfil", None)
    payload = {
        "exportat_at": timezone.now().isoformat(),
        "usuari": {
            "id": u.pk,
            "email": u.email,
            "username": u.username,
            "date_joined": u.date_joined.isoformat() if u.date_joined else None,
            "is_staff": bool(u.is_staff),
        },
        "perfil": (
            {
                "nom_public": perfil.nom_public,
                "bio": perfil.bio,
                "rol_musical": perfil.rol_musical,
                "instruments": perfil.instruments,
                "imatge_url": perfil.imatge_url,
                "visible_directori": perfil.visible_directori,
                "obert_colaboracions": perfil.obert_colaboracions,
                "vol_newsletter": perfil.vol_newsletter,
                "consent_termes_at": (
                    perfil.consent_termes_at.isoformat()
                    if perfil.consent_termes_at
                    else None
                ),
                "consent_termes_versio": perfil.consent_termes_versio,
                "consent_newsletter_at": (
                    perfil.consent_newsletter_at.isoformat()
                    if perfil.consent_newsletter_at
                    else None
                ),
                "social": {
                    f: getattr(perfil, f) or "" for f, _ in (perfil.SOCIAL_FIELDS or [])
                },
            }
            if perfil
            else None
        ),
        "gestio_artistes": [
            {
                "artista": ua.artista.nom,
                "artista_slug": ua.artista.slug,
                "estat": ua.estat,
                "verificat": ua.verificat,
                "sollicitud_text": ua.sollicitud_text,
                "created_at": ua.created_at.isoformat(),
            }
            for ua in UserArtista.objects.filter(usuari=u).select_related("artista")
        ],
        "propostes_artista": [
            {
                "nom": p.nom,
                "estat": p.estat,
                "justificacio": p.justificacio,
                "created_at": p.created_at.isoformat(),
            }
            for p in PropostaArtista.objects.filter(usuari=u)
        ],
        "feedback": [
            {
                "url": f.url,
                "missatge": f.missatge,
                "target_type": f.target_type,
                "target_label": f.target_label,
                "resolt": f.resolt,
                "created_at": f.created_at.isoformat(),
            }
            for f in Feedback.objects.filter(usuari=u)
        ],
        "publicacions": [
            {
                "titol": p.titol,
                "cos": p.cos,
                "visibilitat": p.visibilitat,
                "estat": p.estat,
                "created_at": p.created_at.isoformat(),
                "publicat_at": p.publicat_at.isoformat() if p.publicat_at else None,
            }
            for p in Publicacio.objects.filter(autor=u)
        ],
        "comentaris": [
            {
                "publicacio_id": c.publicacio_id,
                "cos": c.cos,
                "created_at": c.created_at.isoformat(),
            }
            for c in Comentari.objects.filter(autor=u)
        ],
        "missatges_enviats": [
            {
                "destinatari_id": m.destinatari_id,
                "assumpte": m.assumpte,
                "cos": m.cos,
                "created_at": m.created_at.isoformat(),
            }
            for m in Missatge.objects.filter(remitent=u)
        ],
        "missatges_rebuts": [
            {
                "remitent_id": m.remitent_id,
                "assumpte": m.assumpte,
                "cos": m.cos,
                "llegit_at": m.llegit_at.isoformat() if m.llegit_at else None,
                "created_at": m.created_at.isoformat(),
            }
            for m in Missatge.objects.filter(destinatari=u)
        ],
        # NB: HistorialRevisio is intentionally anonymous (no
        # `usuari` FK) — it captures *what* was decided, not who
        # decided it. The actor info lives in StaffAuditLog below
        # (which is what an RGPD subject-access request needs anyway:
        # actions affecting them, not back-office decisions about
        # third-party songs).
        # Audit trail of staff actions where this user is the target
        # (e.g. a moderator deactivating, resetting 2FA, sending
        # password reset). Useful for the user to know who did what
        # to their account.
        "audit_log_sobre_meu": [
            {
                "action": log.action,
                "actor_username": log.actor.username if log.actor else "",
                "target_label": log.target_label,
                "created_at": log.created_at.isoformat(),
            }
            for log in StaffAuditLog.objects.filter(
                target_type="usuari", target_id=u.pk
            )
            .select_related("actor")
            .order_by("-created_at")
        ],
        # Login activity (axes). IP + user-agent + timestamps from
        # successful and failed attempts. Helps a user verify their
        # account isn't being attacked.
        "login_history": (
            [
                {
                    "ip": a.ip_address,
                    "user_agent": a.user_agent,
                    "attempt_time": a.attempt_time.isoformat(),
                    "failures_since_start": a.failures_since_start,
                }
                for a in AccessAttempt.objects.filter(username=u.username).order_by(
                    "-attempt_time"
                )[:200]
            ]
            if AccessAttempt is not None
            else []
        ),
    }

    body_json = json.dumps(payload, indent=2, ensure_ascii=False)
    msg = EmailMessage(
        subject="TopQuaranta · les teves dades",
        body=(
            "Hola,\n\nAdjuntem el JSON amb totes les dades que tenim del "
            f"teu compte ({u.email}).\n\nSi vols esborrar-les, fes-ho des "
            "del teu compte.\n\nGràcies.\n"
        ),
        to=[u.email],
    )
    msg.attach("topquaranta-dades.json", body_json, "application/json")
    try:
        msg.send(fail_silently=False)
    except Exception as e:
        logger.exception("Failed to send data export to %s", u.email)
        return Response({"error": f"No s'ha pogut enviar: {e}"}, status=500)
    return Response({"ok": True, "email": u.email})


@api_view(["GET", "POST"])
@permission_classes([])
@throttle_classes([_NewsletterUnsubThrottle])
def baixa_newsletter(request: Request) -> Response:
    """Token-based newsletter unsubscribe (RGPD art. 7.3 — withdrawal
    must be as easy as giving consent). Intended to be linked from
    every newsletter email; works without login.

    **Accepts both GET and POST** so RFC 8058 one-click unsubscribe
    works (Gmail/Yahoo POST to the URL announced via the
    `List-Unsubscribe-Post: List-Unsubscribe=One-Click` header).
    The token can come from the query string (link click) or the
    POST body (`token=…` form-encoded, per RFC 8058 §3.1).

    Token is `signing.dumps({"u": user.pk}, salt="newsletter-baixa")`
    with the project SECRET_KEY. **Expires after 1 year** (May-2026
    audit fix): a leaked archived-newsletter inbox would otherwise
    grant a permanent unsubscribe primitive. New tokens are issued
    on every send so legitimate links keep working as long as the
    user receives the newsletter regularly."""
    from django.core import signing

    from comptes.models import Usuari

    # RFC 8058: token may arrive in form body on the POST one-click
    # path. GET keeps the legacy query-string contract.
    token = (
        request.GET.get("token")
        or (request.data.get("token") if hasattr(request, "data") else None)
        or ""
    ).strip()
    if not token:
        return Response({"error": "Falta el token."}, status=400)
    try:
        data = signing.loads(token, salt="newsletter-baixa", max_age=60 * 60 * 24 * 365)
        user_pk = int(data["u"])
    except signing.SignatureExpired:
        return Response(
            {
                "error": (
                    "Aquest enllaç ha caducat. Si vols donar-te de baixa "
                    "demana un enllaç nou des de qualsevol newsletter recent o "
                    "des del teu perfil a /compte/perfil."
                )
            },
            status=400,
        )
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        return Response({"error": "Token invàlid."}, status=400)
    try:
        u = Usuari.objects.get(pk=user_pk)
    except Usuari.DoesNotExist:
        return Response({"error": "Usuari inexistent."}, status=404)
    perfil = getattr(u, "perfil", None)
    if perfil is not None and perfil.vol_newsletter:
        perfil.vol_newsletter = False
        perfil.save(update_fields=["vol_newsletter"])
    return Response({"ok": True, "email": u.email})


@api_view(["GET", "POST"])
@permission_classes([])
@throttle_classes([_NewsletterUnsubThrottle])
def baixa_avis_top(request: Request) -> Response:
    """Token-based opt-out from the "has entrat al top" manager alert
    (Fase 2 D1). Same RFC 8058 one-click contract + 1-year token as the
    newsletter unsubscribe, but salt `avis-top-baixa` and it flips
    `PerfilUsuari.vol_avis_top` to False."""
    from django.core import signing

    from comptes.models import Usuari

    token = (
        request.GET.get("token")
        or (request.data.get("token") if hasattr(request, "data") else None)
        or ""
    ).strip()
    if not token:
        return Response({"error": "Falta el token."}, status=400)
    try:
        data = signing.loads(token, salt="avis-top-baixa", max_age=60 * 60 * 24 * 365)
        user_pk = int(data["u"])
    except signing.SignatureExpired:
        return Response(
            {"error": "Aquest enllaç ha caducat. Gestiona-ho des de /compte/perfil."},
            status=400,
        )
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        return Response({"error": "Token invàlid."}, status=400)
    try:
        u = Usuari.objects.get(pk=user_pk)
    except Usuari.DoesNotExist:
        return Response({"error": "Usuari inexistent."}, status=404)
    perfil = getattr(u, "perfil", None)
    if perfil is not None and perfil.vol_avis_top:
        perfil.vol_avis_top = False
        perfil.save(update_fields=["vol_avis_top"])
    return Response({"ok": True, "email": u.email})
