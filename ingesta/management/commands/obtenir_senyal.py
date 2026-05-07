import logging
import unicodedata
from datetime import date, timedelta
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand, CommandError

from ingesta.clients.lastfm import (
    _normalize_track,
    get_track_info,
    get_track_info_literal,
)
from music.constants import DIES_CADUCITAT
from music.models import Canco
from ranking.models import SenyalDiari

logger = logging.getLogger(__name__)

# R5: fuzzy-match thresholds for detecting silent Last.fm autocorrect drift.
# Artist must match tightly — mistaking artist X for artist Y is the
# dangerous case. Track can vary more (remasters, remixes, punctuation).
_ARTIST_DRIFT_THRESHOLD = 0.90
_TRACK_DRIFT_THRESHOLD = 0.80


def _normalize_for_match(s: str) -> str:
    """Lowercase, strip accents + punctuation for fuzzy comparison."""
    if not s:
        return ""
    # NFD decomposes accents into base + combining char; drop combiners.
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    # Keep alphanumerics and whitespace only; collapse spaces.
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(s.split())


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(
        None, _normalize_for_match(a), _normalize_for_match(b)
    ).ratio()


def _detect_drift(
    asked_artist: str, asked_track: str, returned_artist: str, returned_track: str
) -> bool:
    """True if the returned names diverge significantly from what we asked.

    Normalises both sides through the same `(feat. X)` / `(Remaster)` /
    `- Live` stripping we apply before retry calls, so a legitimate
    Last.fm variant of the same recording (`"L'Empordà"` vs
    `"L'Empordà (Remaster 2015)"`) is NOT flagged as drift — it's the
    same track with a decoration. The dangerous case is a different
    artist's track being served.

    Empty returned names → treat as OK (shouldn't happen on success but
    be robust). Callers should skip this check entirely when the Canco
    has lastfm_confirmed=True.
    """
    if not returned_artist or not returned_track:
        return False
    asked_track_n = _normalize_track(asked_track)
    returned_track_n = _normalize_track(returned_track)
    artist_ratio = _fuzzy_ratio(asked_artist, returned_artist)
    track_ratio = _fuzzy_ratio(asked_track_n, returned_track_n)
    return (
        artist_ratio < _ARTIST_DRIFT_THRESHOLD or track_ratio < _TRACK_DRIFT_THRESHOLD
    )


class Command(BaseCommand):
    help = "Ingest daily Last.fm signal (playcount + listeners) for active tracks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data",
            type=str,
            default=None,
            help="Date to ingest for (YYYY-MM-DD). Defaults to today.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of tracks to process (for testing).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be ingested without calling Last.fm or writing to DB.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Parse target date
        if options["data"]:
            try:
                target_date = date.fromisoformat(options["data"])
            except ValueError:
                raise CommandError(
                    f"Invalid date format: {options['data']}. Use YYYY-MM-DD."
                )
        else:
            target_date = date.today()

        cutoff = target_date - timedelta(days=DIES_CADUCITAT)

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN — no API calls, no DB writes.\n")
            )

        self.stdout.write(f"Ingesting Last.fm signal for {target_date}...")
        self.stdout.write(f"  Release cutoff: {cutoff} (tracks older are excluded)")

        # Fetch eligible tracks
        cancons = (
            Canco.objects.filter(
                activa=True,
                verificada=True,
                artista__aprovat=True,
                data_llancament__gte=cutoff,
            )
            .select_related("artista")
            .order_by("pk")
        )

        total = cancons.count()
        self.stdout.write(f"  Eligible tracks: {total}")

        if options["limit"]:
            cancons = cancons[: options["limit"]]
            self.stdout.write(f"  Limited to: {options['limit']}")

        if dry_run:
            for c in cancons[:10]:
                self.stdout.write(
                    f"    Would ingest: '{c.artista.lastfm_nom}' / "
                    f"'{c.lastfm_lookup_nom}'"
                )
            if total > 10:
                self.stdout.write(f"    ... and {total - 10} more")
            return

        # Skip tracks already ingested for this date
        already_ingested = set(
            SenyalDiari.objects.filter(data=target_date).values_list(
                "canco_id", flat=True
            )
        )

        success = 0
        errors = 0
        skipped = 0
        drifts = 0  # R5: count of rows flagged with corregit=True this run
        # Artistes que hem vist amb playcount>0 en aquest run — els
        # marquem amb `lastfm_te_scrobbles=True` en bloc al final si
        # encara no ho estan. Evita fer un UPDATE per cada track.
        artist_ids_with_plays: set[int] = set()

        # P4: buffer SenyalDiari rows and flush every BULK_BATCH calls via
        # bulk_create(ignore_conflicts=True). The per-row update_or_create
        # in the previous implementation ran ~2 queries per track (SELECT
        # + INSERT/UPDATE); with ~1200 tracks that's ~2400 roundtrips.
        # bulk_create collapses each batch to one INSERT. `ignore_conflicts`
        # preserves "skip if already ingested" semantics without a second
        # safety net. Flushing periodically also keeps progress durable if
        # the process crashes mid-run.
        BULK_BATCH = 200
        buffer: list[SenyalDiari] = []

        def flush(b: list[SenyalDiari]) -> None:
            if b:
                SenyalDiari.objects.bulk_create(b, ignore_conflicts=True)
                b.clear()

        # Pre-fetch confirmed aliases per artist to avoid an N+1 query.
        # Most artists have 0 aliases; the dict stays cheap.
        from music.models import ArtistaLastfmAlias

        aliases_by_artist: dict[int, list[str]] = {}
        for a in ArtistaLastfmAlias.objects.filter(
            confirmat=True, rebutjat=False
        ).values("artista_id", "nom"):
            aliases_by_artist.setdefault(a["artista_id"], []).append(a["nom"])

        for i, canco in enumerate(cancons.iterator(), 1):
            if canco.pk in already_ingested:
                skipped += 1
                continue

            artist_name = canco.artista.lastfm_nom
            track_name = canco.lastfm_lookup_nom

            # May-2026 audit follow-up: skip rows with empty
            # `lastfm_nom`. Without this guard the request goes out
            # with `artist=""`, returns error 6, and the song
            # accumulates zero plays forever — a silent failure mode
            # invisible to staff because `error=True` looks like
            # any other transient Last.fm hiccup.
            if not artist_name:
                skipped += 1
                logger.warning(
                    "skip canco pk=%s — artista pk=%s has empty lastfm_nom",
                    canco.pk,
                    canco.artista_id,
                )
                continue

            # May-2026 audit follow-up: thread MBIDs through to
            # Last.fm. Recording-level MBID (when MB cron has matched
            # the track) makes the lookup immune to the homonym
            # redirect that artist-level autocorrect=0 also defends
            # against. Belt and braces.
            result = get_track_info(
                artist_name,
                track_name,
                track_mbid=canco.mb_recording_id or None,
                artist_mbid=canco.artista.musicbrainz_id or None,
            )

            # Sum playcounts/listeners across confirmed aliases of this
            # artist — the Last.fm fragmentation fix (2026-05-01). For
            # 'Boira' + 'Böira' this turns 1 681 plays into 23 168.
            # Aliases are queried with autocorrect=0 (literal page),
            # otherwise Last.fm redirects them all to the canonical and
            # we'd double-count.
            alias_names = aliases_by_artist.get(canco.artista_id, [])
            if result is not None and alias_names:
                for alias in alias_names:
                    # Pass canonical_artist so the literal lookup can
                    # detect Last.fm case-folding the alias into the
                    # canonical page (would otherwise double-count).
                    extra = get_track_info_literal(
                        alias, track_name, canonical_artist=artist_name
                    )
                    if extra is not None:
                        result["playcount"] += extra["playcount"]
                        result["listeners"] += extra["listeners"]

            if result is not None:
                # R5: compare what Last.fm ACTUALLY returned vs what we asked
                # for. lastfm_confirmed=True on the Canco is a staff-set
                # opt-out for tracks where the autocorrect is known-good.
                returned_artist = result.get("returned_artist", "")
                returned_track = result.get("returned_track", "")
                is_drift = not canco.lastfm_confirmed and _detect_drift(
                    artist_name, track_name, returned_artist, returned_track
                )
                if is_drift:
                    drifts += 1

                buffer.append(
                    SenyalDiari(
                        canco=canco,
                        data=target_date,
                        lastfm_playcount=result["playcount"],
                        lastfm_listeners=result["listeners"],
                        lastfm_returned_track=returned_track[:500],
                        lastfm_returned_artista=returned_artist[:255],
                        corregit=is_drift,
                        error=False,
                        error_msg="",
                    )
                )
                # Marca l'artista com a "té scrobbles" si hem vist
                # playcount > 0. Canco sense plays encara compta com a
                # "silent" — el flag és per distingir un artista
                # indexat de Last.fm d'un que no hi és.
                if result["playcount"] and not canco.artista.lastfm_te_scrobbles:
                    artist_ids_with_plays.add(canco.artista_id)
                success += 1
            else:
                buffer.append(
                    SenyalDiari(
                        canco=canco,
                        data=target_date,
                        lastfm_playcount=None,
                        lastfm_listeners=None,
                        lastfm_returned_track="",
                        lastfm_returned_artista="",
                        corregit=False,
                        error=True,
                        error_msg=(
                            f"Last.fm lookup failed for '{artist_name}' / "
                            f"'{track_name}'"
                        ),
                    )
                )
                errors += 1

            if len(buffer) >= BULK_BATCH:
                flush(buffer)

            if i % 100 == 0:
                self.stdout.write(
                    f"  Processed {i}... (ok={success}, err={errors}, "
                    f"skip={skipped}, drift={drifts})"
                )

        flush(buffer)

        # Mark newly-active artistes. Idempotent: artists already True
        # stay True; a single UPDATE per run.
        if artist_ids_with_plays:
            from music.models import Artista

            Artista.objects.filter(
                pk__in=artist_ids_with_plays, lastfm_te_scrobbles=False
            ).update(lastfm_te_scrobbles=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Ingestion complete for {target_date}:\n"
                f"    Success: {success}\n"
                f"    Errors:  {errors}\n"
                f"    Skipped (already ingested): {skipped}\n"
                f"    Drift-flagged (corregit=True): {drifts}\n"
                f"    Newly-active artistes: {len(artist_ids_with_plays)}\n"
                f"    Total processed: {success + errors + skipped}"
            )
        )

        # `tq-run` watchdog protocol (2026-05-07): the LAST line matching
        # `^WORK_DONE=<int>$` becomes `work_done=N` in the status file.
        # `tq-run` then tracks `consecutive_zero_work` so a stuck cron
        # (returning 0 every tick) becomes visible at /staff/estat
        # without a hand-tuned per-command threshold. We count rows
        # actually written to SenyalDiari (success + errors); skipped
        # is "already done by an earlier run today" and shouldn't
        # reset the zero-counter.
        self.stdout.write(f"WORK_DONE={success + errors}")

        # 2026-04-23 (algorithm v2.0): the percentile-rank normalisation
        # used to run here. It's gone — the new ranking algorithm consumes
        # raw `lastfm_playcount` deltas directly (see ranking/algorisme.py).
