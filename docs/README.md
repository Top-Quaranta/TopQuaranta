# docs/

Documentation for TopQuaranta, organised by audience.

```
docs/
├── EMAIL.md                — Stalwart + Brevo/Resend smarthost architecture
│
├── architecture/           # how the codebase fits together
│   ├── algorithm.md        — top algorithm v2.0
│   ├── analytics.md        — pageviews, UTM, social, GoAccess
│   ├── api-versioning.md   — public REST surface contract
│   ├── brand-logo.md       — brand SVG traps (read before touching)
│   ├── comptes.md          — auth + perfil + workflow sol·licituds
│   ├── models.md           — every Django model with fields, relations, indexes
│   ├── pipeline.md         — ingest → signal → top flow + cron + clients
│   ├── seo.md              — SEO architecture (Sprint S)
│   ├── social.md           — distribution (5 channels + narrative engine)
│   └── staff.md            — React staff panel + DRF endpoints
│
├── product/                # what the project is about
│   └── definition.md       — què compta com a "música en català"
│
├── ops/                    # for the people running it
│   ├── deprecation.md      — how we retire fields/commands/endpoints
│   ├── infra.md            — multi-tenant Caddy (shared with cercol-api)
│   ├── retention.md        — what we keep, for how long
│   ├── runbook.md          — incident response + common tasks
│   └── ssh-keys.md         — SSH key policy on the server
│
├── policies/               # consensus rules — prevention over memory
│   ├── conventions.md      — code conventions (migrated from CLAUDE.md §10)
│   ├── docs-maintenance.md — decay process + Spec: backlinks
│   ├── identities.md       — human vs service identities
│   ├── post-mortems.md     — when and how to write one
│   └── sprint-process.md   — when a sprint needs a spec first
│
├── decisions/              # architecture decision records (ADRs)
│   ├── 0000-template.md
│   └── ...
│
├── post-mortems/           # incident write-ups + lessons
│   ├── TEMPLATE.md
│   └── YYYY-MM-DD-<slug>.md
│
├── history/                # what happened and what's next
│   ├── changelog.md        — release tags (Keep a Changelog)
│   └── roadmap.md          — current state + sprints
│
└── archive/                # things older than the decay threshold
    ├── decisions/          — resolved >6m
    ├── sprints/            — completed >3m
    └── changelog/          — compressed per quarter
```

Companion files at the repo root:
- **`README.md`** — public face (badges, stack, install, contributing).
- **`CONTRIBUTING.md`** — quick guide for new contributors.
- **`MANIFEST.md`** — mission, no-goals, values.
- **`LICENSE-DATA.md`** — CC BY 4.0 of the published dataset.
- **`CLAUDE.md`** — entry point for the AI assistant + project conventions.
