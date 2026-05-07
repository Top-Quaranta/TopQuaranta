"""Public endpoints feeding the redesigned HomePage (Sprint I).

All endpoints are anonymous-friendly and rely on `cache_for_anon` to
absorb traffic spikes. Lifecycles:

  GET /api/v1/stats/                — global counters (cache 60 s)
  GET /api/v1/top/nova-setmana/     — newest entry in this week's PPCC
                                       top (cache 1 h)
  GET /api/v1/artistes/destacat/    — artist with the biggest jump in
                                       PPCC this week, restricted to
                                       artists with a verified manager
                                       (cache 1 h)
  GET /api/v1/artistes/descoberta/  — recently-approved artists not
                                       yet in any weekly top (cache 1 h)

The HomePage composes these calls with the existing /top/ and
/comunitat/publicacions/ endpoints to render its 10 sections.
"""

from __future__ import annotations

import datetime

from django.db.models import Count, Exists, OuterRef
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from comptes.models import UserArtista
from music.models import Artista, Canco
from ranking.models import TopSetmanal
from web.api.serializers import artista_minimal
from web.api.utils import cache_for_anon


@api_view(["GET"])
@permission_classes([AllowAny])
@cache_for_anon(300, key_prefix="home-stats")
def stats(request: Request) -> Response:
    """Counters for the HomePage stats strip + countdown indicator.

    `cancons_noves_setmana` counts how many tracks entered the latest
    PPCC weekly top that weren't on it the week before — surfaced on
    the countdown band as "X cançons noves aquesta setmana".
    """
    cancons_verificades = Canco.objects.public().count()
    artistes_aprovats = Artista.objects.public().count()

    latest_setmana = (
        TopSetmanal.objects.order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    if latest_setmana is None:
        territoris_actius = 0
        cancons_noves_setmana = 0
    else:
        territoris_actius = (
            TopSetmanal.objects.filter(setmana=latest_setmana)
            .values("territori")
            .distinct()
            .count()
        )
        prev_setmana = (
            TopSetmanal.objects.filter(territori="PPCC", setmana__lt=latest_setmana)
            .order_by("-setmana")
            .values_list("setmana", flat=True)
            .first()
        )
        cur_ids = set(
            TopSetmanal.objects.filter(
                territori="PPCC", setmana=latest_setmana
            ).values_list("canco_id", flat=True)
        )
        prev_ids = (
            set(
                TopSetmanal.objects.filter(
                    territori="PPCC", setmana=prev_setmana
                ).values_list("canco_id", flat=True)
            )
            if prev_setmana
            else set()
        )
        cancons_noves_setmana = len(cur_ids - prev_ids) if prev_ids else len(cur_ids)

    return Response(
        {
            "cancons_verificades": cancons_verificades,
            "artistes_aprovats": artistes_aprovats,
            "territoris_actius": territoris_actius,
            "cancons_noves_setmana": cancons_noves_setmana,
            "setmana": latest_setmana.isoformat() if latest_setmana else None,
        }
    )


def _serialize_top_entry(entry, posicio_anterior: int | None) -> dict:
    canco = entry.canco
    artista = canco.artista if canco else None
    album = canco.album if canco else None
    return {
        "posicio": entry.posicio,
        "posicio_anterior": posicio_anterior,
        "territori": entry.territori,
        "canco": (
            {
                "nom": canco.nom,
                "slug": canco.slug,
                "data_llancament": (
                    canco.data_llancament.isoformat() if canco.data_llancament else None
                ),
            }
            if canco
            else None
        ),
        "artista": (artista_minimal(artista) if artista else None),
        "album": (
            {
                "slug": album.slug,
                "nom": album.nom,
                "imatge_url": getattr(album, "imatge_url", None) or None,
            }
            if album
            else None
        ),
    }


def _biggest_climb_pk(target_setmana, prev_setmana) -> int | None:
    """Return canco_id with biggest position improvement in PPCC for
    `target_setmana` against `prev_setmana`. None when neither week has
    rows or no entry actually climbed."""
    if target_setmana is None or prev_setmana is None:
        return None
    cur = dict(
        TopSetmanal.objects.filter(
            territori="PPCC", setmana=target_setmana
        ).values_list("canco_id", "posicio")
    )
    prev = dict(
        TopSetmanal.objects.filter(territori="PPCC", setmana=prev_setmana).values_list(
            "canco_id", "posicio"
        )
    )
    best_pk, best_delta = None, 0
    for cid, pos in cur.items():
        prev_pos = prev.get(cid)
        if prev_pos is None or prev_pos <= pos:
            continue
        delta = prev_pos - pos
        if delta > best_delta:
            best_pk, best_delta = cid, delta
    return best_pk


@api_view(["GET"])
@permission_classes([AllowAny])
@cache_for_anon(3600, key_prefix="home-canco-destacada")
def top_canco_destacada(request: Request) -> Response:
    """The week's standout: song with the biggest PPCC climb.

    Tie-breaker: pick the second-best when the natural winner was
    already last week's destacada (avoid two consecutive weeks
    featuring the same track). Returns `null` when there's no
    previous-week PPCC snapshot to diff against (first-week edge).
    """
    latest = (
        TopSetmanal.objects.filter(territori="PPCC")
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    if latest is None:
        return Response({"entry": None, "setmana": None})
    prev = (
        TopSetmanal.objects.filter(territori="PPCC", setmana__lt=latest)
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    if prev is None:
        # No prior week to diff against (first-week edge). Fall back to
        # the current #1 so the section never renders empty just
        # because the system is fresh.
        e = (
            TopSetmanal.objects.select_related(
                "canco", "canco__artista", "canco__album"
            )
            .filter(territori="PPCC", setmana=latest, posicio=1)
            .first()
        )
        if e is None:
            return Response({"entry": None, "setmana": latest.isoformat()})
        payload = _serialize_top_entry(e, posicio_anterior=None)
        payload["delta"] = None
        return Response(
            {
                "setmana": latest.isoformat(),
                "setmana_dissabte": (latest + datetime.timedelta(days=5)).isoformat(),
                "entry": payload,
            }
        )
    prev2 = (
        TopSetmanal.objects.filter(territori="PPCC", setmana__lt=prev)
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )

    # Build list of climbers in the current week.
    cur = dict(
        TopSetmanal.objects.filter(territori="PPCC", setmana=latest).values_list(
            "canco_id", "posicio"
        )
    )
    prev_pos_map = dict(
        TopSetmanal.objects.filter(territori="PPCC", setmana=prev).values_list(
            "canco_id", "posicio"
        )
    )
    climbers: list[tuple[int, int, int]] = []  # (delta, canco_id, posicio_now)
    for cid, pos_now in cur.items():
        pos_prev = prev_pos_map.get(cid)
        if pos_prev is None or pos_prev <= pos_now:
            continue
        climbers.append((pos_prev - pos_now, cid, pos_now))
    if not climbers:
        # No song improved — feature the #1 instead so the slot stays
        # filled. delta=null signals "no movement" to the UI.
        e = (
            TopSetmanal.objects.select_related(
                "canco", "canco__artista", "canco__album"
            )
            .filter(territori="PPCC", setmana=latest, posicio=1)
            .first()
        )
        if e is None:
            return Response({"entry": None, "setmana": latest.isoformat()})
        payload = _serialize_top_entry(e, posicio_anterior=prev_pos_map.get(e.canco_id))
        payload["delta"] = None
        return Response(
            {
                "setmana": latest.isoformat(),
                "setmana_dissabte": (latest + datetime.timedelta(days=5)).isoformat(),
                "entry": payload,
            }
        )
    climbers.sort(
        key=lambda t: (-t[0], t[2])
    )  # biggest delta, ties broken by current pos

    # Skip last week's destacada to keep the rotation moving.
    last_week_destacada = _biggest_climb_pk(prev, prev2)
    pick = next(
        (c for c in climbers if c[1] != last_week_destacada),
        climbers[0],
    )
    delta, canco_id, _ = pick

    e = (
        TopSetmanal.objects.select_related("canco", "canco__artista", "canco__album")
        .filter(territori="PPCC", setmana=latest, canco_id=canco_id)
        .first()
    )
    if e is None:
        return Response({"entry": None, "setmana": latest.isoformat()})

    payload = _serialize_top_entry(e, posicio_anterior=prev_pos_map.get(canco_id))
    payload["delta"] = delta
    return Response(
        {
            "setmana": latest.isoformat(),
            "setmana_dissabte": (latest + datetime.timedelta(days=5)).isoformat(),
            "entry": payload,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
@cache_for_anon(3600, key_prefix="home-destacat")
def artista_destacat(request: Request) -> Response:
    """Verified-managed artist with the biggest PPCC jump this week.

    Considers only artists that have at least one `UserArtista` with
    `verificat=True`. The jump is measured per-canco and aggregated to
    the artist (the artist's biggest movement counts). Tie-breaker:
    largest count of verified cançons. Returns `null` when no
    eligible artist moved in PPCC this week.
    """
    latest = (
        TopSetmanal.objects.filter(territori="PPCC")
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    if latest is None:
        return Response({"artista": None})
    prev = (
        TopSetmanal.objects.filter(territori="PPCC", setmana__lt=latest)
        .order_by("-setmana")
        .values_list("setmana", flat=True)
        .first()
    )
    if prev is None:
        return Response({"artista": None, "setmana": latest.isoformat()})

    # Build canco_id → posicio for both weeks.
    cur = dict(
        TopSetmanal.objects.filter(territori="PPCC", setmana=latest).values_list(
            "canco_id", "posicio"
        )
    )
    prev_pos = dict(
        TopSetmanal.objects.filter(territori="PPCC", setmana=prev).values_list(
            "canco_id", "posicio"
        )
    )

    # Map canco_id → artista_id for the union of canco IDs in both weeks.
    canco_ids = set(cur) | set(prev_pos)
    canco_artista = dict(
        Canco.objects.filter(pk__in=canco_ids).values_list("pk", "artista_id")
    )

    # Per-artist best improvement (positive = went up).
    improvements: dict[int, int] = {}
    for cid, pos_now in cur.items():
        pos_prev = prev_pos.get(cid)
        if pos_prev is None or pos_prev <= pos_now:
            continue
        delta = pos_prev - pos_now
        aid = canco_artista.get(cid)
        if aid is None:
            continue
        if delta > improvements.get(aid, 0):
            improvements[aid] = delta

    if not improvements:
        return Response({"artista": None, "setmana": latest.isoformat()})

    # Restrict to verified-managed artists.
    verified_ids = set(
        UserArtista.objects.filter(
            verificat=True, artista_id__in=improvements
        ).values_list("artista_id", flat=True)
    )
    eligible = {aid: d for aid, d in improvements.items() if aid in verified_ids}
    if not eligible:
        return Response({"artista": None, "setmana": latest.isoformat()})

    # Tie-breaker on verified-cançó count.
    counts = dict(
        Canco.objects.filter(artista_id__in=eligible, verificada=True)
        .values_list("artista_id")
        .annotate(n=Count("pk"))
        .values_list("artista_id", "n")
    )
    best_id = max(eligible, key=lambda a: (eligible[a], counts.get(a, 0)))

    a = Artista.objects.filter(pk=best_id).prefetch_related("territoris").first()
    if a is None:
        return Response({"artista": None})

    bio_raw = (a.bio or a.lastfm_bio_summary or "").strip()
    if len(bio_raw) > 120:
        bio_short = bio_raw[:117].rsplit(" ", 1)[0] + "…"
    else:
        bio_short = bio_raw

    return Response(
        {
            "setmana": latest.isoformat(),
            "delta": eligible[best_id],
            "artista": {
                "pk": a.pk,
                "slug": a.slug,
                "nom": a.nom,
                "imatge_url": (a.lastfm_image_large or "").strip() or None,
                "bio_curta": bio_short,
                "territoris": list(a.territoris.values_list("codi", flat=True)),
                "genere": a.genere or "",
            },
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
@cache_for_anon(3600, key_prefix="home-descoberta")
def artistes_descoberta(request: Request) -> Response:
    """Recently-approved artists never seen in TopSetmanal, with cover.

    Restricted to:
      - `aprovat=True`
      - `created_at >= today − 30 d`
      - never in `TopSetmanal` (no canço of theirs has charted)
      - has at least one `Canco(verificada=True, activa=True)` whose
        related `Album` has a non-empty `imatge_url` — the HomePage
        card uses that cover as the primary visual, so artists
        without a cover would render an empty placeholder and are
        filtered out backend-side.

    Each result includes `imatge_url` = cover of the **most recent**
    verified album that has an image (ordered by
    `Album.data_llancament desc, id desc`). `limit` capped at 12.
    """
    try:
        limit = max(1, min(int(request.GET.get("limit", "6")), 12))
    except ValueError:
        limit = 6

    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
        days=30
    )

    has_verified_canco_with_cover = Canco.objects.filter(
        artista=OuterRef("pk"),
        verificada=True,
        activa=True,
        album__imatge_url__gt="",
    )
    in_top = TopSetmanal.objects.filter(canco__artista=OuterRef("pk"))

    # Pull a generous overshoot so we can still hand back `limit` rows
    # after the per-artist image-resolution loop drops anything that
    # raced (e.g. cover removed mid-request). 3× is empirical headroom.
    qs = (
        Artista.objects.public()
        .filter(created_at__gte=cutoff)
        .annotate(
            te_canco_amb_cover=Exists(has_verified_canco_with_cover),
            ja_al_top=Exists(in_top),
        )
        .filter(te_canco_amb_cover=True, ja_al_top=False)
        .prefetch_related("territoris")
        .order_by("-created_at")[: limit * 3]
    )

    # Lazy import — Album is in the same app as Canco; avoid a circular
    # at module load.
    from music.models import Album

    # Diversity rule: prefer one artist per territori until we run
    # out of fresh ones. Without this the section was 100 % CAT
    # because new approvals are dominated by Catalonia. We only
    # relax the rule when there aren't enough distinct territoris
    # to fill `limit`, and we never duplicate an artist.
    items: list[dict] = []
    leftovers: list[dict] = []
    seen_territoris: set[str] = set()

    for a in qs:
        if len(items) >= limit:
            break
        cover = (
            Album.objects.filter(
                cancons__artista=a,
                cancons__verificada=True,
                cancons__activa=True,
                imatge_url__gt="",
            )
            .order_by("-data_llancament", "-id")
            .values_list("imatge_url", flat=True)
            .first()
        )
        if not cover:
            continue
        territoris = list(a.territoris.values_list("codi", flat=True))
        primary = territoris[0] if territoris else None
        row = {
            "pk": a.pk,
            "slug": a.slug,
            "nom": a.nom,
            "imatge_url": cover,
            "territoris": territoris,
            "genere": a.genere or "",
        }
        if primary and primary not in seen_territoris:
            seen_territoris.add(primary)
            items.append(row)
        else:
            leftovers.append(row)

    # Fill any remaining slots with leftovers (preserves age order).
    for row in leftovers:
        if len(items) >= limit:
            break
        items.append(row)

    return Response({"results": items, "count": len(items)})
