"""Account dashboard + profile read/update endpoints."""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import PropostaArtista, UserArtista, Usuari
from ranking.models import TopSetmanal

from ._common import _profile_payload, _serialize_proposta, _serialize_user_artista


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request: Request) -> Response:
    user = request.user
    gestio_list = list(
        UserArtista.objects.filter(usuari=user)
        .select_related("artista")
        .order_by("-created_at")
    )
    propostes_list = list(
        PropostaArtista.objects.filter(usuari=user)
        .select_related("artista_creat")
        .order_by("-created_at")
    )
    artista_verificat = next((ua for ua in gestio_list if ua.verificat), None)

    # Artist stats, only if the user manages a verified artist.
    stats = None
    if artista_verificat:
        qs = TopSetmanal.objects.filter(canco__artista=artista_verificat.artista)
        stats = {
            "setmanes_al_ranking": qs.values("setmana").distinct().count(),
            "millor_posicio": qs.order_by("posicio")
            .values_list("posicio", flat=True)
            .first(),
            "cancons_al_ranking": qs.values("canco_id").distinct().count(),
            "territoris_presents": qs.values("territori").distinct().count(),
        }

    # Perfil snapshot — Sprint H surfaces directori state on the dashboard
    # so the SPA can show "Activa el teu perfil" / "Edita el perfil" CTAs
    # without a second round-trip to /comunitat/perfil/.
    perfil_obj = getattr(user, "perfil", None)
    perfil_payload = {
        "visible_directori": bool(getattr(perfil_obj, "visible_directori", False)),
        "onboarding_complet": bool(getattr(perfil_obj, "onboarding_complet", False)),
        "nom_public": getattr(perfil_obj, "nom_public", "") or "",
    }

    return Response(
        {
            "user": {
                "email": user.email,
                "username": user.username,
                "date_joined": (
                    user.date_joined.isoformat() if user.date_joined else None
                ),
                "is_staff": bool(user.is_staff),
            },
            "perfil": perfil_payload,
            "gestio_list": [_serialize_user_artista(u) for u in gestio_list],
            "propostes_list": [_serialize_proposta(p) for p in propostes_list],
            "artista_verificat": (
                _serialize_user_artista(artista_verificat)
                if artista_verificat
                else None
            ),
            "stats": stats,
        }
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def perfil(request: Request) -> Response:
    """Current user profile — read + partial update.

    PATCH accepts any subset of:
      email, username, password (requires current_password).

    Email changes are validated (syntax + uniqueness). Password change
    runs Django's full validator chain; on success we keep the session
    alive via `update_session_auth_hash` so the user doesn't get kicked
    out mid-edit.
    """
    user = request.user

    if request.method == "GET":
        return Response(_profile_payload(user))

    data = request.data or {}
    errors: dict[str, str] = {}

    new_email = (data.get("email") or "").strip().lower()
    if new_email and new_email != user.email:
        try:
            validate_email(new_email)
        except ValidationError:
            errors["email"] = "Correu no vàlid."
        else:
            if (
                Usuari.objects.filter(email__iexact=new_email)
                .exclude(pk=user.pk)
                .exists()
            ):
                errors["email"] = "Aquest correu ja està en ús."

    new_username = (data.get("username") or "").strip()
    if new_username and new_username != user.username:
        if len(new_username) < 3:
            errors["username"] = "Massa curt (mínim 3)."
        elif (
            Usuari.objects.filter(username__iexact=new_username)
            .exclude(pk=user.pk)
            .exists()
        ):
            errors["username"] = "Aquest nom d'usuari ja està en ús."

    new_password = data.get("password") or ""
    current_password = data.get("current_password") or ""
    if new_password:
        if not current_password or not user.check_password(current_password):
            errors["current_password"] = "La contrasenya actual és incorrecta."
        else:
            try:
                validate_password(new_password, user=user)
            except ValidationError as exc:
                errors["password"] = "; ".join(exc.messages)

    if errors:
        return Response({"errors": errors}, status=400)

    updated_fields: list[str] = []
    if new_email and new_email != user.email:
        user.email = new_email
        updated_fields.append("email")
    if new_username and new_username != user.username:
        user.username = new_username
        updated_fields.append("username")

    try:
        if updated_fields:
            user.save(update_fields=updated_fields)
        if new_password:
            user.set_password(new_password)
            user.save(update_fields=["password"])
            update_session_auth_hash(request, user)
        # Newsletter opt-in/out — only touch the perfil row if the
        # caller actually sent the field (so a PATCH with only an
        # email change doesn't accidentally reset it).
        if "vol_newsletter" in data:
            from django.utils import timezone

            from comptes.models import PerfilUsuari

            perfil, _ = PerfilUsuari.objects.get_or_create(usuari=user)
            wants = bool(data.get("vol_newsletter"))
            if perfil.vol_newsletter != wants:
                perfil.vol_newsletter = wants
                if wants and not perfil.consent_newsletter_at:
                    perfil.consent_newsletter_at = timezone.now()
                perfil.save(update_fields=["vol_newsletter", "consent_newsletter_at"])
    except IntegrityError:
        return Response(
            {"errors": {"__all__": "Error de validació al desar."}},
            status=400,
        )

    return Response(_profile_payload(user))
