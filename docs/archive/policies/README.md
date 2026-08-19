# docs/policies/

Consensus rules consolidated as written commitments. Nothing here
is "what the code does today" — that goes in `architecture/`.
Everything here is "what we agreed to do, so we don't have to
remember it again next time".

## Philosophy

The errors of May 2026 (three `--reload` 500s in one week, mocked
captures shown as real, smokes mutating production data, GSC
permission lost to identity mix-up) had a common shape: rules that
lived in the operator's head, not on paper. When the operator was
fast or distracted, the rule got skipped and the system bled.

A policy here is a one-off cost (write it once) for a recurring
benefit (the next sprint inherits the rule for free, and CI
enforces what's enforceable).

## Index

- **`conventions.md`** — code conventions (style, imports, commits).
  Originally lived at `CLAUDE.md §10`; canonical here now.
- **`docs-maintenance.md`** — how the documentation stays readable:
  decay schedule, `# Spec:` backlinks, PR template checkbox.
- **`identities.md`** — humans vs services: which account authorises
  which integration, no personal accounts for production auth.
- **`post-mortems.md`** — when an incident becomes a write-up.
- **`sprint-process.md`** — when a sprint needs a written spec
  before the first commit.

## How to add a new policy

A policy is added when a post-mortem ends with "we'd need a rule
that says X". The post-mortem links to the new policy entry, so
future incidents on the same shape have somewhere to land.
