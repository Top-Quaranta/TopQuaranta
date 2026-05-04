"""Server-rendered auth flows for TopQuaranta.

After Sprint 4 (April 2026), the public dashboard, profile editor and
the two artist-CTA forms (gestió + proposta) moved to React under
`web-react/src/pages/` and hit `/api/v1/compte/*` endpoints. The
views that *stayed* here are the ones that still need classic form-
POST + HTML response cycles:

  * `registre` — signup form (creates inactive user + email activation)
  * `activar` — email-verification landing page
  * `TQLoginView` — axes/django-otp aware login wrapper
  * `TQLogoutView` — session teardown
  * `dos_fa_configurar` / `dos_fa_verificar` / `dos_fa_gestio` —
    the three 2FA screens

Every template these render extends `comptes/_base_auth.html`, the
minimal yellow/ink shell that matches the React design. Redirects to
the SPA go to plain paths (`/`, `/compte/`) — Django no longer owns
`/compte` as a URL route beyond what's listed in `comptes/urls.py`.
"""

import base64
import logging
from io import BytesIO

import qrcode
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django_otp import login as otp_login
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from .forms import RegistreForm
from .tokens import email_verification_token

Usuari = get_user_model()
logger = logging.getLogger(__name__)

# S11: number of single-use backup codes issued on enrollment.
BACKUP_CODES_COUNT = 10

# After a successful login / activation, we land the user on the SPA
# dashboard. Django has no URL pattern for this path since the flip —
# it's a literal route handled by React.
SPA_DASHBOARD_URL = "/compte/"


# ─────────────────────────────────────────────────────────────────────────
# Registration + activation
# ─────────────────────────────────────────────────────────────────────────


def registre(request: HttpRequest) -> HttpResponse:
    """User registration: create inactive account and send verification email.

    Anti-enumeration (S5): we always show the same "check your email" page
    whether the address is new or already registered. If the email is taken
    we silently skip user creation and the verification mail, so an attacker
    cannot use the registration form to map existing accounts.
    """
    if request.user.is_authenticated:
        return redirect(SPA_DASHBOARD_URL)

    if request.method == "POST":
        form = RegistreForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            if not Usuari.objects.filter(email=email).exists():
                user = form.save()
                _send_verification_email(request, user)
            else:
                logger.debug(
                    "Registration attempt with existing email (no enumeration leak)"
                )
            return render(request, "comptes/registre_ok.html")
    else:
        form = RegistreForm()

    return render(request, "comptes/registre.html", {"form": form})


def _send_verification_email(request: HttpRequest, user) -> None:
    """Send HTML + plain-text email with activation link."""
    from django.template.loader import render_to_string

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    link = request.build_absolute_uri(f"/compte/activar/{uid}/{token}/")
    subject = "Activa el teu compte TopQuaranta"
    ctx = {"link": link, "subject": subject}
    html_body = render_to_string("comptes/email_activacio.html", ctx)
    text_body = (
        "Benvingut a TopQuaranta.\n\n"
        f"Activa el teu compte obrint aquest enllaç:\n{link}\n\n"
        "Si no esperaves aquest correu, pots ignorar-lo.\n"
    )
    try:
        send_mail(subject, text_body, None, [user.email], html_message=html_body)
    except Exception:
        logger.exception("Failed to send verification email to user pk=%s", user.pk)


def activar(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Activate user account from email verification link."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = Usuari.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Usuari.DoesNotExist):
        user = None

    if user and email_verification_token.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        login(request, user)
        return redirect(SPA_DASHBOARD_URL)

    return render(request, "comptes/activar_error.html")


# ─────────────────────────────────────────────────────────────────────────
# Password reset (triggered by staff from /staff/usuaris/<pk>/)
# ─────────────────────────────────────────────────────────────────────────


def esborrar_compte(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Confirm and execute self-deletion from the email link.

    GET  → show confirmation page with a single "Esborra ara" button.
    POST → validate the token again, delete the Usuari, render done page.
    """
    from django.contrib.auth import logout
    from django.contrib.auth.tokens import default_token_generator

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = Usuari.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Usuari.DoesNotExist):
        user = None

    if not user or not default_token_generator.check_token(user, token):
        return render(request, "comptes/esborrar_compte_error.html", status=400)
    if user.is_staff:
        # Belt-and-braces: refuse even if the token is valid.
        return render(request, "comptes/esborrar_compte_error.html", status=400)

    if request.method == "POST":
        email = user.email
        if request.user.is_authenticated and request.user.pk == user.pk:
            logout(request)
        user.delete()
        return render(request, "comptes/esborrar_compte_ok.html", {"email": email})

    return render(request, "comptes/esborrar_compte.html", {"email": user.email})


def nova_clau(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Land on a token-signed URL, show a form, set the new password."""
    from django.contrib.auth.forms import SetPasswordForm
    from django.contrib.auth.tokens import default_token_generator

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = Usuari.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Usuari.DoesNotExist):
        user = None

    if not user or not default_token_generator.check_token(user, token):
        return render(request, "comptes/nova_clau_error.html", status=400)

    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Contrasenya canviada. Ja pots iniciar sessió.")
            return redirect("comptes:login")
    else:
        form = SetPasswordForm(user)

    return render(
        request, "comptes/nova_clau.html", {"form": form, "email": user.email}
    )


# ─────────────────────────────────────────────────────────────────────────
# Login / logout
# ─────────────────────────────────────────────────────────────────────────


class TQLoginView(LoginView):
    """axes + django-otp aware login wrapper.

    React's SPA has its own login page that posts to
    `/api/v1/auth/login/`, but this Django view stays live because:
      * the 2FA flow at /compte/2fa/verificar/ redirects to ?next
        destinations that include /compte/login/
      * django-axes + TQLoginView remain the source of truth for
        password verification + lockout tracking.
    """

    template_name = "comptes/login.html"
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        """Route staff through 2FA after successful password auth.

        S11: staff lands on enrollment or the TOTP challenge first;
        non-staff users go straight to the SPA dashboard.
        """
        user = self.request.user
        next_url = (
            self.request.GET.get("next")
            or self.request.POST.get("next")
            or SPA_DASHBOARD_URL
        )

        if user.is_staff:
            has_confirmed = TOTPDevice.objects.filter(
                user=user, confirmed=True
            ).exists()
            if not has_confirmed:
                return f"/compte/2fa/configurar/?next={next_url}"
            return f"/compte/2fa/verificar/?next={next_url}"
        return next_url


class TQLogoutView(LogoutView):
    next_page = "/"


# ─────────────────────────────────────────────────────────────────────────
# S11 · 2FA (TOTP + backup codes)
#
# Flow:
#   Enrollment: /compte/2fa/configurar/
#     GET  → create an unconfirmed TOTPDevice, render a QR code.
#     POST → verify the 6-digit token; on success, mark the device
#            confirmed, create 10 single-use backup codes, show
#            them once. Session is marked OTP-verified via otp_login().
#
#   Challenge: /compte/2fa/verificar/
#     GET  → render the code input.
#     POST → accept either a TOTP token or a StaticDevice backup code.
#            On success, mark the session verified and redirect to ?next=.
#
#   Management: /compte/2fa/
#     Shows device status, offers regenerate-backup-codes and
#     remove-device actions. Both require is_verified() in this
#     session (can't reset 2FA just by logging in).
# ─────────────────────────────────────────────────────────────────────────


def _generate_backup_codes(user) -> list[str]:
    """Replace any existing static device with a fresh set of 10 single-use codes.
    Returns the plain-text codes to show to the user ONCE.
    """
    StaticDevice.objects.filter(user=user).delete()
    device = StaticDevice.objects.create(user=user, name="backup-codes")
    codes: list[str] = []
    for _ in range(BACKUP_CODES_COUNT):
        token = StaticToken.random_token()
        device.token_set.create(token=token)
        codes.append(token)
    return codes


@login_required(login_url="/compte/login/")
def dos_fa_configurar(request: HttpRequest) -> HttpResponse:
    """S11a · TOTP enrollment."""
    user = request.user

    if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        return redirect("comptes:dos_fa_gestio")

    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(user=user, name="default", confirmed=False)

    error = None
    backup_codes = None
    if request.method == "POST":
        token = (request.POST.get("token") or "").strip().replace(" ", "")
        if device.verify_token(token):
            device.confirmed = True
            device.save()
            backup_codes = _generate_backup_codes(user)
            otp_login(request, device)
            logger.info("2FA enrolled for user pk=%s", user.pk)
        else:
            error = "Codi incorrecte. Torna-ho a provar."

    uri = device.config_url
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render(
        request,
        "comptes/dos_fa_configurar.html",
        {
            "qr_b64": qr_b64,
            "secret": device.bin_key.hex().upper(),
            "error": error,
            "backup_codes": backup_codes,
        },
    )


@login_required(login_url="/compte/login/")
def dos_fa_verificar(request: HttpRequest) -> HttpResponse:
    """S11a · challenge screen — accepts TOTP or a single-use backup code."""
    user = request.user
    next_url = request.GET.get("next") or request.POST.get("next") or SPA_DASHBOARD_URL

    if user.is_verified():
        return redirect(next_url)

    if not TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        return redirect("comptes:dos_fa_configurar")

    error = None
    if request.method == "POST":
        token = (request.POST.get("token") or "").strip().replace(" ", "")
        verified_device = None
        for d in TOTPDevice.objects.filter(user=user, confirmed=True):
            if d.verify_token(token):
                verified_device = d
                break
        if verified_device is None:
            for d in StaticDevice.objects.filter(user=user, confirmed=True):
                if d.verify_token(token):
                    verified_device = d
                    break
        if verified_device is not None:
            otp_login(request, verified_device)
            logger.info(
                "2FA verified for user pk=%s (%s)", user.pk, verified_device.name
            )
            return redirect(next_url)
        error = "Codi incorrecte."
        logger.warning("2FA failed for user pk=%s", user.pk)

    return render(
        request,
        "comptes/dos_fa_verificar.html",
        {"error": error, "next": next_url},
    )


@login_required(login_url="/compte/login/")
def dos_fa_gestio(request: HttpRequest) -> HttpResponse:
    """S11c · status page + manage backup codes + remove device."""
    user = request.user
    has_totp = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
    has_backup = StaticDevice.objects.filter(
        user=user, token_set__isnull=False
    ).exists()

    new_codes = None
    if request.method == "POST":
        if not user.is_verified():
            return redirect("/compte/2fa/verificar/?next=/compte/2fa/")
        action = request.POST.get("action", "")
        if action == "regenerar_codis":
            new_codes = _generate_backup_codes(user)
            messages.success(
                request,
                "Codis de recuperació regenerats. Desa'ls ara — no podràs "
                "tornar-los a veure.",
            )
        elif action == "eliminar_dispositiu":
            password = request.POST.get("password", "")
            if user.check_password(password):
                TOTPDevice.objects.filter(user=user).delete()
                StaticDevice.objects.filter(user=user).delete()
                messages.success(
                    request,
                    "Dispositiu 2FA eliminat. Hauràs de tornar a configurar-lo.",
                )
                return redirect("comptes:dos_fa_configurar")
            messages.error(request, "Contrasenya incorrecta.")

    return render(
        request,
        "comptes/dos_fa_gestio.html",
        {
            "has_totp": has_totp,
            "has_backup": has_backup,
            "is_verified": user.is_verified(),
            "new_codes": new_codes,
        },
    )
