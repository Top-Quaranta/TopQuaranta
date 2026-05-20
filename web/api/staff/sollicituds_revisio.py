"""Staff workbench endpoints for `SolicitudRevisio` (Sprint Workflow
Sol·licituds, 2026-05-20).

Surface:
  GET    /api/v1/staff/sollicituds-revisio/                 — list
  GET    /api/v1/staff/sollicituds-revisio/<pk>/            — detail
  POST   /api/v1/staff/sollicituds-revisio/<pk>/reconsiderar-rebutjada/
  POST   /api/v1/staff/sollicituds-revisio/<pk>/marcar-en-revisio/
  POST   /api/v1/staff/sollicituds-revisio/<pk>/resoldre/

Permission: `IsStaff` (request.user.is_staff). The IsStaff class lives
in `web/api/staff/_common.py` and is reused across the workbench.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import SolicitudRevisio
from music.models import Canco, HistorialRevisio

from ._common import IsStaff


def _serialize_row(s: SolicitudRevisio) -> dict:
    """Compact payload for the list view."""
    return {
        "pk": s.pk,
        "artista": {"pk": s.artista_id, "nom": s.artista.nom, "slug": s.artista.slug},
        "gestor": {
            "pk": s.gestor_id,
            "username": s.gestor.username,
            "email": s.gestor.email,
        },
        "estat": s.estat,
        "n_pendents": s.n_pendents,
        "n_rebutjades": s.n_rebutjades,
        "created_at": s.created_at.isoformat(),
        "resolt_at": s.resolt_at.isoformat() if s.resolt_at else None,
    }


def _serialize_pendent_inflated(c: Canco) -> dict:
    """Inflate a Canco pk against the live DB for the detail view.

    Snapshot rows in `SolicitudRevisio.pendents_ids` may reference a
    Canco that's been deleted (rare but possible if staff hard-deletes
    between submission and resolution). The caller handles `None`
    misses by surfacing a "no trobada" marker."""
    return {
        "pk": c.pk,
        "slug": c.slug,
        "nom": c.nom,
        "album_nom": c.album.nom if c.album_id else "",
        "data_llancament": (
            c.data_llancament.isoformat() if c.data_llancament else None
        ),
        "verificada": c.verificada,
        "edit_url": f"/staff/cancons/{c.pk}",
    }


# ───────────────────────── LIST ──────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStaff])
def llistar(request: Request) -> Response:
    """List sol·licituds. Defaults to `estat=pendent`. Filters:
    `?estat=pendent|revisada|resolta`, `?artista_pk=<int>`. Paginated
    (20 per page) — workbench rarely has more than a few open."""
    estat = (request.GET.get("estat") or "pendent").strip()
    qs = SolicitudRevisio.objects.select_related("artista", "gestor")
    if estat in {c for c, _ in SolicitudRevisio.ESTAT_CHOICES}:
        qs = qs.filter(estat=estat)
    elif estat == "totes":
        # explicit "show me everything" escape hatch
        pass
    else:
        return Response({"error": "Estat invàlid."}, status=400)

    artista_pk = request.GET.get("artista_pk")
    if artista_pk:
        try:
            qs = qs.filter(artista_id=int(artista_pk))
        except (TypeError, ValueError):
            return Response({"error": "artista_pk invàlid."}, status=400)

    qs = qs.order_by("-created_at")
    page_num = max(1, int(request.GET.get("page", "1") or 1))
    paginator = Paginator(qs, 20)
    page = paginator.get_page(page_num)
    return Response(
        {
            "results": [_serialize_row(s) for s in page.object_list],
            "page": page.number,
            "n_pages": paginator.num_pages,
            "total": paginator.count,
            "n_pendents_total": SolicitudRevisio.objects.filter(
                estat=SolicitudRevisio.ESTAT_PENDENT
            ).count(),
        }
    )


# ───────────────────────── DETAIL ────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsStaff])
def detall(request: Request, pk: int) -> Response:
    s = get_object_or_404(
        SolicitudRevisio.objects.select_related("artista", "gestor", "resolt_per"),
        pk=pk,
    )
    # Inflate pendent Canco rows by pk; misses become {pk, missing:True}.
    by_id = Canco.objects.select_related("album").in_bulk(s.pendents_ids or [])
    pendents = []
    for pk_ in s.pendents_ids or []:
        c = by_id.get(pk_)
        if c is None:
            pendents.append({"pk": pk_, "missing": True})
        else:
            pendents.append(_serialize_pendent_inflated(c))

    # For rebutjades we use the snapshot directly (the original
    # HistorialRevisio may have been pruned or merged). We add a
    # `reconsiderada` flag by re-querying HistorialRevisio for the
    # historial_pks that still exist, so the workbench shows the
    # current state of the toggle.
    historial_pks = [
        r["historial_pk"]
        for r in (s.rebutjades_snapshot or [])
        if r.get("historial_pk")
    ]
    reconsiderada_state = dict(
        HistorialRevisio.objects.filter(pk__in=historial_pks).values_list(
            "pk", "reconsiderada"
        )
    )
    rebutjades = []
    for r in s.rebutjades_snapshot or []:
        hp = r.get("historial_pk")
        rebutjades.append(
            {
                **r,
                "reconsiderada": reconsiderada_state.get(hp, False),
                # If the original row is gone, mark it so the UI greys
                # out the "Reconsiderar" button.
                "historial_present": hp in reconsiderada_state if hp else False,
            }
        )

    return Response(
        {
            "pk": s.pk,
            "estat": s.estat,
            "created_at": s.created_at.isoformat(),
            "resolt_at": s.resolt_at.isoformat() if s.resolt_at else None,
            "resolt_per": (
                {"username": s.resolt_per.username} if s.resolt_per else None
            ),
            "nota_resolucio": s.nota_resolucio or "",
            "artista": {
                "pk": s.artista_id,
                "nom": s.artista.nom,
                "slug": s.artista.slug,
            },
            "gestor": {
                "pk": s.gestor_id,
                "username": s.gestor.username,
                "email": s.gestor.email,
            },
            "pendents": pendents,
            "rebutjades": rebutjades,
        }
    )


# ───────────────────────── ACTIONS ───────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStaff])
def marcar_en_revisio(request: Request, pk: int) -> Response:
    s = get_object_or_404(SolicitudRevisio, pk=pk)
    if s.estat == SolicitudRevisio.ESTAT_RESOLTA:
        return Response({"error": "Aquesta sol·licitud ja està resolta."}, status=400)
    if s.estat != SolicitudRevisio.ESTAT_REVISADA:
        s.estat = SolicitudRevisio.ESTAT_REVISADA
        s.save(update_fields=["estat"])
    return Response({"ok": True, "estat": s.estat})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStaff])
def reconsiderar_rebutjada(request: Request, pk: int) -> Response:
    s = get_object_or_404(SolicitudRevisio, pk=pk)
    data = request.data or {}
    try:
        historial_pk = int(data.get("historial_pk") or 0)
    except (TypeError, ValueError):
        return Response({"error": "historial_pk invàlid."}, status=400)
    if not historial_pk:
        return Response({"error": "Falta historial_pk."}, status=400)

    # Sanity: the historial_pk must be one referenced by this sol·licitud.
    snapshot_pks = {
        r.get("historial_pk")
        for r in (s.rebutjades_snapshot or [])
        if r.get("historial_pk")
    }
    if historial_pk not in snapshot_pks:
        return Response(
            {"error": "Aquest historial no està vinculat a la sol·licitud."},
            status=400,
        )

    h = HistorialRevisio.objects.filter(pk=historial_pk).first()
    if h is None:
        return Response({"error": "Historial no trobat."}, status=404)
    if h.decisio != "rebutjada":
        return Response({"error": "Només es poden reconsiderar rebuigs."}, status=400)
    if not h.reconsiderada:
        h.reconsiderada = True
        h.save(update_fields=["reconsiderada"])
        from music.audit import log_staff_action

        log_staff_action(
            request,
            "rebutjada_reconsiderada",
            target=h,
            sollicitud_pk=s.pk,
        )
    return Response({"ok": True, "historial_pk": h.pk, "reconsiderada": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsStaff])
def resoldre(request: Request, pk: int) -> Response:
    s = get_object_or_404(SolicitudRevisio, pk=pk)
    if s.estat == SolicitudRevisio.ESTAT_RESOLTA:
        return Response({"error": "Aquesta sol·licitud ja està resolta."}, status=400)
    nota = (request.data or {}).get("nota") or ""
    nota = nota.strip()[:5000]

    from comptes.notifications import notify_gestor_sollicitud_revisio_resolta
    from music.audit import log_staff_action

    with transaction.atomic():
        s.estat = SolicitudRevisio.ESTAT_RESOLTA
        s.resolt_at = timezone.now()
        s.resolt_per = request.user
        s.nota_resolucio = nota
        s.save(update_fields=["estat", "resolt_at", "resolt_per", "nota_resolucio"])

    try:
        notify_gestor_sollicitud_revisio_resolta(s)
    except Exception:  # noqa: BLE001
        pass

    log_staff_action(
        request,
        "sollicitud_revisio_resolta",
        target=s.artista,
        sollicitud_pk=s.pk,
        nota_len=len(nota),
    )
    return Response(
        {
            "ok": True,
            "estat": s.estat,
            "resolt_at": s.resolt_at.isoformat(),
            "nota_resolucio": s.nota_resolucio,
        }
    )
