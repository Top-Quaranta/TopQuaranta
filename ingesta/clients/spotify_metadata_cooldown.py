"""Shared cooldown for the Spotify metadata-read endpoints.

Both the maintenance enrichment (`enriquir_spotify`) and the
historical-rebuig backfill (`enriquir_spotify_rebuigs`) hit the
same Spotify quota bucket (`/v1/search`, `/v1/tracks`,
`/v1/artists`). When Spotify hands back a long `Retry-After` on
ANY of those endpoints, both commands must back off; calling
during an active ban is documented to extend the window (see the
comment in `enriquir_spotify.py:60`).

Until 2026-05-25 each command kept its own cooldown file in
`/var/log/topquaranta/status/`. A ban observed by one was
invisible to the other, so the backfill could keep hammering the
quota while maintenance was already in ban. This module
consolidates the cooldown into a single file both commands write
to and read from. The AIMD controller in
`spotify_backfill_controller.py` looks at the same path.

Playlist-write endpoints (`/v1/playlists/<id>/items`) sit in a
SEPARATE bucket per the 2026-05-24 audit: the maintenance
playlist sync ran successfully during a long metadata ban without
extending it. So the playlist sync is intentionally NOT routed
through this cooldown.

Transition from the legacy per-command cooldown files
-----------------------------------------------------
The transition window has to keep the active ban respected even
if the legacy file is the only place it was written. `is_active()`
checks the SHARED path first, then falls back to each LEGACY
path; the latest unexpired `resume_at` wins. New writes always
land in the shared path, so the legacy files drain naturally as
their bans expire.

# Spec: docs/architecture/pipeline.md
"""

from __future__ import annotations

import logging
from datetime import datetime
from datetime import timezone as dt_tz
from pathlib import Path

logger = logging.getLogger(__name__)

STATUS_DIR = Path("/var/log/topquaranta/status")

# Canonical shared cooldown file. Written by both maintenance and
# backfill enrichment. Anything that talks to the Spotify
# metadata-read endpoints MUST check this before issuing the
# first call of a run.
SHARED_PATH = STATUS_DIR / "spotify_metadata.cooldown"

# Legacy per-command cooldown files. Read for backward
# compatibility during the transition: a live ban written by an
# older binary must keep being honoured by the new code. The
# files get pruned automatically when their `resume_at` passes.
LEGACY_PATHS = (
    STATUS_DIR / "enriquir_spotify.cooldown",
    STATUS_DIR / "enriquir_spotify_rebuigs.cooldown",
)


def _utcnow_naive() -> datetime:
    return datetime.now(tz=dt_tz.utc).replace(tzinfo=None)


def _read_resume_at(path: Path) -> datetime | None:
    """Parse the ISO-8601 `resume_at` written in `path`. Returns
    None on any IO / parse error so a corrupt file behaves like an
    absent one."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        logger.warning(
            "Spotify metadata cooldown file %s has unparsable "
            "contents (%r); treating as absent.",
            path,
            text,
        )
        return None


def active_resume_at(
    shared: Path | None = None,
    legacy: tuple[Path, ...] | None = None,
    now: datetime | None = None,
) -> datetime | None:
    """Return the most distant unexpired `resume_at` across the
    shared cooldown and the legacy files, or None if no ban is
    active.

    Picking the latest of all unexpired values means the longest
    pending back-off wins, which is conservative and matches the
    intent of "respect any active ban from any source".
    """
    if shared is None:
        shared = SHARED_PATH
    if legacy is None:
        legacy = LEGACY_PATHS
    now = now or _utcnow_naive()
    candidates: list[datetime] = []
    for path in (shared, *legacy):
        resume = _read_resume_at(path)
        if resume is not None and resume > now:
            candidates.append(resume)
    if not candidates:
        return None
    return max(candidates)


def is_active(
    shared: Path | None = None,
    legacy: tuple[Path, ...] | None = None,
    now: datetime | None = None,
) -> bool:
    """Convenience boolean wrapper around `active_resume_at`."""
    return active_resume_at(shared=shared, legacy=legacy, now=now) is not None


def write(
    resume_at: datetime,
    shared: Path | None = None,
) -> None:
    """Persist a new ban window to the shared cooldown file.

    The legacy files are intentionally NOT touched: new writes
    only go into the shared path so the transition is
    monotonically forward. A legacy file remains active until it
    naturally expires.
    """
    if shared is None:
        shared = SHARED_PATH
    shared.parent.mkdir(parents=True, exist_ok=True)
    shared.write_text(resume_at.isoformat(), encoding="utf-8")


def clear_expired(
    shared: Path | None = None,
    legacy: tuple[Path, ...] | None = None,
    now: datetime | None = None,
) -> None:
    """Delete cooldown files whose `resume_at` is in the past.
    Idempotent: missing files are silently skipped.

    Called by each command when it wakes up and finds no active
    ban, so an expired sentinel does not stay on disk forever.
    Keeps the historical state clean for the AIMD controller
    (which uses mtimes to detect fresh bans, and a never-deleted
    expired file would re-look fresh after every commit touch)."""
    if shared is None:
        shared = SHARED_PATH
    if legacy is None:
        legacy = LEGACY_PATHS
    now = now or _utcnow_naive()
    for path in (shared, *legacy):
        resume = _read_resume_at(path)
        if resume is None:
            continue
        if resume <= now:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
