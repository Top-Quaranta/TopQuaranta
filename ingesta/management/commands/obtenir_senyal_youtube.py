"""Daily YouTube snapshot per matched track — the cheap half.

`videos.list?part=statistics` returns 50 ids for a single quota unit, so
the whole catalogue costs ~60 of the 10.000 daily units. That is the
entire reason this source is viable: discovery is rationed, polling is
not.

Writes one `SenyalYouTube` row per (canco, data) with the cumulative
`viewCount`, mirroring `obtenir_senyal`. The ranking reads 7-day deltas,
never the absolute value, so a track only starts counting once it has a
baseline — same lag as Last.fm.

Idempotent: tracks already snapshotted for the target date are skipped,
so a re-run after a partial failure costs only the missing ids.

    python manage.py obtenir_senyal_youtube [--data YYYY-MM-DD] [--dry-run]

# Spec: docs/architecture/ingesta.md
"""

from __future__ import annotations

import datetime
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ingesta.clients import youtube as yt
from music.constants import DIES_CADUCITAT
from music.models import Canco, CancoYouTubeVideo
from ranking.models import SenyalYouTube

logger = logging.getLogger(__name__)

BATCH = 50  # `videos.list` caps at 50 ids per call — and per quota unit.


class Command(BaseCommand):
    help = "Recull les visualitzacions diàries de YouTube de les cançons aparellades."

    def add_arguments(self, parser):
        parser.add_argument("--data", type=str, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts) -> None:
        if not settings.YOUTUBE_API_KEY:
            self.stdout.write(self.style.WARNING("YOUTUBE_API_KEY buit; no faig res."))
            return

        if opts["data"]:
            try:
                target = datetime.date.fromisoformat(opts["data"])
            except ValueError:
                raise CommandError(f"Data invàlida: {opts['data']}. Usa YYYY-MM-DD.")
        else:
            target = datetime.date.today()
        cutoff = target - datetime.timedelta(days=DIES_CADUCITAT)

        ja = set(
            SenyalYouTube.objects.filter(data=target).values_list("canco_id", flat=True)
        )
        # Two lanes per song: the Art Track (one video, on the Canco) and
        # the official channel (zero or many, in `CancoYouTubeVideo`). A
        # song counts if it has EITHER — an artist reviewed as having no
        # own channel is complete with one lane, not under-measured.
        elegibles = Canco.objects.filter(
            activa=True, verificada=True, data_llancament__gte=cutoff
        ).exclude(pk__in=ja)
        per_canco: dict[int, list[str]] = {}
        # Quin vídeo de cada cançó és l'Art Track: només eixe data la
        # gravació. Un videoclip del canal propi pot ser d'una represa,
        # d'un directe o d'una pujada tardana.
        art_tracks: dict[int, set[str]] = {}
        for pk, vid, publicat in elegibles.exclude(youtube_video_id="").values_list(
            "pk", "youtube_video_id", "youtube_publicat_at"
        ):
            per_canco.setdefault(pk, []).append(vid)
            if publicat is None:
                art_tracks.setdefault(pk, set()).add(vid)
        for pk, vid in CancoYouTubeVideo.objects.filter(
            canco__in=elegibles
        ).values_list("canco_id", "video_id"):
            per_canco.setdefault(pk, []).append(vid)
        # Flat list of (canco_pk, video_id) so batching stays trivial.
        pendents = [(pk, v) for pk, vids in per_canco.items() for v in vids]
        self.stdout.write(
            f"Vídeos pendents per a {target}: {len(pendents)} "
            f"({len(per_canco)} cançons) "
            f"(cost estimat {max(1, (len(pendents) + BATCH - 1) // BATCH)} unitats)"
        )
        if opts["dry_run"] or not pendents:
            self.stdout.write(f"WORK_DONE={0}")
            return

        recollit: dict[int, dict] = {}
        morts: dict[int, list[str]] = {}
        publicacions: dict[int, object] = {}
        try:
            for i in range(0, len(pendents), BATCH):
                tros = pendents[i : i + BATCH]
                stats = yt.video_stats([vid for _, vid in tros])
                for pk, vid in tros:
                    st = stats.get(vid)
                    # La data de publicació de l'Art Track data la
                    # gravació (vegeu `Canco.youtube_publicat_at`). Ve
                    # de gratis amb la mateixa crida, i no canvia mai:
                    # es desa una vegada i prou.
                    if st and st.get("published_at") and vid in art_tracks.get(pk, ()):
                        publicacions[pk] = st["published_at"]
                    if st is None or st["views"] is None:
                        # Gone (takedown, re-upload), a stale id, or an
                        # uploader who hides the view count — all the same
                        # thing to us: this lane reports nothing today.
                        # Summing a hidden counter as `or 0` wrote a song
                        # down as 0 plays with error=False AND inflated
                        # n_videos: a false fact, indistinguishable from a
                        # song nobody played (audit 2026-08-15). Recorded,
                        # not silently dropped, so the daily report can
                        # surface a rising count.
                        morts.setdefault(pk, []).append(vid)
                        continue
                    acc = recollit.setdefault(
                        pk,
                        {"views": 0, "likes": 0, "n": 0, "primer": vid, "detall": {}},
                    )
                    acc["views"] += st["views"]
                    acc["likes"] += st["likes"] or 0
                    acc["n"] += 1
                    # El detall per vídeo és el que permet calcular
                    # l'increment sumant restes en lloc de restar sumes.
                    acc["detall"][vid] = st["views"]
        except yt.QuotaExhausted as exc:
            self.stdout.write(self.style.WARNING(f"Quota exhaurida: {exc}"))

        files: list[SenyalYouTube] = []
        for pk, acc in recollit.items():
            files.append(
                SenyalYouTube(
                    canco_id=pk,
                    data=target,
                    video_id=acc["primer"],
                    views_per_video=acc["detall"],
                    views=acc["views"],
                    likes=acc["likes"],
                    n_videos=acc["n"],
                )
            )
        # Only a song where EVERY lane failed is an error row; one dead
        # video among several is noise, not a missing signal.
        for pk, vids in morts.items():
            if pk in recollit:
                continue
            files.append(
                SenyalYouTube(
                    canco_id=pk,
                    data=target,
                    video_id=vids[0],
                    n_videos=0,
                    error=True,
                    error_msg=f"cap estadística per a {len(vids)} vídeo(s)",
                )
            )
        ok = len(recollit)
        errors = sum(1 for pk in morts if pk not in recollit)

        SenyalYouTube.objects.bulk_create(files, ignore_conflicts=True)
        for pk, publicat in publicacions.items():
            Canco.objects.filter(pk=pk).update(youtube_publicat_at=publicat)
        self.stdout.write(
            self.style.SUCCESS(f"Snapshots: {ok} correctes, {errors} amb error.")
        )
        self.stdout.write(f"WORK_DONE={ok}")
