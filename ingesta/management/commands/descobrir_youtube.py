"""Resolve artists to their YouTube Topic channel and match their tracks.

The expensive half of the YouTube integration: `search.list` costs 100
of the 10.000 daily quota units, so this can only ever resolve ~90
artists a day. Everything else (`channels.list`, `playlistItems.list`)
costs 1 unit and is noise by comparison.

**Order matters more than speed.** Resolving alphabetically would spend
three weeks before touching the artists we actually care about, so the
queue is:

  1. artists with in-window tracks that have NO valid Last.fm signal —
     the blind spot the whole exercise exists to fill (~600 tracks over
     a few hundred artists, so covered in the first days);
  2. the rest of VAL / BAL;
  3. CAT and everything else, which already has usable Last.fm data.

Matching is deliberately conservative. An Art Track title comes from
the distributor's delivery, so an exact match on the normalised title
is strong evidence; anything softer is left for staff rather than
guessed, because a wrong match doesn't look wrong — it looks like a
song nobody plays. ponytail: exact-title only for now — it covered 76% of the recon
sample, and the `MATCH_DURADA` path costs a `videos.list` per candidate.
Wire it once the misses are shown to be title variants rather than
tracks the artist simply never released to YouTube.

    python manage.py descobrir_youtube [--budget N] [--limit N] [--dry-run]

# Spec: docs/architecture/pipeline.md
"""

from __future__ import annotations

import datetime
import logging
import re

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from ingesta.clients import youtube as yt
from ingesta.clients.lastfm import _normalize_track
from music.constants import DIES_CADUCITAT
from music.models import Artista, Canco, CancoYouTubeVideo
from ranking.models import SenyalDiari

logger = logging.getLogger(__name__)

# Leave room for the daily stats poll (~60 units) and a margin, so a
# discovery run can never starve the signal it exists to feed.
DEFAULT_BUDGET = 9_000

# Re-probing an artist we already failed to find costs another 100 units,
# so a miss is remembered for this long before we try again. New releases
# create Topic channels, hence not "never".
REINTENT_DIES = 30


def _norm(s: str) -> str:
    return _normalize_track(s or "").lower().strip()


# What may legitimately trail a song title on a band's own channel.
# Anything else means the title is a different song that merely contains
# ours as a substring.
# Whitespace alone must NOT qualify, or "Oxitocina" swallows "Oxitocina i
# Dopamina". After the title there has to be a real separator or a known
# decoration word.
_SEPARADOR_INICIAL = re.compile(r"^[\s\-–—|·:,]+")

_DECORACIO = re.compile(
    r"^\s*(?:[\-–—|·:,(\[]|"
    r"(?:ft|feat|featuring|amb|with|videoclip|video|vídeo|audio|àudio|"
    r"official|oficial|lyric|letra|directe|live|prod|remix|"
    r"acustic|acústic|clip|hd|4k)\b)",
    re.I,
)


def _conte_titol(titol_video: str, titol_canco: str, artista: str) -> bool:
    """True when the video is *this* song, not one that merely contains it.

    Word boundaries are not enough: "Llibertat" is a whole word inside
    "Buscant la llibertat", and that false match is exactly the shape
    this project decided to refuse rather than accept. The rule is that
    the song title must sit at the START of the title (after an optional
    leading artist name) and be followed only by decoration — a
    separator, a known tag, or the artist's own name.

        "auxili tarrinetes al sol ft dj trapella"  → accepted
        "exorcisme katta lana"                     → accepted
        "buscant la llibertat"   (not at start)    → refused
        "oxitocina i dopamina"   (real other song) → refused
    """
    candidats = [titol_video]
    if artista and titol_video.startswith(artista):
        # Prefix only, and once: a blanket replace also eats the artist
        # name where it belongs to the song — "Malalts · Som Malalts"
        # would lose the very words it needs to match.
        candidats.append(titol_video[len(artista) :])

    for cand in candidats:
        resta = _SEPARADOR_INICIAL.sub("", re.sub(r"\s+", " ", cand)).strip()
        if not resta.startswith(titol_canco):
            continue
        cua = resta[len(titol_canco) :]
        if cua.strip() == "":
            return True
        # The artist's name is legitimate decoration on either side.
        neta = _SEPARADOR_INICIAL.sub("", cua)
        if artista and neta.startswith(artista):
            # "Baby Toca'm · Katta Lana, Brauer": once the artist's own
            # name follows the title, what trails is a credit list, so we
            # stop policing it. The name is the evidence.
            return True
        if _DECORACIO.match(cua):
            return True
    return False


def _cua(limit: int | None) -> list[Artista]:
    """Artists still needing a Topic channel, blind spot first."""
    today = timezone.localdate()
    cutoff = today - datetime.timedelta(days=DIES_CADUCITAT)
    reintent = timezone.now() - datetime.timedelta(days=REINTENT_DIES)

    pendents = Artista.objects.filter(youtube_channel_id="").filter(
        Q(youtube_checked_at__isnull=True) | Q(youtube_checked_at__lt=reintent)
    )

    en_finestra = Canco.objects.filter(
        verificada=True, activa=True, data_llancament__gte=cutoff
    )
    senyal_ok = set(
        SenyalDiari.objects.filter(
            canco__in=en_finestra,
            data__gte=today - datetime.timedelta(days=14),
            error=False,
            lastfm_playcount__isnull=False,
        ).values_list("canco_id", flat=True)
    )
    cegues = en_finestra.exclude(id__in=senyal_ok)

    def _ordena(qs):
        return list(
            qs.annotate(n=Count("cancons", distinct=True))
            .order_by("-n", "pk")
            .distinct()
        )

    vist: set[int] = set()
    cua: list[Artista] = []
    for tram in (
        pendents.filter(cancons__in=cegues),
        pendents.filter(territoris__codi__in=["VAL", "BAL"], cancons__in=en_finestra),
        pendents.filter(cancons__in=en_finestra),
    ):
        for a in _ordena(tram):
            if a.pk in vist:
                continue
            vist.add(a.pk)
            cua.append(a)
            if limit and len(cua) >= limit:
                return cua
    return cua


class Command(BaseCommand):
    help = "Descobreix el canal Topic de YouTube dels artistes i aparella les cançons."

    def add_arguments(self, parser):
        parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts) -> None:
        if not settings.YOUTUBE_API_KEY:
            self.stdout.write(self.style.WARNING("YOUTUBE_API_KEY buit; no faig res."))
            return

        budget = opts["budget"]
        dry = opts["dry_run"]
        cua = _cua(opts["limit"])
        self.stdout.write(
            f"Artistes a la cua: {len(cua)} · pressupost {budget} unitats"
        )

        gastat = 0
        trobats = 0
        sense = 0
        aparellades = 0
        try:
            for artista in cua:
                if gastat + yt.COST_SEARCH + 2 * yt.COST_LIST > budget:
                    self.stdout.write("Pressupost exhaurit per avui.")
                    break
                if dry:
                    self.stdout.write(f"  [dry] {artista.nom}")
                    gastat += yt.COST_SEARCH
                    continue

                channel = yt.find_topic_channel(artista.nom)
                gastat += yt.COST_SEARCH
                artista.youtube_checked_at = timezone.now()
                if not channel:
                    sense += 1
                    artista.save(update_fields=["youtube_checked_at"])
                    continue

                playlist = yt.uploads_playlist(channel)
                gastat += yt.COST_LIST
                artista.youtube_channel_id = channel
                artista.youtube_uploads_playlist = playlist or ""
                artista.save(
                    update_fields=[
                        "youtube_channel_id",
                        "youtube_uploads_playlist",
                        "youtube_checked_at",
                    ]
                )
                trobats += 1
                if not playlist:
                    continue

                videos = yt.playlist_videos(playlist)
                gastat += yt.COST_LIST * max(1, (len(videos) + 49) // 50)
                aparellades += self._aparella(artista, videos)

                # Second lane: the artist's OWN channel, but only when a
                # human has designated it. Never guessed — see the field
                # comment on `Artista.youtube_canal_oficial`.
                if artista.youtube_canal_oficial:
                    gastat += self._carril_oficial(artista)
        except yt.QuotaExhausted as exc:
            self.stdout.write(self.style.WARNING(f"Quota de YouTube exhaurida: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Canals trobats: {trobats} · sense canal: {sense} · "
                f"cançons aparellades: {aparellades} · quota gastada: {gastat}"
            )
        )
        # WORK_DONE protocol: tq-run surfaces this so a run that resolves
        # nothing several days running is visible instead of silently OK.
        self.stdout.write(f"WORK_DONE={trobats + aparellades}")

    def _carril_oficial(self, artista: Artista) -> int:
        """Enumerate the official channel and attach its videos.

        Returns the quota spent. Titles here are decorated by the band
        ("AUXILI - TARRINETES AL SOL ft DJ Trapella"), so we look for the
        song title INSIDE the video title rather than requiring equality.
        That is looser than the Art Track rule and it is only safe
        because the channel identity is already settled: within a channel
        we know belongs to this artist, a title containing "Tarrinetes al
        sol" is that song. Across YouTube at large it would not be.
        """
        playlist = yt.uploads_playlist(artista.youtube_canal_oficial)
        cost = yt.COST_LIST
        if not playlist:
            return cost
        videos = yt.playlist_videos(playlist)
        cost += yt.COST_LIST * max(1, (len(videos) + 49) // 50)

        cancons = list(Canco.objects.filter(artista=artista))
        for v in videos:
            titol_norm = _norm(v["title"])
            for c in cancons:
                clau = _norm(c.nom)
                # Guard against short/common titles swallowing unrelated
                # videos: "Llibertat" must not match "Buscant la
                # llibertat". Substring only above a length floor, and the
                # match has to sit on a word boundary.
                if len(clau) < 3 or not _conte_titol(
                    titol_norm, clau, _norm(artista.nom)
                ):
                    continue
                CancoYouTubeVideo.objects.get_or_create(
                    canco=c,
                    video_id=v["video_id"],
                    defaults={"titol": v["title"][:300]},
                )
                break
        return cost

    def _aparella(self, artista: Artista, videos: list[dict]) -> int:
        """Link the artist's unmatched tracks to Art Tracks by title."""
        per_titol: dict[str, str] = {}
        for v in videos:
            per_titol.setdefault(_norm(v["title"]), v["video_id"])

        n = 0
        for canco in Canco.objects.filter(artista=artista, youtube_video_id=""):
            vid = per_titol.get(_norm(canco.nom))
            if not vid:
                continue
            canco.youtube_video_id = vid
            canco.youtube_match = Canco.MATCH_EXACTE
            canco.youtube_matched_at = timezone.now()
            canco.save(
                update_fields=[
                    "youtube_video_id",
                    "youtube_match",
                    "youtube_matched_at",
                ]
            )
            n += 1
        return n
