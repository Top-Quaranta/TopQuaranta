"""Offsite backup (capa 2) — no-regression guards.

Three families:

1. Behavioral gating of `bin/tq-backup-offsite`: the script runs for
   real against a tmpdir (TQ_* env overrides) and must be a clean no-op
   (exit 0, status=DISABLED, nothing else written) whenever the flag is
   off, the restic vars are missing, or restic is not installed. With
   everything present it must issue exactly two tagged `restic backup`
   calls (verified with a stub restic on PATH — no network).

2. PII exclude-list invariant on `bin/tq-backup`: every table that can
   hold personal data (all of `comptes`, plus any model anywhere with a
   FK to AUTH_USER_MODEL, plus session/axes/otp/admin-log internals)
   must be covered by an `--exclude-table-data` pattern in the
   sanitized monthly dump. Adding a new user-FK model without updating
   the exclude list fails CI here.

3. Retention patterns in `bin/tq-backup`: the new 90-day rule applies
   only to `tq-month-pii-*`; legacy `tq-month-<date>` full dumps keep
   their original 365-day window (no retroactive deletion — Miquel's
   explicit constraint, 2026-07-05).

# Spec: docs/ops/backup-offsite.md
"""

from __future__ import annotations

import fnmatch
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OFFSITE = PROJECT_ROOT / "bin" / "tq-backup-offsite"
BACKUP = PROJECT_ROOT / "bin" / "tq-backup"


# ── helpers ──────────────────────────────────────────────────────────


def _run_offsite(tmp_path: Path, env_lines: list[str], with_restic_stub=False):
    """Run the real script against a sandbox; return (proc, status_dict)."""
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(env_lines) + "\n")
    status_dir = tmp_path / "status"
    backup_dir = tmp_path / "backups"
    (backup_dir / "daily").mkdir(parents=True)
    # A plausible daily dump so the payload step has something to find.
    (backup_dir / "daily" / "tq-20260705-030001.sql.gz").write_bytes(b"x")
    portades = tmp_path / "portades"
    portades.mkdir()

    env = os.environ.copy()
    env.update(
        TQ_APP_DIR=str(tmp_path),
        TQ_ENV_FILE=str(env_file),
        TQ_BACKUP_DIR=str(backup_dir),
        TQ_STATUS_DIR=str(status_dir),
        TQ_PORTADES_DIR=str(portades),
    )
    if with_restic_stub:
        bin_dir = tmp_path / "stub-bin"
        bin_dir.mkdir()
        stub = bin_dir / "restic"
        log = tmp_path / "restic-calls.log"
        stub.write_text(
            "#!/bin/bash\n"
            f'echo "$@" >> "{log}"\n'
            'echo "snapshot deadbeef saved"\n'
        )
        stub.chmod(0o755)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
    else:
        # Guarantee restic is NOT resolvable even on machines that have
        # it installed: reduce PATH to a stub-free dir.
        empty = tmp_path / "empty-bin"
        empty.mkdir()
        for tool in ("bash", "grep", "cut", "head", "ls", "date", "mktemp",
                     "chmod", "mv", "mkdir", "basename", "cat", "tail"):
            src = _which(tool)
            if src:
                (empty / tool).symlink_to(src)
        env["PATH"] = str(empty)

    proc = subprocess.run(
        ["bash", str(OFFSITE)], env=env, capture_output=True, text=True
    )
    status = {}
    sf = status_dir / "tq-backup-offsite.status"
    if sf.is_file():
        for line in sf.read_text().splitlines():
            if "=" in line and not line.startswith("last_output"):
                k, _, v = line.partition("=")
                status[k] = v
    return proc, status


def _which(tool: str) -> str | None:
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = Path(d) / tool
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


BASE_VARS = [
    "RESTIC_REPOSITORY=s3:s3.example/bucket",
    "RESTIC_PASSWORD=secret",
    "AWS_ACCESS_KEY_ID=keyid",
    "AWS_SECRET_ACCESS_KEY=appkey",
]


# ── 1. behavioral gating ─────────────────────────────────────────────


def test_flag_off_is_clean_noop(tmp_path):
    proc, status = _run_offsite(tmp_path, BASE_VARS)  # no flag line
    assert proc.returncode == 0, proc.stderr
    assert status.get("status") == "DISABLED"
    assert "flag apagat" in (tmp_path / "status" / "tq-backup-offsite.status").read_text()
    assert not (tmp_path / "restic-calls.log").exists()


def test_flag_on_but_missing_vars_is_disabled(tmp_path):
    proc, status = _run_offsite(
        tmp_path, ["OFFSITE_BACKUP_ACTIU=1", "RESTIC_REPOSITORY=s3:x"]
    )
    assert proc.returncode == 0, proc.stderr
    assert status.get("status") == "DISABLED"
    body = (tmp_path / "status" / "tq-backup-offsite.status").read_text()
    assert "RESTIC_PASSWORD" in body and "AWS_SECRET_ACCESS_KEY" in body


def test_flag_on_vars_ok_but_no_restic_is_disabled(tmp_path):
    proc, status = _run_offsite(tmp_path, ["OFFSITE_BACKUP_ACTIU=1"] + BASE_VARS)
    assert proc.returncode == 0, proc.stderr
    assert status.get("status") == "DISABLED"
    assert "falta restic" in (tmp_path / "status" / "tq-backup-offsite.status").read_text()


def test_fully_enabled_runs_two_tagged_backups(tmp_path):
    proc, status = _run_offsite(
        tmp_path, ["OFFSITE_BACKUP_ACTIU=1"] + BASE_VARS, with_restic_stub=True
    )
    assert proc.returncode == 0, proc.stderr
    assert status.get("status") == "OK"
    calls = (tmp_path / "restic-calls.log").read_text().splitlines()
    assert len(calls) == 2
    assert calls[0].startswith("backup --tag pii")
    assert calls[1].startswith("backup --tag safe")
    # Never a destructive verb: the server-side key is append-only.
    assert not any(re.search(r"\b(forget|prune|unlock)\b", c) for c in calls)
    # PII snapshot carries the dump and the .env; safe carries portades.
    assert "tq-20260705-030001.sql.gz" in calls[0] and ".env" in calls[0]
    assert "portades" in calls[1]


def test_offsite_script_is_executable_bash():
    assert OFFSITE.is_file()
    assert OFFSITE.stat().st_mode & stat.S_IXUSR
    head = OFFSITE.read_text().splitlines()[0]
    assert head.startswith("#!/bin/bash")
    proc = subprocess.run(["bash", "-n", str(OFFSITE)], capture_output=True)
    assert proc.returncode == 0, proc.stderr


# ── 2. PII exclude-list invariant ────────────────────────────────────


def _exclude_patterns() -> list[str]:
    return re.findall(r"--exclude-table-data='([^']+)'", BACKUP.read_text())


def test_pii_exclude_list_covers_user_tables():
    import django.apps
    from django.conf import settings
    from django.contrib.auth import get_user_model

    patterns = _exclude_patterns()
    assert patterns, "bin/tq-backup no longer builds the sanitized dump?"

    # The real table name, NOT a naive <app>_<model> guess: Usuari keeps
    # the legacy `auth_user` db_table, which is exactly how the original
    # `comptes_*`-only exclude list missed the credentials table.
    user_table = get_user_model()._meta.db_table
    must_cover: set[str] = set()
    for model in django.apps.apps.get_models(include_auto_created=True):
        table = model._meta.db_table
        if model._meta.app_label == "comptes":
            must_cover.add(table)
        for field in model._meta.get_fields():
            if getattr(field, "related_model", None) is not None and (
                field.related_model._meta.label_lower
                == settings.AUTH_USER_MODEL.lower()
            ) and getattr(field, "many_to_one", False):
                must_cover.add(table)
    # Django internals with personal data that get_models may not flag.
    must_cover |= {"django_session", "django_admin_log"}
    assert user_table in must_cover, "sanity: user table collected"

    uncovered = sorted(
        t for t in must_cover if not any(fnmatch.fnmatch(t, p) for p in patterns)
    )
    assert uncovered == [], (
        f"Tables with personal data NOT excluded from the sanitized monthly "
        f"dump: {uncovered}. Add --exclude-table-data patterns to bin/tq-backup "
        f"(and update docs/ops/retention.md §Backups)."
    )


def test_pii_excludes_cover_axes_and_otp():
    patterns = _exclude_patterns()
    for table in ("axes_accessattempt", "axes_accesslog", "otp_totp_totpdevice"):
        assert any(fnmatch.fnmatch(table, p) for p in patterns), table


# ── 3. retention patterns ────────────────────────────────────────────


def test_retention_rules_are_disjoint_and_non_retroactive():
    text = BACKUP.read_text()
    finds = dict(
        re.findall(r'-name "([^"]+)"\s+-mtime \+(\d+)\s+-delete', text)
    )
    assert finds.get("tq-month-pii-*.sql.gz") == "90"
    assert finds.get("tq-month-safe-*.sql.gz") == "365"
    # Legacy full monthlies keep their ORIGINAL 365-day window: the new
    # 90-day PII rule must not touch them (no retroactive deletion).
    assert finds.get("tq-month-2*.sql.gz") == "365"
    # And the legacy glob must not swallow the new names.
    for new_name in ("tq-month-pii-20260801-030001.sql.gz",
                     "tq-month-safe-20260801-030001.sql.gz"):
        assert not fnmatch.fnmatch(new_name, "tq-month-2*.sql.gz")


def test_tq_backup_still_well_formed():
    proc = subprocess.run(["bash", "-n", str(BACKUP)], capture_output=True)
    assert proc.returncode == 0, proc.stderr
