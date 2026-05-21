# ADR-0004 — Workflow Sol·licituds de Revisió

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** Miquel

## Context

The original "demanar revisió" flow from Portal Artista Ampliat
shipped as a free-form `Missatge` from the gestor to the `admin`
pseudo-user. Within ~10 days, the pattern collapsed under real
moderation load: no selection, no state tracking, no path to
reapprove a rejected song. See
`docs/post-mortems/2026-05-19-workflow-sollicituds-redesigned.md`.

The redesign sprint (PR #54) introduced a structured workflow
between the gestor (one actor) and the staff (a different actor)
with state and bulk handling.

## Decision

Introduce a `SolicitudRevisio` model in the `comptes` app with:

- FK to gestor (`Usuari`) and artist (`Artista`).
- `pendents_ids: JSONField` — list of `Canco.pk` selected by the
  gestor.
- `rebutjades_snapshot: JSONField` — list of dicts denormalising
  the `HistorialRevisio` rows the gestor wants reconsidered.
- `estat: CharField` with values `pendent / revisada / resolta`.
- `nota_resolucio: TextField` + `resolt_at` + `resolt_per` set on
  resolution.

Add a `reconsiderada: BooleanField` to `music.HistorialRevisio`.
Patch the cron filters in `ingesta/management/commands/
obtenir_novetats.py` and `obtenir_metadata.py` to respect
`decisio="rebutjada", reconsiderada=False` so a staff
"reconsider" puts the rejected song back into the ingestion
pipeline at the next tick.

Staff workbench at `/staff/sollicituds-revisio/` (list + detail
+ actions: `marcar-en-revisio`, `reconsiderar-rebutjada`,
`resoldre`). Transactional emails on creation (staff) and
resolution (gestor).

## Alternatives considered

- **Continue with richer DMs.** Rejected: the DM has no state
  machine. The fundamental problem was "request vanishes into
  inbox", not "DM doesn't carry enough fields".
- **Build it on top of existing `Feedback` model.** Rejected:
  `Feedback` is anonymous + per-page-URL; the sol·licitud
  semantics require gestor identity + per-artist scope + bulk.
  Stretching `Feedback` would have ambiguified both.
- **Auto-reconsider rejections via heuristic.** Rejected:
  rebutjades exist precisely because a human said "this isn't
  ours". Automating the reversal undermines the curation. A
  staff click is the right gate.

## Consequences

- Positive: the gestor has agency (bulk-select, see status,
  receive resolution email). The staff has a workbench (not an
  inbox to spelunk).
- Negative: a new subsystem to maintain. Cron filter must keep
  honouring `reconsiderada=False`; if a future refactor of
  `obtenir_novetats` drops the filter, rejected songs flood back
  in without the staff click — covered by tests at
  `ingesta/tests/test_previously_rejected_reconsiderada.py`.
- Sharp-edged: `pendents_ids` references `Canco.pk`s by value.
  If a Canco is hard-deleted between submission and resolution,
  the detail view marks the row as `missing: true`. The staff
  workbench tolerates this case.

## Related

- PR: #54
- Post-mortem: `docs/post-mortems/2026-05-19-workflow-sollicituds-redesigned.md`
- Architecture doc: `docs/architecture/comptes.md` (to be
  authored in FASE F of the docs sprint).
- Migrations: `comptes.0018_solicitudrevisio`,
  `music.0075_historialrevisio_reconsiderada`,
  `music.0076_alter_staffauditlog_action`.
