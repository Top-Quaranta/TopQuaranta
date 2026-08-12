# Shared infra — multi-tenant Caddy

The Hetzner CX22 (`188.245.60.20`) hosts more than just TopQuaranta. As
of May 2026 the server also serves `cercol-api` (and any other future
project we co-locate). A single Caddy instance fronts all of them.

## Layout

```
/etc/caddy/
├── Caddyfile               ← owned by TopQuaranta (this repo)
└── conf.d/
    ├── cercol-api.caddy    ← owned by the cercol-api repo
    └── <future>.caddy      ← one snippet per additional project
```

- The main `Caddyfile` ends with `import /etc/caddy/conf.d/*.caddy`,
  which loads every `.caddy` snippet from that directory at config
  parse time. An empty `conf.d/` is valid: the glob expands to zero
  matches and Caddy carries on.
- Each project's snippet contains only its own site blocks (e.g.
  `api.cercol.team { ... }`). It does not redeclare the global
  options block — that lives in the main Caddyfile.

## Ownership

| Path | Owner | Synced by |
|---|---|---|
| `/etc/caddy/Caddyfile` | TopQuaranta | `bin/tq-sync-infra` (this repo) |
| `/etc/caddy/conf.d/*.caddy` | the corresponding project | that project's deploy script |
| `/home/topquaranta/bin/tq-*` (ops scripts) | TopQuaranta | `bin/tq-sync-infra` (since 2026-06-12) |

**Ops scripts (2026-06-12).** The `tq-*` operational scripts live in the repo
(`bin/`) but RUN from `/home/topquaranta/bin/`. They used to be hand-copied, so
repo fixes never reached prod — e.g. `tq-recover`'s self-status report (added
2026-06-07) sat unapplied and the watchdog showed a perennial stale `MISSING`.
`tq-sync-infra` now diffs `bin/tq-*` against the installed copies and re-installs
on drift (exec bit preserved, no sudo — `/home/topquaranta/bin` is
topquaranta-owned). The repo is the source of truth.

The rules are mutual and hard:

1. **TopQuaranta never touches `/etc/caddy/conf.d/`.** Not for read,
   not for write, not for delete. `bin/tq-sync-infra` is the sole
   author of `/etc/caddy/Caddyfile`; the conf.d directory is invisible
   to it. The test
   `topquaranta/tests/test_deploy_safety.py::test_sync_infra_does_not_touch_confd`
   keeps that contract honest.
2. **Other projects never touch `/etc/caddy/Caddyfile`.** They install
   only their own snippet under `conf.d/` and reload Caddy. If a
   project ever needs to change the global options block (auto-TLS
   email, on-demand TLS, etc.), that change goes through the
   TopQuaranta repo via a PR to `deploy/Caddyfile`.

## Deploy contract for project snippets

Each project's deploy script must:

1. Write `<project>.caddy` to a working location in its own tree.
2. `sudo caddy validate --config /etc/caddy/Caddyfile` first (Caddy
   resolves the import, so a syntax error in any project's snippet
   surfaces here).
3. `sudo install -o root -g root -m 644 <project>.caddy
   /etc/caddy/conf.d/<project>.caddy` only after validation passes.
4. `sudo systemctl reload caddy` to pick up the change.

If validation fails the deploy aborts and Caddy keeps running with
the previous config. No partial application.

## Why this design

For four months the server ran with `deploy/Caddyfile` containing
every site for every project. Each TopQuaranta deploy ran
`tq-sync-infra`, which diffs `deploy/Caddyfile` against
`/etc/caddy/Caddyfile` and replaces the live file wholesale on
drift. Any block added manually to the live file (because it
belonged to a different repo) was silently deleted at the next TQ
deploy.

The `import /etc/caddy/conf.d/*.caddy` directive gives every
project its own write surface. TopQuaranta keeps the global block
and its own sites; other projects ship snippets that survive any
TQ deploy because TQ never reads or writes the conf.d directory.

## Access log retention

The TopQuaranta vhost writes JSON access logs to
`/var/log/caddy/topquaranta_access.log` and rotates **by size**:

```
roll_size 10MiB
roll_keep 30
roll_keep_for 90d
```

Raised from `roll_keep 5` on 2026-07-31. Keep the two costs apart —
they differ by ~15×, and conflating them overstates the disk bill by
an order of magnitude:

- **On disk**, a rotated segment is gzipped to ~640 KiB. Thirty of
  them is **~19 MiB**, plus up to 10 MiB for the live file.
- **Read back**, each segment is 10 MiB of JSON. Thirty of them is
  **~300 MiB** — the figure that sets how far back
  `generar_goaccess` can see, not the disk bill.

Because rotation is by size, the days that fit depend on traffic:
~34 days at the 0.37 MiB/h baseline, ~2.7 days under a sustained
crawler sweep. `roll_keep_for 90d` caps the quiet end.

Other vhosts (`cercol_api_access*`) own their own `log` blocks and
are not covered by this. Detail and the measurements behind these
numbers: `docs/architecture/analytics-goaccess.md`.

## Project configuration (`topquaranta/`)

The Django project package at `topquaranta/` is not "infra" in the
Caddy sense but lives in this doc because it pins the environment
the runtime depends on: settings split, WSGI/ASGI entry points,
URL roots, and the `.env` contract.

### Settings split

```
topquaranta/settings/
├── base.py          Shared base. INSTALLED_APPS, middleware, auth,
│                    DRF, axes, otp, paths.
├── production.py    Used by management commands on the server.
│                    Reads DATABASE_URL, SECRET_KEY, etc. from .env.
├── web_server.py    Used by the gunicorn unit. Inherits production
│                    + the production-only middleware (HSTS, secure
│                    cookies, ALLOWED_HOSTS lockdown).
├── local.py         Developer overrides (not committed). Optional.
└── test.py          SQLite in-memory, no external services, pytest
                     defaults. Pinned via `pytest.ini` (--ds=).
```

The convention is that anything user-facing reads
`DJANGO_SETTINGS_MODULE=topquaranta.settings.web_server`; cron and
ad-hoc shells use `topquaranta.settings.production`; pytest is
hard-pinned via `addopts = --ds=topquaranta.settings.test` so an
inherited shell env can never flip the suite to production
settings.

### Entry points

| File | Role |
|---|---|
| `topquaranta/urls.py` | Root URL conf. Mounts `web.api.urls`, `comptes.urls`, the RSS feeds, the SEO views, and the sitemap. |
| `topquaranta/wsgi.py` | gunicorn entry point (HTTP). |
| `topquaranta/asgi.py` | ASGI handle (not used today; reserved for any future channels work). |

### `.env` contract

Loaded via `python-decouple`. Always accessed through
`from django.conf import settings`. Required keys:

```
DJANGO_SECRET_KEY
DJANGO_SETTINGS_MODULE
ALLOWED_HOSTS
DATABASE_URL
LASTFM_API_KEY / LASTFM_API_SECRET
SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET / SPOTIFY_REDIRECT_URI
```

Plus optional service keys for Brevo, Resend, Hetzner Cloud, CDMON
DNS, Google Search Console, etc. (see `CLAUDE.md §8`).

Optional, **`YOUTUBE_API_KEY`** (2026-08): API key of the same Google
Cloud project as `PSI_API_KEY` (the two quotas are independent), with
YouTube Data API v3 enabled. Empty default, so the three YouTube crons
log a warning and exit 0 rather than going red. Quota is 10.000
units/day per *project* and has no paid tier — `descobrir_youtube`
budgets against it explicitly. See `docs/architecture/pipeline.md`
§3.1 bis. Cinc crons: `suggerir_instagram` (02:30, sembra candidats
d'IG per als artistes que entren a la cua de staff — sense quota),
`sembrar_canals_youtube` (02:00),
`descobrir_youtube` (03:00), `obtenir_senyal_youtube` (06:30) i
l'informe temporal `enviar_informe_youtube` (07:00).

Outbound mail from the `noreply@` mailbox carries the display name
**`Josep Quaranta`** (`DEFAULT_FROM_EMAIL` / `SERVER_EMAIL` in
`settings/base.py`, overridable via the `DEFAULT_FROM_EMAIL` env var in
production). Full email architecture: `docs/EMAIL.md`.

Optional, **`NEWSLETTER_ROUTINE_TOKEN`** (2026-06-07): static bearer
token the newsletter cloud routine presents to
`/api/v1/newsletter-routine/{brief,esborrany}/`. Read in
`production.py` via `config("NEWSLETTER_ROUTINE_TOKEN", default="")`;
empty default keeps token auth disabled (blank denies every request).
Generated by an operator and placed in the server `.env` AND in the
routine's own environment. See `docs/architecture/comptes.md`.

## Stalwart TLS: why the cert is not a file

Caddy owns ACME for every hostname on this box, `mail.topquaranta.cat`
included. Getting that certificate *into* Stalwart is the part that
surprises people, so it is written down here rather than rediscovered.

**Stalwart 0.16 does not read its certificate from disk.** Its whole
configuration lives in RocksDB (`/var/lib/stalwart/`), and the
certificate is an inline property of an `x:Certificate` object, not a
path. `/etc/stalwart/stalwart.env` contains:

```sh
STALWART_CERTIFICATE_DEFAULT_CERT=%{file:/etc/stalwart/certs/mail.topquaranta.cat.crt}%
STALWART_CERTIFICATE_DEFAULT_PRIVATE_KEY=%{file:/etc/stalwart/certs/mail.topquaranta.cat.key}%
```

Those variables *are* loaded into the process environment — but the
`%{file:…}%` macro is pre-0.16 config syntax and is never evaluated.
They are vestigial. Writing PEM to `/etc/stalwart/certs/` changes
nothing, and neither does restarting or rebooting afterwards.

That is exactly how the July 2026 outage happened: the sync script
copied files nobody read, so Stalwart kept serving an April
certificate until it expired. See
[`docs/post-mortems/2026-07-26-stalwart-cert-expirat.md`](../post-mortems/2026-07-26-stalwart-cert-expirat.md).

### How the cert actually gets in

Over the JMAP admin API on localhost, under the `urn:stalwart:jmap`
capability:

| Step | Call |
|------|------|
| Resolve account | `GET /.well-known/jmap` → `primaryAccounts["urn:stalwart:jmap"]` |
| Find the object | `x:Certificate/query` filtered on `subjectAlternativeNames` |
| Write it | `x:Certificate/set` with `certificate.value` + `privateKey.secret` |
| Read back | `x:Certificate/get` to confirm the new serial landed |

**A restart is then mandatory.** Writing the config does not swap the
TLS context already loaded in memory: the config read-back will show
the new certificate while the wire still serves the old one. This is
the one step that cannot be skipped.

Two API notes worth keeping:

- `privateKey.secret` reads back as a 4-byte placeholder. A JMAP read
  **cannot** back up the private key; only the public cert round-trips.
- There is no `/api/settings/*` route in 0.16, and the webadmin SPA is
  not deployed on this host, so `/` returns 404. JMAP is the only way in.

### The sync script

[`deploy/stalwart-cert-sync.sh`](../../deploy/stalwart-cert-sync.sh),
installed at `/usr/local/sbin/stalwart-cert-sync.sh` and triggered by
`stalwart-cert-sync.path` when Caddy's cert file changes.

It is **idempotent by design**: it compares the serial of Caddy's cert
on disk against the serial actually served on port 993, and if they
match it logs and exits 0 without restarting anything. The previous
version restarted the mail server on every Caddy renewal for no gain.

Before writing it verifies that cert and key are a real pair
(`sha256` of both public keys), and it refuses to guess if the SAN
query returns zero or several objects. After restarting it re-checks
ports 993, 465 and 25 and exits non-zero if any still serves the old
serial — the exit code reflects the wire, not the intent.

```sh
sudo /usr/local/sbin/stalwart-cert-sync.sh --dry-run   # detect only
sudo /usr/local/sbin/stalwart-cert-sync.sh             # sync if needed
```

Log: `/var/log/stalwart-cert-sync.log`, self-rotating at 1 MiB.
journald on this host does not persist, which is why the script keeps
its own file — the June 2026 evidence was already gone when the
incident was investigated.

The admin credential is read from `/etc/stalwart/stalwart.env` at run
time and passed to `curl` through a stdin config file, so it never
appears in `argv` or in the log.

## Quick checklist when onboarding a new project

- Add an A record at the DNS provider pointing the new hostname at
  `188.245.60.20`.
- In the new project's repo: create a `deploy/<project>.caddy`
  file with the site block. Validate it locally with the
  `caddy:2` Docker image before pushing.
- Add a deploy step that installs the snippet to
  `/etc/caddy/conf.d/<project>.caddy`, validates the merged config,
  and reloads Caddy.
- Do not touch `/etc/caddy/Caddyfile`. Do not touch any other
  project's snippet.
