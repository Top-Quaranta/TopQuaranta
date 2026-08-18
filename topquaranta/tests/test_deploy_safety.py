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


@pytest.mark.django_db
def test_every_cron_has_description():
    """Every entry in `deploy/cron-meta.json` must resolve to a
    description ≥ 30 chars when the staff/estat panel asks for it.

    Resolution order is documented in
    `web.api.staff.estat._resolve_cron_description`:
      1. JSON `description` override (use this for non-Django scripts
         like `tq-restore-test` or command variants like
         `calcular_top_provisional`).
      2. Django `Command.help` attribute on the management command of
         the same name.
      3. Empty string → this test fails, forcing the contributor to
         pick one of the two sources above.

    A 30-char floor catches placeholders ("TODO", "fix me", "(no
    help)") that would otherwise render as a useless dashboard cell.
    """
    from web.api.staff.estat import CRON_META, _resolve_cron_description

    bad = []
    for name, meta in CRON_META.items():
        desc = _resolve_cron_description(name, meta)
        if len(desc) < 30:
            bad.append((name, len(desc), desc))
    assert not bad, "Crons without a usable description (≥30 chars):\n" + "\n".join(
        f"  {n} ({chars}ch): {d!r} — add `description` to "
        f"deploy/cron-meta.json or improve `Command.help`."
        for n, chars, d in bad
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


# ── cron table ↔ cron-meta tag correspondence ───────────────────────

# Scripts invoked directly from cron (not via tq-run) that legitimately
# do NOT have a cron-meta entry: tq-health is the watchdog itself and
# writes no status file.
_CRON_SCRIPTS_WITHOUT_META = {"tq-health"}


def _derive_tag(cmd: str, args: list[str]) -> str:
    """Python mirror of the tag derivation in `bin/tq-run`. Keep in sync
    with the `for`-loop there: a command runs under distinguishing
    variants (--provisional, --freq weekly, --channel X), each needing
    its own status tag so one variant's run doesn't hide another's."""
    tag = cmd
    for i, a in enumerate(args):
        nxt = args[i + 1] if i + 1 < len(args) else ""
        if a == "--provisional":
            tag = f"{cmd}_provisional"
        elif a == "--freq":
            if nxt == "weekly":
                tag = f"{cmd}_weekly"
        elif a == "--freq=weekly":
            tag = f"{cmd}_weekly"
        elif a == "--channel":
            if nxt:
                tag = f"{cmd}_{nxt}"
        elif a.startswith("--channel="):
            tag = f"{cmd}_{a[len('--channel=') :]}"
    return tag


def _parse_cron_invocations(text: str) -> list[tuple[str, str, list[str]]]:
    """Yield (kind, name, args) for each cron line that runs a
    /home/topquaranta/bin/ entrypoint. kind is "tq-run" (name is the
    manage.py command) or "script" (name is the bin script)."""
    invs: list[tuple[str, str, list[str]]] = []
    marker = "/home/topquaranta/bin/"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or marker not in line:
            continue
        # Drop shell redirections (>> logfile 2>&1, > /dev/null 2>&1).
        cut = line.find(">")
        if cut != -1:
            line = line[:cut]
        parts = line.split()
        bin_idx = next(i for i, p in enumerate(parts) if p.startswith(marker))
        script = parts[bin_idx].rsplit("/", 1)[1]
        rest = parts[bin_idx + 1 :]
        if script == "tq-run":
            invs.append(("tq-run", rest[0], rest[1:]))
        else:
            invs.append(("script", script, rest))
    return invs


def _load_cron_meta() -> dict:
    import json

    with (PROJECT_ROOT / "deploy" / "cron-meta.json").open() as fh:
        raw = json.load(fh)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def test_every_cron_invocation_has_meta_entry():
    """Every cron line in `deploy/cron.topquaranta` must resolve to a
    status tag that has a `deploy/cron-meta.json` entry, so tq-health
    monitors it. Caught 2026-06-07: `--freq weekly` and the four
    `--channel X` runs shared a tag (or had none) and slipped past the
    watchdog entirely."""
    text = (PROJECT_ROOT / "deploy" / "cron.topquaranta").read_text()
    meta = _load_cron_meta()
    missing = []
    for kind, name, args in _parse_cron_invocations(text):
        if kind == "script":
            if name in _CRON_SCRIPTS_WITHOUT_META:
                continue
            tag = name
        else:
            tag = _derive_tag(name, args)
        if tag not in meta:
            missing.append(tag)
    assert not missing, (
        "Cron invocations with no cron-meta.json entry (tq-health would "
        f"not monitor them): {sorted(set(missing))}"
    )


def test_no_orphan_cron_meta_entries():
    """The reverse: every cron-meta.json entry must correspond to a real
    cron invocation. An orphan meta entry means a removed/renamed cron
    left stale metadata that would show as a perpetual WAITING/MISSING
    row."""
    text = (PROJECT_ROOT / "deploy" / "cron.topquaranta").read_text()
    meta = _load_cron_meta()
    produced: set[str] = set()
    for kind, name, args in _parse_cron_invocations(text):
        produced.add(name if kind == "script" else _derive_tag(name, args))
    orphan = set(meta) - produced
    assert not orphan, (
        "cron-meta.json entries with no matching cron invocation "
        f"(stale metadata): {sorted(orphan)}"
    )


# ── estat.py ETA constants ↔ cron `--limit` (Patró 3) ───────────────


def _cron_limit(text: str, command: str) -> int | None:
    """Return the int after `--limit` on the `tq-run <command>` line in
    the cron table. Exact command match so `enriquir_spotify` does not
    pick up `enriquir_spotify_rebuigs`."""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#") or "tq-run" not in line:
            continue
        toks = line.split("tq-run", 1)[1].split()
        if not toks or toks[0] != command or "--limit" not in toks:
            continue
        return int(toks[toks.index("--limit") + 1])
    return None


def test_estat_constants_match_cron_table():
    """The per-day budgets `estat.py` uses for backlog ETAs are mirrored
    from the cron `--limit`. Caught 2026-06-07: `WHISPER_DAILY_LIMIT` was
    stuck at 100 while the cron moved to `--limit 200` (ETA 2×
    pessimistic), and the Spotify enrich rate was reported per-hour while
    the cron is nightly. This guards the mirror against future drift."""
    from web.api.staff.estat import ENRICH_SPOTIFY_DAILY_LIMIT, WHISPER_DAILY_LIMIT

    text = (PROJECT_ROOT / "deploy" / "cron.topquaranta").read_text()
    assert _cron_limit(text, "analitzar_whisper") == WHISPER_DAILY_LIMIT
    assert _cron_limit(text, "enriquir_spotify") == ENRICH_SPOTIFY_DAILY_LIMIT


# ── Multi-tenant Caddy: import contract + conf.d isolation ──────────


def test_static_social_excluded_from_security_headers():
    """The `/static/social/*` render path must NOT receive the site-level
    CSP / X-Frame-Options headers: Instagram's media fetcher (code 9004)
    and Telegram's fetcher reject media responses that carry them. The
    security-headers block is therefore scoped with a matcher that
    excludes the path. Static tripwire: if a refactor drops the
    exclusion, this fails before it ships (runtime regression would only
    surface as a failed social publish). See docs/ops/infra.md."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    body = (repo_root / "deploy" / "Caddyfile").read_text()
    assert (
        "handle_path /static/social/*" in body
    ), "deploy/Caddyfile must serve /static/social/* as plain static files."
    assert "not path /static/social/*" in body, (
        "deploy/Caddyfile must exclude /static/social/* from the security-"
        "headers block (CSP / X-Frame-Options trigger Instagram code 9004). "
        "Scope the `header` block with `@<name> not path /static/social/*`."
    )


def test_caddyfile_imports_confd():
    """The repo Caddyfile must include an `import` directive that
    pulls every `.caddy` snippet under /etc/caddy/conf.d/. Without
    this line, snippets owned by other projects on the shared host
    (e.g. cercol-api) are silently ignored by Caddy."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    body = (repo_root / "deploy" / "Caddyfile").read_text()
    assert "import /etc/caddy/conf.d/*.caddy" in body, (
        "deploy/Caddyfile must contain the line "
        "`import /etc/caddy/conf.d/*.caddy` so per-project snippets "
        "are loaded. See docs/ops/infra.md."
    )


def test_sync_infra_does_not_touch_confd():
    """tq-sync-infra is the sole owner of /etc/caddy/Caddyfile and
    must never read, write, or delete anything under
    /etc/caddy/conf.d/. Asserting on the literal substring is a
    cheap belt-and-braces guard: any future refactor that touches
    the conf.d directory will trip this test.

    The ownership-contract header comment intentionally names the
    directory to document the prohibition; strip comment lines
    before the substring check so the docstring itself isn't what
    fails the test."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    body = (repo_root / "bin" / "tq-sync-infra").read_text()
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    assert "conf.d" not in code, (
        "bin/tq-sync-infra must not reference /etc/caddy/conf.d/ in "
        "executable code. That directory is reserved for snippets "
        "owned by other repos. See docs/ops/infra.md."
    )


def _git(cwd, *args):
    import os

    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", ""),
    }
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def test_tq_git_drift_classifies_doc_only_vs_code(tmp_path):
    """`bin/tq-git-drift` must NOT flag a prod tree that merely lags
    origin/main by doc-only commits (deploy.yml skips those), but MUST
    flag a lag that includes code, or a dirty tree. Regression guard for
    the false red alert every doc-only merge produced before this
    helper existed (#328/#329 while prod stayed on the last code deploy)."""
    drift = PROJECT_ROOT / "bin" / "tq-git-drift"
    if not drift.is_file():
        pytest.skip("tq-git-drift not present")

    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    prod = tmp_path / "prod"
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", "--bare", str(origin)],
        check=True,
    )
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    (work / "app").mkdir()
    (work / "app" / "code.py").write_text("x = 1\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "init")
    _git(work, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", str(origin), str(prod)], check=True)

    def run():
        return subprocess.run(
            [str(drift), str(prod)], capture_output=True, text=True, timeout=30
        )

    # In sync → OK.
    r = run()
    assert r.returncode == 0, r.stdout

    # Origin advances by a docs-only commit; prod lags → still OK.
    (work / "docs").mkdir()
    (work / "docs" / "x.md").write_text("hi\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "docs")
    _git(work, "push", "-q", "origin", "main")
    r = run()
    assert r.returncode == 0, f"doc-only lag flagged as drift: {r.stdout}"
    assert "doc-only" in r.stdout

    # Origin advances by a CODE commit; prod lags → DRIFT.
    (work / "app" / "more.py").write_text("y = 2\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "code")
    _git(work, "push", "-q", "origin", "main")
    r = run()
    assert r.returncode == 1, f"code lag not flagged: {r.stdout}"

    # Dirty tree (untracked non-data file) → DRIFT.
    _git(prod, "fetch", "-q", "origin", "main")
    _git(prod, "reset", "-q", "--hard", "origin/main")
    (prod / "app" / "hack.py").write_text("hack\n")
    r = run()
    assert r.returncode == 1, f"dirty tree not flagged: {r.stdout}"


# ── bin/tq-changed-files (2026-07-27) ─────────────────────────────────
#
# Regression guard for the defect described in the script's own header:
# the changed-file detection used to live inside an `if` condition, where
# `set -e` does not apply, so a git failure collapsed into "that path did
# not change" and the deploy skipped work while still exiting 0.
# "I could not look" must never share an exit path with "nothing changed".


def _changed_files_script():
    script = PROJECT_ROOT / "bin" / "tq-changed-files"
    if not script.is_file():
        pytest.skip("tq-changed-files not present")
    return script


def _run_changed_files(repo, *args):
    return subprocess.run(
        [str(_changed_files_script()), *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=20,
    )


def _repo_with_two_commits(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "-c", "init.defaultBranch=main", "init", "-q")
    (repo / "keep.txt").write_text("one\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")
    first = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (repo / "requirements.txt").write_text("django==6.0.6\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")
    return repo, first


def test_tq_changed_files_lists_the_changed_paths(tmp_path):
    repo, first = _repo_with_two_commits(tmp_path)
    result = _run_changed_files(repo, first, "HEAD")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["requirements.txt"]


def test_tq_changed_files_identical_refs_is_empty_and_ok(tmp_path):
    repo, _first = _repo_with_two_commits(tmp_path)
    result = _run_changed_files(repo, "HEAD", "HEAD")
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_tq_changed_files_fails_loudly_when_the_diff_is_not_computable(tmp_path):
    """THE test. A git failure must exit non-zero with a message, never
    return an empty list that downstream reads as 'nothing changed'."""
    repo, _first = _repo_with_two_commits(tmp_path)
    result = _run_changed_files(repo, "no-such-ref", "HEAD")
    assert result.returncode == 7, result.stdout
    assert result.stdout.strip() == ""
    assert "git diff failed" in result.stderr


def test_tq_changed_files_rejects_wrong_usage(tmp_path):
    repo, _first = _repo_with_two_commits(tmp_path)
    assert _run_changed_files(repo, "only-one-ref").returncode == 64


def test_tq_deploy_computes_the_diff_once_outside_any_condition():
    """Static guard: `tq-deploy` must not go back to piping `git diff`
    into `grep` inside an `if`, which is what made a failure silent."""
    script = PROJECT_ROOT / "bin" / "tq-deploy"
    if not script.is_file():
        pytest.skip("tq-deploy not present")
    body = script.read_text()
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    assert "git diff --name-only" not in code, (
        "bin/tq-deploy must not compute the diff inline; delegate to "
        "bin/tq-changed-files so a git failure is loud. See that script's "
        "header and docs/ops/runbook.md."
    )
    assert "tq-changed-files" in code
    assert "exit 7" in code, "the not-computable path must have its own exit code"


def test_tq_deploy_documents_every_exit_code_it_uses():
    """Codes drifted once already: 6 was in use and undocumented."""
    script = PROJECT_ROOT / "bin" / "tq-deploy"
    if not script.is_file():
        pytest.skip("tq-deploy not present")
    body = script.read_text()
    header = body.split("set -euo pipefail")[0]
    used = {
        line.split("exit ")[1].split()[0]
        for line in body.splitlines()
        if line.lstrip().startswith("exit ")
    }
    documented = set()
    for line in header.splitlines():
        if not line.startswith("#"):
            continue
        parts = line[1:].split()
        if parts and parts[0].isdigit():
            documented.add(parts[0])
    undocumented = {c for c in used if c.isdigit()} - documented
    assert (
        not undocumented
    ), f"exit codes used but not documented: {sorted(undocumented)}"


def test_sync_infra_installs_every_file_it_declares():
    """Adding a line to `FILES` must be enough to get the file installed.

    The `case "$dst"` had a branch per known destination and no default,
    so a new entry matched nothing, installed nothing, and the script
    still exited 0. That happened on 2026-08-18 with the mail autoconfig:
    the deploy reported success, the file was never written, and Caddy —
    already rewritten to point at it — went from serving a stale config
    to serving a 404.

    The branches that remain exist only for files that ALSO need
    validation or a reload; the map is the source of truth.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    body = (repo_root / "bin" / "tq-sync-infra").read_text()

    inici = body.index('case "$dst" in')
    fi = body.index("esac", inici)
    case = body[inici:fi]
    assert "*)" in case, (
        "tq-sync-infra: el `case` no té branca per defecte, així que una "
        "entrada nova a FILES s'instal·laria en silenci... o no."
    )

    # …and every destination declared must be reachable: either it has
    # its own branch or the default catches it. With `*)` present the
    # second half is automatic, so this only guards the ordering — a
    # default placed before a specific branch would swallow it.
    assert case.rindex("*)") > case.index("/etc/caddy/Caddyfile"), (
        "la branca per defecte ha d'anar l'última, o s'empassa les "
        "específiques (i el Caddyfile deixaria de validar-se)"
    )
