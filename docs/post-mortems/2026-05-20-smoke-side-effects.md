# Smoke E2E mutated production data — 2026-05-20

- **Date of incident:** 2026-05-20
- **Severity:** medium
- **Author:** Miquel

## Impact

During the FASE E smoke of the Workflow Sol·licituds sprint (PR
#54), the smoke script executed real mutations against production
data:

1. Reconsidered a real `HistorialRevisio` row (`pk=3980`, song
   "Sexo, Violencia Y Llantas" — rightfully rejected as
   non-Catalan). Setting `reconsiderada=True` would have caused
   the next ingestion cron to re-import it.
2. Created `SolicitudRevisio` `pk=1` linked to a real gestor
   (`miquelmatoses`) and a real artist (Rosalía), then advanced
   it through the full lifecycle (pendent → revisada → resolta).
3. Bumped `Artista[rosalia].ultim_ping_revisio_at`, starting a
   7-day cooldown against further smokes.

All three side-effects were manually reverted post-smoke via
`manage.py shell` (cleanup script in the same sprint chat log).

## Timeline

- ~16:44 UTC — smoke script runs end-to-end against production.
- ~16:45 UTC — Miquel realises the mutations are real, not
  isolated to a fixture.
- ~16:50 UTC — cleanup script reverts: `reconsiderada=False`,
  `SolicitudRevisio.delete()`, `ultim_ping_revisio_at=None`.

No public impact: the reconsidered song wouldn't have re-imported
until the next cron tick (overnight), and the sol·licitud was
never visible to anyone other than the operator.

## Root cause

The smoke used `force_authenticate(user=Usuari.objects.get(
username="miquelmatoses"))` and operated on the live Rosalía slug.
No fixture user or fixture artist was available, and the smoke
spec did not flag that absence as a blocker — it just used
whichever real records were closest.

## Fix applied

- **Immediate:** manual cleanup script in
  `manage.py shell` (reported in the original sprint chat).
- **Process:** new policy `docs/policies/identities.md` Rule 2
  requires E2E smokes to use a `qa_smoke` user + fixture artist.
- **Open backlog item:** create the `qa_smoke` fixture (Usuari +
  Artista with slug `qa-smoke` + Deezer ID in a reserved test
  range). Until that exists, smokes against production are
  permitted only with explicit per-mutation documentation +
  guaranteed revert script in the same session.

## Prevention

- `docs/policies/identities.md` § "Rule 2 — E2E smokes use a
  dedicated QA account, never real artists".

## Lessons learned

- Production data is convenient when the test is "does the flow
  work end-to-end against real DB shapes". The convenience is not
  worth the cleanup surface area when something goes wrong.
- The cleanup did work cleanly because each side-effect was
  documented during the smoke. That's a partial substitute for
  the missing fixture, but it relies on the operator being
  careful. The fixture is the right structural fix.
