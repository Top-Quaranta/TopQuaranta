"""Sprint Portal Artista Ampliat — slug-based manager endpoints.

Surface for the new `/compte/artista/<slug>/` portal: the dashboard
quality view, the extended editor (incl. image / M2M management), and
the per-artist ping-staff for unverified songs.

Permission model: every endpoint resolves the artist by slug and runs
through `_gestor_check(request, artista_pk)` from the legacy
`propostes.py` module so the auth contract stays identical to the
existing `/compte/artista/<int:pk>/editar/` endpoint.
"""

from __future__ import annotations

from datetime import timedelta

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import HTTP_ONLY_URL, Usuari
from music.models import (
    Artista,
    ArtistaDeezer,
    ArtistaLastfmAlias,
    ArtistaLocalitat,
    Municipi,
)

from .propostes import (
    GESTOR_EDITABLE_CHOICE_FIELDS,
    GESTOR_EDITABLE_TEXT_FIELDS,
    GESTOR_EDITABLE_URL_FIELDS,
    _clean_url,
    _gestor_check,
    _serialize_gestor_artista,
)

PING_COOLDOWN = timedelta(days=7)


# ───────────────────────── slug resolver ──────────────────────────


def _resolve_or_403(request, slug: str):
    """Look up the artist by slug, then run the manager check.

    Returns the `Artista` instance on success, or a DRF `Response`
    (404/403) on failure — the same pattern as `_gestor_check`."""
    artista = Artista.objects.filter(slug=slug).first()
    if artista is None:
        return Response({"error": "Artista no trobat."}, status=404)
    return _gestor_check(request, artista.pk)


# ───────────────────────── editar (slug) ──────────────────────────


def _serialize_gestor_artista_full(a: Artista) -> dict:
    """Editor snapshot — extends the legacy `_serialize_gestor_artista`
    with the manager-controlled image, M2M lists, and the prioritari
    alias name (mirror of `Artista.lastfm_nom`)."""
    base = _serialize_gestor_artista(a)
    base["imatge_url"] = a.imatge_url or ""
    base["deezer_ids"] = [
        {"pk": d.pk, "deezer_id": d.deezer_id, "principal": d.principal}
        for d in a.deezer_ids.order_by("-principal", "deezer_id")
    ]
    base["lastfm_aliases"] = [
        {
            "pk": al.pk,
            "nom": al.nom,
            "confirmat": al.confirmat,
            "rebutjat": al.rebutjat,
            "prioritari": al.prioritari,
        }
        for al in a.lastfm_aliases.order_by("-prioritari", "-confirmat", "nom")
    ]
    base["localitats"] = [
        {
            "pk": loc.pk,
            "municipi_pk": loc.municipi_id,
            "nom": loc.nom_display,
            "comarca": loc.comarca_display,
            "territori": loc.territori_display,
            "descripcio": loc.descripcio,
        }
        for loc in a.localitats.select_related("municipi", "municipi__territori")
    ]
    base["ultim_ping_revisio_at"] = (
        a.ultim_ping_revisio_at.isoformat() if a.ultim_ping_revisio_at else None
    )
    return base


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def editar(request: Request, slug: str) -> Response:
    """GET snapshot / PATCH editable fields. Mirror of the legacy
    `gestor_artista_editar` PK endpoint but slug-routed and with the
    extra surface (image + M2M lists in the snapshot)."""
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    if request.method == "GET":
        return Response(_serialize_gestor_artista_full(artista))

    data = request.data or {}
    errors: dict[str, str] = {}
    valid_choices = {v for v, _ in Artista.PERCENTATGE_FEMENI_CHOICES}
    canviats: list[str] = []

    for f in GESTOR_EDITABLE_TEXT_FIELDS:
        if f not in data:
            continue
        new = (data.get(f) or "").strip()
        if getattr(artista, f, "") != new:
            setattr(artista, f, new)
            canviats.append(f)

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

    # New: manager-uploaded hero image. Pipeline produced an absolute
    # URL under MEDIA_URL; we trust it since the upload endpoint
    # already ran `_gestor_check` for kind="artista".
    if "imatge_url" in data:
        raw = (data.get("imatge_url") or "").strip()
        if raw:
            try:
                HTTP_ONLY_URL(raw)
            except ValidationError:
                errors["imatge_url"] = "URL no vàlida (només http/https)."
        if "imatge_url" not in errors and artista.imatge_url != raw:
            artista.imatge_url = raw
            canviats.append("imatge_url")

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
        {"ok": True, "canviats": canviats, **_serialize_gestor_artista_full(artista)}
    )


# ───────────────────────── qualitat ───────────────────────────────


def _indicator(key, label, severity, message, cta=None):
    out = {"key": key, "label": label, "severity": severity, "message": message}
    if cta:
        out["cta"] = cta
    return out


def _compute_qualitat(artista: Artista) -> dict:
    """The 9 dashboard indicators + the rolled-up score.

    Each indicator is one of:
      * `success` — no action needed, counts toward the score.
      * `warning` — partial / actionable but not blocking.
      * `danger`  — missing critical data; counts as 0 toward score.

    Score = round(sum(success) / total * 100).
    `n_alerts` = count of non-success entries (warning + danger), used
    by the ArtistaCard pill in fase D."""
    indicators: list[dict] = []

    # 1. Deezer vinculat
    n_deezer = artista.deezer_ids.count()
    indicators.append(
        _indicator(
            "deezer_vinculat",
            "Deezer vinculat",
            "success" if n_deezer >= 1 else "danger",
            (
                f"{n_deezer} Deezer ID{'s' if n_deezer != 1 else ''} actiu."
                if n_deezer
                else "No hi ha cap Deezer ID. Sense Deezer no ingestem cap "
                "cançó nova."
            ),
            cta=None if n_deezer else {"href": "#deezer-ids", "label": "Afegir-ne un"},
        )
    )

    # 2. Deezer net — 0 rebuigs album_incorrecte sobre les seves cançons
    from music.models import HistorialRevisio

    n_rebutjats = HistorialRevisio.objects.filter(
        artista_nom=artista.nom,
        decisio="rebutjada",
        motiu="album_incorrecte",
    ).count()
    indicators.append(
        _indicator(
            "deezer_net",
            "Deezer net (sense rebuigs «àlbum incorrecte»)",
            "success" if n_rebutjats == 0 else "warning",
            (
                "Cap rebuig per «àlbum incorrecte»."
                if n_rebutjats == 0
                else f"{n_rebutjats} cançó/ns rebutjades per «àlbum incorrecte». "
                "Sol indicar col·lisió de noms a Deezer."
            ),
        )
    )

    # 3. Deezer profile únic — un sol source_deezer_id als albums
    from music.models import Album

    distinct_sources = (
        Album.objects.filter(cancons__artista=artista, source_deezer_id__isnull=False)
        .values_list("source_deezer_id", flat=True)
        .distinct()
        .count()
    )
    indicators.append(
        _indicator(
            "deezer_unique",
            "Un sol perfil Deezer als àlbums",
            "success" if distinct_sources <= 1 else "warning",
            (
                "Tots els àlbums vénen del mateix perfil Deezer."
                if distinct_sources <= 1
                else f"Els àlbums vénen de {distinct_sources} perfils Deezer "
                "diferents. Verifica si cal fusionar o separar artistes."
            ),
        )
    )

    # 4. MusicBrainz present
    has_mbid = bool(artista.musicbrainz_id)
    indicators.append(
        _indicator(
            "mb_present",
            "MusicBrainz vinculat",
            "success" if has_mbid else "danger",
            (
                f"MBID {artista.musicbrainz_id}."
                if has_mbid
                else "Sense MBID. MusicBrainz desambigua col·lisions de nom."
            ),
            cta=(
                None
                if has_mbid
                else {
                    "href": "https://musicbrainz.org/artist/create",
                    "label": "Crear a MusicBrainz",
                    "external": True,
                }
            ),
        )
    )

    # 5. MB info completa (mb_area + mb_begin_date + mb_type)
    if has_mbid:
        mb_complete_parts = sum(
            1 for v in (artista.mb_area, artista.mb_begin_date, artista.mb_type) if v
        )
        if mb_complete_parts == 3:
            sev, msg = "success", "Àrea, data d'inici i tipus omplerts."
        elif mb_complete_parts >= 1:
            sev, msg = (
                "warning",
                f"{mb_complete_parts}/3 camps clau (àrea / data inici / tipus) "
                "omplerts a MusicBrainz.",
            )
        else:
            sev, msg = "danger", "MBID present però sense àrea, data ni tipus."
    else:
        sev, msg = (
            "danger",
            "Sense MBID, no podem mostrar metadades de MusicBrainz.",
        )
    indicators.append(
        _indicator("mb_complete", "Metadades MusicBrainz completes", sev, msg)
    )

    # 6. MB cançons mapejades — % verificades amb mb_recording_id
    from music.models import Canco

    cancons_v = Canco.objects.filter(artista=artista, verificada=True, activa=True)
    total_v = cancons_v.count()
    if total_v == 0:
        sev, msg = (
            "warning",
            "Encara no hi ha cap cançó verificada per a aquest artista.",
        )
    else:
        mapped = cancons_v.exclude(mb_recording_id="").count()
        pct = round(mapped / total_v * 100)
        if pct == 100:
            sev, msg = "success", f"100% ({mapped}/{total_v}) cançons amb MBID."
        elif pct >= 50:
            sev, msg = "warning", f"{pct}% ({mapped}/{total_v}) cançons amb MBID."
        else:
            sev, msg = "danger", f"Només {pct}% ({mapped}/{total_v}) cançons amb MBID."
    indicators.append(
        _indicator("mb_cancons_mapejades", "Cançons mapejades a MusicBrainz", sev, msg)
    )

    # 7. Last.fm URL present
    has_lastfm_url = bool(artista.lastfm_url)
    indicators.append(
        _indicator(
            "lastfm_url",
            "Last.fm URL vinculada",
            "success" if has_lastfm_url else "warning",
            (
                "Perfil de Last.fm enllaçat."
                if has_lastfm_url
                else "Sense URL de Last.fm. Afegeix-la per facilitar la verificació."
            ),
            cta=(
                None
                if has_lastfm_url
                else {"href": "#lastfm-aliases", "label": "Editar"}
            ),
        )
    )

    # 8. Last.fm senyal — % verificades amb playcount>0 als últims 30 dies.
    # SenyalDiari té (canco, data, lastfm_playcount). Considerem "té
    # senyal" si hi ha alguna fila amb lastfm_playcount>0 dins de la
    # finestra.
    from ranking.models import SenyalDiari

    since = timezone.now().date() - timedelta(days=30)
    if total_v == 0:
        sev8, msg8 = "warning", "No hi ha cançons verificades per mesurar el senyal."
    else:
        cancons_amb_senyal = (
            SenyalDiari.objects.filter(
                canco__artista=artista,
                canco__verificada=True,
                canco__activa=True,
                data__gte=since,
                lastfm_playcount__gt=0,
            )
            .values_list("canco_id", flat=True)
            .distinct()
            .count()
        )
        pct = round(cancons_amb_senyal / total_v * 100)
        if pct == 100:
            sev8, msg8 = (
                "success",
                f"Totes les cançons ({total_v}) tenen senyal Last.fm dels últims 30 dies.",
            )
        elif pct > 0:
            sev8, msg8 = (
                "warning",
                f"{cancons_amb_senyal}/{total_v} cançons amb senyal Last.fm (30d).",
            )
        else:
            sev8, msg8 = (
                "danger",
                "Cap cançó verificada ha rebut senyal Last.fm els últims 30 dies.",
            )
    indicators.append(_indicator("lastfm_senyal", "Senyal Last.fm actiu", sev8, msg8))

    # 9. Perfil intern % complet (bio + genere_canonical + percentatge_femeni
    # + localitat + ≥1 social).
    n_socials = sum(1 for f, _ in Artista.SOCIAL_LINK_FIELDS if getattr(artista, f))
    has_localitat = artista.localitats.exists()
    parts = [
        bool(artista.bio),
        bool(artista.genere_canonical),
        bool(artista.percentatge_femeni),
        has_localitat,
        n_socials >= 1,
    ]
    n_ok = sum(parts)
    pct_perfil = round(n_ok / len(parts) * 100)
    if pct_perfil == 100:
        sev9, msg9 = "success", "Perfil 100 % complet."
    elif pct_perfil >= 60:
        sev9, msg9 = (
            "warning",
            f"Perfil {pct_perfil} % complet ({n_ok}/{len(parts)} camps).",
        )
    else:
        sev9, msg9 = (
            "danger",
            f"Perfil {pct_perfil} % complet ({n_ok}/{len(parts)} camps).",
        )
    indicators.append(_indicator("perfil_intern", "Perfil intern complet", sev9, msg9))

    n_total = len(indicators)
    n_success = sum(1 for ind in indicators if ind["severity"] == "success")
    n_alerts = n_total - n_success
    score = round(n_success / n_total * 100)
    return {"score": score, "n_alerts": n_alerts, "indicators": indicators}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def qualitat(request: Request, slug: str) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    return Response(_compute_qualitat(result))


# ───────────────────────── Deezer IDs (M2M) ───────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def deezer_id_add(request: Request, slug: str) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    try:
        deezer_id = int((request.data or {}).get("deezer_id") or 0)
    except (TypeError, ValueError):
        return Response({"error": "Deezer ID invàlid."}, status=400)
    if deezer_id <= 0:
        return Response({"error": "Deezer ID invàlid."}, status=400)

    if ArtistaDeezer.objects.filter(artista=artista, deezer_id=deezer_id).exists():
        return Response(
            {"error": "Aquest Deezer ID ja està vinculat a aquest artista."},
            status=400,
        )
    # Global uniqueness — Deezer IDs are unique across the whole table.
    if ArtistaDeezer.objects.filter(deezer_id=deezer_id).exists():
        return Response(
            {"error": "Aquest Deezer ID ja està assignat a un altre artista."},
            status=400,
        )

    # Liveness check — Deezer /artist/<id> must respond. We do the
    # network call last so we don't burn API budget on duplicates. The
    # call is cheap (single GET, ~80ms) and the public Deezer API has no
    # auth requirement.
    try:
        r = requests.get(f"https://api.deezer.com/artist/{deezer_id}", timeout=5)
        r.raise_for_status()
        body = r.json()
        if body.get("error"):
            return Response(
                {"error": f"Deezer no reconeix l'ID {deezer_id}."}, status=400
            )
    except requests.RequestException:
        return Response(
            {"error": "No s'ha pogut verificar contra Deezer ara mateix."},
            status=502,
        )

    ArtistaDeezer.objects.create(artista=artista, deezer_id=deezer_id, principal=False)
    return Response({"ok": True, "deezer_id": deezer_id}, status=201)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def deezer_id_delete(request: Request, slug: str, dz_id: int) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    row = ArtistaDeezer.objects.filter(artista=artista, deezer_id=dz_id).first()
    if row is None:
        return Response({"error": "Aquest Deezer ID no està vinculat."}, status=404)
    if artista.deezer_ids.count() <= 1:
        return Response(
            {
                "error": (
                    "No pots esborrar l'únic Deezer ID. Afegeix-ne un altre " "primer."
                )
            },
            status=400,
        )
    row.delete()
    return Response({"ok": True})


# ───────────────────────── Last.fm aliases (M2M) ──────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def lastfm_alias_add(request: Request, slug: str) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    nom = ((request.data or {}).get("nom") or "").strip()
    if not nom:
        return Response({"error": "El nom no pot estar buit."}, status=400)
    if len(nom) > 255:
        return Response({"error": "Màxim 255 caràcters."}, status=400)
    # Case-insensitive duplicate check (the unique constraint is
    # case-sensitive so this catches typographic-only diffs upfront).
    if ArtistaLastfmAlias.objects.filter(artista=artista, nom__iexact=nom).exists():
        return Response(
            {"error": "Aquest alias ja existeix per a aquest artista."}, status=400
        )

    alias = ArtistaLastfmAlias.objects.create(
        artista=artista,
        nom=nom,
        confirmat=True,
        confirmat_at=timezone.now(),
        confirmat_per=request.user,
        prioritari=False,
    )
    return Response(
        {
            "ok": True,
            "pk": alias.pk,
            "nom": alias.nom,
            "confirmat": True,
            "prioritari": False,
        },
        status=201,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def lastfm_alias_delete(request: Request, slug: str, alias_id: int) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    alias = ArtistaLastfmAlias.objects.filter(pk=alias_id, artista=artista).first()
    if alias is None:
        return Response({"error": "Alias no trobat."}, status=404)

    # Block deletion of the prioritari if there are other confirmed
    # aliases — the manager must promote another row first so the
    # mirror (`Artista.lastfm_nom`) doesn't silently clear and stop
    # the signal collector. If this row is the only one, allow the
    # delete (the artist loses Last.fm coverage; that's a deliberate
    # choice the manager is taking).
    if alias.prioritari and artista.lastfm_aliases.exclude(pk=alias.pk).exists():
        return Response(
            {
                "error": (
                    "No pots esborrar l'alias prioritari quan n'hi ha d'altres. "
                    "Marca'n un com a prioritari abans d'esborrar aquest."
                )
            },
            status=400,
        )

    alias.delete()
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def lastfm_alias_set_prioritari(request: Request, slug: str, alias_id: int) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    alias = ArtistaLastfmAlias.objects.filter(pk=alias_id, artista=artista).first()
    if alias is None:
        return Response({"error": "Alias no trobat."}, status=404)
    if not alias.confirmat:
        return Response(
            {"error": "Només es pot promoure un alias confirmat."}, status=400
        )

    # The signal layer enforces partial-unique. We demote others
    # explicitly first to avoid a transient state where two rows are
    # prioritari=True (the partial unique would block the second save
    # anyway, but doing it in one atomic block is cleaner).
    with transaction.atomic():
        ArtistaLastfmAlias.objects.filter(artista=artista, prioritari=True).exclude(
            pk=alias.pk
        ).update(prioritari=False)
        alias.prioritari = True
        alias.save(update_fields=["prioritari"])

    return Response({"ok": True, "pk": alias.pk, "nom": alias.nom})


# ───────────────────────── Localitats (M2M) ───────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def localitat_add(request: Request, slug: str) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    data = request.data or {}
    descripcio = (data.get("descripcio") or "").strip()[:255]
    municipi_pk_raw = data.get("municipi_pk")
    manual = (data.get("manual") or "").strip()

    if municipi_pk_raw:
        try:
            municipi = Municipi.objects.get(pk=int(municipi_pk_raw))
        except (TypeError, ValueError, Municipi.DoesNotExist):
            return Response({"error": "Municipi no trobat."}, status=400)
        if ArtistaLocalitat.objects.filter(artista=artista, municipi=municipi).exists():
            return Response(
                {"error": "Aquest municipi ja està associat a l'artista."},
                status=400,
            )
        loc = ArtistaLocalitat.objects.create(
            artista=artista, municipi=municipi, descripcio=descripcio
        )
    elif manual:
        if ArtistaLocalitat.objects.filter(
            artista=artista, municipi__isnull=True, localitat_manual__iexact=manual
        ).exists():
            return Response(
                {"error": "Aquesta localitat manual ja està associada."},
                status=400,
            )
        loc = ArtistaLocalitat.objects.create(
            artista=artista,
            municipi=None,
            localitat_manual=manual[:255],
            descripcio=descripcio,
        )
    else:
        return Response({"error": "Cal indicar `municipi_pk` o `manual`."}, status=400)

    return Response(
        {
            "ok": True,
            "pk": loc.pk,
            "nom": loc.nom_display,
            "comarca": loc.comarca_display,
            "territori": loc.territori_display,
        },
        status=201,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def localitat_delete(request: Request, slug: str, loc_id: int) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    loc = ArtistaLocalitat.objects.filter(pk=loc_id, artista=artista).first()
    if loc is None:
        return Response({"error": "Localitat no trobada."}, status=404)
    loc.delete()
    return Response({"ok": True})


# ───────────────────────── Cançons pendents + ping staff ──────────


def _serialize_canco_pendent(c) -> dict:
    return {
        "pk": c.pk,
        "slug": c.slug,
        "nom": c.nom,
        "album_nom": c.album.nom if c.album_id else "",
        "data_llancament": (
            c.data_llancament.isoformat() if c.data_llancament else None
        ),
    }


def _serialize_canco_rebutjada(h) -> dict:
    """Payload minim per a una fila de HistorialRevisio rebutjada.

    HistorialRevisio és un snapshot append-only: la `Canco` original
    pot estar esborrada, així que confiem en `canco_nom`, `album_nom`,
    `canco_isrc` i `canco_deezer_id` (denormalitzats al moment del
    rebuig)."""
    return {
        "pk": h.pk,
        "canco_nom": h.canco_nom,
        "album_nom": h.album_nom,
        "motiu": h.motiu,
        "data_rebuig": h.created_at.isoformat() if h.created_at else None,
        "canco_deezer_id": h.canco_deezer_id,
        "isrc": h.canco_isrc,
    }


def _query_cancons_rebutjades(artista, limit: int = 50):
    """HistorialRevisio rows matching any of this artist's Deezer IDs
    where the decision was «rebutjada». Ordered by date desc."""
    from music.models import HistorialRevisio

    deezer_ids = list(artista.deezer_ids.values_list("deezer_id", flat=True))
    if not deezer_ids:
        return HistorialRevisio.objects.none()
    return HistorialRevisio.objects.filter(
        artista_deezer_id__in=deezer_ids,
        decisio="rebutjada",
    ).order_by("-created_at")[:limit]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cancons_pendents(request: Request, slug: str) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    from music.models import Canco

    pendents = (
        Canco.objects.filter(artista=artista, verificada=False, activa=True)
        .select_related("album")
        .order_by("-data_llancament", "nom")
    )
    rebutjades = _query_cancons_rebutjades(artista)
    # Verified tracks (`verificada=True, activa=True`). Same shape as
    # pendents so the SPA can reuse the row renderer. Capped at 50
    # recents (desc by `data_llancament`) — established artists can
    # have hundreds and the panel is informational, not actionable.
    verificades = (
        Canco.objects.filter(artista=artista, verificada=True, activa=True)
        .select_related("album")
        .order_by("-data_llancament", "nom")[:50]
    )
    n_verificades_total = Canco.objects.filter(
        artista=artista, verificada=True, activa=True
    ).count()

    next_ping = None
    if artista.ultim_ping_revisio_at:
        next_ping = (artista.ultim_ping_revisio_at + PING_COOLDOWN).isoformat()
    return Response(
        {
            # Legacy key — the SPA reads `pendents` for the new tab
            # layout; `results` stays for any pre-quick-fixes client.
            "results": [_serialize_canco_pendent(c) for c in pendents],
            "pendents": [_serialize_canco_pendent(c) for c in pendents],
            "rebutjades": [_serialize_canco_rebutjada(h) for h in rebutjades],
            "verificades": [_serialize_canco_pendent(c) for c in verificades],
            "n_verificades_total": n_verificades_total,
            "cooldown_until": next_ping,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancons_pendents_ping_staff(request: Request, slug: str) -> Response:
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    # Cooldown guard — 7 days between pings. We compute Retry-After in
    # seconds so the SPA can render a friendly "Pròxim ping disponible
    # el DD/MM/AAAA" tooltip without a second round-trip.
    now = timezone.now()
    if artista.ultim_ping_revisio_at:
        elapsed = now - artista.ultim_ping_revisio_at
        if elapsed < PING_COOLDOWN:
            remaining = PING_COOLDOWN - elapsed
            resp = Response(
                {
                    "error": (
                        "Cooldown actiu. Pots tornar a demanar revisió en "
                        f"{remaining.days} dies."
                    ),
                    "next_ping_at": (
                        artista.ultim_ping_revisio_at + PING_COOLDOWN
                    ).isoformat(),
                },
                status=429,
            )
            resp["Retry-After"] = str(int(remaining.total_seconds()))
            return resp

    from music.models import Canco, HistorialRevisio

    body = request.data or {}

    # Pendents — same `include_canco_ids` filter as before. Defaults
    # to ALL unverified.
    raw_ids = body.get("include_canco_ids") or []
    pendent_qs = Canco.objects.filter(
        artista=artista, verificada=False, activa=True
    ).select_related("album")
    if raw_ids:
        try:
            ids = [int(x) for x in raw_ids]
        except (TypeError, ValueError):
            return Response({"error": "IDs de cançons invàlids."}, status=400)
        pendent_qs = pendent_qs.filter(pk__in=ids)
    pendents = list(pendent_qs.order_by("-data_llancament", "nom"))

    # Rebutjades — opt-in via `include_rebutjada_historial_pks`
    # (canonical name, Sprint Workflow) or its legacy alias
    # `include_rebutjada_ids` (still emitted by the SPA at quick-fixes
    # rollout time). Both carry HistorialRevisio PKs.
    raw_reb_ids = (
        body.get("include_rebutjada_historial_pks")
        or body.get("include_rebutjada_ids")
        or []
    )
    kind = (body.get("kind") or "").strip()
    rebutjades_qs = _query_cancons_rebutjades(artista)
    if raw_reb_ids:
        try:
            reb_ids = [int(x) for x in raw_reb_ids]
        except (TypeError, ValueError):
            return Response({"error": "IDs de rebutjades invàlids."}, status=400)
        rebutjades_qs = HistorialRevisio.objects.filter(
            pk__in=reb_ids,
            decisio="rebutjada",
            artista_deezer_id__in=list(
                artista.deezer_ids.values_list("deezer_id", flat=True)
            ),
        ).order_by("-created_at")
    elif kind == "rebutjades":
        # Explicit "rebutjades only" → drop pendents from this ping.
        pendents = []
    else:
        # Default for the existing pendents-only call path: don't
        # include rebutjades unless the caller asked. Keeps the
        # legacy behaviour intact.
        rebutjades_qs = HistorialRevisio.objects.none()

    rebutjades = list(rebutjades_qs)

    if not pendents and not rebutjades:
        return Response(
            {"error": "No hi ha cançons per a demanar revisió."},
            status=400,
        )

    # Sprint Workflow Sol·licituds (2026-05-20): the per-row workflow
    # supersedes the old DM-to-admin ping. We create a `SolicitudRevisio`
    # row and send an email to staff with the workbench link. The DM
    # path (`Missatge` to the Admin pseudouser) is DEPRECATED — every
    # call site flows through this endpoint now.
    from comptes.models import SolicitudRevisio
    from comptes.notifications import notify_admins_nova_sollicitud_revisio

    total = len(pendents) + len(rebutjades)
    pendents_ids = [c.pk for c in pendents]
    rebutjades_snapshot = [
        {
            "historial_pk": h.pk,
            "deezer_id": h.canco_deezer_id,
            "isrc": h.canco_isrc,
            "nom": h.canco_nom,
            "album_nom": h.album_nom,
            "motiu": h.motiu,
        }
        for h in rebutjades
    ]

    with transaction.atomic():
        sollicitud = SolicitudRevisio.objects.create(
            gestor=request.user,
            artista=artista,
            pendents_ids=pendents_ids,
            rebutjades_snapshot=rebutjades_snapshot,
        )
        artista.ultim_ping_revisio_at = now
        artista.save(update_fields=["ultim_ping_revisio_at"])

    # Best-effort: a mail-server hiccup shouldn't undo the row that
    # the gestor has already paid the cooldown for.
    try:
        notify_admins_nova_sollicitud_revisio(sollicitud)
    except Exception:  # noqa: BLE001
        pass

    from music.audit import log_staff_action

    log_staff_action(
        request,
        "sollicitud_revisio_creada",
        target=artista,
        sollicitud_pk=sollicitud.pk,
        n_pendents=len(pendents),
        n_rebutjades=len(rebutjades),
        usuari=request.user.pk,
    )
    return Response(
        {
            "ok": True,
            "sollicitud_pk": sollicitud.pk,
            "n_cancons": total,
            "n_pendents": len(pendents),
            "n_rebutjades": len(rebutjades),
            "next_ping_at": (now + PING_COOLDOWN).isoformat(),
        },
        status=201,
    )


# ───────────────────────── Sol·licituds (gestor side) ────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sollicituds_gestor(request: Request, slug: str) -> Response:
    """Summary of the artist's SolicitudRevisio history for the
    gestor's portal. Returns the latest row (any estat) + total
    count. Sprint Workflow Sol·licituds B.5."""
    result = _resolve_or_403(request, slug)
    if isinstance(result, Response):
        return result
    artista = result

    from comptes.models import SolicitudRevisio

    qs = SolicitudRevisio.objects.filter(artista=artista).order_by("-created_at")
    n_total = qs.count()
    ultima = qs.first()
    payload = {"n_total": n_total, "ultima": None}
    if ultima is not None:
        payload["ultima"] = {
            "pk": ultima.pk,
            "created_at": ultima.created_at.isoformat(),
            "estat": ultima.estat,
            "resolt_at": (ultima.resolt_at.isoformat() if ultima.resolt_at else None),
            "nota_resolucio": ultima.nota_resolucio or "",
            "n_pendents": ultima.n_pendents,
            "n_rebutjades": ultima.n_rebutjades,
        }
    return Response(payload)


# NOTE on B.6 (pk → slug redirect): the legacy
# `/api/v1/compte/artista/<int:pk>/editar/` endpoint is kept live by
# the existing `gestor_artista_editar` view in `propostes.py`. We do
# NOT 308-redirect it here because the in-flight SPA still calls it
# directly; once FASE C lands and the SPA switches to slug-based
# fetches we can deprecate it (or rewrite it as a redirect view).
