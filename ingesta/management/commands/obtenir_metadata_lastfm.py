"""Pull artist-level metadata from Last.fm into `Artista.lastfm_*`.

Usage:
    ./manage.py obtenir_metadata_lastfm
    ./manage.py obtenir_metadata_lastfm --limit 500
    ./manage.py obtenir_metadata_lastfm --artista-id 1234
    ./manage.py obtenir_metadata_lastfm --dry-run

Behaviour:
  * Single-instance `fcntl.flock` on `/tmp/lastfm_artist_sync.lock`.
  * Per artist (queue-priority order):
      1. `artist.getInfo` → fill bio/listeners/playcount/tags/images.
      2. `artist.getSimilar` (limit 100, match >= 0.3) → for each
         similar artist, find an existing Artista by `lastfm_nom` or
         case-insensitive `nom`. If found, increment
         `nb_similars_lastfm`. Otherwise create a pendent placeholder
         (`pendent_review=True`, `auto_descobert=True`,
         `font_descoberta="lastfm_similar"`).
      3. Stamp `lastfm_last_sync = now()`.
  * Idempotency: an artist re-processed within `--refresh-days`
    (default 7) is skipped entirely. Within a single sync the
    `nb_similars_lastfm` of every similar gets incremented exactly
    once because the work is gated by the source artist's recency,
    not the targets'.
  * Last.fm is rate-limited globally (`LASTFM_RATE_LIMIT`); expect
    ~2 requests per artist (info + similar).

Cron: 05:00 UTC daily, between backup and senyal ingestion.
"""

from __future__ import annotations

import datetime
import fcntl
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from ingesta.clients.lastfm import get_artist_info, get_artist_similar
from music.models import Artista

logger = logging.getLogger(__name__)

# Minimum Last.fm "match" score to even consider creating a pendent
# placeholder for a similar artist. Below this the network noise is
# too high (Last.fm exposes hundreds of weak matches).
MIN_SIMILAR_MATCH = 0.3


class Command(BaseCommand):
    help = "Pull Last.fm artist metadata (info + similar) into our DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Max artists to process this invocation (default 500).",
        )
        parser.add_argument(
            "--artista-id",
            type=int,
            default=None,
            help="Process only this Artista pk (ignores --refresh-days).",
        )
        parser.add_argument(
            "--refresh-days",
            type=int,
            default=7,
            help="Skip artists synced more recently than N days ago.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch + log but don't write to the DB.",
        )

    def handle(self, *args, **opts):
        lock_file = "/tmp/lastfm_artist_sync.lock"
        try:
            lock = open(lock_file, "w")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            self.stdout.write("Ja hi ha una instància corrent. Sortint.")
            return
        try:
            self._run(**opts)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def _run(self, **opts):
        limit = opts["limit"]
        refresh_days = opts["refresh_days"]
        artista_id = opts["artista_id"]
        dry_run = opts["dry_run"]

        if artista_id:
            try:
                a = Artista.objects.get(pk=artista_id)
            except Artista.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"No Artista pk={artista_id}"))
                return
            self._process(a, dry_run=dry_run)
            return

        cutoff = timezone.now() - timedelta(days=refresh_days)
        # Queue priority: aprovats first, oldest sync first (NULL = never
        # synced → highest priority within a tier). Honours the staff
        # lockout flag — homonym-collision artists who share their
        # Last.fm name with another act stay out of the queue entirely.
        qs = (
            Artista.objects.filter(
                Q(lastfm_last_sync__isnull=True) | Q(lastfm_last_sync__lt=cutoff)
            )
            .exclude(lastfm_auto_match_disabled=True)
            .annotate(
                _prio=Case(
                    When(aprovat=True, then=Value(0)),
                    When(pendent_review=True, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("_prio", "lastfm_last_sync", "pk")[:limit]
        )

        processed = 0
        for a in qs:
            self._process(a, dry_run=dry_run)
            processed += 1
        self.stdout.write(f"Processats {processed} artistes.")

    def _process(self, artista: Artista, *, dry_run: bool = False) -> None:
        if artista.lastfm_auto_match_disabled:
            self.stdout.write(
                f"  · {artista.nom} (pk={artista.pk}) … LFM lockout, skip"
            )
            return
        name = artista.lastfm_nom or artista.nom
        if not name:
            return
        self.stdout.write(f"  · {artista.nom} (pk={artista.pk}) …", ending="")

        info = get_artist_info(name)
        new_pendents = 0
        bumped_similars = 0

        if info:
            if not dry_run:
                self._fill_artist_fields(artista, info)
            similar = get_artist_similar(name, limit=100)
            for sim in similar:
                try:
                    match = float(sim.get("match") or 0)
                except (TypeError, ValueError):
                    match = 0.0
                if match < MIN_SIMILAR_MATCH:
                    continue
                sim_name = (sim.get("name") or "").strip()
                if not sim_name:
                    continue
                created = self._touch_similar(sim_name, dry_run=dry_run)
                if created:
                    new_pendents += 1
                else:
                    bumped_similars += 1

        if not dry_run:
            artista.lastfm_last_sync = timezone.now()
            artista.save(update_fields=["lastfm_last_sync"])

        self.stdout.write(
            f" info={'OK' if info else 'KO'}"
            f" similars(+{bumped_similars} bumped, +{new_pendents} new pendents)"
        )

    # ── Helpers ──────────────────────────────────────────────────────

    def _fill_artist_fields(self, artista: Artista, info: dict) -> None:
        """Copy fields from the Last.fm `artist` block into the Artista."""
        url = (info.get("url") or "").strip()
        if url:
            artista.lastfm_url = url

        stats = info.get("stats") or {}
        try:
            artista.lastfm_listeners = int(stats.get("listeners") or 0) or None
        except (TypeError, ValueError):
            pass
        try:
            artista.lastfm_playcount_total = int(stats.get("playcount") or 0) or None
        except (TypeError, ValueError):
            pass

        # Last.fm returns "0" / "1" as strings.
        ontour = info.get("ontour")
        if ontour is not None:
            artista.lastfm_ontour = str(ontour) == "1"

        bio = info.get("bio") or {}
        summary = (bio.get("summary") or "").strip()
        content = (bio.get("content") or "").strip()
        if summary:
            artista.lastfm_bio_summary = summary
        if content:
            artista.lastfm_bio_content = content
        published = (bio.get("published") or "").strip()
        if published:
            # Last.fm format: "12 Apr 2024, 09:23". Tolerate failure.
            for fmt in ("%d %b %Y, %H:%M", "%d %b %Y", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.datetime.strptime(published, fmt)
                    artista.lastfm_bio_published = timezone.make_aware(
                        parsed, timezone.get_current_timezone()
                    )
                    break
                except ValueError:
                    continue

        # Tags: `tags.tag` may be a dict or list.
        tag_block = (info.get("tags") or {}).get("tag")
        if isinstance(tag_block, dict):
            tag_block = [tag_block]
        if isinstance(tag_block, list):
            tags = [
                {
                    "name": (t.get("name") or "").strip(),
                    "url": (t.get("url") or "").strip(),
                    "count": t.get("count"),
                }
                for t in tag_block
                if (t.get("name") or "").strip()
            ]
            artista.lastfm_tags = tags

        # Images: list of {"#text": url, "size": "small"|"medium"|...}.
        sizes = {"small", "medium", "large", "extralarge"}
        for img in info.get("image") or []:
            if not isinstance(img, dict):
                continue
            sz = (img.get("size") or "").strip()
            url = (img.get("#text") or "").strip()
            if sz in sizes and url:
                setattr(artista, f"lastfm_image_{sz}", url)

        artista.save(
            update_fields=[
                "lastfm_url",
                "lastfm_listeners",
                "lastfm_playcount_total",
                "lastfm_ontour",
                "lastfm_bio_summary",
                "lastfm_bio_content",
                "lastfm_bio_published",
                "lastfm_tags",
                "lastfm_image_small",
                "lastfm_image_medium",
                "lastfm_image_large",
                "lastfm_image_extralarge",
            ]
        )

    def _touch_similar(self, sim_name: str, *, dry_run: bool) -> bool:
        """Find or create an Artista for a similar-name match.

        Returns True when a new pendent was created, False otherwise.
        Increments `nb_similars_lastfm` either way (counts the
        recommendation; idempotency is guaranteed by the source-artist
        recency gate one level up).
        """
        target = (
            Artista.objects.filter(
                Q(lastfm_nom__iexact=sim_name) | Q(nom__iexact=sim_name)
            )
            .order_by("-aprovat", "pk")
            .first()
        )
        created = False
        if target is None:
            if dry_run:
                return True
            target = Artista.objects.create(
                nom=sim_name,
                lastfm_nom=sim_name,
                aprovat=False,
                pendent_review=True,
                auto_descobert=True,
                font_descoberta="lastfm_similar",
                nb_similars_lastfm=1,
            )
            created = True
        else:
            if not dry_run:
                Artista.objects.filter(pk=target.pk).update(
                    nb_similars_lastfm=(target.nb_similars_lastfm or 0) + 1
                )
        return created
