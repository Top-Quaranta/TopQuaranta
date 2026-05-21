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
