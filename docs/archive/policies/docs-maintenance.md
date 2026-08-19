# Docs maintenance

How the documentation stays small, current, and trustworthy.

## Philosophy

Docs degrade by accretion. Every sprint adds an entry, nothing
ever leaves, and after a year the canonical files are illegible
because half their content is stale. The fix is not "be more
careful when writing"; it's a scheduled decay process and a few
machine-enforced backlinks so code and docs can't drift silently.

## Rules

### Rule 1 — `# Spec:` backlinks in Python modules

When a module has a dedicated doc, its top docstring or a header
comment names that doc:

```python
"""<module-purpose summary>

# Spec: docs/architecture/social.md
"""
```

A pre-commit hook (`scripts/check_spec_paths.py`) validates that
every `# Spec: docs/<path>.md` line points to a real file. A
rename without updating the spec backlinks is a commit-time
error, not a runtime discovery.

The same hook runs in CI on PR (see `.github/workflows/ci-docs.yml`).

### Rule 2 — Hard CI gates for docs coupling, novelty and size

Three independent CI checks (each its own job under
`.github/workflows/ci-docs.yml`, so branch protection can require
them individually):

| Check name | What it asserts |
|---|---|
| `docs-coherence` | A PR that touches a subsystem mapped in `docs-map.yml` must also update the mapped doc, OR carry an override line in the PR body. |
| `docs-novelty` | Every top-level code directory (Django app or any dir with at least one `*.py`) must appear in `docs-map.yml` under `mapping:` or `exclude:`. |
| `docs-size` | Every doc inside `size.scope` must respect `size.threshold_lines` unless it appears under `exempt_permanent` or `grandfathered`. |

The canonical prefix-to-doc mapping (which paths trigger which
docs, longest-prefix match, plus the exclude list and the size
thresholds) lives at `docs/policies/docs-map.yml`. All three
checks consume it; the planned pre-commit hook will too.

#### `docs-coherence` override format

Single line, anywhere in the PR body, repeat once per doc to skip:

```
docs-reviewed: <doc-path> : <reason>
```

The verifier checks three facts (it does not judge the truth of the
reason):

1. `<doc-path>` exists on disk.
2. `<doc-path>` is exactly the doc the mapping resolved for one of
   the subsystems the PR touched.
3. `<reason>` is non-empty after whitespace strip.

When the override is accepted, the workflow adds the
`docs-review-skipped` label so reviewers can filter and audit.

Editing the PR body to add an override re-triggers the check
(`types: [..., edited]` on `pull_request`), so you can fix an
override without pushing an empty commit.

#### When to update the doc vs when to override

Closing both bad doors at once: the override is not a shortcut for
"I did not want to write docs today", and an unrelated doc edit is
not a way to silence the gate.

**Update the doc** when the PR alters what the doc DESCRIBES.
Concrete triggers:

- a new public surface (a new API endpoint, route, view, page,
  background command, cron job, channel, model, or pipeline stage),
- a change to existing data flow, contract, or schema (the diagram
  in the doc would now lie),
- a new model field that other parts of the system are expected to
  read (an externally-visible attribute),
- a removed or renamed concept that the doc still names,
- a new constraint, invariant, or assumption the doc was supposed
  to track.

**Use the override (excepcional)** when you touch a mapped
subsystem but the doc's content stays accurate. Concrete examples:

- internal refactor with identical public behaviour (renaming a
  private helper, extracting a function, splitting a module),
- typo fix or comment-only change in a source file,
- adding a log line, a metric counter, or a debug branch,
- style-only edits (whitespace, import order, type-hint cosmetics),
- adding a one-off detail to an existing cell of an existing table
  in code that the doc summarises at a higher level.

Doubt: if you cannot point to a sentence in the doc that would
become wrong without your change, you probably don't need to update
the doc, but you still need the override because the gate cannot
read your mind. Write the override line; the `<reason>` should
explain in one sentence why the doc stays valid.

### Rule 3 — Quarterly decay sweep

Four times a year (15 March, 15 June, 15 September, 15 December),
a `chore/docs-decay-YYYY-Qx` branch lands a PR that applies the
table below. The PR is visible and reviewable; nothing slips into
the archive silently.

| Document | Archive trigger | What remains in the live file |
|---|---|---|
| `CLAUDE.md §6` (Key decisions table) | Entry's decision is resolved AND >6 months old AND not consulted in recent sprints | 1 line: `[archived] <Title> · <Date> · see docs/archive/decisions/<slug>.md` |
| `docs/history/roadmap.md` sprints | Sprint completed >3 months ago | 1 line: `[DONE YYYY-MM] <Sprint Title> · <Brief outcome> · archive: docs/archive/sprints/YYYY-Qx/<slug>.md` |
| `docs/history/changelog.md` | Entries older than rolling year | Compressed into `docs/archive/changelog/YYYY-Qx.md`; live file keeps current rolling year |
| `docs/architecture/<X>.md` | LOC >500 | Split by sub-area; `<X>.md` becomes an index pointing to the sub-files |
| `docs/archive/decisions/<NNNN>.md` | `Status: Superseded` >6 months | Move to `docs/archive/decisions/`; live file becomes a 1-line stub pointing to the archive |

### Rule 4 — Canonical files never archive whole

`README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `MANIFEST.md` never
move to the archive in full. Only sections inside them (like
`CLAUDE.md §6` entries) follow the decay table.

### Rule 5 — Post-mortems live forever

The `docs/archive/post-mortems/` folder doesn't decay. Cost is bytes; the
value of "I just hit something familiar, let me check if we've
seen this before" is high enough to keep the full log accessible.

## When the decay sweep finds something contentious

If the operator is unsure whether to archive a particular item,
the sweep PR leaves it in place and adds a comment to the PR
discussion ("considered archiving X; not sure if still active —
input?"). Default is to keep, not to archive.
