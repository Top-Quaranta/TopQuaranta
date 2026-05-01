"""Single-instance locking for management commands.

Uses fcntl flock so the lock is automatically released by the kernel
on process death (no stale lock files surviving crashes).

Critical design choice — exit code 75 (EX_TEMPFAIL) when the lock
is already held:

  Background: a long-running command holding the lock for hours/days
  blocks every subsequent hourly cron tick. Before this helper, the
  blocked tick exited with status 0 ("Ja hi ha una instància
  corrent. Sortint."), and `tq-run` wrote `status=OK` with a fresh
  `last_run=now`. Result: `tq-health` saw a healthy-looking
  status entry refreshed every hour while the actual ingestion had
  been stuck for days. Caught 2026-05-01 with `obtenir_novetats`
  hung for ~12 days while every hourly tick reported OK.

  Fix: exit 75 (EX_TEMPFAIL, the conventional Unix code for
  "transient skip"). `tq-run` is taught to treat 75 specially —
  writes `status=SKIPPED_BY_LOCK` *without* touching `last_run`,
  so the previous successful run's timestamp is preserved. After
  N consecutive hourly skips, `last_run` falls outside
  `tq-health`'s max-age window and the alert fires.
"""

from __future__ import annotations

import fcntl
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

EXIT_LOCK_HELD = 75  # EX_TEMPFAIL


class SingletonLock:
    """Acquire a per-command file lock, or call `sys.exit(75)`.

    Used as a context manager so the lock is held for the duration
    of the protected work and released cleanly on exit (or kernel-
    released on crash).

    Usage::

        with SingletonLock("mb_sync"):
            do_the_work()

    The lockfile lives at /tmp/<name>.lock. Holds the file open for
    the lifetime of the context (closing the fd releases the flock).
    """

    def __init__(self, name: str, lock_dir: str = "/tmp"):
        self.path = Path(lock_dir) / f"{name}.lock"
        self._fd = None

    def __enter__(self):
        self._fd = open(self.path, "w")
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # Another instance already holds the lock. Print to
            # stdout for the cron log, then exit 75 so tq-run
            # records this as SKIPPED_BY_LOCK and preserves the
            # previous successful `last_run`.
            self._fd.close()
            self._fd = None
            sys.stdout.write(
                f"Ja hi ha una instància corrent ({self.path.name}). "
                f"Sortint amb exit 75 (skipped-by-lock).\n"
            )
            sys.exit(EXIT_LOCK_HELD)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            self._fd.close()
            self._fd = None
        return False  # don't swallow exceptions
