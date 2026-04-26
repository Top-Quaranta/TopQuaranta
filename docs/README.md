# docs/

Documentation for TopQuaranta, organised by audience.

```
docs/
├── architecture/   # how the codebase fits together
│   ├── models.md          — every Django model with fields, relations, indexes
│   ├── pipeline.md        — ingest → signal → top flow + cron + clients
│   ├── algorithm.md       — top algorithm v2.0
│   ├── staff.md           — React staff panel + DRF endpoints
│   └── api-versioning.md  — public REST surface contract
│
├── product/        # what the project is about
│   └── definition.md      — què compta com a "música en català"
│
├── ops/            # for the people running it
│   ├── runbook.md         — incident response + common tasks
│   ├── retention.md       — what we keep, for how long
│   ├── deprecation.md     — how we retire fields/commands/endpoints
│   └── ssh-keys.md        — SSH key policy on the server
│
└── history/        # what happened and what's next
    ├── roadmap.md         — current state, pending sprints, completed sprints
    └── changelog.md       — release tags (Keep a Changelog)
```

Companion files at the repo root:
- **`README.md`** — public face (badges, stack, install, contributing).
- **`MANIFEST.md`** — mission, no-goals, values.
- **`LICENSE-DATA.md`** — CC BY 4.0 of the published dataset.
- **`CLAUDE.md`** — entry point for the AI assistant + project conventions.
