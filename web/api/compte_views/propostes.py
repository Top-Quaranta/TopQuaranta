"""Artist proposal + management request + verified-manager self-edit."""

from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import HTTP_ONLY_URL, PropostaArtista, UserArtista
from music.models import Artista, Municipi

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
