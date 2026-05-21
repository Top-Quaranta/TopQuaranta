# DM ping pattern collapsed → workflow redesign — 2026-05-19

- **Date of incident:** 2026-05-19 (decision); pattern in use for
  ~10 days prior
- **Severity:** medium (no production breakage, but the existing
  approach didn't scale)
- **Author:** Miquel

## Impact

The previous "demanar revisió" feature for verified gestors sent
a free-form `Missatge` to the `admin` pseudo-user. It worked for a
single song, but:

- No selection — the gestor pinged for "all unverified" with no
  ability to scope.
- No state — staff had no way to mark a request "I'm on it" or
  "done"; subsequent gestor pings re-asked the same question.
- Rebutjades not reaprovable — once a song landed in
  `HistorialRevisio` as `decisio=rebutjada`, no path existed to
  push it back into the ingestion cron. Genuine staff mistakes
  ("wrong language detection") couldn't be undone except by
  manual DB edits.

Within ~10 days of the feature shipping (Sprint Portal Artista
Ampliat), the operator (Miquel) had escalated three artists'
batches manually because the pattern didn't survive contact with
real moderation work.

## Timeline

- 2026-05-09 — DM ping ships as part of Portal Artista Ampliat.
- 2026-05-09 to 2026-05-18 — operator manually escalates batches
  via direct DB shell sessions.
- 2026-05-19 — decision: workflow redesign sprint.
- 2026-05-20 — Workflow Sol·licituds sprint completes (PR #54):
  `SolicitudRevisio` model with state, workbench staff page,
  `HistorialRevisio.reconsiderada` flag, gestor↔staff email
  notifications.

## Root cause

The Portal Artista Ampliat spec sized "demanar revisió" as a
one-shot DM. It didn't model the staff side (workbench, state,
batch acceptance) because the original use case was "gestor
spots one missing song and wants it looked at". Real moderation
work involves batches and follow-up; the DM pattern broke under
real load.

## Fix applied

The Workflow Sol·licituds sprint (PR #54) introduced:

- `SolicitudRevisio` model (gestor + artista + pendents_ids +
  rebutjades_snapshot + estat ∈ {pendent, revisada, resolta}).
- Workbench page at `/staff/sollicituds-revisio/`.
- `HistorialRevisio.reconsiderada` boolean flag — the cron filter
  in `obtenir_novetats` and `obtenir_metadata` respects
  `reconsiderada=False` so a staff "reconsider" puts the song
  back into the pipeline at the next ingestion tick.
- Email notifications to staff (creation) and to gestor
  (resolution).

ADR `docs/decisions/0004-workflow-sollicituds-revisio.md` records
the decision and consequences.

## Prevention

- `docs/policies/sprint-process.md` § "Medium / Large" — flows
  with multi-actor + state + batch acceptance now require a
  mini-spec (ADR Proposed) before the first commit. The Portal
  Artista Ampliat sprint had a spec but it under-modelled the
  staff side; the new policy says explicitly "if the sprint
  introduces a new actor flow, the actor receiving the work
  must be in the spec".
- `docs/policies/sprint-process.md` § "Restrictions added
  mid-sprint" — the moment "must support batch" became real
  (within the same week of shipping), the original spec should
  have been re-opened rather than worked around in production
  shell sessions.

## Lessons learned

- A pattern that works for one use case isn't a feature; it's a
  demo. The DM pattern shipped because a single song looked
  fine. Day-of-week stress (multiple artists, repeated pings,
  rebutjades cases) found the failure mode within a sprint.
- Designing for the receiving actor matters as much as the
  sending actor. The staff workbench's existence in the new
  design isn't decoration — it's the difference between "request
  vanishes into an inbox" and "request lives in a queue with
  state".
