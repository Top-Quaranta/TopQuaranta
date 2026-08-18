# docs/decisions/

Architecture Decision Records (ADRs). One file per significant
decision, numbered sequentially. The format is loosely Michael
Nygard's: status, context, decision, alternatives, consequences.

## When to write one

A decision earns an ADR when it meets at least one of:

- **Cross-cutting:** touches more than one subsystem (e.g. a new
  authentication path that affects models + middleware + cron).
- **Hard to reverse:** the cost of undoing it later is high
  (a schema choice, an external API contract).
- **Counter-intuitive:** the choice looks wrong at first reading.
  An ADR with the alternatives section saves the next reader from
  re-litigating the same options.

Criteria are listed in `docs/policies/sprint-process.md`.

## Format

Copy `0000-template.md` to a new file `NNNN-slug.md` (next free
number, kebab-case slug). Fill in:

| Field | Meaning |
|---|---|
| Status | `Proposed` while sprint runs, `Accepted` when merged, `Superseded by ADR-NNNN`, `Deprecated`. |
| Date | When the status was last updated. |
| Context | What problem motivates the decision. Cite a post-mortem if one exists. |
| Decision | What we are doing. One paragraph; the rest is context. |
| Alternatives considered | What else we looked at and why we rejected each. |
| Consequences | What this commits us to. Include the awkward ones. |
| Related | Commits, PRs, post-mortems, other ADRs. |

## Index

| # | Title | Status | Date |
|---|---|---|---|
| 0001 | Gunicorn `--reload` removed | Accepted | 2026-05-20 |
| 0002 | GSC auth via OAuth user creds (admin@) | Accepted | 2026-05-21 |
| 0003 | Pytest pin via `--ds=` to block env override | Accepted | 2026-05-20 |
| 0004 | Workflow Sol·licituds de Revisió | Accepted | 2026-05-20 |
| 0005 | Bluesky `upload_blob` timeout 180 s + retry 3× | Accepted | 2026-05-21 |
| 0006 | Posicions com a ordinals catalans en lloc de `#N` | Accepted | 2026-05-21 |
| 0007 | `@username` restituït al composer d'Instagram | Accepted | 2026-05-21 |
| 0008 | Detectors narratius a9–a12 + slot terciari a IG | Accepted | 2026-05-21 |
| 0009 | Spotify identity migrated to admin@ + Premium | Accepted | 2026-05-22 |
| 0010 | No second-output to YouTube Music (yet) | Accepted | 2026-05-22 |
| 0011 | Spotify sync cron schedule (daily 6h + weekly) | Proposed | 2026-05-22 |
| 0017 | Pytest runs with `-n 4` fixed (xdist), not `-n auto` | Accepted | 2026-08-18 |

## Lifecycle

- An ADR with `Status: Superseded` for more than 6 months gets
  moved to `docs/archive/decisions/` during the quarterly decay
  sweep. The file in the live folder stays as a one-line stub
  pointing to the archive entry.
- An ADR with `Status: Deprecated` stays in the live folder
  indefinitely — the deprecation might still be acted on.
