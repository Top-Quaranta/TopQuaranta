# ADR-0001 — Gunicorn `--reload` removed

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** Miquel

## Context

Between 2026-05-19 and 2026-05-20, three production 5xx bursts hit
on consecutive days, all on the same shape: gunicorn workers
running with `--reload` picked up modified `models.py` files in
the server worktree before the matching Django migration had been
applied, so the ORM queried columns/tables that did not exist
yet. Full incident report at
`docs/post-mortems/2026-05-19-gunicorn-reload-incidents.md`.

The `--reload` flag was added 2026-04-27 to avoid the "stale code
after edit" friction; the cost-benefit was correct in isolation
but did not survive multi-session Claude Code work where the
server worktree was the only place with a working venv.

## Decision

Remove `--reload` from `deploy/topquaranta-web.service`. Code
changes reach production exclusively through `bin/tq-deploy`,
which:

1. `git reset --hard origin/main` (wipes worktree drift).
2. `manage.py migrate` before reload.
3. `systemctl reload topquaranta-web` (SIGHUP — graceful worker
   swap, no downtime).

The unit file installs via `bin/tq-sync-infra` on every deploy,
so the repo's `deploy/topquaranta-web.service` is the source of
truth and re-adding `--reload` requires going through the repo +
PR.

## Alternatives considered

- **Keep `--reload` + operator discipline.** Rejected: the three
  incidents this week proved operator discipline doesn't survive
  multi-session work. Discipline is the wrong layer for the fix.
- **Auto-migrate on `--reload` trigger.** Rejected: ties the
  worker process to migration logic, makes startup non-atomic,
  and still doesn't solve uncommitted-edit cases.

## Consequences

- Positive: hot-reload-induced 5xx errors are no longer possible.
  Code edits in the server worktree do nothing until
  `tq-deploy` runs.
- Negative: minor inconvenience when iterating on the server.
  Mitigated by the fact that all real development happens on the
  Mac with a working venv; the server worktree is rarely the
  edit surface any more.
- Follow-up: pre-commit hook on the server that rejects edits to
  `*.py` under `/home/topquaranta/app/` if it's not a clean
  `tq-deploy` invocation (open backlog, low priority).

## Related

- Post-mortem: `docs/post-mortems/2026-05-19-gunicorn-reload-incidents.md`
- PR: #55 (caddy/gunicorn workflow updates)
- Policy: `docs/policies/conventions.md` § "Migrations"
- Backup unit file: `/etc/systemd/system/topquaranta-web.service.bak-20260520`
