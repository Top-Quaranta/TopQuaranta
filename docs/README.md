# docs/

Documentation for TopQuaranta, organised by audience.

```
docs/
├── platform-overview.md    — START HERE: cross-cutting onboarding map (stack,
│                             data model, pipeline, territories, staff, social)
├── EMAIL.md                — correu: Purelymail + Brevo/Resend
│
├── architecture/           # one file per app: INVARIANTS + TRAPS only
│   ├── music.md            — domain models: approval anchors, ISRC, MB, aliases
│   ├── ranking.md          — top algorithm, cutoffs, soft cap, distribution gates
│   ├── ingesta.md          — Last.fm/Deezer/MB/Spotify/YouTube ingest rules
│   ├── social.md           — publish contract, channel limits, narrative, IG tags
│   ├── web.md              — API/SEO/staff invariants (auth, throttles, indexability)
│   ├── comptes.md          — auth flow, gestors, community, newsletter
│   ├── analytics.md        — privacy rules, health report, digest
│   └── frontend.md         — SPA design layers, brand SVG traps, pagination
│   (narrative versions of these live read-only in archive/architecture/)
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
├── DECISIONS.md            — ADR digest: one entry per decision (what/why/guard)
├── LESSONS.md              — incident digest: one paragraph per incident + its guard
│
├── policies/               # the rules
│   ├── conventions.md      — code + documentation conventions (what a doc may say,
│   │                         when a PR must touch one, post-mortems, specs)
│   ├── docs-map.yml        — prefix → doc mapping + size scope (CI reads this)
│   └── identities.md       — human vs service identities
│
├── history/                # what happened and what's next
│   ├── changelog.md        — release tags (Keep a Changelog)
│   └── roadmap.md          — current state + sprints
│
└── archive/                # kept, not maintained; excluded from the link checker
    ├── architecture/       — pre-2026-08-19 narrative docs
    ├── audits/             — audit + recon reports of finished sprints
    ├── notes/              — session notes / informes that used to sit at the repo root
    ├── recon/              — community + SEO outreach recon (2026-06)
    ├── decisions/          — full ADRs (digest: docs/DECISIONS.md)
    ├── post-mortems/       — full write-ups (digest: docs/LESSONS.md)
    ├── policies/           — superseded policy files (now in conventions.md)
    ├── sprints/            — sprint narratives moved out of history/roadmap.md
    └── changelog/          — compressed per quarter
```

Companion files at the repo root:
- **`README.md`** — public face (badges, stack, install, contributing).
- **`CONTRIBUTING.md`** — quick guide for new contributors.
- **`MANIFEST.md`** — mission, no-goals, values.
- **`LICENSE-DATA.md`** — CC BY 4.0 of the published dataset.
- **`CLAUDE.md`** — entry point for the AI assistant + project conventions.
