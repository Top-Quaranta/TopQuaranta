"""Auth endpoints for the React SPA.

Uses Django's session middleware (the same chain that powers the current
templates) so nothing new on the backend is required to support login
— we just need a JSON surface over the existing behaviour. `django-axes`
stays active on `login()`; 2FA via `django-otp` remains enforced at the
decorator level on sensitive endpoints (not here — this is public-ish).

Endpoints
---------
GET  /api/v1/auth/me/      — current user, or {is_authenticated: False}
POST /api/v1/auth/login/   — {email, password} → session cookie + user
POST /api/v1/auth/logout/  — clears the session
"""

import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _profile(request_or_user) -> dict:
    """Shape matching what the React `AuthContext` expects.

    Accepts either a DRF request (preferred — we can read the session
    OTP flag off its user) or a bare user. For staff users we also
    expose `is_verified` (did the session pass the 2FA challenge) and
    `has_totp` (is a confirmed TOTP device registered). React's
    `AdminRoute` relies on those to bounce staff who authenticated
    via the API into the Django 2FA flow.
    """
    user = getattr(request_or_user, "user", request_or_user)
    if not user or not user.is_authenticated:
        return {"is_authenticated": False}

    is_verified = False
    has_totp = False
    if user.is_staff:
        is_verified_fn = getattr(user, "is_verified", None)
        if callable(is_verified_fn):
            is_verified = bool(is_verified_fn())
        # Lazy import so non-staff requests skip the query cost.
        from django_otp.plugins.otp_totp.models import TOTPDevice

        has_totp = TOTPDevice.objects.filter(user=user, confirmed=True).exists()

    # onboarding_complet surfaces so the SPA knows whether to auto-route
    # newly registered users to the guided profile form. Defaults to
    # True for users that pre-date the PerfilUsuari signal — the
    # backfill sets the flag on existing rows so they aren't pestered.
    perfil = getattr(user, "perfil", None)
    onboarding_complet = bool(perfil.onboarding_complet) if perfil else True

    # Verified-manager set: list of Artista PKs this user is allowed to
    # self-edit via /api/v1/compte/artista/<pk>/editar/. Surfaced on
    # /me/ so any public page (e.g. ArtistaPage) can pivot UI on it
    # without a second round-trip. Cheap query — small per-user N.
    from comptes.models import UserArtista

    verified_artist_pks = list(
        UserArtista.objects.filter(usuari=user, verificat=True).values_list(
            "artista_id", flat=True
        )
    )

    return {
        "id": user.pk,
        "email": user.email,
        "username": user.username,
        "is_staff": bool(user.is_staff),
        "is_superuser": bool(user.is_superuser),
        "is_authenticated": True,
        "is_verified": is_verified,
        "has_totp": has_totp,
        "onboarding_complet": onboarding_complet,
        "verified_artist_pks": verified_artist_pks,
    }


@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
def me(request: Request) -> Response:
    """Return the current user profile (or an anonymous shape).

    Setting `ensure_csrf_cookie` here means any SPA doing a GET to /me/
    on page load picks up the `csrftoken` cookie it needs for later
    POST requests. The React `lib/api.js` client reads that cookie and
    forwards it as `X-CSRFToken` automatically.
    """
    return Response(_profile(request))


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request: Request) -> Response:
    """Authenticate via email + password and open a session.

    `django-axes` rate-limits failed attempts automatically via its
    authentication backend; no extra logic here.
    """
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password") or ""
    if not email or not password:
        return Response({"error": "Missing credentials"}, status=400)

    # Usuari inherits AbstractUser (USERNAME_FIELD="username"), but we
    # expose a single email field in the UI. Look the user up by email
    # first, then authenticate by their actual username so ModelBackend
    # + django-axes both work untouched.
    from comptes.models import Usuari

    lookup = Usuari.objects.filter(email__iexact=email).first()
    if lookup is None:
        return Response({"error": "Credencials invàlides"}, status=401)

    user = authenticate(request, username=lookup.username, password=password)
    if user is None:
        return Response({"error": "Credencials invàlides"}, status=401)

    login(request, user)
    return Response(_profile(request))


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request: Request) -> Response:
    """Clear the session cookie."""
    logout(request)
    return Response({"ok": True})


def _send_verification_email(request, user) -> None:
    """Send an email with an activation link.

    Mirrors comptes.views._send_verification_email so the activation
    URL (handled by Django at /compte/activar/<uid>/<token>/) keeps
    working for both the Django form and this API.
    """
    # Late import to avoid a circular apps-not-loaded issue at startup.
    from comptes.tokens import email_verification_token

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    link = request.build_absolute_uri(f"/compte/activar/{uid}/{token}/")
    subject = "Activa el teu compte TopQuaranta"
    body = (
        "Hola,\n\n"
        "Activa el teu compte fent clic a l'enllaç:\n"
        f"{link}\n\n"
        "Si no has estat tu, pots ignorar aquest correu.\n\n"
        "TopQuaranta"
    )
    try:
        send_mail(subject, body, None, [user.email])
    except Exception:
        logger.exception("Failed to send verification email to %s", user.email)


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request: Request) -> Response:
    """Create an inactive user and send an activation email.

    Body: {email, password1, password2, accepta_termes (bool),
           edat_min (bool), vol_newsletter (bool, optional)}.

    Sprint J: requires explicit acceptance of terms+privacy AND
    confirmation of minimum age (14). Newsletter is opt-in and
    recorded separately so we can prove RGPD-compliant consent
    granularity if ever asked.

    Anti-enumeration (S5): whether the address is new or already
    registered we return the same 201 "check your email" payload.
    """
    from django.utils import timezone

    from comptes.models import Usuari
    from web.legal_versions import TERMES_VERSIO

    data = request.data or {}
    email = (data.get("email") or "").strip().lower()
    p1 = data.get("password1") or ""
    p2 = data.get("password2") or ""
    accepta_termes = bool(data.get("accepta_termes"))
    edat_min = bool(data.get("edat_min"))
    vol_newsletter = bool(data.get("vol_newsletter"))

    errors: dict[str, str] = {}
    if not email:
        errors["email"] = "Introdueix un correu."
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors["email"] = "Correu no vàlid."

    if not p1 or not p2:
        errors["password2"] = "Has d'omplir les dues contrasenyes."
    elif p1 != p2:
        errors["password2"] = "Les contrasenyes no coincideixen."
    else:
        try:
            validate_password(p1)
        except ValidationError as exc:
            errors["password1"] = "; ".join(exc.messages)

    if not accepta_termes:
        errors["accepta_termes"] = (
            "Has d'acceptar els termes i la política de privacitat."
        )
    if not edat_min:
        errors["edat_min"] = "Has de confirmar que tens 14 anys o més."

    if errors:
        return Response({"errors": errors}, status=400)

    if not Usuari.objects.filter(email__iexact=email).exists():
        user = Usuari.objects.create(
            email=email,
            username=email,
            is_active=False,
        )
        user.set_password(p1)
        user.save()
        # PerfilUsuari is created by the post_save signal; populate
        # the consent fields immediately after.
        perfil = getattr(user, "perfil", None)
        if perfil is not None:
            now = timezone.now()
            perfil.consent_termes_at = now
            perfil.consent_termes_versio = TERMES_VERSIO
            if vol_newsletter:
                perfil.vol_newsletter = True
                perfil.consent_newsletter_at = now
            perfil.save(
                update_fields=[
                    "consent_termes_at",
                    "consent_termes_versio",
                    "vol_newsletter",
                    "consent_newsletter_at",
                ]
            )
        _send_verification_email(request, user)
    else:
        logger.info("Registration for existing email ignored: %s", email)

    return Response(
        {
            "ok": True,
            "message": (
                "T'hem enviat un correu amb l'enllaç d'activació. "
                "Revisa la safata d'entrada (i la de spam) per a acabar."
            ),
        },
        status=201,
    )
