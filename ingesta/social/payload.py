"""Payload builders — turn DB rows into the dict shape the renderer
+ caption helpers expect.

Each builder returns either:
  - {"entries": [...], "hero_cover_url": ...}  for top_*
  - {"items":   [...]}                         for nous_*
or `None` when there's nothing publishable (calling command marks
the SocialPost as `omes` and exits cleanly).
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from django.db.models import Q

from music.models import Album, Canco
from ranking.models import TopSetmanal

logger = logging.getLogger(__name__)


def _prev_setmana(setmana: datetime.date, territori: str) -> datetime.date | None:
    return (
        TopSetmanal.objects.filter(territori=territori, setmana__lt=setmana)
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )


def _instagram_url(artista) -> str:
    """Best-guess instagram URL on the artist."""
    if artista is None:
        return ""
    return getattr(artista, "instagram_url", "") or ""


def build_top(territori: str, setmana: datetime.date) -> Optional[dict]:
    """Build the top entries (chart order) + previous-week positions
    so the renderer can draw arrows. Returns None if the requested
    week has no data for the territori."""
    rows = list(
        TopSetmanal.objects.filter(territori=territori, setmana=setmana)
        .select_related("canco", "canco__artista", "canco__album")
        .order_by("posicio")[:40]
    )
    if not rows:
        return None
    prev_week = _prev_setmana(setmana, territori)
    prev_pos = {}
    if prev_week is not None:
        prev_pos = dict(
            TopSetmanal.objects.filter(
                territori=territori, setmana=prev_week
            ).values_list("canco_id", "posicio")
        )

    entries: list[dict] = []
    for r in rows:
        canco = r.canco
        artista = canco.artista if canco else None
        album = canco.album if canco else None
        entries.append(
            {
                "posicio": r.posicio,
                "posicio_anterior": prev_pos.get(r.canco_id),
                "canco_nom": canco.nom if canco else "—",
                "canco_slug": canco.slug if canco else None,
                "artista_nom": artista.nom if artista else "—",
                "artista_slug": artista.slug if artista else None,
                "artista_instagram_url": _instagram_url(artista),
                "cover_url": getattr(album, "imatge_url", None) or None,
            }
        )
    return {
        "entries": entries,
        "hero_cover_url": entries[0]["cover_url"] if entries else None,
    }


def build_novetats(
    tipus: str, setmana: datetime.date, *, dies_enrere: int = 7
) -> Optional[dict]:
    """For nous_albums + nous_singles. `setmana` is the Monday of the
    target week; we list everything released within the past
    `dies_enrere` days that has at least one verified, active cançó."""
    cutoff = setmana - datetime.timedelta(days=dies_enrere)
    qs = Album.objects.filter(
        data_llancament__gte=cutoff, data_llancament__lte=setmana
    ).select_related("artista")
    if tipus == "nous_albums":
        qs = qs.filter(tipus__iexact="album")
    elif tipus == "nous_singles":
        # legacy values: "single" or "EP" — treat both as "single"
        qs = qs.filter(Q(tipus__iexact="single") | Q(tipus__iexact="ep"))
    else:
        return None

    qs = qs.filter(cancons__verificada=True, cancons__activa=True).distinct()
    qs = qs.order_by("-data_llancament", "-id")[:30]

    items: list[dict] = []
    for a in qs:
        artista = a.artista
        items.append(
            {
                "nom": a.nom,
                "slug": a.slug,
                "artista_nom": artista.nom if artista else "—",
                "artista_slug": artista.slug if artista else None,
                "artista_instagram_url": _instagram_url(artista),
                "cover_url": getattr(a, "imatge_url", None) or None,
            }
        )
    if not items:
        return None
    return {"items": items}
