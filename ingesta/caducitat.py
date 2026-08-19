# Spec: docs/architecture/ingesta.md
"""Caducity guard shared by every Canco-creation frontier.

`DIES_CADUCITAT` is the project's hard "tracks older than this don't
enter the active pool" rule (`music/constants.py`). Historically the
window was enforced at the *queue* level — `obtenir_novetats` P3
asked Deezer for `min_date=cutoff`, `obtenir_metadata` likewise, the
ranking math filtered on `data_llancament`, and `netejar_caducades`
swept the survivors every night. But the queue-level filter has
holes:

  * Deezer's `release_date` can be empty/unparseable at the artist-
    albums level, so the album passes through `get_artist_albums`
    unfiltered.
  * The "Fix album date" step inside the track-creation helpers can
    *rewind* `album.data_llancament` to an older value (track-level
    `album_release_date` < album's) AFTER the queue gate ran.
  * `netejar_caducades` deletes physically and leaves no trail in
    `HistorialRevisio`, so on the next P2 tick (≥30 days later for
    >365-day albums) `_previously_rejected()` finds nothing, the
    `deezer_id` dedup misses (the row is physically gone), and the
    same ancient tracks reappear in the staff pendents queue. Real
    case caught 2026-06-02: Tres Fan Ball 1994/1997/2005/2013 albums
    recreating 38 pendents every ~30 days.

This helper closes the hole at the *creation* frontier: every code
path that is about to call `Canco.objects.create(...)` (or
`get_or_create`/`update_or_create` with insert intent) must consult
`is_caducat(album.data_llancament, cutoff)` first.

NULL handling is intentional and explicit: `data_llancament=NULL` is
treated as "unknown → do not caducate", preserving current behaviour.
The wider NULL hole (`netejar_caducades` also skips NULLs, so files
with NULL `data_llancament` accumulate in the staff queue indefinitely)
is a separate, known follow-up — not addressed here.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from music.constants import DIES_CADUCITAT

if TYPE_CHECKING:
    from django.db.models import QuerySet


def caducitat_cutoff(today: date | None = None) -> date:
    """The `data_llancament` boundary: anything strictly older than the
    returned date is past `DIES_CADUCITAT`. `today` is overridable for
    deterministic tests."""
    if today is None:
        today = date.today()
    return today - timedelta(days=DIES_CADUCITAT)


def is_caducat(data_llancament: date | None, cutoff: date) -> bool:
    """Return True iff `data_llancament` is set AND strictly older
    than `cutoff` (i.e. past the `DIES_CADUCITAT` window).

    NULL → False (unknown date is treated as "don't caducate"; same
    semantics as `netejar_caducades`, which uses a `__lt` filter that
    excludes NULLs)."""
    return data_llancament is not None and data_llancament < cutoff


def exclude_caducats(qs: QuerySet, today: date | None = None) -> QuerySet:
    """Queryset mirror of `is_caducat`: drop rows whose `data_llancament`
    is strictly older than the caducity cutoff, KEEPING both recent and
    NULL-dated rows.

    This returns EXACTLY the survivor set of `netejar_caducades`, which
    deletes `data_llancament__lt=cutoff` — a `__lt` filter, so NULLs are
    never matched and therefore kept. Use it wherever a queryset must
    contain exactly the purge survivors, e.g. the `enriquir_spotify`
    pending pool, so the equity floor never spends a slot on a track the
    04:00 purge will delete an hour later. Same `caducitat_cutoff()` and
    same NULL treatment as the purge and `is_caducat`; no second cutoff.
    """
    return qs.exclude(data_llancament__lt=caducitat_cutoff(today))
