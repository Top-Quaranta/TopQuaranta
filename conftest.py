from contextlib import contextmanager
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _bypass_singleton_lock():
    """Replace SingletonLock with a no-op context manager for all tests.

    The real SingletonLock flocks files under /tmp/. On the Hetzner box
    the cron creates them as topquaranta and ``fs.protected_regular=2``
    prevents root from reopening them (and vice-versa). This fixture
    removes the cross-user collision so ``pytest`` runs cleanly
    regardless of who executes it.

    Pattern from ``test_obtenir_novetats_cooldown.py`` (2026-05-01),
    promoted to project-wide conftest (2026-05-23).
    """

    @contextmanager
    def _noop_lock(*args, **kwargs):
        yield

    with patch("music.locks.SingletonLock", _noop_lock):
        yield
