# Contributing to TopQuaranta

What this project is: weekly Catalan-language music ranking. See
[`MANIFEST.md`](./MANIFEST.md) for mission and values, and the main
[`README.md`](./README.md) for stack, structure, and local setup.

## Before you start

Read first, in this order:

1. **[`CLAUDE.md`](./CLAUDE.md)** — entry point for Claude Code
   and human contributors. Project conventions in compressed form.
2. **[`docs/policies/`](./docs/policies/)** — canonical rules
   (code conventions, identities, docs maintenance, sprint
   process, post-mortems).
3. **[`docs/architecture/`](./docs/architecture/)** — how each
   subsystem fits together. Read the doc for the area you're
   touching.

## Where things live

```
docs/
├── architecture/   how the codebase fits together — read before touching
├── policies/       the rules — read before contributing
├── decisions/      ADRs — the why behind significant choices
├── post-mortems/   incident write-ups — read before redesigning
├── ops/            runbook + retention + deprecation + ssh keys
├── product/        scope (what counts as "music in Catalan")
└── history/        roadmap + changelog
```

## How to contribute

1. **Branch** off `main`. Name: `feat/<slug>`, `fix/<slug>`,
   `chore/<slug>`, `docs/<slug>`.
2. **Spec first** when the sprint is medium or large. See
   `docs/policies/conventions.md` for the sizing rules. The
   spec lives as an ADR with `Status: Proposed`.
3. **Commit per phase** for multi-phase sprints (`docs: FASE A -
   …`). Easier to revert one phase than to unwind a single
   commit.
4. **Migrate immediately.** If you touch `models.py`, generate the
   migration in the same PR. `bin/tq-deploy` applies it before
   the gunicorn reload.
5. **PR via the template.** GitHub will pre-fill the checklist
   from `.github/PULL_REQUEST_TEMPLATE.md`. Tick the boxes or
   justify why you didn't.

## What CI checks

Every PR runs:

- **pytest** (Django suite, mocks all external APIs).
- **black** + **isort** (autoformat verifiers).
- **migrations check** (`manage.py makemigrations --check`).
- **destructive migrations warn** (soft warning on
  `RemoveField`/`DeleteModel`/`Rename*`).
- **frontend tests** (Vitest on the SPA).
- **caddyfile validate** (multi-tenant infra safety).
- **markdownlint** (docs)
- **link-checker** (every `.md` link in the repo)
- **spec-path validator** (`# Spec: docs/<path>.md` backlinks
  must point to real files)
- **docs-coherence label** (touches subsystem with a doc?
  needs-docs-review label suggested)

## Code conventions (highlights)

Authoritative source: `docs/policies/conventions.md`.

- Python: `logging` over `print`, `CommandError` over `sys.exit`,
  ORM over raw SQL (one documented exception in
  `ranking/algorisme.py`).
- Comments and docstrings in **English**; user-facing strings in
  **Catalan**.
- Modules with a dedicated architecture doc carry a
  `# Spec: docs/<path>.md` line in the top docstring.
- Captures shown in reports must be real or labelled `EXAMPLE` /
  `MOCK`.

## Single-operator note

This is currently a single-operator project. There is no PR
review queue. The PR template + CI checks are the substitute for
peer review — they're meant to make "merge this myself" safe.
Don't bypass them.
