"""Weekly YouTube views for a song, computed honestly.

Lives here and not in the report because two implementations of the same
delta is how they drift, and this one has already been wrong twice:

1. `SenyalYouTube.views` is the **sum of every lane** of a song (the
   auto-generated Art Track plus whatever videos of the artist's own
   channel got matched). When a lane is added the sum jumps by the new
   video's lifetime count. Andreu Valor went from 140 views with one
   video to 88.450 with four in a night; read as a week that is 103.048
   views against 17 real ones, and it put him top of the Valencian chart.
2. Guarding on the **count** of lanes is not enough. If one small video
   leaves and a big one arrives the count does not move and the jump
   still lands (Miquel, 2026-08-18).

So the delta is the **sum of per-video differences** over the videos
present in both snapshots. A video contributes nothing the day it
appears — there is no baseline for it — and everything it earns from
then on. One that disappears stops contributing without subtracting
what it had accumulated.

`views_per_video` carries that detail since 2026-08-19. Rows written
before have only the total, and fall back to the count check, which is
equivalent for a single-lane song.

# Spec: docs/architecture/algorithm.md
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from ranking.models import SenyalYouTube

# Same slack the Last.fm delta uses: a missing day must not blank the
# week. `ranking.algorisme._WEEK_WINDOW_DAYS` is the sibling constant.
MARGE_DIES = 3


def visualitzacions_setmanals(
    canco_ids, today: datetime.date, *, dies: int = 7
) -> dict[int, float]:
    """`{canco_id: visualitzacions de la setmana}`, rescaled to `dies`.

    Songs with no comparable pair of snapshots are simply absent from
    the result — never present with a zero, which would be a claim we
    cannot make.
    """
    objectiu = today - datetime.timedelta(days=dies)
    des_de = objectiu - datetime.timedelta(days=MARGE_DIES)
    fins_a = objectiu + datetime.timedelta(days=MARGE_DIES)

    fotos: dict[int, dict[datetime.date, tuple]] = defaultdict(dict)
    for s in SenyalYouTube.objects.filter(
        canco_id__in=canco_ids,
        error=False,
        data__gte=des_de,
        data__lte=today,
        views__isnull=False,
    ).only("canco_id", "data", "views", "n_videos", "views_per_video"):
        fotos[s.canco_id][s.data] = (s.views, s.n_videos, s.views_per_video or {})

    out: dict[int, float] = {}
    for canco_id, dies_fotos in fotos.items():
        if today not in dies_fotos:
            continue
        candidates = [d for d in dies_fotos if des_de <= d <= fins_a]
        if not candidates:
            continue
        base = min(candidates, key=lambda d: abs((d - objectiu).days))
        span = (today - base).days
        if span <= 0:
            continue

        total_avui, carrils_avui, detall_avui = dies_fotos[today]
        total_base, carrils_base, detall_base = dies_fotos[base]

        if detall_avui and detall_base:
            comuns = set(detall_avui) & set(detall_base)
            if not comuns:
                continue
            delta = sum(
                detall_avui[v] - detall_base[v]
                for v in comuns
                if detall_avui[v] >= detall_base[v]
            )
        else:
            # Pre-2026-08-19 rows: only the total. Demand the same lane
            # count at both ends — weaker, but it is what the history
            # written before the detail existed can support.
            if carrils_avui != carrils_base or total_avui < total_base:
                continue
            delta = total_avui - total_base

        out[canco_id] = delta * dies / span
    return out
