"""Payload builders — turn DB rows into the dict shape the renderer
+ caption helpers expect.

# Spec: docs/architecture/social.md

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


def _instagram_urls_for_canco(canco) -> list[str]:
    """Return Instagram URLs for the principal artist + every
    collaborator that has one, in canonical order. Artistes without
    an instagram_url are silently skipped (no broken tags).

    Used by the publicar_social.IG tagger so every artist on a track
    gets a `user_tags` entry on the slide where their entry was
    drawn. Mirrors `Canco.artistes_col_ordered` so the visual order
    matches the renderer caption.
    """
    if canco is None:
        return []
    out: list[str] = []
    principal = canco.artista
    if principal is not None:
        u = _instagram_url(principal)
        if u:
            out.append(u)
    # Collaborators in stable insertion order.
    try:
        cols = canco.artistes_col_ordered()
    except Exception:
        # Defensive: a Canco fixture without the helper (unlikely
        # in prod) falls back to the unordered manager.
        cols = canco.artistes_col.all()
    seen = set(out)
    for a in cols:
        u = _instagram_url(a)
        if u and u not in seen:
            out.append(u)
            seen.add(u)
    return out


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

    # Re-entry: a track absent last week is RE (not NEW) if it ever charted in
    # an EARLIER week for this territori. One batched indexed exists-style query
    # over just the candidate (absent-last-week) cançons.
    new_ids = [
        r.canco_id for r in rows if r.canco_id and prev_pos.get(r.canco_id) is None
    ]
    reentrades: set[int] = set()
    if new_ids:
        reentrades = set(
            TopSetmanal.objects.filter(
                territori=territori, canco_id__in=new_ids, setmana__lt=setmana
            ).values_list("canco_id", flat=True)
        )

    entries: list[dict] = []
    for r in rows:
        canco = r.canco
        artista = canco.artista if canco else None
        album = canco.album if canco else None
        # `artistes_noms` is the canonical list: main artist first,
        # then collaborators in the order they were attached to the
        # cançó (M2M through-table PK ASC; see
        # `Canco.artistes_col_ordered`). `artista_nom` is kept for
        # backwards compatibility with any caller that still reads
        # a single string (DEPRECATED — new code should use
        # `artistes_noms` and join via `_join_artists` / `_join_artists_text`).
        if canco and artista:
            col_objs = canco.artistes_col_ordered()
            artistes_noms = [artista.nom, *[a.nom for a in col_objs]]
            # Parallel to `artistes_noms` (same order: principal first,
            # then collaborators). ADDITIVE — `artistes_noms` is untouched.
            # Lets the newsletter link every collaborator to /artista/{slug}
            # (Slice 2); the social engine ignores this field.
            artistes_slugs = [artista.slug, *[a.slug for a in col_objs]]
        else:
            artistes_noms = ["—"]
            artistes_slugs = [None]
        entries.append(
            {
                "posicio": r.posicio,
                "posicio_anterior": prev_pos.get(r.canco_id),
                # True ⇒ absent last week but charted earlier → "RE" (re-entry).
                "reentrada": r.canco_id in reentrades,
                "canco_nom": canco.nom if canco else "—",
                "canco_slug": canco.slug if canco else None,
                "artistes_noms": artistes_noms,
                "artistes_slugs": artistes_slugs,
                "artista_nom": artista.nom if artista else "—",  # DEPRECATED
                "artista_slug": artista.slug if artista else None,
                # Principal-only URL kept for backward compatibility
                # (renderer + caption code still reads this single field).
                "artista_instagram_url": _instagram_url(artista),
                # Every artist on the track (principal + collabs) that
                # has an instagram_url, in canonical insertion order.
                # The publicar_social tagger reads this list to attach
                # one `user_tags` payload per artist per slide.
                "artistes_instagram_urls": _instagram_urls_for_canco(canco),
                "cover_url": getattr(album, "imatge_url", None) or None,
                # Deezer album id for the newsletter's local-cover lookup
                # (`comptes.newsletter_covers.album_cover_url`).
                "album_deezer_id": getattr(album, "deezer_id", None),
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

    albums = list(qs)
    if not albums:
        return None

    # ── Batched enrichment for the narrative detectors (n1-n4) ───────
    # Compute the flags once, in a handful of queries, instead of an
    # N+1 lookup per album inside the detectors.
    flags = _novetats_flags(albums, publish_date)

    # Pre-fetch each artist's primary territori so the renderer can
    # paint the right icon per row without an N+1 lookup.
    items: list[dict] = []
    for a in albums:
        artista = a.artista
        territori = ""
        if artista is not None:
            codis = list(artista.territoris.values_list("codi", flat=True))
            # Prefer a non-aggregate territory for icon variety; fall
            # back to PPCC if the artist is only tagged as global.
            non_ppcc = [c for c in codis if c != "PPCC"]
            territori = (non_ppcc or codis or ["PPCC"])[0]
        f = flags.get(a.id, {})
        dies = None
        if a.data_llancament:
            dies = max(0, (publish_date - a.data_llancament).days)
        items.append(
            {
                "nom": a.nom,
                "slug": a.slug,
                "tipus": a.tipus,
                "artista_id": artista.id if artista else None,
                "artista_nom": artista.nom if artista else "—",
                "artista_slug": artista.slug if artista else None,
                "artista_instagram_url": _instagram_url(artista),
                "artista_territori": territori,
                "cover_url": getattr(a, "imatge_url", None) or None,
                "album_deezer_id": getattr(a, "deezer_id", None),
                # narrative flags (audit #5):
                "dies": dies,
                "segell": (a.label or "").strip(),
                "artista_en_top": f.get("en_top", False),
                "primer_release": f.get("primer", False),
                "te_collab": f.get("collab", False),
                "segell_compartit": f.get("segell_compartit", False),
            }
        )
    return {"items": items}


def _novetats_flags(albums, publish_date: datetime.date) -> dict[int, dict]:
    """Batch-compute the narrative flags for a list of new Albums.

    Returns `{album_id: {en_top, primer, collab, segell_compartit}}`.
    All work is done in a small fixed number of queries (no N+1)."""
    from datetime import timedelta

    from django.db.models import Count, Min

    from music.models import Album, Canco
    from ranking.models import TopSetmanal

    artista_ids = {a.artista_id for a in albums if a.artista_id}
    album_ids = [a.id for a in albums]
    labels = {(a.label or "").strip() for a in albums if (a.label or "").strip()}

    # Artists present in the top in the last ~90 days.
    since = publish_date - timedelta(days=90)
    en_top_artists: set[int] = set(
        TopSetmanal.objects.filter(
            canco__artista_id__in=artista_ids, setmana__gte=since
        )
        .values_list("canco__artista_id", flat=True)
        .distinct()
    )

    # Earliest album release per artist → "first release" = this album is
    # the artist's earliest (and the artist has a single release date min).
    earliest: dict[int, datetime.date] = {}
    n_albums: dict[int, int] = {}
    for row in (
        Album.objects.filter(artista_id__in=artista_ids)
        .values("artista_id")
        .annotate(n=Count("id"), first=Min("data_llancament"))
    ):
        earliest[row["artista_id"]] = row["first"]
        n_albums[row["artista_id"]] = row["n"]

    # Albums whose tracks include a featuring (artistes_col).
    collab_album_ids: set[int] = set(
        Canco.objects.filter(album_id__in=album_ids, artistes_col__isnull=False)
        .values_list("album_id", flat=True)
        .distinct()
    )

    # Labels shared by >= 2 distinct artists who appear in the recent top.
    shared_labels: set[str] = set()
    if labels:
        for row in (
            Album.objects.filter(label__in=labels, artista_id__in=en_top_artists)
            .values("label")
            .annotate(n=Count("artista_id", distinct=True))
        ):
            if row["n"] >= 2:
                shared_labels.add(row["label"])

    out: dict[int, dict] = {}
    for a in albums:
        aid = a.artista_id
        primer = bool(
            aid
            and a.data_llancament
            and earliest.get(aid) == a.data_llancament
            and n_albums.get(aid, 0) <= 1
        )
        out[a.id] = {
            "en_top": aid in en_top_artists,
            "primer": primer,
            "collab": a.id in collab_album_ids,
            "segell_compartit": (a.label or "").strip() in shared_labels,
        }
    return out
