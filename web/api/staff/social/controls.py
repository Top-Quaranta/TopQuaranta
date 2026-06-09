"""ConfiguracioGlobal toggles for the social pipeline:
per-channel kill switches, story cap, per-channel delay, the
distribution matrix (canal × tipus × dia_setmana)."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from ranking.models import ConfiguracioGlobal
from web.api.staff._common import IsStaff


@api_view(["POST"])
@permission_classes([IsStaff])
def social_toggle(request: Request) -> Response:
    """Flip a distribution switch.

    `channel` is REQUIRED and explicit (2026-06-07: the old
    default-to-`instagram` was a footgun — the "global" UI button sent
    no channel and silently toggled Instagram only). Accepted values:
    `global` → the master `distribucio_activa`; or a per-channel switch
    (`instagram` | `mastodon` | `bluesky` | `telegram` | `newsletter`
    | `rss`).
    """
    field_map = {
        "global": "distribucio_activa",
        "instagram": "instagram_actiu",
        "mastodon": "mastodon_actiu",
        "bluesky": "bluesky_actiu",
        "telegram": "telegram_actiu",
        "newsletter": "newsletter_actiu",
        "rss": "rss_actiu",
    }
    channel = (request.data.get("channel") or "").strip()
    field = field_map.get(channel)
    if field is None:
        return Response(
            {
                "error": f"unknown channel '{channel}'; expected one of {list(field_map)}"
            },
            status=400,
        )
    cfg = ConfiguracioGlobal.load()
    new_val = bool(request.data.get("actiu", not getattr(cfg, field)))
    setattr(cfg, field, new_val)
    cfg.save(update_fields=[field])
    return Response({field: new_val})


@api_view(["POST"])
@permission_classes([IsStaff])
def social_story_cap(request: Request) -> Response:
    try:
        n = int(request.data.get("n"))
    except (TypeError, ValueError):
        return Response({"error": "n must be int 1-40"}, status=400)
    if n < 1 or n > 40:
        return Response({"error": "n must be in [1, 40]"}, status=400)
    cfg = ConfiguracioGlobal.load()
    cfg.story_max_cancons_ppcc = n
    cfg.save(update_fields=["story_max_cancons_ppcc"])
    return Response({"story_max_cancons_ppcc": cfg.story_max_cancons_ppcc})


_DELAY_CHANNELS = ("instagram", "mastodon", "bluesky", "telegram", "newsletter")


@api_view(["POST"])
@permission_classes([IsStaff])
def social_delay(request: Request) -> Response:
    """Set per-channel publish delay in minutes (Sprint Distribució v2
    lot B). Cron fires the channel at its base time; each command
    sleeps `delay_<channel>_min` before doing work, letting staff
    spread the schedule wider without editing crontab. Capped at
    180 min (a worker holds a slot idle for the duration).
    """
    channel = (request.data.get("channel") or "").strip()
    if channel not in _DELAY_CHANNELS:
        return Response(
            {
                "error": f"unknown channel '{channel}'; expected one of {_DELAY_CHANNELS}"
            },
            status=400,
        )
    try:
        n = int(request.data.get("min"))
    except (TypeError, ValueError):
        return Response({"error": "min must be int 0-180"}, status=400)
    if n < 0 or n > 180:
        return Response({"error": "min must be in [0, 180]"}, status=400)
    cfg = ConfiguracioGlobal.load()
    field = f"delay_{channel}_min"
    setattr(cfg, field, n)
    cfg.save(update_fields=[field])
    return Response({field: n})


# Distribution matrix (canal × tipus) — the third gate over the master
# switch and the per-channel switches.
_MATRIU_TIPUS = [
    ("top_ppcc", "Top global"),
    ("top_territorial", "Top territorial"),
    ("nous_singles", "Nous singles"),
    ("nous_albums", "Nous àlbums"),
]

# Weekday options for the matrix `dia_setmana` dropdown (Python weekday():
# 0=Monday … 6=Sunday). `null` = "sense restricció" is rendered by the UI.
_DIES_SETMANA = [
    {"value": 0, "label": "Dilluns"},
    {"value": 1, "label": "Dimarts"},
    {"value": 2, "label": "Dimecres"},
    {"value": 3, "label": "Dijous"},
    {"value": 4, "label": "Divendres"},
    {"value": 5, "label": "Dissabte"},
    {"value": 6, "label": "Diumenge"},
]


@api_view(["GET"])
@permission_classes([IsStaff])
def social_matriu(request: Request) -> Response:
    """The distribution matrix: every `MatriuPublicacio` cell plus the
    canal/tipus dimensions the grid renders. Read-only.

    Cells the seed never created (e.g. newsletter × nous_albums) are
    reported with `seeded=False`; the publishers treat a missing row as
    on (fail-open to the pre-matrix world), so the grid shows them as a
    non-toggleable blank rather than a real switch."""
    from ranking.models import MatriuPublicacio

    existing = {(m.canal, m.tipus): m for m in MatriuPublicacio.objects.all()}
    cells = []
    for canal, canal_label in MatriuPublicacio.CANALS:
        for tipus, _ in _MATRIU_TIPUS:
            key = (canal, tipus)
            row = existing.get(key)
            cells.append(
                {
                    "canal": canal,
                    "tipus": tipus,
                    "actiu": row.actiu if row else True,
                    "dia_setmana": row.dia_setmana if row else None,
                    "seeded": row is not None,
                }
            )
    return Response(
        {
            "canals": [{"canal": c, "label": l} for c, l in MatriuPublicacio.CANALS],
            "tipus": [{"tipus": t, "label": l} for t, l in _MATRIU_TIPUS],
            "dies": _DIES_SETMANA,
            "cells": cells,
        }
    )


@api_view(["POST"])
@permission_classes([IsStaff])
def social_matriu_toggle(request: Request) -> Response:
    """Set one matrix cell. Body: `canal`, `tipus`, and either/both of
    `actiu` (bool; defaults to flipping when only `actiu` is sent with no
    value) and `dia_setmana` (int 0-6, or null to clear the restriction).
    Only seeded cells can be toggled (a non-seeded combo is not a real
    distribution slot)."""
    from ranking.models import MatriuPublicacio

    canal = (request.data.get("canal") or "").strip()
    tipus = (request.data.get("tipus") or "").strip()
    valid_canals = {c for c, _ in MatriuPublicacio.CANALS}
    valid_tipus = {t for t, _ in _MATRIU_TIPUS}
    if canal not in valid_canals or tipus not in valid_tipus:
        return Response({"error": "canal o tipus desconegut"}, status=400)
    cell = MatriuPublicacio.objects.filter(canal=canal, tipus=tipus).first()
    if cell is None:
        return Response(
            {"error": "aquesta combinació no és un slot de distribució"},
            status=400,
        )

    has_dia = "dia_setmana" in request.data
    update_fields = []
    prev_actiu = cell.actiu
    prev_dia = cell.dia_setmana

    if has_dia:
        dia_raw = request.data.get("dia_setmana")
        if dia_raw is None or dia_raw == "":
            cell.dia_setmana = None
        else:
            try:
                dia = int(dia_raw)
            except (TypeError, ValueError):
                return Response({"error": "dia_setmana invàlid"}, status=400)
            if dia < 0 or dia > 6:
                return Response({"error": "dia_setmana fora de rang [0,6]"}, status=400)
            cell.dia_setmana = dia
        update_fields.append("dia_setmana")

    # `actiu` only flips when `dia_setmana` was NOT the field being edited,
    # or when an explicit `actiu` value is sent — so changing the day never
    # silently toggles the switch.
    if not has_dia or "actiu" in request.data:
        raw = request.data.get("actiu", None)
        cell.actiu = (not cell.actiu) if raw is None else bool(raw)
        update_fields.append("actiu")

    cell.save(update_fields=update_fields)
    # Audit: this toggle changes what actually gets distributed (an off
    # newsletter cell silences the Sunday send, a pinned day restricts it),
    # so it is a consequential config change — record who/when/what.
    from music.audit import log_staff_action

    log_staff_action(
        request,
        "config_update",
        target=cell,
        camp="matriu_distribucio",
        canal=canal,
        tipus=tipus,
        anterior={"actiu": prev_actiu, "dia_setmana": prev_dia},
        nou={"actiu": cell.actiu, "dia_setmana": cell.dia_setmana},
    )
    return Response(
        {
            "canal": canal,
            "tipus": tipus,
            "actiu": cell.actiu,
            "dia_setmana": cell.dia_setmana,
        }
    )
