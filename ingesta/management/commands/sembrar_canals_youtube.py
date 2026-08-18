"""Seed `Artista.youtube_canal_oficial` from what we already know.

MusicBrainz editors have already curated a YouTube link for 137 of our
artists, sitting unused in `Artista.youtube_url`. That is exactly the
human decision the staff queue is about to ask for, made by somebody
else and for free — so we take it before asking anyone to click.

Two URL shapes:

  * `youtube.com/channel/UC…` — the id is in the URL. Costs nothing.
  * `youtube.com/@handle`, `/user/x`, `/c/x` — needs one `search.list`
    (100 units) to resolve, so it is opt-in via `--resolve`.

Nothing here guesses: a MusicBrainz link is an editorial statement that
this channel belongs to this artist. What it does NOT do is mark the
artist reviewed when no link exists — "nobody looked yet" and "looked,
has no channel" stay distinct, and only a human writes the second.

    python manage.py sembrar_canals_youtube [--resolve] [--dry-run]

# Spec: docs/architecture/pipeline.md
"""

from __future__ import annotations

import datetime
import logging
import re

from django.core.management.base import BaseCommand

from ingesta.clients import youtube as yt
from music.constants import DIES_CADUCITAT
from music.models import Artista

logger = logging.getLogger(__name__)

# `youtube.com/channel/UC…` — the only shape that carries the id itself.
_CHANNEL_URL = re.compile(r"youtube\.com/channel/(UC[\w-]{20,30})", re.I)
# Everything else we can still recognise as "a YouTube channel of sorts".
_HANDLE_URL = re.compile(r"youtube\.com/(?:@([\w.-]+)|user/([\w-]+)|c/([\w-]+))", re.I)


class Command(BaseCommand):
    help = "Sembra el canal oficial de YouTube des dels enllaços de MusicBrainz."

    def add_arguments(self, parser):
        parser.add_argument(
            "--resolve",
            action="store_true",
            help="Resol també els /@handle (1 unitat via forHandle).",
        )
        parser.add_argument(
            "--nomes-finestra",
            action="store_true",
            help="Només artistes amb cançons dins dels 365 dies.",
        )
        parser.add_argument(
            "--budget",
            type=int,
            default=4_000,
            help="Sostre de quota per a --resolve. Amb forHandle cada un "
            "val 1 unitat, però el fallback per nom encara en val 100, "
            "així que el sostre continua tenint sentit.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts) -> None:
        pendents = (
            Artista.objects.filter(youtube_canal_oficial="")
            .exclude(youtube_url="")
            .exclude(youtube_url__isnull=True)
        )
        if opts["nomes_finestra"]:
            cutoff = datetime.date.today() - datetime.timedelta(days=DIES_CADUCITAT)
            pendents = pendents.filter(
                cancons__verificada=True,
                cancons__activa=True,
                cancons__data_llancament__gte=cutoff,
            ).distinct()
        directes = 0
        resolts = 0
        pendents_handle = 0
        gastat = 0

        for a in pendents:
            m = _CHANNEL_URL.search(a.youtube_url)
            channel = m.group(1) if m else None

            if channel is None:
                h = _HANDLE_URL.search(a.youtube_url)
                if not h:
                    continue
                if not opts["resolve"]:
                    pendents_handle += 1
                    continue
                if gastat + yt.COST_LIST > opts["budget"]:
                    pendents_handle += 1
                    continue
                gastat += yt.COST_LIST
                nom = next(g for g in h.groups() if g)
                # `forHandle` costs 1 unit; the old `search.list` path cost
                # 100 and made resolving the backlog a seven-day affair.
                channel = yt.resolve_handle(nom)
                if channel is None:
                    gastat += yt.COST_SEARCH
                    channel = self._resolve(a.nom)
                if not channel:
                    continue
                resolts += 1
            else:
                directes += 1

            if opts["dry_run"]:
                self.stdout.write(f"  [dry] {a.nom} → {channel}")
                continue
            a.youtube_canal_oficial = channel
            a.youtube_canal_revisat = True
            a.save(update_fields=["youtube_canal_oficial", "youtube_canal_revisat"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Directes des de la URL: {directes} · resolts amb cerca: "
                f"{resolts} ({gastat} unitats)"
                + (
                    f" · {pendents_handle} amb handle sense resoldre (--resolve)"
                    if pendents_handle
                    else ""
                )
            )
        )
        self.stdout.write(f"WORK_DONE={directes + resolts}")

    def _resolve(self, term: str) -> str | None:
        try:
            data = yt._get(
                "search", part="snippet", q=term, type="channel", maxResults=1
            )
        except yt.QuotaExhausted:
            self.stdout.write(self.style.WARNING("Quota exhaurida."))
            raise
        items = data.get("items") or []
        if not items:
            return None
        return items[0].get("snippet", {}).get("channelId") or None
