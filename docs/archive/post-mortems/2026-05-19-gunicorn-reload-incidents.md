# Gunicorn `--reload` cascade — 3 incidents in one week — 2026-05-19

- **Date of incident:** 2026-05-19 to 2026-05-20 (three separate
  500-bursts on three consecutive days)
- **Severity:** high
- **Author:** Miquel

## Impact

Three production 5xx bursts on consecutive days, all on the same
shape:

- **2026-05-19 14:50-15:05 UTC** — 29 errors `500` on
  `/canco/<slug>` (and related staff API paths) for ~15 min.
  Reason: `Artista.imatge_url` referenced in code before migration
  `music.0072` was applied.
- **2026-05-20 ~13:00 UTC** — `obtenir_novetats` cron failed:
  `HistorialRevisio.reconsiderada` field referenced before
  migration `music.0075` was applied.
- **2026-05-20 (workbench)** — staff workbench 500 on first hit:
  `SolicitudRevisio` table referenced before migration
  `comptes.0018` was applied.

The handler at `django.utils.log.AdminEmailHandler` mailed
`admin@topquaranta.cat` for each batch of errors; ~30 admin
emails across the three incidents.

## Timeline

For the first incident, by way of example (the other two follow
the same shape):

- 14:30 UTC — sprint PR work in flight; `models.py` modified on
  the server worktree (Claude Code session, Mac venv unavailable).
- 14:50 UTC — gunicorn `--reload` picks up the modified module.
- 14:50 UTC — first request hits the staff API path; ORM tries
  `SELECT … "music_artista"."imatge_url" …`; PostgreSQL raises
  `UndefinedColumn`; Django returns 500.
- 14:51-15:05 UTC — 29 more 500s across various paths.
- 15:05 UTC — manual `manage.py migrate music` applied; 0
  pending after.
- 15:06 UTC — error rate drops to 0.

## Root cause

Two compounding causes:

1. `gunicorn` was running with `--reload`, configured 2026-04-27
   to avoid the "stale code after edit" friction. That made the
   server worktree an implicit deploy surface.
2. Claude Code sessions had been editing `models.py` directly on
   the server worktree (no Mac venv available) without running
   the matching `manage.py makemigrations + migrate` first.

The combination meant the workers always ran the *latest* code
but the DB schema lagged.

## Fix applied

- **Immediate:** manually applied the pending migration after each
  incident.
- **Definitive (PR #55, 2026-05-20):** removed `--reload` from
  `deploy/topquaranta-web.service`. Deploys now go exclusively
  through `bin/tq-deploy` (which runs `git reset --hard` →
  `manage.py migrate` → `systemctl reload`).
- Backup of the previous unit at
  `/etc/systemd/system/topquaranta-web.service.bak-20260520`.

## Prevention

The rules that catch this shape next time:

- `docs/policies/conventions.md` § "Migrations" — model change and
  migration land in the same PR; `bin/tq-deploy` applies before
  reload.
- `docs/decisions/0001-gunicorn-no-reload.md` — formal record of
  the `--reload` removal decision and why it stays removed.
- `docs/policies/identities.md` Rule 2 (E2E smokes) — adjacent
  guard against side-effects on production data during
  development.

## Lessons learned

- `--reload` is a development tool. Adding it to a production unit
  file (even with "low cost") turns every uncommitted edit into a
  silent deploy. The Apr-2026 rationale was correct in isolation;
  it didn't survive contact with multi-session Claude Code work.
- Admin email floods (30 emails in 15 min) are uncomfortable but
  useful detection. Without them we'd have noticed slower.
- The `tq-health` watchdog detected pending migrations in its
  hourly tick, but the bursts were too short for the hourly run
  to be the first signal.
