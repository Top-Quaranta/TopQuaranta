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

### Rule 2 — PR template checkbox for docs coupling

The repo's pull-request template asks the contributor to either:

- check the box "I updated `docs/architecture/<area>.md` for this
  change", **or**
- justify why no docs update was needed (one line).

CI gives the PR a `needs-docs-review` label when it touches a
subsystem with a dedicated doc and the doc wasn't touched. The
label is a signal, not a hard block — sometimes "no doc update
needed" is genuinely the right answer.

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
| `docs/decisions/<NNNN>.md` | `Status: Superseded` >6 months | Move to `docs/archive/decisions/`; live file becomes a 1-line stub pointing to the archive |

### Rule 4 — Canonical files never archive whole

`README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `MANIFEST.md` never
move to the archive in full. Only sections inside them (like
`CLAUDE.md §6` entries) follow the decay table.

### Rule 5 — Post-mortems live forever

The `docs/post-mortems/` folder doesn't decay. Cost is bytes; the
value of "I just hit something familiar, let me check if we've
seen this before" is high enough to keep the full log accessible.

## When the decay sweep finds something contentious

If the operator is unsure whether to archive a particular item,
the sweep PR leaves it in place and adds a comment to the PR
discussion ("considered archiving X; not sure if still active —
input?"). Default is to keep, not to archive.
