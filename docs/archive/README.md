# docs/archive/

Things older than the decay threshold defined in
`docs/policies/docs-maintenance.md`. Stored here so the live docs
stay small and current; available for history, audits, or sprint
post-mortems that need full context.

## What lives here

```
docs/archive/
├── decisions/     # ADRs with status Superseded or Resolved >6 months
├── sprints/       # roadmap entries for sprints completed >3 months ago
└── changelog/     # entries older than the current rolling year,
                  # compressed per quarter
```

## When to reach for the archive

Rarely. Most operational questions are answered by the live docs.
Open the archive when:

- You're auditing why a past decision was made (read the old ADR
  before reopening it).
- You're writing a post-mortem and need the original sprint context.
- You're onboarding a long-form contributor who wants the back story.

## Naming convention

- **Decisions:** keep the original `NNNN-slug.md` filename. Status
  inside the file is updated (e.g. `Status: Superseded by ADR-0042`).
- **Sprints:** `YYYY-Qx/<sprint-slug>.md` — quarter folder so the
  archive doesn't flatten into hundreds of sibling files.
- **Changelog:** `YYYY-Qx.md` — one file per quarter with the
  entries that used to live at the top of `docs/history/changelog.md`.

## How things get here

Via a scheduled `chore/docs-decay-YYYY-Qx` PR, four times a year
(15 March, 15 June, 15 September, 15 December). The PR is visible
and reviewable: nothing slips into the archive silently. Process at
`docs/policies/docs-maintenance.md`.

## Sweep log

### 2026-05-21 — initial sweep (FASE H of docs sprint)

**Result: 0 items archived.**

The project's documented sprint cadence began ~2026-04-16 (oldest
`.md` mtime). All `CLAUDE.md §6` entries (36 total) and all
`docs/history/roadmap.md` sprint headers (~30) are dated within
the last 5-6 weeks. None meet the policy thresholds:

- `CLAUDE.md §6`: archive trigger is "resolved AND >6 months
  old AND not consulted in recent sprints". Oldest entry is
  2026-04-21 — 30 days ago.
- `docs/history/roadmap.md`: archive trigger is "sprint completed
  >3 months ago". Oldest completed sprint is 2026-04-25 — 26 days
  ago.
- `docs/history/changelog.md`: 52 LOC total, already compact.
- `docs/architecture/*.md`: largest is `models.md` (425 LOC),
  followed by `pipeline.md` (531 LOC). The 500-LOC split trigger
  is borderline for `pipeline.md` but not exceeded by enough to
  justify a forced split now; revisit at next sweep.

The first real archival pass is expected at the
**2026-06-15 sweep** (Q2 close): by then, the April-launch
entries will be 8+ weeks old, and items resolved in May with no
follow-up consulting will be aging into the candidate window.

The sweep document is also a place to record drift not caught
by CI:
- The roadmap entry for "motor narratiu social (library)" was
  out of date (`not wired yet`) — corrected during FASE A of
  this sprint.
- The README listed Python 3.10 / Django 5.2 — corrected during
  FASE A.

### Next sweep

Scheduled: 2026-06-15. Branch name: `chore/docs-decay-2026-Q2`.

