"""Authenticated /compte/ endpoints for the React SPA.

GET   /api/v1/compte/dashboard/   — managed artists + proposals + stats
GET   /api/v1/compte/perfil/      — current profile snapshot
PATCH /api/v1/compte/perfil/      — update email / username / password
POST  /api/v1/compte/propostes/   — submit a new-artist proposal
POST  /api/v1/compte/solicituds/  — submit a management request for an
                                    existing artist
"""

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import HTTP_ONLY_URL, Feedback, PropostaArtista, UserArtista, Usuari
from music.models import Artista, Municipi
from ranking.models import TopSetmanal


def _serialize_user_artista(ua) -> dict:
    a = ua.artista
    return {
        "pk": ua.pk,
        "estat": ua.estat,
        "verificat": ua.verificat,
        "created_at": ua.created_at.isoformat() if ua.created_at else None,
        "artista": {
            # `pk` is needed by the SPA so verified managers can deep-link
            # into /compte/artista/<pk>/editar (the gestor self-edit form).
            "pk": a.pk,
            "slug": a.slug,
            "nom": a.nom,
        },
    }


def _serialize_proposta(p) -> dict:
    return {
        "pk": p.pk,
        "nom": p.nom,
        "estat": p.estat,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "justificacio": p.justificacio,
        "artista_creat": (
            {"slug": p.artista_creat.slug, "nom": p.artista_creat.nom}
            if p.artista_creat
            else None
        ),
    }


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


def _profile_payload(user) -> dict:
    return {
        "email": user.email,
        "username": user.username,
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        "is_staff": bool(user.is_staff),
        "is_superuser": bool(user.is_superuser),
    }


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
    except IntegrityError:
        return Response(
            {"errors": {"__all__": "Error de validació al desar."}},
            status=400,
        )

    return Response(_profile_payload(user))


# ─────────────────────────────────────────────────────────────────────────
# Propostes d'artistes nous (user-submitted)
# ─────────────────────────────────────────────────────────────────────────

SOCIAL_FIELDS = [f for f, _ in Artista.SOCIAL_LINK_FIELDS]
# Subset of SOCIAL_FIELDS that also exists on PropostaArtista. Myspace
# lives on Artista only; skipping it here keeps setattr() safe.
PROPOSTA_SOCIAL_FIELDS = [
    "spotify_url",
    "viasona_url",
    "web_url",
    "bandcamp_url",
    "youtube_url",
    "viquipedia_url",
    "soundcloud_url",
    "tiktok_url",
    "facebook_url",
    "instagram_url",
    "twitter_url",
]


def _clean_url(raw: str) -> tuple[str, str | None]:
    """Validate a user-submitted URL. Returns (value, error)."""
    raw = (raw or "").strip()
    if not raw:
        return "", None
    try:
        HTTP_ONLY_URL(raw)
    except ValidationError:
        return raw, "URL no vàlida (només http/https)."
    return raw, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def proposta_crear(request: Request) -> Response:
    """Create a PropostaArtista for the authenticated user.

    Body:
      nom            str, required
      justificacio   str, required
      deezer_ids     list, REQUIRED (≥ 1 numeric ID) — without a Deezer
                     ID no track of the artist can be verified, so the
                     proposal can't enter the ranking pipeline.
      localitzacions list, REQUIRED (≥ 1 entry) — each
                     {"municipi_id": int} or {"manual": str}.
                     "manual" is reserved for ALT-territori artists
                     whose localitat isn't in the PPCC Municipi table.
      <social>_url   optional URL fields (one per social network)
    """
    data = request.data or {}
    errors: dict[str, str] = {}

    nom = (data.get("nom") or "").strip()
    if not nom:
        errors["nom"] = "Obligatori."
    elif len(nom) > 255:
        errors["nom"] = "Massa llarg (màxim 255 caràcters)."

    justificacio = (data.get("justificacio") or "").strip()
    if not justificacio:
        errors["justificacio"] = "Obligatòria."

    socials: dict[str, str] = {}
    for f in PROPOSTA_SOCIAL_FIELDS:
        val, err = _clean_url(data.get(f, ""))
        if err:
            errors[f] = err
        socials[f] = val

    # ── Deezer IDs (required, ≥ 1) ────────────────────────────────────
    raw_deezer = data.get("deezer_ids") or []
    deezer_ids: list[int] = []
    for raw in raw_deezer:
        try:
            deezer_ids.append(int(raw))
        except (TypeError, ValueError):
            errors["deezer_ids"] = "Els IDs han de ser números enters."
            break
    if "deezer_ids" not in errors and not deezer_ids:
        errors["deezer_ids"] = (
            "Cal almenys un Deezer ID. Sense ell no podem verificar "
            "cap cançó de l'artista ni fer-lo entrar al rànquing."
        )

    # ── Stopper: block a proposta if any Deezer ID is already on an
    # aprovat=True artist. The system already knows this artist — the
    # proposal adds noise to the staff queue without giving any new
    # signal. For Deezer IDs on pending (non-aprovat) artists we let
    # the proposal through; the pendents page aggregates the "n
    # propostes" counter so staff can see the repeated interest. ────
    from music.models import ArtistaDeezer

    if deezer_ids and "deezer_ids" not in errors:
        already_live = list(
            ArtistaDeezer.objects.filter(
                deezer_id__in=deezer_ids, artista__aprovat=True
            ).select_related("artista")
        )
        if already_live:
            names = ", ".join(
                f"«{ad.artista.nom}» (Deezer {ad.deezer_id})" for ad in already_live
            )
            errors["deezer_ids"] = (
                "Aquest Deezer ID ja pertany a un artista ja registrat i "
                f"aprovat al sistema: {names}. No cal proposar-lo — "
                "prova de demanar-ne la gestió des del seu perfil."
            )

    # ── Localitzacions (required, ≥ 1) ────────────────────────────────
    raw_locs = data.get("localitzacions") or []
    localitzacions: list[dict] = []
    for loc in raw_locs:
        if not isinstance(loc, dict):
            continue
        if loc.get("municipi_id"):
            try:
                pk = int(loc["municipi_id"])
            except (TypeError, ValueError):
                continue
            if not Municipi.objects.filter(pk=pk).exists():
                continue
            localitzacions.append({"municipi_id": pk})
        elif loc.get("manual"):
            manual = str(loc["manual"]).strip()
            if manual:
                localitzacions.append({"manual": manual})
    if not localitzacions:
        errors["localitzacions"] = (
            "Cal indicar almenys una localitat (territori → comarca → "
            "municipi, o 'Altres' + nom lliure)."
        )

    if errors:
        return Response({"errors": errors}, status=400)

    p = PropostaArtista.objects.create(
        usuari=request.user,
        nom=nom,
        justificacio=justificacio,
        deezer_ids=deezer_ids,
        localitzacions=localitzacions,
        **socials,
    )
    return Response({"ok": True, "pk": p.pk, "estat": p.estat}, status=201)


# ─────────────────────────────────────────────────────────────────────────
# Sol·licituds de gestió (UserArtista)
# ─────────────────────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def solicitud_crear(request: Request) -> Response:
    """Create a UserArtista request for the authenticated user.

    Body:
      artista_slug  str, required — must resolve to an aprovat=True artist
      sollicitud_text  str, required — why you should manage this artist
    """
    data = request.data or {}
    errors: dict[str, str] = {}

    slug = (data.get("artista_slug") or "").strip()
    text = (data.get("sollicitud_text") or "").strip()
    if not slug:
        errors["artista_slug"] = "Tria un artista."
    if not text:
        errors["sollicitud_text"] = "Cal una justificació."

    if errors:
        return Response({"errors": errors}, status=400)

    try:
        artista = Artista.objects.get(slug=slug, aprovat=True)
    except Artista.DoesNotExist:
        return Response(
            {"errors": {"artista_slug": "Artista no trobat o no aprovat."}},
            status=404,
        )

    # Deny duplicates: same user + same artist + still open.
    existing = UserArtista.objects.filter(
        usuari=request.user,
        artista=artista,
        estat__in=[UserArtista.ESTAT_PENDENT, UserArtista.ESTAT_APROVAT],
    ).first()
    if existing:
        return Response(
            {
                "errors": {
                    "artista_slug": (
                        "Ja tens una sol·licitud activa per a aquest artista."
                    )
                }
            },
            status=400,
        )

    ua = UserArtista.objects.create(
        usuari=request.user,
        artista=artista,
        sollicitud_text=text,
        estat=UserArtista.ESTAT_PENDENT,
    )
    return Response({"ok": True, "pk": ua.pk, "estat": ua.estat}, status=201)


# ─────────────────────────────────────────────────────────────────────────
# Gestor d'artista — self-service edit of non-critical fields
# ─────────────────────────────────────────────────────────────────────────

# Fields a verified manager (UserArtista.verificat=True) may write directly
# to their managed artist. Anything outside this set is silently ignored
# (we don't 400 on extras so a future SPA bundle adding fields stays
# forward-compatible). Critical fields kept staff-only:
#   nom, slug, deezer_ids/ArtistaDeezer, ArtistaLocalitat (territoris),
#   aprovat, pendent_review, MusicBrainz lockouts.
GESTOR_EDITABLE_TEXT_FIELDS = ("bio", "genere")
GESTOR_EDITABLE_CHOICE_FIELDS = ("percentatge_femeni",)
GESTOR_EDITABLE_URL_FIELDS = tuple(f for f, _ in Artista.SOCIAL_LINK_FIELDS)
GESTOR_EDITABLE_FIELDS = (
    GESTOR_EDITABLE_TEXT_FIELDS
    + GESTOR_EDITABLE_CHOICE_FIELDS
    + GESTOR_EDITABLE_URL_FIELDS
)


def _serialize_gestor_artista(a: Artista) -> dict:
    """Snapshot of the editable surface, plus choice metadata for the form."""
    return {
        "pk": a.pk,
        "slug": a.slug,
        "nom": a.nom,
        "bio": a.bio or "",
        "genere": a.genere or "",
        "percentatge_femeni": a.percentatge_femeni or "",
        "social": {f: getattr(a, f) or "" for f in GESTOR_EDITABLE_URL_FIELDS},
        # Form metadata so the SPA doesn't hard-code the choice list.
        "percentatge_choices": list(Artista.PERCENTATGE_FEMENI_CHOICES),
        "social_fields": list(Artista.SOCIAL_LINK_FIELDS),
    }


def _gestor_check(request, pk: int) -> Artista | Response:
    """Return the Artista if `request.user` may manage it, else a 403/404."""
    try:
        artista = Artista.objects.get(pk=pk)
    except Artista.DoesNotExist:
        return Response({"error": "Artista no trobat."}, status=404)
    has_verified = UserArtista.objects.filter(
        usuari=request.user, artista=artista, verificat=True
    ).exists()
    if not has_verified:
        return Response(
            {"error": "No tens permís per editar aquest artista."}, status=403
        )
    return artista


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def gestor_artista_editar(request: Request, pk: int) -> Response:
    """Verified-manager self-service editor for non-critical Artista fields.

    GET   returns the current snapshot + form metadata.
    PATCH writes any subset of GESTOR_EDITABLE_FIELDS. Unknown keys are
          silently dropped. URLFields go through HTTP_ONLY_URL; bad URLs
          return 400 with per-field errors. Choice fields are validated
          against `PERCENTATGE_FEMENI_CHOICES`. Audit row is written
          *only* when at least one field actually changed (no log spam
          on no-op PATCHes from auto-saves)."""
    result = _gestor_check(request, pk)
    if isinstance(result, Response):
        return result
    artista = result

    if request.method == "GET":
        return Response(_serialize_gestor_artista(artista))

    data = request.data or {}
    errors: dict[str, str] = {}
    valid_choices = {v for v, _ in Artista.PERCENTATGE_FEMENI_CHOICES}
    canviats: list[str] = []

    # Free-text fields
    for f in GESTOR_EDITABLE_TEXT_FIELDS:
        if f not in data:
            continue
        new = (data.get(f) or "").strip()
        if getattr(artista, f, "") != new:
            setattr(artista, f, new)
            canviats.append(f)

    # Choice fields
    for f in GESTOR_EDITABLE_CHOICE_FIELDS:
        if f not in data:
            continue
        new = (data.get(f) or "").strip()
        if new and new not in valid_choices:
            errors[f] = "Valor no vàlid."
            continue
        if getattr(artista, f) != new:
            setattr(artista, f, new)
            canviats.append(f)

    # URL fields — validated via the same HTTP-only validator the
    # proposta endpoint uses. Empty string clears the field.
    for f in GESTOR_EDITABLE_URL_FIELDS:
        if f not in data:
            continue
        val, err = _clean_url(data.get(f, ""))
        if err:
            errors[f] = err
            continue
        if getattr(artista, f) != val:
            setattr(artista, f, val)
            canviats.append(f)

    if errors:
        return Response({"errors": errors}, status=400)

    if canviats:
        artista.save(update_fields=canviats)
        from music.audit import log_staff_action

        log_staff_action(
            request,
            "gestor_edita_artista",
            target=artista,
            camps=canviats,
            usuari=request.user.pk,
        )

    return Response(
        {"ok": True, "canviats": canviats, **_serialize_gestor_artista(artista)}
    )


# ─────────────────────────────────────────────────────────────────────────
# Feedback (user-filed correction reports)
# ─────────────────────────────────────────────────────────────────────────

VALID_TARGETS = {t for t, _ in Feedback.TARGET_CHOICES}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def feedback_crear(request: Request) -> Response:
    """File a feedback/correction report from a public page.

    Body:
      url           str, required    — absolute or path-only, max 500 chars
      target_type   str, optional    — one of {artista, album, canco, altres}
      target_pk     int, optional
      target_slug   str, optional
      target_label  str, optional    — display name snapshot
      missatge      str, required    — the actual comment/correction
    """
    data = request.data or {}
    errors: dict[str, str] = {}

    url = (data.get("url") or "").strip()
    if not url:
        errors["url"] = "Falta la URL de la pàgina."
    elif len(url) > 500:
        errors["url"] = "URL massa llarga."

    missatge = (data.get("missatge") or "").strip()
    if not missatge:
        errors["missatge"] = "Escriu què cal corregir."
    elif len(missatge) > 5000:
        errors["missatge"] = "Missatge massa llarg (màxim 5000 caràcters)."

    target_type = (data.get("target_type") or Feedback.TARGET_ALTRES).strip()
    if target_type not in VALID_TARGETS:
        target_type = Feedback.TARGET_ALTRES

    target_pk_raw = data.get("target_pk")
    target_pk = None
    if target_pk_raw not in (None, ""):
        try:
            target_pk = int(target_pk_raw)
        except (TypeError, ValueError):
            pass

    if errors:
        return Response({"errors": errors}, status=400)

    fb = Feedback.objects.create(
        usuari=request.user,
        url=url,
        target_type=target_type,
        target_pk=target_pk,
        target_slug=(data.get("target_slug") or "").strip()[:550],
        target_label=(data.get("target_label") or "").strip()[:500],
        missatge=missatge,
    )
    return Response({"ok": True, "pk": fb.pk}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
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


# ─────────────────────────────────────────────────────────────────────────
# Sprint J — RGPD endpoints
# ─────────────────────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def exportar_dades(request: Request) -> Response:
    """Right to data portability (RGPD art. 20).

    Collects everything the system knows about the user across the
    domain models (perfil, gestió d'artistes, propostes, feedback,
    publicacions, comentaris, missatges) and emails it to the user
    as a JSON attachment. Inline only — never persisted to disk.
    """
    import json
    import logging
    from email.mime.application import MIMEApplication

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


@api_view(["GET"])
@permission_classes([])
def baixa_newsletter(request: Request) -> Response:
    """Token-based newsletter unsubscribe (RGPD art. 7.3 — withdrawal
    must be as easy as giving consent). Intended to be linked from
    every newsletter email; works without login.

    Token is `signing.dumps({"u": user.pk}, salt="newsletter-baixa")`
    with the project SECRET_KEY. No max_age — links don't expire."""
    from django.core import signing

    from comptes.models import Usuari

    token = (request.GET.get("token") or "").strip()
    if not token:
        return Response({"error": "Falta el token."}, status=400)
    try:
        data = signing.loads(token, salt="newsletter-baixa")
        user_pk = int(data["u"])
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
