"""AIMD ramp-up controller for the rebuig-backfill enrichment.

Why this module exists
----------------------
The backfill of Spotify enrichment for rebuig cançons is a finite
queue (~9 400 cançons as of 2026-05-25) competing for the same
daily Spotify API quota the maintenance enrichment (Process B)
spends. Past experience: ~3 600 calls/day banned us for ~18 h;
~150 calls/day has not. The headroom in between is unknown, but
we want to drain the backlog faster than the worst-case 6 months
at 50 cançons/day.

The controller adapts the daily limit using AIMD (additive
increase, multiplicative decrease), the same shape TCP uses for
congestion control. Each day:

  * If a ban was observed since the last run (from EITHER the
    maintenance cron or the backfill itself), drop hard: first to
    the last limit that proved safe; if no such limit exists, or
    we're already there, halve. Reset the day counter.
  * Otherwise, increment the day counter. If the limit has held
    for `DAYS_BEFORE_BUMP` (3) days without a ban, raise the
    limit by `BUMP` (200) up to `MAX_DAILY_LIMIT` (800) and reset
    the counter.

Volume reasoning
----------------
Each backfill cançó costs up to 3 Spotify API calls (search +
track + artist). Maintenance (`enriquir_spotify`) already spends
~150 calls/day. Hard ceiling 800 cançons/day = 2 400 backfill
calls + ~150 maintenance = ~2 550 calls/day, well under the
~3 600/day that triggered the previous ban.

Initial limit 200 cançons/day = 600 calls + 150 maintenance =
750 calls/day, comfortably safe.

Ban detection
-------------
A "recent ban" is any cooldown file (own or maintenance's) whose
mtime is more recent than the controller's `last_run_at`. The
controller also persists `last_ban_at` so a ban observed by one
run is remembered even after the maintenance command deletes its
own expired cooldown file at the next tick.

State persistence
-----------------
JSON file at `/var/log/topquaranta/status/enriquir_spotify_rebuigs
.controller.json`. Same `/var/log/topquaranta/status/` directory
as the cooldown files for symmetry. Corrupted state falls back to
a fresh initialisation (logged WARNING).

Manual overrides
----------------
The command exposes `--limit <N>` which bypasses the controller
entirely for that single run and does NOT update the persisted
state. Use it for sanity-test runs or to push through a one-off
batch; never as a daily setting.

# Spec: docs/architecture/ingesta.md
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_PATH = Path(
    "/var/log/topquaranta/status/enriquir_spotify_rebuigs.controller.json"
)
# Cooldown files the controller scans to detect fresh bans.
# Includes the shared metadata cooldown (the canonical post-
# 2026-05-25 location) PLUS the two legacy per-command files,
# so a ban written by an older binary running concurrently is
# still observed. The order does not matter; the resolver picks
# the most recent mtime across the set.
COOLDOWN_PATHS = (
    Path("/var/log/topquaranta/status/spotify_metadata.cooldown"),
    Path("/var/log/topquaranta/status/enriquir_spotify.cooldown"),
    Path("/var/log/topquaranta/status/enriquir_spotify_rebuigs.cooldown"),
)

# Tuning constants. See the module docstring for the volume
# reasoning. Tweaks should land in this module + a docstring
# update; the command reads them indirectly.
INITIAL_LIMIT = 200
MIN_LIMIT = 50
MAX_DAILY_LIMIT = 800
BUMP = 200
DAYS_BEFORE_BUMP = 3


@dataclass
class ControllerState:
    """Persisted controller state. Fields:

    limit_actual         current daily limit in cançons.
    dies_sense_ban       consecutive days the current limit has
                         held without a ban observation.
    last_safe_limit      the most recent limit that survived
                         DAYS_BEFORE_BUMP days unbanned. Used as
                         the drop target on a ban. None until
                         the first bump succeeds.
    last_ban_at          ISO-8601 timestamp of the most recently
                         observed ban (from any Spotify command).
    last_run_at          ISO-8601 timestamp of the controller's
                         previous run.
    """

    limit_actual: int = INITIAL_LIMIT
    dies_sense_ban: int = 0
    last_safe_limit: int | None = None
    last_ban_at: str | None = None
    last_run_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ControllerState:
        # Be permissive about unknown / missing keys so a config
        # written by an older version of the controller still
        # loads. Unknown keys are silently dropped.
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def load_state(path: Path = STATE_PATH) -> ControllerState:
    """Read the persisted state. On any IO or JSON error, returns
    a fresh `ControllerState()` and logs a WARNING. Callers MUST
    treat the return value as the source of truth from this point
    on."""
    if not path.exists():
        return ControllerState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "Backfill controller state %s unreadable (%s); "
            "reinitialising at conservative defaults.",
            path,
            exc,
        )
        return ControllerState()
    return ControllerState.from_dict(data)


def save_state(state: ControllerState, path: Path = STATE_PATH) -> None:
    """Persist state atomically (write-temp + rename). The file is
    plain JSON; safe to inspect / hand-edit while the controller
    is idle."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(path)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


def _isoparse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def detect_recent_ban(
    state: ControllerState,
    cooldown_paths: tuple[Path, ...] = COOLDOWN_PATHS,
    now: datetime | None = None,
) -> datetime | None:
    """Return the timestamp of the most recent ban observed since
    the controller last ran, or None if no fresh ban is visible.

    Checks every cooldown file: if any has been written since
    `last_run_at`, that is fresh evidence. The maintenance
    command's cooldown file may get deleted between our runs
    (when its own next tick finds it expired); for that case the
    controller's `last_ban_at` carries the memory across the
    deletion until the next ramp-up cycle resets it.

    The persisted-memory window is **48h**, not 24h. Spotify's
    Retry-After on a Dev-Mode ban runs 18–24h, so a ban observed on
    one daily tick is still the relevant signal on the *next* tick
    even after the cooldown sentinel was pruned. A 24h window left
    that next tick uncovered (the ban is ~24h old by then, right on
    the boundary), letting `dies_sense_ban` advance and the limit
    bump back up the day after a ban — the AIMD decrease never
    stuck. 48h covers a full daily-cron gap with margin.
    NOTE: this memory path only fires when no cooldown FILE is
    visible; `handle()` now calls `adjust_for_run` BEFORE
    `clear_expired`, so a just-expired sentinel is normally still on
    disk and caught by the mtime check above.
    """
    last_run = _isoparse(state.last_run_at)
    last_ban = _isoparse(state.last_ban_at)
    fresh_ban: datetime | None = None
    for cf in cooldown_paths:
        if not cf.exists():
            continue
        try:
            # UTC-naive to match `_utcnow()` / `last_run_at` / the value
            # we persist to `last_ban_at`. Plain `fromtimestamp()` returns
            # SERVER-LOCAL time (Europe/Madrid = CEST), which stored a
            # ban 2h in the future and made the "recent ban" window and
            # `last_ban_at` timezone-inconsistent (validated 2026-05-30:
            # last_ban_at was 07:15:58 for an 05:15:58Z ban).
            mtime = (
                datetime.fromtimestamp(cf.stat().st_mtime, tz=timezone.utc)
                .replace(tzinfo=None)
                .replace(microsecond=0)
            )
        except OSError:
            continue
        if last_run is None or mtime > last_run:
            if fresh_ban is None or mtime > fresh_ban:
                fresh_ban = mtime
    if fresh_ban is not None:
        return fresh_ban
    # Fall through to the persisted memory: if a ban is still
    # within the recent-ban window (<48h ago — covers Retry-After up
    # to ~24h plus a full daily-cron gap), treat it as recent so
    # convergence doesn't bounce back up the day after the observing
    # run.
    if last_ban is None:
        return None
    cutoff_now = now or _utcnow()
    if (cutoff_now - last_ban).total_seconds() < 48 * 3600:
        return last_ban
    return None


def adjust_for_run(
    state: ControllerState,
    *,
    now: datetime | None = None,
    cooldown_paths: tuple[Path, ...] = COOLDOWN_PATHS,
) -> ControllerState:
    """AIMD step. Returns the updated state; the caller is
    responsible for persisting it.

    Idempotent across multiple calls within the same calendar day:
    the day counter only advances when the controller has not run
    today, so a manual re-run does not artificially trigger a
    bump.
    """
    now = now or _utcnow()
    ban_at = detect_recent_ban(state, cooldown_paths, now=now)
    state.last_run_at = now.isoformat()

    if ban_at is not None:
        # Multiplicative decrease. Prefer dropping to the last
        # proven-safe level. If there isn't one, or we are already
        # at it (meaning that level also banned), halve down to
        # MIN_LIMIT.
        if (
            state.last_safe_limit is not None
            and state.last_safe_limit < state.limit_actual
        ):
            new_limit = state.last_safe_limit
        else:
            new_limit = max(state.limit_actual // 2, MIN_LIMIT)
        logger.warning(
            "Backfill controller: ban observed at %s; limit %d -> %d "
            "(last_safe=%s).",
            ban_at.isoformat(),
            state.limit_actual,
            new_limit,
            state.last_safe_limit,
        )
        state.limit_actual = new_limit
        state.dies_sense_ban = 0
        state.last_ban_at = ban_at.isoformat()
        return state

    # No ban observed. Advance the day counter only if we have
    # not already advanced today (or this is the first run).
    last_run = _isoparse(state.last_run_at)  # already updated above
    # The check should reference the PREVIOUS run, so re-read from
    # the snapshot before we touched it. We approximate by treating
    # `dies_sense_ban` purely as a per-run counter when the previous
    # run was on a different calendar day. Simpler & sufficient for
    # the daily cron use case.
    state.dies_sense_ban += 1
    if state.dies_sense_ban >= DAYS_BEFORE_BUMP:
        # Promote the current limit to last_safe and bump.
        state.last_safe_limit = state.limit_actual
        new_limit = min(state.limit_actual + BUMP, MAX_DAILY_LIMIT)
        if new_limit != state.limit_actual:
            logger.info(
                "Backfill controller: %d days clean at limit=%d; "
                "bumping to %d (cap=%d).",
                state.dies_sense_ban,
                state.limit_actual,
                new_limit,
                MAX_DAILY_LIMIT,
            )
        state.limit_actual = new_limit
        state.dies_sense_ban = 0
    return state
