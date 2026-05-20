"""Re-export the data-migration body so tests can exercise the
backfill logic without spinning up Django's migration runner.

Migration modules whose name starts with a digit can't be imported
as plain Python (`import music.migrations.0073_…` is a syntax
error), so we import via `importlib.util` and surface `_backfill`
under a stable name here."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_migration():
    path = Path(__file__).parent / "0073_data_migrate_lastfm_prioritari.py"
    spec = importlib.util.spec_from_file_location("_migration_0073", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_backfill_lastfm_prioritari() -> None:
    """Execute the data-migration backfill against the live DB.

    The migration uses `apps.get_model(...)` which works equally
    well outside the migration runner — Django returns the live
    model state when no historical context is active, which is
    exactly what we want from a `@pytest.mark.django_db` test."""
    from django.apps import apps

    mod = _load_migration()

    class _DummyEditor:
        pass

    mod._backfill(apps, _DummyEditor())
