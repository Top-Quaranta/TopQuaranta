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
from django.db.models import Q
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
        # See `music.locks.SingletonLock` for the exit-75 design.
        from music.locks import SingletonLock

        with SingletonLock("lastfm_artist_sync"):
            self._run(**opts)

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
        # Only approved artistes act as discovery sources. Second-level
        # discovery (pendent → pendent edges) used to be enabled via a
        # _prio=1 tier but saturated the backlog without adding signal:
        # the review queue is the bottleneck, not the recommendation
        # graph (2026-05-12 empirical audit: 61 % of all edges came
        # from pendent sources, mostly inheriting noise from the
        # initial Crator-style genre cascades).
        #
        # Side-effect: pendents no longer get their lastfm_* metadata
        # auto-enriched. Staff who need it can trigger a one-shot
        # sync via `--artista-id <pk>` from the staff panel.
        # Lockout flag still excludes homonym-collision artistes.
        qs = (
            Artista.objects.filter(aprovat=True)
            .filter(Q(lastfm_last_sync__isnull=True) | Q(lastfm_last_sync__lt=cutoff))
            .exclude(lastfm_auto_match_disabled=True)
            .order_by("lastfm_last_sync", "pk")[:limit]
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

        # Sprint S Bloc D follow-up (2026-05-06): pass the MBID when
        # we have one *and* always pass autocorrect=0. Two layers of
        # the same disambiguation:
        #   - MBID lookup wins on Last.fm's side and skips name-based
        #     autocorrect entirely.
        #   - autocorrect=0 (the API equivalent of `/music/+noredirect/`
        #     on the website) suppresses the silent merge that turns
        #     "Fades" into "The Fades" or "Miley Cyrus" into the wrong
        #     entry — relevant on the no-MBID fallback path.
        # We trust `artista.lastfm_nom` (curated by staff). If it
        # mismatches, returning None is what we want — staff will see
        # the empty stats and either fix the name or set
        # `lastfm_auto_match_disabled=True`.
        mbid = artista.musicbrainz_id or None
        info = get_artist_info(name, mbid=mbid, autocorrect=False)
        new_pendents = 0
        bumped_similars = 0

        if info:
            if not dry_run:
                self._fill_artist_fields(artista, info)
            similar = get_artist_similar(name, limit=100, mbid=mbid, autocorrect=False)
            # Per-source dedup: many Last.fm pages list the same
            # artist under multiple spellings ('Delên' AND 'dêlen'
            # in the same response). Resolving each candidate
            # through the alias table collapses the variants onto
            # one target, so the count of unique recommenders stays
            # honest. Caught 2026-05-01.
            seen_target_pks: set[int] = set()
            new_targets: list[tuple[Artista, float]] = []
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
                # `artist.getSimilar` includes the MBID per similar
                # when Last.fm has it. Pass it down so the resolver
                # can match by MusicBrainz ID — Last.fm's `name`
                # field is its CANONICAL spelling (autocorrected at
                # index time), so a Mallorcan "Fades" recommended
                # by another artiste comes back as "The Fades" if
                # Last.fm has merged the pages. Resolving by MBID
                # avoids creating a "The Fades" pendent that points
                # at our actual Mallorcan band.
                sim_mbid = (sim.get("mbid") or "").strip() or None
                target, created = self._resolve_similar_target(
                    sim_name, sim_mbid=sim_mbid, dry_run=dry_run
                )
                if target is None:
                    continue
                if target.pk == artista.pk:
                    # Last.fm sometimes lists the artist as similar
                    # to itself via a variant spelling; ignore.
                    continue
                if target.pk in seen_target_pks:
                    continue
                seen_target_pks.add(target.pk)
                new_targets.append((target, match))
                if created:
                    new_pendents += 1
                else:
                    bumped_similars += 1
            if not dry_run:
                self._replace_similars(artista, new_targets)

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
        from ingesta.clients.lastfm import to_noredirect_url

        url = (info.get("url") or "").strip()
        if url:
            # Store the `+noredirect` form so every UI link clicks
            # straight to the literal page (the website otherwise
            # silently merges low-listener artists into namesakes —
            # Fades → The Fades). API-layer twin of autocorrect=0.
            artista.lastfm_url = to_noredirect_url(url)

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

    def _resolve_similar_target(
        self, sim_name: str, *, sim_mbid: str | None = None, dry_run: bool
    ) -> tuple[Artista | None, bool]:
        """Resolve a similar-name to a canonical Artista, alias-aware.

        Lookup order (case-insensitive). Step 0 (MBID) wins over name
        matching: Last.fm's `name` field on similar entries is the
        canonical spelling (autocorrected at index time), so a
        Mallorcan "Fades" listed as a similar comes back as "The
        Fades" — the WRONG band's name. The MBID, when present,
        unambiguously identifies our intended target. Step 2
        (alias-of-approved) beats step 3 (literal-match of pendent)
        by design — catches stale duplicates created before the
        alias path existed.

        Caught 2026-05-01 with Anna Roig: the canonical (ASCII
        apostrophe) was approved at pk=6717 with a confirmed alias
        for the typographic spelling. A stale pendent at pk=7078
        also held that typographic spelling. The first version of
        this function found pk=7078 first; new order resolves the
        alias to pk=6717.

        Caught 2026-05-07 with Fades: 22 "The Fades" pendents had
        accumulated because Last.fm's `getSimilar` returned them as
        the canonical spelling for what was originally our Mallorcan
        Fades. MBID lookup (step 0) is the fix.

          0. ANY Artista with the given MusicBrainz ID (approved or
             pendent — MBID is unique). Skipped when no mbid given
             or no row matches.
          1. APPROVED Artista with lastfm_nom OR nom matching.
          2. APPROVED Artista via confirmed ArtistaLastfmAlias.
          3. NON-approved Artista with lastfm_nom OR nom matching.
          4. Create new pendent placeholder.

        Returns (artista_or_None, created_flag).
        """
        from music.models import ArtistaLastfmAlias

        # 0. MBID lookup — wins over name when Last.fm has the right
        # MBID for this similar. Doesn't filter on aprovat: matching
        # on a pendent that already exists at the right MBID is
        # better than creating a duplicate at the autocorrected name.
        if sim_mbid:
            by_mbid = (
                Artista.objects.filter(musicbrainz_id=sim_mbid)
                .order_by("-aprovat", "pk")  # approved beats pendent
                .first()
            )
            if by_mbid is not None:
                return by_mbid, False

        # 1. Approved artist by canonical name.
        approved = (
            Artista.objects.public()
            .filter(Q(lastfm_nom__iexact=sim_name) | Q(nom__iexact=sim_name))
            .order_by("pk")
            .first()
        )
        if approved is not None:
            return approved, False

        # 2. Approved artist via a confirmed alias. Beats step 3:
        # an alias-of-approved is more authoritative than a stale
        # pendent that happens to share the literal spelling.
        alias = (
            ArtistaLastfmAlias.objects.filter(
                nom__iexact=sim_name,
                confirmat=True,
                artista__aprovat=True,
            )
            .select_related("artista")
            .order_by("artista__pk")
            .first()
        )
        if alias is not None:
            return alias.artista, False

        # 3. Any non-approved artist matching the literal name.
        non_approved = (
            Artista.objects.filter(aprovat=False)
            .filter(Q(lastfm_nom__iexact=sim_name) | Q(nom__iexact=sim_name))
            .order_by("pk")
            .first()
        )
        if non_approved is not None:
            return non_approved, False

        # 4. Nothing matched → create a pendent placeholder.
        if dry_run:
            return None, True
        target = Artista.objects.create(
            nom=sim_name,
            lastfm_nom=sim_name,
            aprovat=False,
            pendent_review=True,
            auto_descobert=True,
            font_descoberta="lastfm_similar",
        )
        return target, True

    def _replace_similars(
        self, source: Artista, targets: list[tuple[Artista, float]]
    ) -> None:
        """Replace `source`'s entire set of similar→target rows with
        the freshly-resolved one, then recompute the cached
        `nb_similars_lastfm` on every affected target.

        Idempotent: re-running for the same source produces the same
        end state regardless of how many times Last.fm's response
        has shifted between calls.
        """
        from music.models import ArtistaLastfmSimilar

        # Capture the previous targets so their cached counts get
        # recomputed too (in case some are no longer recommended).
        previous_target_ids = set(
            ArtistaLastfmSimilar.objects.filter(source=source).values_list(
                "target_id", flat=True
            )
        )
        ArtistaLastfmSimilar.objects.filter(source=source).delete()
        ArtistaLastfmSimilar.objects.bulk_create(
            [
                ArtistaLastfmSimilar(source=source, target=t, match=m)
                for t, m in targets
            ],
            ignore_conflicts=True,
        )
        affected_target_ids = previous_target_ids | {t.pk for t, _ in targets}
        for tid in affected_target_ids:
            count = ArtistaLastfmSimilar.objects.filter(target_id=tid).count()
            Artista.objects.filter(pk=tid).update(nb_similars_lastfm=count)
