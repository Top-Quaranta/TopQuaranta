"""Community-platform endpoints (Grup C).

All routes live under `/api/v1/`. This module owns:

  * `/compte/perfil-usuari/`         GET + PATCH — authenticated user's own profile
  * `/comunitat/directori/`          GET — listing of users with visible_directori=True
  * `/comunitat/publicacions/`       GET (list) + POST (create)
  * `/comunitat/publicacions/<pk>/`  GET + PATCH + DELETE (owner or staff)
  * `/comunitat/publicacions-publiques/`  GET — unauthenticated public feed
  * `/staff/publicacions/`           GET — staff moderation list
  * `/staff/publicacions/<pk>/decidir/`   POST — publicar / rebutjar
  * `/staff/directori-usuaris/`      GET + `/staff/directori-usuaris/<pk>/toggle/`

Visibility rules:

  - `interna` + `publicat` → visible to any authenticated user.
  - `publica` + `publicat` → visible to everyone (no auth needed).
  - `esborrany` / `pendent` / `rebutjat` → visible only to the author
    and to staff.

Staff bypass: staff posts skip the `pendent` step and land in `publicat`
immediately. Non-staff posts with `visibilitat=publica` start in
`pendent` and wait for staff review.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import URLValidator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import (
    HTTP_ONLY_URL,
    PerfilUsuari,
    Publicacio,
    UserArtista,
)
from music.models import Municipi
from web.api.search_utils import normalize_search_term, unaccent_field
from web.api.staff_views import IsStaff

# ═════════════════════════════════════════════════════════════════════════
# PerfilUsuari
# ═════════════════════════════════════════════════════════════════════════


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


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def perfil_usuari(request: Request) -> Response:
    """Authenticated user's own PerfilUsuari — read + partial update.

    The signal on User creation guarantees `usuari.perfil` exists, so we
    can assume the OneToOne. If for any reason it doesn't we create it
    on-the-fly.
    """
    user = request.user
    perfil, _ = PerfilUsuari.objects.get_or_create(usuari=user)

    if request.method == "PATCH":
        data = request.data or {}
        errors: dict[str, str] = {}

        # Simple fields
        simple = {
            "nom_public": 120,
            "bio": 2000,
            "instruments": 255,
        }
        for field, maxlen in simple.items():
            if field in data:
                val = (data.get(field) or "").strip()
                if len(val) > maxlen:
                    errors[field] = f"Massa llarg (màxim {maxlen})."
                else:
                    setattr(perfil, field, val)

        # Image URL (optional)
        if "imatge_url" in data:
            val, err = _clean_url(data.get("imatge_url", ""))
            if err:
                errors["imatge_url"] = err
            else:
                perfil.imatge_url = val

        # Localitat: either municipi_id (int) or null
        if "localitat_pk" in data:
            raw = data.get("localitat_pk")
            if raw in (None, "", 0):
                perfil.localitat = None
            else:
                try:
                    perfil.localitat = Municipi.objects.get(pk=int(raw))
                except (ValueError, Municipi.DoesNotExist):
                    errors["localitat_pk"] = "Municipi no trobat."

        # Rol + instruments + visibility flags
        if "rol_musical" in data:
            v = (data.get("rol_musical") or "").strip()
            if v not in {k for k, _ in PerfilUsuari.ROL_CHOICES}:
                errors["rol_musical"] = "Valor no vàlid."
            else:
                perfil.rol_musical = v

        for flag in (
            "visible_directori",
            "obert_colaboracions",
            "onboarding_complet",
            "notificar_missatges_email",
            "notificar_comentaris_email",
        ):
            if flag in data:
                setattr(perfil, flag, bool(data.get(flag)))

        # Socials
        for field, _label in PerfilUsuari.SOCIAL_FIELDS:
            if field in data:
                val, err = _clean_url(data.get(field, ""))
                if err:
                    errors[field] = err
                else:
                    setattr(perfil, field, val)

        if errors:
            return Response({"errors": errors}, status=400)
        perfil.save()

    return Response(_serialize_perfil(perfil, include_private=True))


# ═════════════════════════════════════════════════════════════════════════
# Directori (authenticated users only)
# ═════════════════════════════════════════════════════════════════════════


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def directori(request: Request) -> Response:
    """Public-to-registered-users directory.

    Filters: q (name/username/instruments), rol, obert_colaboracions,
    territori (by localitat.municipi.territori). Page size 30.
    """
    qs = (
        PerfilUsuari.objects.filter(visible_directori=True, usuari__is_active=True)
        .select_related("usuari", "localitat", "localitat__territori")
        .prefetch_related("usuari__artistes_vinculats__artista")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        nq = normalize_search_term(q)
        qs = qs.annotate(
            _nom_norm=unaccent_field("nom_public"),
            _user_norm=unaccent_field("usuari__username"),
            _instr_norm=unaccent_field("instruments"),
            _bio_norm=unaccent_field("bio"),
        ).filter(
            Q(_nom_norm__contains=nq)
            | Q(_user_norm__contains=nq)
            | Q(_instr_norm__contains=nq)
            | Q(_bio_norm__contains=nq)
        )
    rol = request.GET.get("rol", "")
    if rol in {k for k, _ in PerfilUsuari.ROL_CHOICES}:
        qs = qs.filter(rol_musical=rol)
    if request.GET.get("obert") == "1":
        qs = qs.filter(obert_colaboracions=True)
    territori = request.GET.get("territori", "")
    if territori:
        qs = qs.filter(localitat__territori_id=territori)

    qs = qs.order_by("nom_public", "usuari__username")

    try:
        per_page = min(int(request.GET.get("per_page") or 30), 100)
    except ValueError:
        per_page = 30
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(request.GET.get("page") or 1)

    rows = []
    for p in page.object_list:
        artistes_gestionats = [
            {"slug": ua.artista.slug, "nom": ua.artista.nom}
            for ua in p.usuari.artistes_vinculats.all()
            if ua.estat == UserArtista.ESTAT_APROVAT and ua.artista
        ]
        loc = p.localitat
        rows.append(
            {
                "usuari_id": p.usuari_id,
                "username": p.usuari.username,
                "nom_public": p.nom_public or p.usuari.username,
                "rol_musical": p.rol_musical,
                "instruments": p.instruments or "",
                "obert_colaboracions": p.obert_colaboracions,
                "imatge_url": p.imatge_url or "",
                "localitat": (
                    f"{loc.nom}, {loc.comarca} ({loc.territori_id})" if loc else ""
                ),
                "territori": loc.territori_id if loc else None,
                "artistes_gestionats": artistes_gestionats,
            }
        )

    return Response(
        {
            "results": rows,
            "page": page.number,
            "num_pages": paginator.num_pages,
            "total": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
            "rol_choices": list(PerfilUsuari.ROL_CHOICES),
        }
    )


# ═════════════════════════════════════════════════════════════════════════
# Publicacions
# ═════════════════════════════════════════════════════════════════════════


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


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def publicacions(request: Request) -> Response:
    """List + create. List returns internal + public (authenticated view)."""
    if request.method == "POST":
        cleaned, errors = _validate_publicacio_body(request.data or {})
        save_as = (request.data or {}).get("save_as", "submit")
        if errors:
            return Response({"errors": errors}, status=400)
        user = request.user
        # Staff bypasses the pending queue for any visibility.
        # Regular users: `interna` → published directly;
        # `publica` → goes through the pending queue.
        if save_as == "draft":
            estat = Publicacio.ESTAT_ESBORRANY
            publicat_at = None
        elif user.is_staff or cleaned["visibilitat"] == Publicacio.VISIBILITAT_INTERNA:
            estat = Publicacio.ESTAT_PUBLICAT
            publicat_at = timezone.now()
        else:
            estat = Publicacio.ESTAT_PENDENT
            publicat_at = None

        pub = Publicacio.objects.create(
            autor=user,
            titol=cleaned["titol"],
            cos=cleaned["cos"],
            visibilitat=cleaned["visibilitat"],
            estat=estat,
            publicat_at=publicat_at,
        )
        return Response(_serialize_publicacio(pub), status=201)

    # ── GET: combined internal + own drafts/pending + public ───────────
    qs = Publicacio.objects.select_related("autor", "autor__perfil")
    # Show: (visibilitat=interna AND estat=publicat) + own in any state
    own = Q(autor=request.user)
    internal_published = Q(
        visibilitat=Publicacio.VISIBILITAT_INTERNA, estat=Publicacio.ESTAT_PUBLICAT
    )
    public_published = Q(
        visibilitat=Publicacio.VISIBILITAT_PUBLICA, estat=Publicacio.ESTAT_PUBLICAT
    )
    qs = qs.filter(own | internal_published | public_published)

    filter_mode = request.GET.get("filtre", "")
    if filter_mode == "meves":
        qs = qs.filter(autor=request.user)
    elif filter_mode == "internes":
        qs = qs.filter(internal_published)
    elif filter_mode == "publiques":
        qs = qs.filter(public_published)

    qs = qs.order_by("-publicat_at", "-created_at")
    try:
        per_page = min(int(request.GET.get("per_page") or 20), 100)
    except ValueError:
        per_page = 20
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(request.GET.get("page") or 1)
    return Response(
        {
            "results": [_serialize_publicacio(p) for p in page.object_list],
            "page": page.number,
            "num_pages": paginator.num_pages,
            "total": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        }
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def publicacio_detail(request: Request, pk: int) -> Response:
    pub = get_object_or_404(
        Publicacio.objects.select_related("autor", "autor__perfil"), pk=pk
    )
    # Authorization: author can always see; staff can always see; other
    # users only if it's published.
    user = request.user
    can_view = (
        pub.autor_id == user.id
        or user.is_staff
        or pub.estat == Publicacio.ESTAT_PUBLICAT
    )
    if not can_view:
        return Response({"detail": "No trobat."}, status=404)

    if request.method == "DELETE":
        if pub.autor_id != user.id and not user.is_staff:
            return Response({"detail": "No autoritzat."}, status=403)
        pub.delete()
        return Response(status=204)

    if request.method == "PATCH":
        if pub.autor_id != user.id and not user.is_staff:
            return Response({"detail": "No autoritzat."}, status=403)
        cleaned, errors = _validate_publicacio_body(request.data or {})
        if errors:
            return Response({"errors": errors}, status=400)
        pub.titol = cleaned["titol"]
        pub.cos = cleaned["cos"]
        # Visibility change rules: staff free; author can only move
        # between esborrany/interna. Switching to `publica` resubmits
        # for approval unless staff.
        old_vis = pub.visibilitat
        pub.visibilitat = cleaned["visibilitat"]
        if not user.is_staff and old_vis != pub.visibilitat:
            if pub.visibilitat == Publicacio.VISIBILITAT_PUBLICA:
                pub.estat = Publicacio.ESTAT_PENDENT
                pub.publicat_at = None
            else:
                pub.estat = Publicacio.ESTAT_PUBLICAT
                pub.publicat_at = pub.publicat_at or timezone.now()
        pub.save()

    return Response(
        _serialize_publicacio(pub, for_staff=user.is_staff or pub.autor_id == user.id)
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def publicacions_publiques(request: Request) -> Response:
    """Public feed — visible without auth, only `publica + publicat`."""
    qs = (
        Publicacio.objects.filter(
            visibilitat=Publicacio.VISIBILITAT_PUBLICA,
            estat=Publicacio.ESTAT_PUBLICAT,
        )
        .select_related("autor", "autor__perfil")
        .order_by("-publicat_at")
    )
    try:
        per_page = min(int(request.GET.get("per_page") or 20), 100)
    except ValueError:
        per_page = 20
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(request.GET.get("page") or 1)
    return Response(
        {
            "results": [_serialize_publicacio(p) for p in page.object_list],
            "page": page.number,
            "num_pages": paginator.num_pages,
            "total": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        }
    )


# ═════════════════════════════════════════════════════════════════════════
# Staff moderation
# ═════════════════════════════════════════════════════════════════════════


@api_view(["GET"])
@permission_classes([IsStaff])
def staff_publicacions(request: Request) -> Response:
    qs = Publicacio.objects.select_related("autor", "autor__perfil")
    estat = request.GET.get("estat", "pendent")
    if estat in {k for k, _ in Publicacio.ESTAT_CHOICES}:
        qs = qs.filter(estat=estat)
    q = (request.GET.get("q") or "").strip()
    if q:
        nq = normalize_search_term(q)
        qs = qs.annotate(
            _titol_norm=unaccent_field("titol"),
            _cos_norm=unaccent_field("cos"),
            _user_norm=unaccent_field("autor__username"),
            _email_norm=unaccent_field("autor__email"),
        ).filter(
            Q(_titol_norm__contains=nq)
            | Q(_cos_norm__contains=nq)
            | Q(_user_norm__contains=nq)
            | Q(_email_norm__contains=nq)
        )
    qs = qs.order_by("-created_at")
    try:
        per_page = min(int(request.GET.get("per_page") or 25), 100)
    except ValueError:
        per_page = 25
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(request.GET.get("page") or 1)
    return Response(
        {
            "results": [
                _serialize_publicacio(p, for_staff=True) for p in page.object_list
            ],
            "page": page.number,
            "num_pages": paginator.num_pages,
            "total": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
            "estat_choices": list(Publicacio.ESTAT_CHOICES),
        }
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def staff_publicacio_decidir(request: Request, pk: int) -> Response:
    """Publish, reject or unpublish a publication.

    Body: {action: "publicar" | "rebutjar" | "despublicar", notes_staff?}.
    """
    pub = get_object_or_404(Publicacio, pk=pk)
    data = request.data or {}
    action = (data.get("action") or "").strip()
    notes = (data.get("notes_staff") or "").strip()

    if action == "publicar":
        pub.estat = Publicacio.ESTAT_PUBLICAT
        pub.publicat_at = pub.publicat_at or timezone.now()
    elif action == "rebutjar":
        pub.estat = Publicacio.ESTAT_REBUTJAT
        pub.publicat_at = None
    elif action == "despublicar":
        pub.estat = Publicacio.ESTAT_ESBORRANY
        pub.publicat_at = None
    else:
        return Response({"error": "Acció no vàlida."}, status=400)

    pub.notes_staff = notes
    pub.save()
    return Response(_serialize_publicacio(pub, for_staff=True))


@api_view(["GET"])
@permission_classes([IsStaff])
def staff_directori_usuaris(request: Request) -> Response:
    """Staff view over every PerfilUsuari regardless of visible_directori."""
    qs = (
        PerfilUsuari.objects.select_related("usuari", "localitat")
        .annotate(n_publicacions=Count("usuari__publicacions"))
        .order_by("usuari__username")
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        nq = normalize_search_term(q)
        qs = qs.annotate(
            _user_norm=unaccent_field("usuari__username"),
            _email_norm=unaccent_field("usuari__email"),
            _nom_norm=unaccent_field("nom_public"),
        ).filter(
            Q(_user_norm__contains=nq)
            | Q(_email_norm__contains=nq)
            | Q(_nom_norm__contains=nq)
        )
    visible = request.GET.get("visible", "")
    if visible == "1":
        qs = qs.filter(visible_directori=True)
    elif visible == "0":
        qs = qs.filter(visible_directori=False)

    try:
        per_page = min(int(request.GET.get("per_page") or 30), 100)
    except ValueError:
        per_page = 30
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(request.GET.get("page") or 1)
    rows = []
    for p in page.object_list:
        loc = p.localitat
        rows.append(
            {
                "usuari_id": p.usuari_id,
                "username": p.usuari.username,
                "email": p.usuari.email,
                "nom_public": p.nom_public,
                "rol_musical": p.rol_musical,
                "obert_colaboracions": p.obert_colaboracions,
                "visible_directori": p.visible_directori,
                "onboarding_complet": p.onboarding_complet,
                "localitat": (
                    f"{loc.nom}, {loc.comarca} ({loc.territori_id})" if loc else ""
                ),
                "n_publicacions": p.n_publicacions,
                "is_staff": p.usuari.is_staff,
                "is_active": p.usuari.is_active,
            }
        )
    return Response(
        {
            "results": rows,
            "page": page.number,
            "num_pages": paginator.num_pages,
            "total": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
        }
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def staff_directori_toggle_visible(request: Request, usuari_id: int) -> Response:
    p = get_object_or_404(PerfilUsuari, usuari_id=usuari_id)
    p.visible_directori = not p.visible_directori
    p.save(update_fields=["visible_directori", "updated_at"])
    return Response({"usuari_id": usuari_id, "visible_directori": p.visible_directori})


# ═════════════════════════════════════════════════════════════════════════
# Image upload — shared by publication editor + profile photo
# ═════════════════════════════════════════════════════════════════════════


# Max bytes per upload. 5 MB covers a decent JPEG at 3000×2000 after
# resize; more than that is almost always an un-optimized source.
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024

# Per-user quota on `publicacions/` folder to keep disk bounded.
_MAX_PER_USER_BYTES = 20 * 1024 * 1024

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Max width after resize. Taller images keep their aspect ratio.
_MAX_WIDTH = {"publicacio": 1600, "perfil": 600}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_imatge(request: Request) -> Response:
    """Accept one image upload, resize it, store under MEDIA_ROOT.

    Form fields:
      * `fitxer` (required) — the image file.
      * `kind`   (optional, default "publicacio") — one of
                 {"publicacio", "perfil"}; picks target dir and max width.

    Returns `{"url": "/media/..."}` suitable for `imatge_url` fields or
    markdown `![](url)` inserts.
    """
    import io
    import uuid
    from pathlib import Path

    from django.conf import settings
    from PIL import Image, UnidentifiedImageError

    f = request.FILES.get("fitxer")
    if not f:
        return Response({"error": "Falta el fitxer."}, status=400)
    if f.size > _MAX_UPLOAD_BYTES:
        return Response(
            {"error": f"Màxim {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB per imatge."},
            status=400,
        )
    if f.content_type not in _ALLOWED_CONTENT_TYPES:
        return Response(
            {"error": "Tipus no permès. Només JPEG, PNG o WebP."}, status=400
        )

    kind = request.POST.get("kind", "publicacio")
    if kind not in _MAX_WIDTH:
        return Response({"error": "kind invàlid."}, status=400)

    # Per-user disk quota for publicacions (profile photos overwrite so
    # they don't accumulate).
    if kind == "publicacio":
        user_dir = Path(settings.MEDIA_ROOT) / "publicacions" / str(request.user.pk)
        if user_dir.exists():
            used = sum(p.stat().st_size for p in user_dir.rglob("*") if p.is_file())
            if used + f.size > _MAX_PER_USER_BYTES:
                return Response(
                    {
                        "error": (
                            "Quota d'imatges superada "
                            f"({_MAX_PER_USER_BYTES // (1024 * 1024)} MB). "
                            "Esborra'n alguna o enllaça imatges externes."
                        )
                    },
                    status=400,
                )
    else:
        user_dir = Path(settings.MEDIA_ROOT) / "perfil" / str(request.user.pk)
    user_dir.mkdir(parents=True, exist_ok=True)

    try:
        img = Image.open(f)
        img.load()  # force read so exceptions surface here, not later
    except (UnidentifiedImageError, OSError):
        return Response({"error": "El fitxer no és una imatge vàlida."}, status=400)

    # Normalize: convert to RGB for JPEG, strip EXIF, resize if wider
    # than the target. Square-crop profile photos to a tidy 1:1.
    max_w = _MAX_WIDTH[kind]
    if kind == "perfil":
        # Square-center-crop, then resize.
        s = min(img.width, img.height)
        left = (img.width - s) // 2
        top = (img.height - s) // 2
        img = img.crop((left, top, left + s, top + s))
        if img.width > max_w:
            img = img.resize((max_w, max_w), Image.Resampling.LANCZOS)
    elif img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.Resampling.LANCZOS)

    # Always save as JPEG (smaller than PNG for photos, no transparency
    # needed for either use case).
    if img.mode in ("RGBA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    filename = f"{uuid.uuid4().hex}.jpg"
    dest = user_dir / filename
    img.save(dest, format="JPEG", quality=85, optimize=True)

    # Build a canonical absolute URL so it satisfies URLField validators
    # (HTTP_ONLY_URL) when stored on PerfilUsuari.imatge_url. Caddy
    # serves /media/* directly off disk.
    rel = dest.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
    url = request.build_absolute_uri(f"{settings.MEDIA_URL}{rel}")
    return Response({"url": url})


# ═════════════════════════════════════════════════════════════════════════
# Missatgeria interna
# ═════════════════════════════════════════════════════════════════════════


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
    """
    import logging

    from django.core.mail import send_mail
    from django.template.loader import render_to_string

    logger = logging.getLogger(__name__)
    dest = msg.destinatari
    if not dest.email:
        return
    perfil = getattr(dest, "perfil", None)
    if perfil and not perfil.notificar_missatges_email:
        return

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
        send_mail(ctx["subject"], text, None, [dest.email], html_message=html)
    except Exception:
        logger.exception("Failed to send message notification to %s", dest.email)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def missatges_inbox(request: Request) -> Response:
    """Conversation list: latest message per other user, with unread counter."""
    viewer = request.user

    # Aggregate per "altre usuari": most recent message timestamp + unread count.
    from comptes.models import Missatge

    qs = Missatge.objects.filter(
        Q(remitent=viewer) | Q(destinatari=viewer)
    ).select_related("remitent__perfil", "destinatari__perfil")

    per_altre: dict[int, dict] = {}
    for m in qs.order_by("-created_at"):
        other_id = m.remitent_id if m.destinatari_id == viewer.pk else m.destinatari_id
        if other_id is None or other_id == viewer.pk:
            continue
        slot = per_altre.get(other_id)
        if slot is None:
            other = m.remitent if m.destinatari_id == viewer.pk else m.destinatari
            slot = {
                "altre": {
                    "pk": other.pk,
                    "username": other.username,
                    "nom_public": getattr(
                        getattr(other, "perfil", None), "nom_public", ""
                    ),
                    "imatge_url": getattr(
                        getattr(other, "perfil", None), "imatge_url", ""
                    ),
                },
                "darrer_missatge": _serialize_missatge(m, viewer),
                "no_llegits": 0,
            }
            per_altre[other_id] = slot
        # Count unread (only incoming + not yet read).
        if m.destinatari_id == viewer.pk and m.llegit_at is None:
            slot["no_llegits"] += 1

    converses = sorted(
        per_altre.values(),
        key=lambda x: x["darrer_missatge"]["created_at"] or "",
        reverse=True,
    )
    return Response(
        {
            "results": converses,
            "no_llegits_total": sum(c["no_llegits"] for c in converses),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def missatges_amb_usuari(request: Request, altre_pk: int) -> Response:
    """Thread of messages exchanged with `altre_pk`, oldest → newest.

    Marks all incoming-from-altre as read as a side effect.
    """
    from django.utils import timezone

    from comptes.models import Missatge
    from comptes.models import Usuari as _U

    viewer = request.user
    altre = get_object_or_404(_U, pk=altre_pk)
    if altre.pk == viewer.pk:
        return Response({"error": "No pots xatejar amb tu mateix."}, status=400)

    qs = (
        Missatge.objects.filter(
            (Q(remitent=viewer) & Q(destinatari=altre))
            | (Q(remitent=altre) & Q(destinatari=viewer))
        )
        .select_related("remitent__perfil", "destinatari__perfil")
        .order_by("created_at")
    )
    msgs = list(qs)
    Missatge.objects.filter(
        remitent=altre, destinatari=viewer, llegit_at__isnull=True
    ).update(llegit_at=timezone.now())

    return Response(
        {
            "altre": {
                "pk": altre.pk,
                "username": altre.username,
                "nom_public": getattr(getattr(altre, "perfil", None), "nom_public", ""),
                "imatge_url": getattr(getattr(altre, "perfil", None), "imatge_url", ""),
            },
            "missatges": [_serialize_missatge(m, viewer) for m in msgs],
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def missatge_crear(request: Request) -> Response:
    """Send a new message. Body: `{destinatari_pk, assumpte, cos}`."""
    from comptes.models import Missatge
    from comptes.models import Usuari as _U

    viewer = request.user
    data = request.data or {}
    try:
        dest_pk = int(data.get("destinatari_pk"))
    except (TypeError, ValueError):
        return Response({"error": "Destinatari invàlid."}, status=400)
    if dest_pk == viewer.pk:
        return Response(
            {"error": "No pots enviar-te un missatge a tu mateix."}, status=400
        )
    destinatari = get_object_or_404(_U, pk=dest_pk)
    cos = (data.get("cos") or "").strip()
    if not cos:
        return Response({"error": "El missatge no pot estar buit."}, status=400)
    if len(cos) > 10000:
        return Response({"error": "Màxim 10 000 caràcters."}, status=400)
    assumpte = (data.get("assumpte") or "")[:200]

    m = Missatge.objects.create(
        remitent=viewer,
        destinatari=destinatari,
        assumpte=assumpte,
        cos=cos,
    )
    _enviar_notificacio_missatge(request, m)
    return Response(_serialize_missatge(m, viewer), status=201)


# ═════════════════════════════════════════════════════════════════════════
# Comentaris a publicacions
# ═════════════════════════════════════════════════════════════════════════


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


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def publicacio_comentaris(request: Request, pk: int) -> Response:
    """List + create comments for a publication. List is public-ish
    (requires auth same as the containing post); create is authenticated."""
    pub = get_object_or_404(Publicacio, pk=pk)
    # Only allow comments on posts the viewer can see.
    if pub.estat != Publicacio.ESTAT_PUBLICAT:
        if not (request.user.is_staff or request.user.pk == pub.autor_id):
            return Response({"error": "Publicació no disponible."}, status=404)

    from comptes.models import Comentari

    if request.method == "GET":
        rows = list(
            pub.comentaris.select_related("autor__perfil").order_by("created_at")
        )
        return Response([_serialize_comentari(c) for c in rows])

    cos = (request.data.get("cos") or "").strip()
    if not cos:
        return Response({"error": "El comentari no pot estar buit."}, status=400)
    if len(cos) > 2000:
        return Response({"error": "Màxim 2 000 caràcters."}, status=400)

    c = Comentari.objects.create(publicacio=pub, autor=request.user, cos=cos)
    _enviar_notificacio_comentari(request, c)
    return Response(_serialize_comentari(c), status=201)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def comentari_esborrar(request: Request, pk: int) -> Response:
    from comptes.models import Comentari

    c = get_object_or_404(Comentari, pk=pk)
    # Author, post owner or staff can delete.
    if not (
        request.user.is_staff
        or request.user.pk == c.autor_id
        or request.user.pk == c.publicacio.autor_id
    ):
        return Response({"error": "No autoritzat."}, status=403)
    c.delete()
    return Response(status=204)


def _enviar_notificacio_comentari(request, comentari) -> None:
    """Tell the post author someone commented on their publication.

    Skipped if the commenter IS the author (no self-pings), if the
    author opted out or lacks an email.
    """
    import logging

    from django.core.mail import send_mail
    from django.template.loader import render_to_string

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
