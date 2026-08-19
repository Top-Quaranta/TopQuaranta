# Ops runbook

Procedures you need at 3 a.m. Host, service, paths and the Caddy
routing map are in `CLAUDE.md §3` — not repeated here. Incident
narratives live in `docs/LESSONS.md` (linked by date); decisions in
`docs/DECISIONS.md`. Every script named below exists in `bin/` (repo)
and is installed to `/home/topquaranta/bin/` by `bin/tq-sync-infra`.

## 1. First 60 seconds

```bash
ssh topquaranta@188.245.60.20
tq-health                                   # exit 0 = healthy, 1 = anomaly, 2 = renderer/meta missing
systemctl is-active topquaranta-web caddy postgresql
curl -sI https://www.topquaranta.cat/ | head -3
```

| Symptom | Look at | Fix |
|---|---|---|
| 502 + gunicorn inactive | `journalctl -u topquaranta-web -n 100` | `sudo systemctl restart topquaranta-web` |
| 504 | `sudo -u postgres psql topquaranta -c "SELECT pid,state,query FROM pg_stat_activity WHERE state='active'"` | `SELECT pg_cancel_backend(PID)` |
| Blank SPA but `/api/v1/auth/me/` 200 | `web-react/dist/` stale | `cd /home/topquaranta/app/web-react && npm run build` (Caddy serves `dist/`, no reload) |
| Django 500 on `/api/*` or `/compte/*` | `tail -50 /var/log/topquaranta/errors.log` | roll back (§3) or fix forward |
| Django page renders unstyled | CSP hash stale (§7) | regenerate hash |
| TLS error | `journalctl -u caddy -n 200` | Caddy retries; watch the `CERTIFICATS TLS` row in `tq-health` |
| Disk full | `df -h; du -sh /var/log/topquaranta /home/topquaranta/backups /var/topquaranta/portades` | `sudo logrotate -f /etc/logrotate.d/topquaranta`; retention in §11 |

Logs: `/var/log/topquaranta/*.log` (one per cron area, CEST timestamps;
cron lines are UTC), `/var/log/caddy/topquaranta_access.log`,
`journalctl -u topquaranta-web`.

## 2. Deploy pipeline

Push to `main` → `.github/workflows/ci.yml` (pytest, lint, migrations
check, SPA build) → `.github/workflows/deploy.yml` SSHes as
`topquaranta` and runs `/home/topquaranta/app/bin/tq-deploy` under
`set -e`. `paths-ignore` skips deploys for `docs/**`, `*.md`,
`LICENSE*`, `ci*.yml`, so prod legitimately lags `origin/main` after
doc-only merges (`bin/tq-git-drift` knows this).

`bin/tq-deploy` (must run as `topquaranta`; flags `--skip-build`,
`--dry`) does, in order:

1. touch `/var/run/topquaranta/deploy.lock` (blocks ML retrain,
   `music/ml.py::DEPLOY_LOCK_PATH`; removed on EXIT)
2. `git fetch origin main && git reset --hard origin/main && git clean -fd -e data/`
   — **the prod tree is discarded on every deploy**; anything written
   directly into `/home/topquaranta/app/` vanishes (LESSONS 2026-06-02)
3. `bin/tq-changed-files PRE POST` computed once, up front
4. `bin/tq-sync-infra` (§6)
5. `pip install -r requirements.txt` if it changed → forces `restart`
6. `migrate --check` → `migrate` if pending, **before** the reload
7. `npm run build` if `web-react/` changed
8. `systemctl reload topquaranta-web` (or `restart` after step 5)
9. smoke: `/` and `/api/v1/top/?territori=PPCC` must be 200

| Exit | Meaning |
|---|---|
| 0 | OK |
| 1 | `migrate` failed |
| 2 | SPA build failed |
| 3 | reload/restart failed |
| 4 | smoke endpoint answered non-200 |
| 5 | `tq-sync-infra` failed |
| 6 | venv missing or `pip install` failed |
| 7 | changed-file list not computable (refuses to guess) |
| 8 | smoke endpoint unreachable (DNS/TLS) |
| 64 | unknown flag or not run as `topquaranta` |

Guards: `topquaranta/tests/test_deploy_safety.py` (`test_no_pending_model_migrations`,
`test_tq_deploy_documents_every_exit_code_it_uses`,
`test_tq_deploy_computes_the_diff_once_outside_any_condition`,
`test_tq_changed_files_*`, `test_tq_git_drift_*`).

**Manual deploy** (GHA down): `ssh topquaranta@… /home/topquaranta/app/bin/tq-deploy`.
Never `git pull` + bare `systemctl reload` by hand.

**Destructive migration** (RemoveField / DeleteModel / Rename* /
narrowing AlterField): a long-running cron keeps the old model in
memory and `systemctl reload` does not touch it (LESSONS 2026-05-07).
Before merging: `bin/tq-pre-migrate` lists `manage.py` processes older
than 5 min; `--kill` kills them. CI job `destructive-migrations` warns
(soft). Then watch `errors.log` for 5 min after deploy.

**ML features**: append to the END of `music/ml.py::FEATURE_NAMES`;
`_get_clf` refuses a misaligned joblib and `/staff/estat` shows a red
banner (LESSONS 2026-05-23).

## 3. Rollback

The prod tree is `origin/main` by construction (§2 step 2), so a
manual `git reset --hard <sha>` on the box is undone by the next
deploy and flagged as DRIFT within the hour. Roll back **through
GitHub**:

```bash
# on the Mac
git revert <bad-sha>            # or revert the squash-merge commit
git push origin main            # GHA redeploys the revert
```

If the bad commit carried a migration, revert the code first, then
land a second PR whose migration reverses it (never combine). Only in
a true emergency with GHA down: `git reset --hard <good-sha>` on the
box + `bin/tq-deploy`-equivalent steps by hand (`migrate <app>
<prev>`, `sudo systemctl reload topquaranta-web`) — and revert on
GitHub immediately after, or the next push re-breaks it.

## 4. Crons: tq-run / tq-health / tq-recover

Every cron line runs `tq-run <command> [args]` (`deploy/cron.topquaranta`;
metadata per tag in `deploy/cron-meta.json`, both installed by
`tq-sync-infra`). `tq-run` writes
`/var/log/topquaranta/status/<tag>.status`:

| Field | Meaning |
|---|---|
| `status=` | `OK`, `FAIL`, `SKIPPED_BY_LOCK` (exit 75 from `music.locks.SingletonLock`; `last_run` NOT refreshed) |
| `attempts=` | retries: 3 with 60 s / 300 s backoff; `obtenir_novetats` 1 |
| `consecutive_skips=` / `consecutive_failures=` | escalation counters |
| `work_done=` / `consecutive_zero_work=` | opt-in `WORK_DONE=<int>` last line of stdout; 0 repeatedly ⇒ silent no-op |

Tag = command + variant: `--provisional` → `<cmd>_provisional`,
`--freq weekly` → `<cmd>_weekly`, `--channel X` → `<cmd>_X`. Bash
scripts (`tq-backup`, `tq-backup-offsite`, `tq-restore-test`,
`tq-recover`) write their own status file in the same format.
`test_deploy_safety.py::test_every_cron_invocation_has_meta_entry`
asserts every cron line resolves to a `cron-meta.json` key.

`tq-health` (hourly `:15`, `--email-on-fail` mails `admin@` once per
distinct anomaly signature — `analytics/health_report.py`) states:

| State | Meaning | Action |
|---|---|---|
| `OK` / `WAITING` | fine / weekly-monthly cron not yet due | — |
| `SKIP(N)` | lock held, N under `skip_concern` | none if a long run is in progress |
| `STUCK(Nh, Nskips)` | skips ≥ threshold or ≥10 | find the holder: `ps auxf \| grep manage.py`; kill it; lock is an flock on `/tmp/<cmd>.lock`, released on death — no file to remove |
| `STALE(Nh)` | `last_run` older than `max_age_hours` | run by hand: `sudo -u topquaranta tq-run <cmd> [args]` |
| `FAIL` | non-zero exit after retries | read `last_output` / the area log; fix; re-run to clear |
| `MISSING` | frequent cron with no status file | cron line dropped or tag mismatch |
| `ORPHAN` | status file with no meta entry | register it or `rm` the file |
| `DISABLED` | gated feature off (offsite backup) | legitimate |
| `DRIFT` (Git tree row) | prod tree dirty or ahead/divergent | someone bypassed the pipeline; `bin/tq-deploy` |
| `DB migrations` row | pending migrations | deploy bypassed `tq-deploy` |

`silenced=true` in `cron-meta.json` swallows the email but stays red.
Also watched: disk, SPA shell + hashed assets by content-type
(`scripts/health/spa_assets.sh`), TLS on the wire for
`ConfiguracioGlobal.tls_endpoints_vigilats` (`scripts/health/tls_certs.sh`,
list ships empty), Spotify Premium + coverage, Instagram token expiry
(WARN ≤10 d / CRIT ≤5 d on the stored expiry only).

`tq-recover` (every 30 min) re-launches missed/failed commands via
`tq-run`, max 5/day per command. Common FAIL causes: upstream 429/5xx
(wait 1 h, re-run); code error from a deploy (§3); Whisper
`SKIPPED_BY_LOCK` at 04:00 UTC = an MB run still holds `ram_heavy.lock`
(kill the MB python; the next tick resumes idempotently).

Weekly top missing: `sudo -u topquaranta tq-run calcular_top [--setmana YYYY-MM-DD]`.

## 5. Locked out

```bash
M="sudo -u topquaranta env DJANGO_SETTINGS_MODULE=topquaranta.settings.production /home/topquaranta/app/.venv/bin/python /home/topquaranta/app/manage.py"
$M changepassword <username>
$M reset_2fa <username>
$M axes_reset_username <username>
```

## 6. Infra files and Caddy

`bin/tq-sync-infra` (run by `tq-deploy`, idempotent, exit 1 on missing
source or Caddyfile validation failure) is the **only** path for files
outside the working tree — `FILES` map in the script: `deploy/Caddyfile`
→ `/etc/caddy/Caddyfile`, `deploy/cron.topquaranta`, `deploy/logrotate.topquaranta`,
`deploy/topquaranta-web.service`, `deploy/autoconfig-topquaranta.xml` →
`/var/www/autoconfig/config-v1.1.xml`, plus `bin/tq-*`. Adding a file
= one line in `FILES` (`test_sync_infra_installs_every_file_it_declares`).
Editing a file on the box by hand = reverted on the next deploy.

**Multi-tenant Caddy contract.** The box also serves other projects
(`cercol-api`, …). `/etc/caddy/Caddyfile` ends with
`import /etc/caddy/conf.d/*.caddy`; each other project owns exactly
one snippet there and never touches the main file; TopQuaranta never
reads, writes or deletes under `conf.d/`
(`test_caddyfile_imports_confd`, `test_sync_infra_does_not_touch_confd`).
Global options block changes go through a PR to `deploy/Caddyfile`.
Onboarding a project: A record → snippet in its repo → its deploy
runs `caddy validate --config /etc/caddy/Caddyfile`, installs to
`conf.d/`, `systemctl reload caddy`.

**Firewall** (Hetzner Cloud, managed via `hcloud` /
`HETZNER_API_TOKEN`): inbound **22, ICMP, 80/443 only**. Postgres is
localhost-only; no mail ports (§9).

**Security headers** apply to everything except `/static/social/*`
(Meta's fetcher rejects them — `test_static_social_excluded_from_security_headers`).

## 7. CSP inline-style hash trap

`style-src` carries one `'sha256-…'` per inline `<style>` block —
`web-react/index.html` and every Django template under
`comptes/templates/`, `web/templates/` — and no `'unsafe-inline'`.
Edit a block without updating the hash and the browser drops the
**whole** block: page renders unstyled, `curl` and tests look fine.
Guard: `topquaranta/tests/test_csp_style_hashes.py` recomputes each
hash and prints the string to paste. Procedure: edit → run that test
→ paste the hash into `deploy/Caddyfile` → PR → after deploy
`curl -sI https://www.topquaranta.cat/ | grep -i content-security`.
`script-src` is `'self'` only: no inline scripts, ever — put them in
`web-react/public/`.

## 8. Secrets: inventory and rotation

Rule: production auth belongs to `admin@topquaranta.cat`, never a
personal account (LESSONS 2026-05-20). Rotate yearly; after a
suspected leak revoke first, then re-issue. Normal order: issue new →
update `.env`/DB row → `sudo systemctl reload topquaranta-web` (crons
pick up `.env` on next tick) → verify one call → revoke old.
`DB row` = editable at the staff URL, no SSH.

| Secret | Identity / storage | Rotate |
|---|---|---|
| `DJANGO_SECRET_KEY` | `.env` | `python -c "import secrets;print(secrets.token_urlsafe(50))"`; reload. Invalidates sessions + every `signing.dumps` link (unsubscribe, delete-confirm) |
| Postgres password | `.env::DATABASE_URL` | `sudo -u postgres psql -c "ALTER USER topquaranta WITH PASSWORD '…'"`; reload |
| `LASTFM_API_KEY/SECRET` | `.env` | last.fm/api/account |
| `SPOTIFY_CLIENT_ID/SECRET` | admin@ + Premium; `.env`; redirect default `/spotify/callback` (`production.py`) must match the dashboard | Spotify dashboard, then re-OAuth at `/staff/social/spotify/` |
| Spotify refresh token | `music.SpotifyAuth` row | `/staff/social/spotify/` "Reautoritzar" (fallback `manage.py autoritzar_spotify`). `invalid_grant`/401 ⇒ this; 403 "premium required" ⇒ renew Premium at spotify.com, wait 3–6 h |
| Instagram long-lived token | `social.InstagramAuth` row (`.env` fallback) | **Manual, every 60 d**: Meta App Dashboard → Instagram-Login token (`instagram_business_content_publish`) → paste at `/staff/social/instagram`. `renovar_token_instagram` (monthly cron) only prints; Meta can also revoke early (LESSONS 2026-07-07) — shows as publish `FAIL`, not expiry |
| `MastodonAuth`, `BlueskyAuth`, `TelegramAuth` | DB rows | re-OAuth `/staff/social/mastodon/`; new app password (bsky.app) → `/staff/social/bluesky/`; BotFather `/revoke` → `/staff/social/telegram/` |
| Brevo SMTP key | admin@; `.env::EMAIL_HOST_PASSWORD` | Brevo → SMTP & API → regenerate; reload |
| Resend key (cercol.team) | Cercol repo `.env`, not here | Resend dashboard |
| `GSC_OAUTH_REFRESH_TOKEN` (+ client id/secret) | admin@ OAuth user creds, `.env` | OAuth Playground with own creds, scope `webmasters.readonly`, authorise as admin@; reload; backfill `tq-run recollir_metrics_gsc --date YYYY-MM-DD`. Service account is unusable (`DECISIONS` ADR-0002) |
| `YOUTUBE_API_KEY`, `PSI_API_KEY` | `.env` | Google Cloud console (same project) |
| `NEWSLETTER_ROUTINE_TOKEN` | `.env` + routine env | regenerate both sides together |
| `HETZNER_API_TOKEN`, `CDMON_API_KEY` | `.env`; manual scripts only | provider console; no reload |
| restic `RESTIC_PASSWORD` + B2 server key | `.env` (§10) | B2 console; password never rotates without a re-init |

**SSH keys**: GitHub is reached only via the read-only ed25519 deploy
key `~/.ssh/id_ed25519_github` (server) and the `HETZNER_DEPLOY_KEY`
GHA secret. Never a PAT — not in `.env`, `.git/config` or `~/.netrc`
(check: `grep -E 'ghp_|://.+:.+@github' ~/app/.git/config ~/.netrc`).
Rotate yearly or on machine loss: `ssh-keygen -t ed25519`, add as
deploy key (no write), switch `~/.ssh/config`, `ssh -T git@github.com`,
then delete the old key on GitHub and `shred -u` it locally. Wipe the
disk on decommission.

## 9. Mail

Mailboxes for `topquaranta.cat` and `cercol.team` live at
**Purelymail** (MX `mailserver.purelymail.com`; IMAP
`imap.purelymail.com:993`, SMTP `smtp.purelymail.com:465`, mailbox
password for both). Automatic sending is separate: Django →
**Brevo** (`smtp-relay.brevo.com:587`, `EMAIL_HOST_*` in
`production.py`, From `Josep Quaranta <noreply@topquaranta.cat>`),
Cercol → **Resend**; SPF includes both. **No mail is hosted on this
box** and won't be: Hetzner blocks outbound port 25 (Stalwart retired
2026-08-18; LESSONS 2026-07-26). `mail.topquaranta.cat` no longer
exists (DNS or Caddy). The only mail artefact we serve is the
autoconfig XML (§6), a copy of Purelymail's that Spark Desktop needs;
`web/tests/test_autoconfig_correu.py` pins it to Purelymail. Accounts
are managed in the Purelymail panel; `admin@topquaranta.cat` receives
`tq-health` alerts and moderation mail. DNS records: CDMON panel/API.

## 10. Backups and restore

**Layer 1 (local)** — `tq-backup` daily 03:00 as `postgres`, into
`/home/topquaranta/backups/`; `tq-restore-test` monthly (1st, 04:30)
restores the latest daily into `topquaranta_restore_test`. Hetzner
Cloud snapshots ×7 in parallel.

| Series | Content | Keep |
|---|---|---|
| `daily/tq-*` | full dump (PII) | 7 d |
| `weekly/tq-week-*` | full dump | 30 d |
| `monthly/tq-month-pii-*` | full dump | 90 d |
| `monthly-safe/tq-month-safe-*` | schema + data minus PII tables (`--exclude-table-data`, CI-guarded by `test_backup_offsite.py`) | 12 m |
| legacy `monthly/tq-month-2*` (pre-2026-07) | full dump | 365 d, delete earlier only with Miquel's OK |

**Layer 2 (offsite, gated)** — `bin/tq-backup-offsite` daily 03:30:
restic → Backblaze B2 (EU), server key append-only (no `deleteFiles`),
encrypted at origin; tags `pii` (latest daily + `.env` + `data/`, ≤90 d)
and `safe` (`monthly-safe/` + portades, 12 m). Reports `DISABLED` until
`.env` has `OFFSITE_BACKUP_ACTIU=1`, `RESTIC_REPOSITORY`,
`RESTIC_PASSWORD`, `AWS_ACCESS_KEY_ID/SECRET` and `restic` is installed.
Activation: B2 account + bucket, two keys (server: list/read/write;
admin: Mac only), password in manager **and on paper**, `restic init`
from the Mac, `.env`, first run, `tq-health | grep -i offsite`, then a
cold drill typing the paper password. Retention is enforced **from the
Mac** quarterly:

```bash
restic -r s3:s3.eu-central-003.backblazeb2.com/<bucket> check --read-data-subset=10%
restic forget --tag pii  --keep-within 90d --prune
restic forget --tag safe --keep-monthly 12 --prune
```

**Restore to production** (overwrites; take a fresh `pg_dump` first):

```bash
ls -lt /home/topquaranta/backups/daily/ | head
gunzip -c /home/topquaranta/backups/daily/tq-YYYYMMDD-HHMMSS.sql.gz | sudo -u postgres psql topquaranta
sudo systemctl restart topquaranta-web
```

Box lost entirely: from the Mac, `restic restore latest --tag pii
--target /tmp/tq-restore`, then the same `psql` load on the new box.
No dump with personal data outlives 90 days anywhere.

## 11. Retention

| What | Keep | Mechanism |
|---|---|---|
| `TopSetmanal`, `HistorialRevisio`, `StaffAuditLog`, `PropostaArtista`, `UserArtista`, catalogue | forever | — (audit logs are never deleted) |
| `SenyalDiari` | 2 years live | `arxivar_senyal_vell` quarterly → `/home/topquaranta/archive/senyal-YYYY.csv.gz`, then delete (restore: `gunzip -c … \| psql -c "COPY ranking_senyaldiari FROM STDIN CSV HEADER"`) |
| `TopProvisional` | rebuilt daily | — |
| `axes_*` | 6 months | `manage.py axes_reset_logs --age=180` |
| Sessions | 2 weeks | Django |
| Portades (`/var/topquaranta/portades`) | public catalogue ∪ ever-ranked | `netejar_portades` Mon 03:00 |
| Social renders | 60 d | `deploy/logrotate.topquaranta` prerotate |
| Django logs | 8 weekly rotations | logrotate |
| Caddy access log | 30 × 10 MiB, ≤90 d | `deploy/Caddyfile` `log` block |
| Backups | see §10 | `tq-backup` |

## 12. Deprecation

Applies to anything with a consumer: model fields, management
commands, `/api/v1/*`, staff URLs, `bin/tq-*` flags and status keys.
(1) Announce in `docs/history/changelog.md` `### Deprecated` with
removal date and replacement. (2) Warn in code: `DeprecationWarning` /
`help_text="DEPRECATED …"` / `X-Deprecated` + `X-Deprecation-Removal`
headers / staff banner. (3) Wait ≥90 d internal, ≥180 d external API.
(4) Remove: move the entry to `### Removed`; one migration per column
drop; API removal bumps to `/api/v2/` with v1 alive 180 d more.
Security hazards skip the wait (note it in the entry); declared
experiments and never-shipped code need no window.
