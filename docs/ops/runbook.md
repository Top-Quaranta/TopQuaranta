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

**If you fixed it:** re-run manually to clear the FAIL:
```bash
sudo -u topquaranta /home/topquaranta/bin/tq-run <command>
```

---

## 3. Ranking is wrong / a week is missing

**Weekly official ranking missing** (Saturday didn't publish):

```bash
grep calcular_ranking /var/log/topquaranta/status/*.status
# If FAIL, re-run manually:
sudo -u topquaranta tq-run calcular_ranking

# Compute a specific week:
sudo -u topquaranta tq-run calcular_ranking --setmana 2026-04-13
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

## Phone numbers

This is a single-operator project. The phone number is yours. In that
case — the best thing to do is **write more here** each time you solve
an incident, so future-you doesn't start from zero.
