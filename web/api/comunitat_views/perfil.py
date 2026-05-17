"""PerfilUsuari endpoints: own profile, public directori, image upload."""

from __future__ import annotations

from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import PerfilUsuari, UserArtista
from music.models import Municipi
from web.api.search_utils import normalize_search_term, unaccent_field
from web.api.utils import paginate

from ._common import _clean_url, _serialize_perfil


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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def directori(request: Request) -> Response:
    """Public-to-registered-users directory.

    Filters: q (name/username/instruments), rol, obert_colaboracions,
    territori (by localitat.municipi.territori). Page size 30.

    Staff users see EVERY active profile, including those with
    `visible_directori=False`. This is so admins can reach users for
    one-on-one moderation correspondence without forcing the user to
    self-publish (Fase 1.5.B partial, 2026-05-17). The user's privacy
    preference is preserved: non-staff viewers still only see
    `visible_directori=True` rows, and the response surfaces
    `visible_directori` per row so the SPA can flag non-public
    profiles distinctly in the staff view.
    """
    base = PerfilUsuari.objects.filter(usuari__is_active=True)
    if not request.user.is_staff:
        base = base.filter(visible_directori=True)
    qs = base.select_related(
        "usuari", "localitat", "localitat__territori"
    ).prefetch_related("usuari__artistes_vinculats__artista")
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

    page, meta = paginate(qs, request, default=30, cap=100)

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
                # Surfaced unconditionally so the SPA can render a
                # "perfil no públic" badge in the staff view; for
                # non-staff viewers it's always True (filtered above).
                "visible_directori": p.visible_directori,
            }
        )

    return Response(
        {"results": rows, **meta, "rol_choices": list(PerfilUsuari.ROL_CHOICES)}
    )


# ─── Image upload (shared by publication editor + profile photo) ─────────


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
    # NB: `f.content_type` is the browser-supplied header; trivially
    # spoofable. We use it as a fast rejection but the authoritative
    # check is Pillow's `img.format` after load (below). May-2026
    # audit fix.
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

    # Authoritative format check via Pillow's auto-detection.
    # Defends against polyglot uploads where the client lies in
    # `content_type` but the actual binary is e.g. an SVG with
    # JS or a weaponised file disguised as an image.
    if img.format not in {"JPEG", "PNG", "WEBP"}:
        return Response(
            {"error": f"Format detectat invàlid: {img.format}."}, status=400
        )

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
