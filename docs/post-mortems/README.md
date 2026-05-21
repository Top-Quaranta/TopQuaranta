# docs/post-mortems/

Incident write-ups and lessons. A post-mortem here is not a
chronicle of blame; it's a structured artefact that ends with a
**Prevention** link to a rule in `docs/policies/`. If no policy
covers the failure mode, the post-mortem is the trigger to add one.

## When to write one

- An incident that produced visible 5xx errors, data loss, or a
  publication channel going silent.
- A redesign of code less than a sprint old (sprint just finished
  and we're already rewriting parts of it — what's the missing
  policy?).
- A decision that proved wrong in practice and forced a follow-up
  PR to undo it.

## Where they live

- **Live folder** (`docs/post-mortems/`): every post-mortem is
  accessible without archiving. Reading them is part of onboarding
  and part of "don't repeat this".
- **No archive:** we keep them all here. Cost is low (text), value
  of accidental re-reading is high.

## Format

Copy `TEMPLATE.md` to `YYYY-MM-DD-<slug>.md`. The date is the
incident date, not the write-up date. Fields:

- Date, Title, Severity (critical / high / medium / low)
- Impact (user-visible effect)
- Timeline (wall-clock log of events)
- Root cause (real cause, not symptom)
- Fix applied (what we did immediately to stop the bleed)
- Prevention (link to the `docs/policies/` rule that catches this
  shape next time)
- Lessons learned (text; can include "we'd want X but it's out of
  scope right now")

## Index

| Date | Title | Severity |
|---|---|---|
| 2026-05-19 | `gunicorn-reload-incidents` — 3× 500 from worker reload before migrate | High |
| 2026-05-19 | `workflow-sollicituds-redesigned` — DM ping pattern collapsed | Medium |
| 2026-05-20 | `smoke-side-effects` — E2E smoke mutated production data | Medium |
| 2026-05-20 | `gsc-permission-revoked` — refresh token belonged to wrong identity | Medium |
| 2026-05-20 | `narrative-engine-collapsed` — IG @handle regression + #N hashtags | High |
| 2026-05-20 | `jordi-sarra-mock` — mock screenshot shown as real data | Low |
| 2026-05-21 | `bluesky-silent-failures` — 5 days of dropped publications | High |
