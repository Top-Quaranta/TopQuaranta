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
  paths exist.

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
   `docs/archive/decisions/0001-gunicorn-no-reload.md`).

Editing the live `app/models.py` on the server before the
migration has been applied is the failure mode of
`docs/archive/post-mortems/2026-05-19-gunicorn-reload-incidents.md`.

## End-to-end smokes

When testing a production-shaped flow E2E, **use the dedicated
`qa_smoke` user + fixture artist** (slug `qa-smoke`). See
`docs/ops/runbook.md` (identities). Mutations against real
artists are off-limits.

Until the fixture is created (open backlog item), the operator
manually documents every smoke side-effect and reverts it.

## Ops scripts

An ops script must assert the **externally observable outcome** it
claims to produce, not the exit codes of the commands it ran. Its own
exit code has to reflect that assertion: green means the world
changed, not that every step returned 0.

Concretely, a script that installs a certificate checks what is being
served on the port afterwards; one that reloads a service checks the
service answers; one that publishes checks the item is visible. If
the observable check cannot be done, say so in the log rather than
exiting 0.

Two corollaries:

- **Be idempotent, and let a no-op be a no-op.** If the desired state
  already holds, log it and exit 0 without restarting or rewriting
  anything. Restarting a production service "just in case" on every
  trigger is a cost with no benefit.
- **Log to a durable file.** journald on this host does not persist;
  a script whose only trace is journald will have no evidence left by
  the time anyone investigates. Timestamp each line and cap the size.

This rule was added after
`docs/archive/post-mortems/2026-07-26-stalwart-cert-expirat.md`, where a sync
script reported success for a month while the mail server served a
certificate that eventually expired. Every command it ran did return
0; none of them observed the certificate actually in use.

## Captures and screenshots

When showing captured output of a system (status panels, API
responses, rendered UI), the capture must be **a real one**. If
the captured value is illustrative — not from an actual call —
label it **explicitly** as `EXAMPLE` or `MOCK` at the top of the
block. Mixing real captures with imagined ones without labels
makes the entire report untrustworthy.

This rule was added after
`docs/archive/post-mortems/2026-05-20-jordi-sarra-mock.md`. Claude Code in
particular respects it as an active memory rule.

## Documentation

**Docs say only what matters.** A doc line survives only if someone
touching the system would otherwise not know it and cannot get it
faster from the code, a test or a docstring. There are two kinds of
document and nothing else:

- `docs/architecture/<app>.md` — **invariants and traps** of one app,
  each with the test/check that guards it. No field tables, no
  endpoint catalogues, no UI narration, no sprint history. ≤ 150
  lines by habit, 400 by CI (`docs-size`).
- `docs/DECISIONS.md` and `docs/LESSONS.md` — one paragraph per
  decision / per incident. The full ADR or write-up goes to
  `docs/archive/` the day it is written; the digest is what people
  read.

Everything else — session notes, recon, audits, informes, plans —
is history: it goes straight to `docs/archive/`, out of the map and
out of the link checker. `docs/ops/runbook.md` is the exception:
procedures you need at 3 a.m.

**When a PR must touch a doc.** Only when it changes an invariant:
a constraint the code enforces or an external service imposes, the
*why* of a decision, an operational procedure, a lesson. A new
endpoint, route, page, model field, column, cron line, log line,
config knob, or copy string is **not** a doc change — write the
override line and move on. At this stage of the project the
override is the normal case, not the exception; 75–90 % of PRs
carrying one is healthy.

**The gates** (`.github/workflows/ci-docs.yml`, config in
`docs/policies/docs-map.yml`, tests in `topquaranta/tests/test_docs_*.py`):

- `docs-coherence` — a PR that touches an app without touching its
  doc needs one line in the body: `docs-reviewed: <doc> : <reason>`.
  CI checks the doc is the mapped one and the reason is non-empty.
  The mapping is one entry per app; if a prefix keeps tripping for
  changes that never touch an invariant, fix the mapping, not the
  reason.
- `docs-size` — 400 lines hard for `docs/architecture/` and
  `docs/ops/`; no grandfathering. Over the line means the doc is
  narrating again: cut, don't split.
- `docs-novelty` — a new top-level code directory must appear in
  `docs-map.yml` (`mapping:` with its doc, or `exclude:` with a reason).

**Post-mortems.** Write one (into `docs/LESSONS.md`, full text to
`docs/archive/post-mortems/`) after: a production incident with
user-visible breakage or a silenced channel; a redesign of work
merged days earlier; an ADR reversed in under 6 months; a captured
output that turns out to be invented (see *Captures*). Every entry
names the test or check that now guards the lesson — a lesson
without a guard is a lesson we will relearn.

**Specs before sprints.** A change that touches two or more apps,
adds an actor or a state machine, or introduces a contract others
must respect gets a short spec first — as an entry in
`docs/DECISIONS.md` with status *Proposed*, promoted to *Accepted*
when the sprint merges, updated in the same PR if the sprint
deviates. Smaller changes: code first, rationale in the PR body.
