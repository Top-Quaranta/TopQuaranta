# RUNBOOK — TopQuaranta

Emergency playbook for the single-operator case (you, SSHed in).
When something breaks, start here. Each section is "symptom → diagnostic
command → remediation".

This document assumes user `topquaranta` on host `188.245.60.20`.
Service: `topquaranta-web.service` (gunicorn on :8083), reverse proxy
Caddy, PostgreSQL on localhost.

**Two front-ends since Sprint 4**: React SPA bundle at
`/home/topquaranta/app/web-react/dist/` served directly by Caddy from the
root, and a small Django HTML surface for auth flows (`/compte/2fa/*`,
`/compte/registre/`, `/compte/activar/*`, `/compte/login/`,
`/compte/logout/`) plus `/api/v1/*` and `/sitemap.xml` / `/robots.txt`.
A page serving blank despite `systemctl` being OK is almost always a
missing `npm run build` in `web-react/` — see §1 below.

---

## First 60 seconds — "is it still alive?"

```bash
ssh topquaranta@188.245.60.20
tq-health                   # one-line per cron; exits non-zero if anything is wrong
systemctl is-active topquaranta-web caddy postgresql
curl -sI https://www.topquaranta.cat/ | head -3
```

If all three are OK and `tq-health` exits 0, move on. If not, jump to
the matching section below.

---

## 1. The public site is down (5xx / timeout)

**Diagnose:**
```bash
systemctl status topquaranta-web
journalctl -u topquaranta-web -n 100 --no-pager
tail -50 /var/log/topquaranta/errors.log
systemctl status caddy
```

**Common causes + fix:**

| Symptom | Likely cause | Fix |
|---|---|---|
| `502 Bad Gateway` + gunicorn inactive | Service crashed / OOM | `sudo systemctl restart topquaranta-web` — for code deploys prefer `reload` to avoid 502 during worker swap |
| `504 Gateway Timeout` | Slow DB query, worker starvation | Check `SELECT * FROM pg_stat_activity WHERE state='active'` via `sudo -u postgres psql topquaranta`. Kill runaway query with `SELECT pg_cancel_backend(PID)`. |
| Blank page on `/` or `/top` but `/api/v1/auth/me/` → 200 | React bundle missing or stale | `cd /home/topquaranta/app/web-react && npm run build`. Caddy serves from `dist/` directly, no gunicorn reload needed. |
| TLS cert error | Caddy auto-renew failed | `sudo journalctl -u caddy -n 200`. Usually resolves itself within 24h; Caddy retries. |
| Django 500 on `/api/*` or `/compte/2fa/*` | Bug in code | `tail -50 /var/log/topquaranta/errors.log`. Rollback: `git reset --hard HEAD~1 && sudo systemctl reload topquaranta-web`. |
| "Alguna cosa ha fallat" React error boundary | Client-side JS crash | Browser console gives the stack. Most common: null-guard on a new API field that wasn't returned. |

---

## 2. A cron failed (`tq-health` shows FAIL or STALE)

`tq-recover` already retries automatically every 30 minutes (R7) — up to
5 times per command per day. If after that the status is still FAIL,
human attention is needed.

**Diagnose:**
```bash
cat /var/log/topquaranta/status/<tag>.status
tail -50 /var/log/topquaranta/<tag>.log     # e.g. senyal.log for obtenir_senyal
```

**Common causes:**

- **Last.fm or Deezer rate-limiting** → look at the tail of the output. If
  you see `429` or `Forbidden`, wait 1h and retry manually:
  `sudo -u topquaranta tq-run <command>`.
- **Python exception from a recent deploy** → rollback, or fix forward and
  push. Then run `tq-run <command>` to clear the FAIL status.
- **Lock file held by a runaway process** (obtenir_novetats only):
  `ps auxf | grep obtenir_novetats`. If stuck, `kill` the PID and
  `rm /tmp/obtenir_novetats.lock`.
- **Signal D5 self-collab** (ValidationError trace ending in
  `prevent_self_collab`): an artista has multiple `ArtistaDeezer`
  rows and Deezer returned the alternate as a contributor. Fixed
  in code 2026-05-03 — if the trace recurs, check that
  `_create_track`/`_upsert_track` still compare the contributor
  against `artista.deezer_ids.values_list("deezer_id", flat=True)`
  (the full set, not just `deezer_id_principal`). Quickest hot-fix
  if you can't deploy: open the Django shell and remove the
  offending alternate `ArtistaDeezer` row.
- **`obtenir_novetats` re-checking thousands of albums every hour**:
  by design after the 2026-05-03 P2 redesign — the cron now uses
  `Album.last_album_check` + age-based cooldown (24 h / 7 d / 30 d).
  After a deploy, NULL `last_album_check` rows take precedence and
  drain in ~6-7 hours, then the steady-state queue shrinks. If
  the queue never settles, check that the legacy
  `cancons_obtingudes` filter wasn't reintroduced.
- **`obtenir_novetats` returning `Total crides: 0` for many hours
  in a row** (no new tracks ingesting): the per-artist 24 h cooldown
  on `last_checked_deezer` clusters all timestamps together if a
  single run swept the entire fleet (caught 2026-05-05 after a
  backfill processed all 1900 artistes in 40 min). Two-step fix:
  (a) cap future runs with `--max-p3-per-run 200` (already in the
  cron line); (b) one-shot redistribution to scatter the existing
  timestamps:
  ```python
  from django.utils import timezone
  from datetime import timedelta
  import random
  from music.models import Artista
  qs = list(Artista.objects.filter(aprovat=True, deezer_ids__isnull=False).distinct())
  random.shuffle(qs)
  step = (24 * 3600) // max(len(qs), 1)
  now = timezone.now()
  for i, a in enumerate(qs):
      a.last_checked_deezer = now - timedelta(hours=24) + timedelta(seconds=i * step)
      a.save(update_fields=["last_checked_deezer"])
  ```
- **Whisper SKIPPED_BY_LOCK at 04:00 UTC** (was 05:00 pre-2026-05-05):
  the shared `ram_heavy.lock` is held by an MB cron that overran its
  30-min slot. The 2026-05-05 cron tuning (MB `--limit 100`, Whisper
  slot 04:00 UTC with `--limit 200`) prevents this in steady state.
  If it still happens, check the artiste being processed by the live
  MB run — large foreign discographies (50+ albums) can stretch the
  walltime. One-off fix: `kill` the MB python PID and let the next
  hour's MB tick continue from where it stopped (the cron is
  idempotent — `mb_last_sync` records progress).

**If you fixed it:** re-run manually to clear the FAIL:
```bash
sudo -u topquaranta /home/topquaranta/bin/tq-run <command>
```

**Other states you may see** (auditoria 2026-06-07):

- **MISSING** — a frequent cron (`max_age_hours <= 48`) with no status
  file at all. The tag was never written: a cron line was dropped, the
  `tq-run` tag derivation doesn't match the registered tag, or `tq-run`
  itself is broken. Check `deploy/cron.topquaranta` has the line and
  that its derived tag (see below) matches a `deploy/cron-meta.json`
  key. Weekly/monthly crons with no file yet stay the benign WAITING.
- **ORPHAN** — a `*.status` file with no `cron-meta.json` entry. Either
  register the cron in `cron-meta.json`, or, if it is stale residue
  from a removed/renamed command, just `rm` the file:
  `sudo -u topquaranta rm /var/log/topquaranta/status/<tag>.status`.

**Status-file contract — what writes a tag.** Every cron run through
`tq-run` writes `/var/log/topquaranta/status/<tag>.status`. The `<tag>`
is the command name plus its distinguishing variant, so runs on
different cadences don't overwrite each other:

| invocation | tag |
|---|---|
| `calcular_top --provisional` | `calcular_top_provisional` |
| `actualitzar_playlists_spotify --freq weekly` | `actualitzar_playlists_spotify_weekly` |
| `actualitzar_playlists_spotify --freq daily` | `actualitzar_playlists_spotify` |
| `publicar_canal --channel mastodon` | `publicar_canal_mastodon` |

The Postgres backup (`tq-backup`) and the recovery sweep (`tq-recover`)
are bash scripts, not `tq-run` commands, but they now write their own
`tq-backup.status` / `tq-recover.status` in the same format, so the
backup and the recovery net are themselves monitored by `tq-health`
(before 2026-06-07 they ran outside the contract and nothing watched
them). A CI test (`test_every_cron_invocation_has_meta_entry`) asserts
every cron line resolves to a registered tag.

---

## 3. Ranking is wrong / a week is missing

**Weekly official ranking missing** (Saturday didn't publish):

```bash
grep calcular_top /var/log/topquaranta/status/*.status
# If FAIL, re-run manually:
sudo -u topquaranta tq-run calcular_top

# Compute a specific week:
sudo -u topquaranta tq-run calcular_top --setmana 2026-04-13
```

**Provisional is obviously wrong** (e.g. a known-popular track missing):

```bash
# Check the artist is approved and has verified tracks
sudo -u postgres psql topquaranta -c "
  SELECT a.nom, a.aprovat, COUNT(c.id) FILTER (WHERE c.verificada)
  FROM music_artista a LEFT JOIN music_canco c ON c.artista_id=a.id
  WHERE a.nom ILIKE '%name%'
  GROUP BY a.id, a.nom;"
# Check SenyalDiari has recent rows:
sudo -u postgres psql topquaranta -c "
  SELECT data, COUNT(*) FROM ranking_senyaldiari
  WHERE data >= CURRENT_DATE - 7 GROUP BY data ORDER BY data DESC;"
```

---

## 4. Database is broken

**Full backup + restore to a test DB** (R14 runs this monthly; run
manually if you want extra confidence):

```bash
sudo -u postgres /home/topquaranta/bin/tq-restore-test
cat /var/log/topquaranta/status/tq-restore-test.status
```

**Emergency restore to production** (data loss):

```bash
# List backups, newest first
ls -lt /home/topquaranta/backups/daily/ | head
# Pick one
gunzip -c /home/topquaranta/backups/daily/tq-YYYYMMDD-HHMMSS.sql.gz \
    | sudo -u postgres psql topquaranta
# Restart gunicorn to drop any stale connections from the pool
sudo systemctl restart topquaranta-web
```

**⚠ This overwrites current data.** Take a fresh `pg_dump` first.

### Backup layers — local + offsite (capa 2)

Backups land at `/home/topquaranta/backups/{daily,weekly,monthly,monthly-safe}/`
on the same Hetzner CX22 (retention tiers: `docs/ops/retention.md`
§Backups). The 2026-05-07 "single-host, accepted risk" decision was
**revisited 2026-07-05** when the DB gained community PII: a second,
offsite layer now exists — `bin/tq-backup-offsite` (daily 03:30,
restic → Backblaze B2, append-only server key, encrypted at origin).
It ships **gated**: until `OFFSITE_BACKUP_ACTIU=1` + the restic vars
land in the `.env` and restic is installed, it reports `DISABLED`
(gray in tq-health — a legitimate state, not a failure). Activation
procedure, threat model and payload: `docs/ops/backup-offsite.md`.

To restore from the offsite layer (box lost entirely): from the Mac,
with the restic password from the password manager and the B2 admin
key, `restic -r <repo> restore latest --target /tmp/restore`. The
quarterly manual drill in `backup-offsite.md` §9 keeps this path warm.

---

## 5. Disk is full

```bash
df -h
du -sh /var/log/topquaranta /home/topquaranta/backups /home/topquaranta/app/staticfiles
```

Main offenders: log files (rotated weekly by logrotate — see
`deploy/logrotate.topquaranta`), old backups (retention is
7d/4w/12m), staticfiles (safe to delete; `collectstatic` rebuilds).

**Quick wins:**
```bash
sudo logrotate -f /etc/logrotate.d/topquaranta
find /home/topquaranta/backups/daily -mtime +7 -delete
```

---

## 6. Rolling back a bad deploy

```bash
cd /home/topquaranta/app
git log --oneline -10
git reset --hard <known-good-commit-sha>
sudo systemctl restart topquaranta-web
# If the bad commit included a migration:
sudo -u topquaranta DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    /home/topquaranta/app/.venv/bin/python manage.py migrate <app> <previous-migration>
```

---

## 7. Locked out of the staff panel

**Lost 2FA device / lost password:**

Password reset requires SSH access to the server (there's no admin
invite flow). Reset directly:

```bash
sudo -u topquaranta DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    /home/topquaranta/app/.venv/bin/python manage.py changepassword <username>

# Remove 2FA for a user (requires management command from S11):
sudo -u topquaranta DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    /home/topquaranta/app/.venv/bin/python manage.py reset_2fa <username>
```

**django-axes has locked me out** (S4 brute-force protection):

```bash
sudo -u topquaranta DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    /home/topquaranta/app/.venv/bin/python manage.py axes_reset_username <username>
```

---

## 8. "I need to re-run a data migration"

Django migrations should be idempotent, but `RunPython` blocks aren't
always. Before re-running:

```bash
sudo -u postgres psql topquaranta -c \
    "SELECT * FROM django_migrations WHERE app='music' ORDER BY id DESC LIMIT 5;"
```

If you need to mark a migration as un-applied (dangerous):

```bash
sudo -u postgres psql topquaranta -c \
    "DELETE FROM django_migrations WHERE app='music' AND name='0034_d5_cleanup_self_collabs';"
```

Then re-run `manage.py migrate music`.

---

## 9.4. WORK_DONE protocol — silent-noop detection

`tq-run` recognises an opt-in line in command output:

```
WORK_DONE=<int>
```

The LAST occurrence is parsed and written to the status file as
`work_done=N`. `tq-run` also tracks `consecutive_zero_work=N` —
incremented when `WORK_DONE=0`, reset otherwise. The staff
dashboard at `/staff/estat` surfaces both.

**Why**: a cron exiting 0 with no real work (early-return on empty
queryset, silent skip path, etc.) used to look identical to a healthy
run. `obtenir_novetats` was stuck for ~12 days in 2026-05 with
nightly `status=OK` reports; the SKIPPED_BY_LOCK path closed one
hole, this protocol closes another.

To opt a command in, emit one line at the end of `handle()`:

```python
self.stdout.write(f"WORK_DONE={n_rows_written}")
```

What "work" means is up to the command — pick whatever quantity
would be 0 if the command is broken. Examples:

  - `obtenir_senyal`: `success + errors` (rows written to SenyalDiari).
  - `obtenir_novetats` (when migrated): albums actually re-checked.
  - `inferir_genere` (when migrated): artistes whose canonical genre
    changed.

Commands that don't opt in are unaffected; `work_done` stays
unset on the dashboard.

---

## 9.4 bis. Deploy ordering — always `tq-deploy`

**Caught 2026-05-07**: a `feat(ingest)` push landed code that read
`Album.label` BEFORE the migration adding the column was applied.
Gunicorn `--reload` picked up the new code in under a second; every
visitor to `/album/<slug>` hit a 500 for ~15 minutes, sending one
admin email per request — 30 emails landed in the inbox before
anyone noticed.

**The rule**: never run `git pull` followed by a bare
`systemctl reload` on the production box. Always:

```bash
/home/topquaranta/bin/tq-deploy
```

`tq-deploy` enforces the safe ordering:
  1. `git pull --ff-only`
  2. `manage.py migrate --check` → if pending, `migrate` BEFORE the
     reload (otherwise the new code reads columns the DB doesn't
     have)
  3. `npm run build` if `web-react/` changed in the pulled commits
  4. `systemctl reload topquaranta-web`
  5. Smoke-test homepage + a hot API endpoint

Flags: `--skip-build` (when SPA isn't touched), `--dry` (show plan).
Exit codes: 1 migration failed, 2 build failed, 3 reload failed,
4 smoke test failed.

**Detection net**: `tq-health` now emits a `DB migrations: ...`
row (added 2026-05-07). If somehow a deploy bypasses `tq-deploy`
and leaves the DB behind the code, the next hourly tick of the
`tq-health --email-on-fail` cron flags it. The signature-dedup
limits inbox noise to one alert per distinct failure state: the
signature is computed (by `health_report.py --print-signature`) over
the STABLE identity of the anomaly set — escalating crons by
`(name, state)` plus a boolean per system threshold crossing — NOT
over the rendered text. So a persistent failure mails ONCE; only a
new or cleared problem re-alerts. (Before 2026-06-07 the signature
grep'd the report, which embedded the summary timestamp, the "fa Xh"
ages and the daily error count, so every hourly tick re-spammed.)

**TLS certificate expiry watch** (added 2026-07-27): `tq-health` emits
a `CERTIFICATS TLS` block that opens a real TLS connection to every
configured endpoint, with explicit SNI, and reads `notAfter` from the
certificate **actually served**. It never reads a PEM from disk. That
is the entire lesson of the July 2026 incident: `/etc/stalwart/certs`
held a valid certificate from 26 June onwards while Stalwart kept
serving an April one that expired on 26 July, so a file-based check
would have reported healthy for a month. See
`docs/post-mortems/2026-07-26-stalwart-cert-expirat.md`.

Wired as `scripts/health/tls_certs.sh` → `music.health.check_tls_certs`,
the same sub-check pattern as the Spotify and Instagram-token rows.

Per endpoint there are three states:

| State | Meaning | Severity |
|---|---|---|
| `ok` | more than the threshold in days of runway | OK |
| `expiring` | inside the threshold — or already past it | WARN, CRIT once expired |
| `error` | could not connect, handshake, or parse | CRIT |

An endpoint that cannot be reached is **never** reported as `ok`, and
one failing endpoint does not stop the others from being measured. The
handshake deliberately does not verify the chain: verification raises
on an expired certificate, which would surface the one case we care
about as "unreachable" instead of "expired". Timeout is 5 s per
endpoint.

Configuration lives in `ConfiguracioGlobal`, editable from
`/staff/configuracio` under **Fiabilitat i certificats**:

- `tls_endpoints_vigilats` — one `host:port` per line. Blank lines and
  `#` comments are ignored, so a candidate can be parked without being
  enabled. Ports 25 and 587 negotiate STARTTLS; everything else is
  direct TLS.
- `tls_avis_dies` — days of runway below which it warns. Default 21,
  which sits above Let's Encrypt's ~30-day renewal window, so a
  renewal that never lands is noticed before it is urgent.

**The list ships EMPTY.** Deploying the check changes nothing until an
operator opts in. Recommended entries when you do:

```
mail.topquaranta.cat:993
mail.topquaranta.cat:465
mail.topquaranta.cat:25
topquaranta.cat:443
api.cercol.team:443
autoconfig.topquaranta.cat:443
```

A failing endpoint escalates `overall`, so the hourly
`tq-health --email-on-fail` cron mails admin@ within the hour, and it
contributes `tls:certs` to the dedup signature — one mail per distinct
problem, not one per hour.

**SPA asset check** (hardened 2026-07-31): the `Web SPA shell` row is
produced by `scripts/health/spa_assets.sh`, same sub-check pattern as
the TLS and Spotify rows. It fetches `/`, asserts `<div id="root">`,
extracts the two hashed paths the shell references, and probes both.

It asserts **content-type, not just the status code**. The SPA vhost
ends in `try_files {path} /index.html` (`deploy/Caddyfile`), so a
missing asset is served as the SPA shell with HTTP 200 — never a 404.
Measured on prod 2026-07-31:

```
/assets/index-Cmw8JJjD.css    200  [text/css; charset=utf-8]
/assets/index-7Kggo81f.js     200  [text/javascript; charset=utf-8]
/assets/index-NOEXISTEIX.css  200  [text/html; charset=utf-8]   <-- fallback
```

The status-only check this replaced was therefore unfalsifiable: its
`(dist stale?)` branch could not be reached by a stale dist. The module
script was not probed at all; now it is, expecting
`text/javascript` or `application/javascript`.

Three failure branches, each naming its own cause:

| Branch | Detail says | Where to look |
|---|---|---|
| No HTTP response | `000 cap resposta HTTP (transport: …)` | network, TLS, Caddy up? |
| Unexpected status | `HTTP <code> (el servidor respon…)` | Caddy routing, backend |
| Wrong content-type | `200 però content-type '…' (fallback try_files)` | the dist — asset genuinely absent |

A transport failure is retried once after a short wait before it goes
red. A probe that recovers stays green and appends `— reintent OK: …`
to the detail, so a flapping edge stays visible instead of being
swallowed. This is why the hourly tick of 2026-07-31 11:15 paged: one
dropped connection, no dist problem, and the detail read `000000`
because `%{http_code}` already emits `000` and the old
`|| echo 000` appended a second one.

Tested at `topquaranta/tests/test_health_spa_assets.py`, which runs the
real script against a stub server that emulates the `try_files`
fallback. Env overrides for a manual run: `TQ_HEALTH_WEB_PUBLIC`,
`TQ_HEALTH_ASSET_TIMEOUT`, `TQ_HEALTH_RETRY_WAIT`.

**Git-tree drift detection** (added 2026-06-02): `tq-health` also
emits a `Git tree: ...` row, delegating the classification to
`bin/tq-git-drift` (a standalone helper so the logic is unit-tested —
`topquaranta/tests/test_deploy_safety.py::test_tq_git_drift_*`). It
flags a `DRIFT` anomaly (and escalates `overall`, so `--email-on-fail`
mails admin@ within the hour) when:

- `git status --porcelain` is non-empty (excluding the `data/` scratch
  dir) — someone wrote code directly into `/home/topquaranta/app/`,
  bypassing push→GHA→`tq-deploy`. Such edits run un-reviewed and are
  silently reverted on the next deploy. Canonical incident: the
  2026-06-02 caducitat guard (`ingesta/caducitat.py`) ran in prod for
  days while absent from `origin/main`; or
- `HEAD` is **ahead of / divergent from** `origin/main`, or behind it by
  a commit that touches **code** — a real deploy is pending or failed.

It does **NOT** flag a `HEAD` that merely lags `origin/main` by
**doc-only** commits (`docs/**`, `*.md`, `LICENSE*`, CI/docs workflows).
`deploy.yml`'s `paths-ignore` skips deploys for those, so prod
legitimately stays behind until the next code change — reporting it as
`OK (behind origin by N doc-only commit(s), deploy-skipped)`. This
closed a false-🔴 that fired after every doc-only merge (surfaced
2026-07-14 by PRs #328/#329 landing while prod sat on the last code
deploy). The helper's `paths-ignore` regex MUST mirror `deploy.yml`.
The token `DRIFT` is included in the email-alert grep.

### Where the deploy's "it failed, so it went red" guarantee lives

**Audited 2026-07-27.** `deploy.yml` used to carry `script_stop: true`
and a comment promising "any non-zero exit aborts the deploy and the
workflow fails". That promise rested on an input the action no longer
accepts.

Established by reading `action.yml` at both tags via `gh api`:

- **v1.2.0** declared `script_stop` as an input (and passed it through
  as `INPUT_SCRIPT_STOP`). It was a real parameter.
- **v1.2.5** does not declare it at all. The Dependabot bump in **#32**
  changed exactly one line — the version — so the input was dropped
  silently and every run since has logged
  `Unexpected input(s) 'script_stop'`.
- v1.2.5 adds `capture_stdout`, `curl_insecure` and `version`; **none**
  of them replaces `script_stop`, and its `action.yml` says nothing
  about how the remote exit status is propagated.

**Still unverified, deliberately**: whether a non-zero remote exit turns
the GitHub job red. That behaviour lives in the `drone-ssh` binary the
action downloads at run time, which we have not read. Do not infer it
from a deploy that succeeded — a green run says nothing about the
failure path. Treat the chain as unproven end to end.

What we did instead of trusting the action:

- `set -e` in the workflow's `script` block, so the remote shell aborts
  on the first failure without needing any input from the action.
- The **absolute** path `/home/topquaranta/app/bin/tq-deploy`. With the
  old relative `bin/tq-deploy`, a failed `cd` would have resolved it
  against the SSH login directory. `/home/topquaranta/bin/tq-deploy`
  does exist — but it is a **symlink to the same repo file** (verified
  2026-07-27, identical sha256), so the hazard was latent, not live.
  The absolute path removes it regardless.
- `bin/tq-deploy` propagates its own documented exit codes, now
  including every code it actually uses (6 and 64 were in use and
  undocumented).

### The changed-file list is computed once, and loudly

`tq-deploy` used to detect what changed with
`git diff --name-only A B | grep -q X` **inside an `if` condition**,
once for `requirements.txt` and once for `web-react/`. Inside a
condition `set -e` does not apply, so a git failure made the condition
false — indistinguishable from "that path did not change". The deploy
then skipped the venv sync and the SPA build, printed
`✓ Deploy complete` and exited 0.

That is the same shape as the certificate sync script that reported
success for a month while the mail server served an expiring
certificate: **a check that cannot tell "nothing changed" from "I could
not look"**. See `docs/post-mortems/2026-07-26-stalwart-cert-expirat.md`
and the Ops-scripts rule in `docs/policies/conventions.md`.

The list is now computed once, before any condition, by
`bin/tq-changed-files <from-ref> <to-ref>`, which exits **7** with a
message on stderr when git cannot answer. `tq-deploy` aborts on that
code before taking any action. The helper is separate so the failure
path is unit-testable — `tq-deploy` itself refuses to run as anyone but
`topquaranta` and needs sudo and network, so the logic could not be
exercised while it was inline. Tests:
`topquaranta/tests/test_deploy_safety.py::test_tq_changed_files_*`,
plus a static guard that the inline `git diff --name-only` form does not
come back.

Smoke-test failures are also split now: **4** means the endpoint
answered with something other than 200, **8** means it could not be
reached at all (DNS, connection, TLS). Previously a network-level
`curl` failure aborted with curl's own status, and curl's 6
("couldn't resolve host") collided with the venv/pip 6.

**Pytest gates**: `topquaranta/tests/test_deploy_safety.py` asserts
(a) `makemigrations --check` is clean (every model change has a
committed migration), (b) `tq-deploy` and `tq-health` parse with
`bash -n`, (c) `tq-health` still emits the migration-status row, and
(d) the changed-file detection fails loudly instead of skipping.
A future refactor that drops any of these silently breaks a test.

## 9.5. CSP inline-style hash regeneration

The Caddyfile `Content-Security-Policy` allows the single inline
`<style>` block in `web-react/index.html` (critical above-the-fold
paint) via a SHA-256 hash. **If you ever edit that `<style>` block,
the deployed page will start failing CSP and refuse to paint with
the splash colours.** Procedure:

```bash
cd /home/topquaranta/app/web-react
npm run build  # regenerate dist/index.html

# Hash the inline <style> body (whitespace-sensitive)
python3 -c "
import re, hashlib, base64
html = open('dist/index.html').read()
m = re.search(r'<style[^>]*>(.*?)</style>', html, re.S)
print('sha256-' + base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode())
"
# → sha256-XYZ...
```

Replace the hash in `deploy/Caddyfile` (search for `sha256-` in the
`Content-Security-Policy` line, swap), then:

```bash
sudo install -o root -g root -m 644 deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl -sI https://www.topquaranta.cat/ | grep -i content-security
```

Verify the new hash is in the response and the homepage paints
without console errors. If it doesn't, your hash is wrong (likely
whitespace mismatch — be careful copy-pasting from the script
output).

The `<script>` directive uses `'self'` only; no inline scripts allowed.
If you ever need to add an inline `<script>` to `index.html`, either
move it to `public/<name>.js` (preferred — covered by `'self'`) or
add another `'sha256-...'` to script-src using the same procedure.

---

## 9. Secret rotation

> Cadence: every secret in `.env` and the Django DB should be rotated
> at least once a year. After a known compromise (laptop loss, phishing
> click, suspected leak in logs/screenshots), rotate **immediately**.

| Secret | Where | How |
|---|---|---|
| `DJANGO_SECRET_KEY` | `.env` | Generate (`python -c "import secrets; print(secrets.token_urlsafe(50))"`); replace in `.env`; `sudo systemctl reload topquaranta-web`. **Side effect**: every active session is invalidated, every `signing.dumps` token (newsletter unsubscribe, email-confirm-delete) breaks — accept it, affected users get a fresh link on next email cycle. |
| Postgres `topquaranta` password | `DATABASE_URL` in `.env` | `sudo -u postgres psql -c "ALTER USER topquaranta WITH PASSWORD '...';"` → update `.env` → reload web. |
| `LASTFM_API_KEY` + `LASTFM_API_SECRET` | `.env` | Re-issue at `https://www.last.fm/api/account` → update `.env` → reload. Cron picks up the new key on next tick. |
| `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` | `.env` | Re-issue at Spotify Developer Dashboard. After update, **re-OAuth** via `/staff/social/spotify/` since the existing refresh_token gets invalidated. |
| Spotify refresh_token | `SpotifyAuth` row (pk=1) | Re-OAuth from `/staff/social/spotify/` when the daily sync starts failing `invalid_grant`. |
| Instagram long-lived token | `InstagramAuth` row (pk=1), **not** `.env` | **Renewal is MANUAL.** The Meta app is in *development mode* (business verification denied), so there is no working auto-refresh — `renovar_token_instagram` only *prints*, it never persists. Regenerate a long-lived **Instagram-Login** token (scope `instagram_business_content_publish`, `graph.instagram.com` flavor) for @topquaranta from the Meta App Dashboard, then paste it at **`/staff/social/instagram`** (writes the DB row, resolves `user_id`, sets `expires_at = now+60d`). `tq-health` alerts **WARN ≤10d / CRIT ≤5d** on that stored expiry (real Meta expiry isn't queryable with our token — `debug_token` 400s). Note: a token can also be **invalidated out-of-band** by Meta before expiry (2026-07-07 incident); that surfaces as `publicar_social`/`publicar_canal` `status=FAIL`, not as the expiry alert. |
| `BREVO_API_KEY` | Stalwart MTA relay config | Brevo dashboard → API & SMTP → regenerate v3 key → update Stalwart relay → `sudo systemctl restart stalwart`. |
| `RESEND_API_KEY` | Stalwart MTA relay config | Resend dashboard → API Keys → roll → update Stalwart → restart. |
| `HETZNER_API_TOKEN` | `.env` | Hetzner Cloud Console → Security → API Tokens → roll → update `.env`. Used by manual scripts only; no restart needed. |
| `CDMON_API_KEY` | `.env` | CDMON panel → API → regenerate → update `.env`. Manual scripts only. |
| `MastodonAuth.access_token` | DB row (singleton) | Re-OAuth from `/staff/social/mastodon/`. |
| `BlueskyAuth.app_password` | DB row (singleton) | Generate new app password at bsky.app → settings → app passwords → update via `/staff/social/bluesky/`. |
| `TelegramAuth.bot_token` | DB row (singleton) | Re-issue from BotFather (`/revoke` then `/token`) → update via `/staff/social/telegram/`. |

**Rotation checklist** (do in this order to avoid downtime):

1. Generate the new secret BEFORE invalidating the old one (most
   providers let both coexist briefly).
2. Update `.env` (or DB row).
3. Reload the affected service:
   - Django path → `sudo systemctl reload topquaranta-web`
   - Mail path   → `sudo systemctl restart stalwart`
   - Cron-only   → nothing; next tick uses new value.
4. Verify by triggering one operation that uses the secret.
5. **Only then** revoke the old secret on the provider's side.

**After a compromise** (deviates from above): revoke the old secret
**first**, accept the temporary breakage, then issue and deploy the
new one. The risk of a leaked secret being used outweighs the
deploy window.

---

## 10. Applying destructive migrations safely

A "destructive migration" is one that drops, renames, or narrows a
column (or drops/renames a model). Concretely, any migration with an
operation matching:

  - `RemoveField`
  - `DeleteModel`
  - `RenameField`     — old name disappears
  - `RenameModel`     — old table disappears
  - `AlterField`      — when narrowing (CharField → smaller max_length,
                        NULL → NOT NULL, etc.)

### Why this section exists

**Caught 2026-05-07**: I dropped `Album.cancons_obtingudes` via
migration `0069`. A long-running `obtenir_metadata_musicbrainz` cron
that started ~25 min before the migration kept the OLD model
definition in memory. Every subsequent `Album.objects.filter(...)`
query produced `psycopg2.errors.UndefinedColumn: column
music_album.cancons_obtingudes does not exist`. **15 errors before
the cron was killed manually**. The cron isn't restarted by
`systemctl reload topquaranta-web` because it runs via cron, not
gunicorn — so the standard reload doesn't catch it.

### Pre-flight checklist

Before `manage.py migrate`:

```bash
# 1. Identify long-running cron processes that might cache the old model.
/home/topquaranta/bin/tq-pre-migrate
```

That script lists every `manage.py` process running for >5 minutes
and tells you whether any of them have been alive longer than the
migration is safe to apply. If anything is listed:

```bash
# 2. Kill the stale process(es). The next cron tick (≤15 min) will
#    start a fresh python with the new code.
sudo pkill -f 'manage.py obtenir_metadata_musicbrainz'
# Confirm:
ps aux | grep manage.py | grep -v grep
```

```bash
# 3. Now apply the migration.
sudo systemctl reload topquaranta-web    # gunicorn picks up new code
DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    /home/topquaranta/app/.venv/bin/python /home/topquaranta/app/manage.py migrate
```

```bash
# 4. Verify no errors in the next 5 minutes.
tail -f /var/log/topquaranta/errors.log
```

### What if a cron is mid-flight when you realise

Same fix retroactively: kill the stale process, then check that
`/var/log/topquaranta/errors.log` stops accumulating new entries.

### CI flag

A GitHub Actions job (`destructive-migrations`) flags every PR that
adds a migration with a destructive operation. It's a soft warning
(doesn't block merge) — the checklist is the safety net, not the CI.

---

## Phone numbers

This is a single-operator project. The phone number is yours. In that
case — the best thing to do is **write more here** each time you solve
an incident, so future-you doesn't start from zero.

---

## Gunicorn — sense `--reload`

El unit file de `topquaranta-web` **NO** ha de contenir el flag
`--reload`. Aquest flag causa que els workers agafin codi del worktree
sense aplicar migracions, provocant errors 500 a producció.

Incidents 2026-05 que ho van demostrar:
- 2026-05-19 — `Artista.imatge_url` referenciat al codi abans de la
  migració 0072. 29 errors 500 a `/canco/<slug>` en 15 min.
- 2026-05-20 — `HistorialRevisio.reconsiderada` referenciat abans
  de la migració 0075. `obtenir_novetats` cron-fail.
- 2026-05-20 — `SolicitudRevisio` table referenciada abans de
  `comptes 0018`. Staff workbench 500.

El deploy s'ha de fer **SEMPRE** via `bin/tq-deploy`, que:
1. `git reset --hard origin/main` (neteja drift del worktree).
2. Aplica migracions pendents abans del reload (`manage.py migrate`).
3. Reload graceful de gunicorn via SIGHUP.

Backup del unit file anterior (amb `--reload`):
`/etc/systemd/system/topquaranta-web.service.bak-20260520`.

Font de veritat del unit: `deploy/topquaranta-web.service` al repo.
`bin/tq-sync-infra` el sincronitza a `/etc/systemd/system/` quan
detecta drift, i fa `systemctl daemon-reload`.

Vegeu `docs/decisions/0001-gunicorn-no-reload.md` i
`docs/post-mortems/2026-05-19-gunicorn-reload-incidents.md`.

---

## GSC — auth path

El cron `recollir_metrics_gsc` usa OAuth user credentials del compte
**admin@topquaranta.cat** (refresh_token al `.env` com a
`GSC_OAUTH_REFRESH_TOKEN`). El service account
`seo-ingest@topquaranta-seo.iam.gserviceaccount.com` queda al
`.secrets/` com a fallback inactiu però **NO es pot usar** perquè
Google té un bug confirmat
(https://support.google.com/webmasters/community-guide/429538961)
que impedeix afegir service accounts nous a propietats `sc-domain:`
amb error "Failed to add user: email address not found".

Bug documentat al commit `9391e3f` del 2026-05-06 al repo.

### Si cal regenerar el refresh_token

(Per pèrdua de permisos, canvi de responsable de la propietat, o
revocació explícita al panel del compte Google.)

1. Verificar a GSC que el compte propietari té rol Owner/Full a la
   propietat `sc-domain:topquaranta.cat`.
2. OAuth Playground (https://developers.google.com/oauthplayground/)
   → engranatge dalt-dreta → "Use your own OAuth credentials" →
   enganxar `GSC_OAUTH_CLIENT_ID` i `GSC_OAUTH_CLIENT_SECRET` del
   `.env` actual.
3. Scope: `https://www.googleapis.com/auth/webmasters.readonly`.
4. Autoritzar amb **admin@topquaranta.cat**.
5. Substituir `GSC_OAUTH_REFRESH_TOKEN` al `.env`, fer backup, i
   `sudo systemctl restart topquaranta-web`.
6. Re-executar manualment cobrint el gap dels dies fallits:
   `sudo -u topquaranta /home/topquaranta/bin/tq-run recollir_metrics_gsc`
   (o `manage.py recollir_metrics_gsc --date YYYY-MM-DD` per cada
   dia perdut; el flag és `--date`, no `--since`).

Backup del `.env` pre-canvi a `/home/topquaranta/app/.env.bak-YYYYMMDD`.

Vegeu `docs/decisions/0002-gsc-oauth-user-creds.md` i
`docs/post-mortems/2026-05-20-gsc-permission-revoked.md`.

## Spotify — auth path

El cron `actualitzar_playlists_spotify` usa OAuth user credentials
del compte **admin@topquaranta.cat** (refresh_token a la fila
singleton `music.SpotifyAuth(pk=1)`) i requereix una subscripció
**Spotify Premium activa** al mateix compte. Política Spotify des
de finals de 2024: qualsevol crida Web API des d'una app amb
propietari free retorna `403 "Active premium subscription
required for the owner of the app"`.

`SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` al `.env`,
`SPOTIFY_REDIRECT_URI=https://www.topquaranta.cat/staff/social/spotify/callback`.

### Si Spotify Premium ha expirat

Símptoma: tots els cron tick fallen amb el 403 anterior. La pàgina
`/staff/social/spotify/` mostra el badge "Premium" en vermell amb
el valor real de `me().product`.

1. Re-activar Premium a `https://www.spotify.com/account/upgrade/`
   amb el compte `admin@topquaranta.cat`.
2. Esperar la propagació. Spotify diu literalment _"it can take
   a few hours before requests are allowed again"_; observat: 3-6
   hores típic. No es pot accelerar.
3. Re-validar via Client Credentials des de prod:
   `cd /home/topquaranta/app && .venv/bin/python /tmp/check_playlists.py`.
4. Quan totes 10 retornin 200, el cron correrà al seu pròxim tick.

### Si el refresh_token ha caducat

Símptoma: la pàgina mostra `live_error` amb `401 Unauthorized`.

1. Anar a `/staff/social/spotify/`.
2. Click "Reautoritzar Spotify".
3. Logar-se a Spotify amb `admin@topquaranta.cat` (si no ho està
   ja) i acceptar els scopes.
4. La pàgina valida `product == "premium"` i persisteix la nova
   fila. Si retorna 400 amb "no és Premium", reactivar Premium
   primer (apartat anterior).

### Si la cobertura `last_n_matched / last_n_tracks` cau

Llindar WARN: < 0.85. Llindar CRITICAL: < 0.50.

Símptoma típic: una caiguda sobtada al 70% indica drift d'ISRC a la
ingest (Deezer/Last.fm) o que un block d'ISRC noves encara no
està a Spotify (artistes auto-editats sense distribució). A
investigar abans de reactivar Premium si es comporta diferent al
patró 95%+ històric.

Vegeu `docs/decisions/0009-spotify-identity-migration.md`,
`docs/decisions/0011-spotify-cron-schedule.md` i
`docs/architecture/playlists.md`.

## Lessons learned

### Squash-merge + parallel branches

Quan una branca llarga (X) es fa squash-merge a `main`, una segona
branca (Y) que va sortir abans del merge i conté els mateixos
commits individuals NO es pot rebasar netament: `git rebase main`
intenta re-aplicar cada commit de Y, però main ja en té els
canvis sota un sol SHA diferent (la squash), i això produeix
conflictes de contingut a cada commit individual.

**Solució pragmàtica**:

1. `git rebase --abort`.
2. `git checkout origin/main -b <nova-branca>`.
3. `git cherry-pick <SHA-1> <SHA-2> ...` només els commits propis
   de Y que NO eren a X.
4. `git branch -D <branca-vella>` i renombrar la nova si vols
   mantenir el nom.
5. `git push --force-with-lease origin <nom-branca>` per actualitzar
   la PR en curs.

Observat al sprint Playlists revival (2026-05-22): la PR #59
(social refactor) es va squash-mergeger mentre la PR #60 (Spotify
identity + UI) tenia 7 commits propis més 7 commits de la #59 que
ja estaven incorporats a main. El rebase fallava en cada commit
de la #59. Cherry-pick dels 2 commits únics de #60 sobre main
fresc va resoldre-ho en 5 min.

**Per a evitar-ho la pròxima vegada**: si una branca llarga està a
prop de mergejar, no comencis una segona branca sobre ella fins
que el merge hagi pujat a main. Si ja és tard, la solució
cherry-pick d'avall és més ràpida que intentar resoldre conflictes.

### Black corromp JSON quan li passes el fitxer explícitament

`black` només processa fitxers `.py` per defecte (via include
filter), però **arguments explícits salten el filtre** i black
intenta formatar-los igual. Quan li passes un `.json` (per error o
per bulk-format), interpreta el JSON com a Python i hi afegeix
trailing commas — JSON invàlid. Caught al sprint Process A+B
(FASE 7, 2026-05-22) amb `deploy/cron-meta.json`.

**Regla**: a `bin/tq-deploy`, scripts de format en bloc, o quan
invoquis black manualment, **no passis fitxers no-Python com a
arguments**. El patró segur és:
```sh
git diff --name-only origin/main | grep '\.py$' | xargs .venv/bin/black
```
o bé deixar que black descobreixi els fitxers per ell mateix:
```sh
.venv/bin/black .
```
(que respecta include + extend-exclude de `pyproject.toml`).

**Detecció**: si veus `black` reformatant un fitxer no-`.py` al log
("would reformat .../foo.json"), atura, restaura amb
`git checkout HEAD -- foo.json` i re-aplica el diff manualment.
La integritat del fitxer es valida amb `python -c "import json;
json.load(open('foo.json'))"`.

### Inserir features ML noves: SEMPRE al final de FEATURE_NAMES

Convencio establerta despres de l'incident del 2026-05-23 (PR #75):
inserir `spotify_artist_dispersio` al MIG de la llista
(entre el bloc MB i el TF-IDF tail) va exposar una finestra de race
entre `tq-deploy` i el thread background de `recalcular_ml_si_cal`.

El thread va fer `fit()` amb el codi pre-deploy (49 features), va
escriure `ml_model.joblib`, i poc despres gunicorn va recarregar amb
el codi nou (50 features). El RF es va quedar amb 49 columnes mentre
el codi en passava 50. Cada inferencia llencava `ValueError`,
atrapada per `pre_classificar` que cau al heuristic fallback. La
desalineacio va durar ~1.5 h fins que algu va notar els f-numbers al
panell `/staff/estat`.

**Regla**: les features noves al RF s'afegeixen sempre al FINAL de
`music.ml.FEATURE_NAMES` (i del vector que retornen `_build_features`
i `_build_features_from_historial`). Mai al mig. Aixi un model
antic carregat sota codi nou conserva els indexs 0..N-1 alineats
amb els seus noms; nomes la nova columna queda en buit fins al
proxim retrain.

**Salvaguardes que la cobreixen** (totes al mateix PR de l'incident):
- `_get_clf` valida `clf.n_features_in_ == len(FEATURE_NAMES)` cada
  cop que carrega el joblib. Si no coincideix marca
  `_model_cache["misaligned"]=True` i ho exposa via
  `music.ml.model_misaligned()`.
- `/staff/estat` retorna `ml.misaligned=True` i el frontend dibuixa
  un banner vermell.
- `entrenar_model()` consulta `DEPLOY_LOCK_PATH`
  (`/var/run/topquaranta/deploy.lock`); si el lock existeix, NO
  entrena i deixa el retrain al proper cicle.
- `bin/tq-deploy` toca el lock al principi i el neteja al EXIT (trap).
