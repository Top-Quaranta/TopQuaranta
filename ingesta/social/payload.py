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
from social.models import SocialPost

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


def _last_publication_date(tipus: str) -> Optional[datetime.date]:
    """Most recent successful publication date for `tipus`, used as
    the lower bound of the next window. Returns None on first ever
    run (caller falls back to `setmana - 7d`)."""
    pub = (
        SocialPost.objects.filter(tipus=tipus, status=SocialPost.STATUS_PUBLICAT)
        .order_by("-published_at", "-setmana")
        .first()
    )
    if pub is None:
        return None
    if pub.published_at:
        return pub.published_at.date()
    # Fallback: derive from the stored week — Tuesday for albums,
    # Friday for singles. Imported here to avoid a top-level cycle.
    from .calendari import publication_date_for

    return publication_date_for(tipus, pub.setmana)


def build_novetats(
    tipus: str,
    setmana: datetime.date,
    *,
    publish_date: datetime.date | None = None,
    dies_enrere: int = 7,
) -> Optional[dict]:
    """For nous_albums + nous_singles.

    Window: `(last_publication_of_same_tipus, publish_date]`. This
    avoids the previous behaviour where two consecutive Tuesdays of
    "nous albums" overlapped on the boundary day and a release would
    appear twice. Falls back to `[publish_date - dies_enrere,
    publish_date]` on first run.

    `setmana` is the Monday of the TopSetmanal-style week and is
    only used by the caller for the SocialPost row; the window is
    computed from `publish_date` (the actual day the slot fires).
    """
    if publish_date is None:
        # Best-effort: treat the stored Monday as the window's upper
        # bound. Old callers without `publish_date` keep working.
        publish_date = setmana
    last = _last_publication_date(tipus)
    if last is None:
        cutoff = publish_date - datetime.timedelta(days=dies_enrere)
    else:
        # Strictly after last publication so the boundary day isn't
        # counted twice across consecutive weeks.
        cutoff = last + datetime.timedelta(days=1)
    qs = Album.objects.filter(
        data_llancament__gte=cutoff, data_llancament__lte=publish_date
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

    # Pre-fetch each artist's primary territori so the renderer can
    # paint the right icon per row without an N+1 lookup.
    items: list[dict] = []
    for a in qs:
        artista = a.artista
        territori = ""
        if artista is not None:
            codis = list(artista.territoris.values_list("codi", flat=True))
            # Prefer a non-aggregate territory for icon variety; fall
            # back to PPCC if the artist is only tagged as global.
            non_ppcc = [c for c in codis if c != "PPCC"]
            territori = (non_ppcc or codis or ["PPCC"])[0]
        items.append(
            {
                "nom": a.nom,
                "slug": a.slug,
                "artista_nom": artista.nom if artista else "—",
                "artista_slug": artista.slug if artista else None,
                "artista_instagram_url": _instagram_url(artista),
                "artista_territori": territori,
                "cover_url": getattr(a, "imatge_url", None) or None,
            }
        )
    if not items:
        return None
    return {"items": items}
