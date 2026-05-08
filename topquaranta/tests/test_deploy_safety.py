"""Deploy-safety regression tests.

Anchor for the 2026-05-07 lesson learned: a `feat(ingest)` push
landed code that read `Album.label` BEFORE the migration adding
that column was applied. Gunicorn `--reload` picked up the new
code instantly; every visitor to `/album/<slug>` hit a 500 for
~15 minutes, sending one admin email per request — 30 emails
landed in the inbox before anyone noticed.

The structural fix is `bin/tq-deploy` (orders migrate → reload)
plus a `tq-health` row that surfaces pending migrations so the
hourly cron catches a desync within an hour even when the
operator bypasses `tq-deploy`. These tests guard the static
invariant — "every model change has a committed migration" —
that has to hold before either of those tools can help.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.django_db
def test_no_pending_model_migrations():
    """Every model change in the working tree must have a matching
    migration committed. Running `makemigrations --check --dry-run`
    exits non-zero if any model has changed since its last migration —
    the code-without-migration drift that produced the 2026-05-07
    `column music_album.label does not exist` 500 storm.

    CI's `migrations` job runs the same check, so this test is
    belt-and-braces on the local pytest path. Catching it locally is
    cheaper than catching it in CI which is cheaper than catching it
    in production logs.
    """
    out = io.StringIO()
    try:
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
    except SystemExit as exc:
        pytest.fail(
            "makemigrations --check failed — model changes without a "
            f"committed migration:\n{out.getvalue()}\n"
            f"exit={exc.code}"
        )


@pytest.mark.django_db
def test_no_unapplied_migrations_in_test_db():
    """The test DB used by pytest must have every committed migration
    applied. Asserts the MigrationLoader sees zero leaves outside
    `applied_migrations`. Equivalent of `manage.py migrate --check`
    in code form.

    This is a smoke check on the pytest fixture chain: if migrations
    are committed but pytest isn't running them (e.g. broken
    `pytest-django` config) the production runtime check would
    catch the desync, but locally we'd never see it.
    """
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    leaves = set(loader.graph.leaf_nodes())
    applied = set(loader.applied_migrations.keys())
    pending = leaves - applied
    assert pending == set(), f"Migrations committed but not applied: {pending}"


def test_tq_deploy_script_is_executable_and_well_formed():
    """`bin/tq-deploy` must be present, executable, and pass `bash -n`
    (parse check). Any syntax error here would mean the wrapper
    itself is broken — and the operator would fall back to the
    bare `systemctl reload` that produced the 30-email flood.
    """
    candidates = [
        Path("/home/topquaranta/bin/tq-deploy"),
        PROJECT_ROOT / "bin" / "tq-deploy",
    ]
    script = next((p for p in candidates if p.is_file()), None)
    if script is None:
        pytest.skip("tq-deploy not deployed in this environment")
    assert script.stat().st_mode & 0o111, f"{script} is not executable"
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"bash -n failed for {script}:\n{result.stderr}"


def test_tq_health_script_is_executable_and_well_formed():
    """Same posture for `bin/tq-health`. Its migration-pending row
    is what alerts the operator when someone deploys without
    `tq-deploy`; a broken script means no alert."""
    candidates = [
        Path("/home/topquaranta/bin/tq-health"),
        PROJECT_ROOT / "bin" / "tq-health",
    ]
    script = next((p for p in candidates if p.is_file()), None)
    if script is None:
        pytest.skip("tq-health not deployed in this environment")
    assert script.stat().st_mode & 0o111, f"{script} is not executable"
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"bash -n failed for {script}:\n{result.stderr}"


def test_cron_meta_json_loads_and_matches_estat():
    """The single source of truth for cron metadata is
    `deploy/cron-meta.json`. `web/api/staff/estat.py::CRON_META`
    loads it. `bin/tq-health` parses the same JSON via jq. If the
    JSON ever stops parsing, both consumers break in lockstep —
    this test catches that at CI time, before the next push.
    """
    import json

    meta_path = PROJECT_ROOT / "deploy" / "cron-meta.json"
    assert meta_path.is_file(), f"{meta_path} missing"
    with meta_path.open() as fh:
        data = json.load(fh)
    # Every entry (skipping `_doc`) must carry the three required keys.
    for name, meta in data.items():
        if name.startswith("_"):
            continue
        for required in ("frequency_label", "max_age_hours", "skip_concern"):
            assert required in meta, f"{name} missing {required}"
        # max_age_hours must be a positive int.
        assert isinstance(meta["max_age_hours"], int)
        assert meta["max_age_hours"] > 0


def test_cron_meta_json_consumed_by_estat():
    """estat.CRON_META must round-trip from the JSON source. Catches
    a future regression where someone re-introduces a hardcoded
    Python dict and silently drifts from the JSON."""
    import json

    from web.api.staff.estat import CRON_META

    meta_path = PROJECT_ROOT / "deploy" / "cron-meta.json"
    with meta_path.open() as fh:
        raw = json.load(fh)
    expected = {k: v for k, v in raw.items() if not k.startswith("_")}
    assert CRON_META == expected


def test_cron_meta_json_consumed_by_tq_health():
    """`bin/tq-health` must derive its MAX_AGE_HOURS from the JSON.
    We can't assert the bash array contents directly, but we can run
    tq-health and assert it reports rows for every cron in the JSON
    (using the COMMAND column of its output). Catches the failure
    mode that prompted this refactor: a new cron added in JSON +
    estat but missed from tq-health's hardcoded list."""
    import json

    script = Path("/home/topquaranta/bin/tq-health")
    if not script.is_file():
        pytest.skip("tq-health not deployed in this environment")
    meta_path = PROJECT_ROOT / "deploy" / "cron-meta.json"
    with meta_path.open() as fh:
        raw = json.load(fh)
    expected_names = {k for k in raw if not k.startswith("_")}

    result = subprocess.run([str(script)], capture_output=True, text=True, timeout=30)
    # Each cron name appears as a leading word on its row.
    for name in expected_names:
        assert name in result.stdout, (
            f"tq-health output missing row for cron '{name}' — "
            f"refactor must keep tq-health in sync with cron-meta.json"
        )


def test_tq_health_emits_migration_status_row():
    """Run tq-health in this environment and assert the output
    contains the migration-status line. If a future refactor drops
    the row, this test fails — preventing silent regression of the
    safety net."""
    script = Path("/home/topquaranta/bin/tq-health")
    if not script.is_file():
        pytest.skip("tq-health not deployed in this environment")
    result = subprocess.run(
        [str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # tq-health may exit 0 or 1 depending on system state; we only
    # care that it ran and printed the migration row.
    assert "DB migrations:" in result.stdout, (
        f"tq-health output missing migration row.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
