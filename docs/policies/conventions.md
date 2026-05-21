# Code conventions

Canonical conventions for TopQuaranta. This file supersedes the
contents of `CLAUDE.md §10` (which now links here).

## Python

- No `print()` in application code. Use `logging` (`logger.info`,
  `logger.warning`, etc.) or, inside management commands,
  `self.stdout.write(...)`.
- No `sys.exit()`. Management commands raise `CommandError(...)`.
- No `TRUNCATE`, `DROP`, or raw DDL outside migration files.
- No raw `psycopg2` — always Django ORM. The only documented
  exception is `ranking/algorisme.py`, which uses raw SQL for
  the 14-CTE rank query.
- All DB writes inside `transaction.atomic()`.
- Type hints on new public functions.
- f-strings in regular code; `%s` placeholders in `logger` calls
  (so the formatter is lazy).
- `black` + `isort` autoformat. Versions pinned in
  `requirements-dev.txt`; CI checks the same versions.

## Comments and docstrings

- All comments and docstrings in **English**.
- User-facing strings (React pages, Django templates, email
  bodies, audit log messages) in **Catalan**.
- A module with a dedicated doc carries a `# Spec:` backlink:

  ```python
  """<purpose>

  # Spec: docs/architecture/<area>.md
  """
  ```

  Pre-commit hook `scripts/check_spec_paths.py` validates the
  paths exist. See `docs/policies/docs-maintenance.md` Rule 1.

## Commits

- One logical change per commit. The PR description carries the
  rationale; the commit messages can be short imperatives.
- Sprints commit per phase (`docs: FASE A - ...`, `feat: FASE B -
  ...`) so a revert can roll back one phase without disturbing
  the rest.
- Squash-merge at the PR level; the squash commit message inherits
  the PR title and body.

## Migrations

If a commit changes `models.py`, **the migration is generated and
applied to production in the same deploy cycle as the code change
that uses it**. Concretely:

1. Generate the migration locally or on the server.
2. Include the migration file in the same PR as the model change.
3. After merge, `bin/tq-deploy` will detect pending migrations and
   apply them **before** the gunicorn reload (see
   `docs/decisions/0001-gunicorn-no-reload.md`).

Editing the live `app/models.py` on the server before the
migration has been applied is the failure mode of
`docs/post-mortems/2026-05-19-gunicorn-reload-incidents.md`.

## End-to-end smokes

When testing a production-shaped flow E2E, **use the dedicated
`qa_smoke` user + fixture artist** (slug `qa-smoke`). See
`docs/policies/identities.md` Rule 2. Mutations against real
artists are off-limits.

Until the fixture is created (open backlog item), the operator
manually documents every smoke side-effect and reverts it.

## Captures and screenshots

When showing captured output of a system (status panels, API
responses, rendered UI), the capture must be **a real one**. If
the captured value is illustrative — not from an actual call —
label it **explicitly** as `EXAMPLE` or `MOCK` at the top of the
block. Mixing real captures with imagined ones without labels
makes the entire report untrustworthy.

This rule was added after
`docs/post-mortems/2026-05-20-jordi-sarra-mock.md`. Claude Code in
particular respects it as an active memory rule.
