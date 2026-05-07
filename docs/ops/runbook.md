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
| `INSTAGRAM_ACCESS_TOKEN` | `.env` | Auto-refreshed by cron `renovar_token_instagram` monthly. Manual override: regenerate at Meta Graph API Explorer (`pages_read_engagement` + `instagram_content_publish` scopes) → update `.env` → reload. |
| `BREVO_API_KEY` | Stalwart MTA relay config | Brevo dashboard → API & SMTP → regenerate v3 key → update Stalwart relay → `sudo systemctl restart stalwart-mail`. |
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
   - Mail path   → `sudo systemctl restart stalwart-mail`
   - Cron-only   → nothing; next tick uses new value.
4. Verify by triggering one operation that uses the secret.
5. **Only then** revoke the old secret on the provider's side.

**After a compromise** (deviates from above): revoke the old secret
**first**, accept the temporary breakage, then issue and deploy the
new one. The risk of a leaked secret being used outweighs the
deploy window.

---

## Phone numbers

This is a single-operator project. The phone number is yours. In that
case — the best thing to do is **write more here** each time you solve
an incident, so future-you doesn't start from zero.
