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

## CSP: cada `<style>` en línia va amb la seua empremta

`deploy/Caddyfile` envia `style-src 'self' '<sha256…>' …`, una empremta
per cada bloc `<style>` en línia que servim. La política **no** porta
`'unsafe-inline'`, i això té una conseqüència que cal tindre molt clara:

> Si edites el CSS de dins d'una plantilla i no actualitzes l'empremta,
> el navegador rebutja el bloc **sencer** i la pàgina ix **sense cap
> estil**.

La fallada és silenciosa i total. L'HTML és correcte, el CSS hi és, les
proves passen i `curl` ho ensenya tot al seu lloc: només un navegador de
veres aplica la CSP. Va passar exactament així — el redisseny del
2026-06-13 va reescriure `comptes/_base_auth.html`, el Caddyfile va
quedar amb l'empremta vella, i durant dos mesos totes les pàgines que
renderitza Django (accés, registre, les tres de 2FA, nova contrasenya,
esborrar compte) i les de 403/404/500 van eixir en HTML pelat. Ho vam
descobrir perquè el Miquel va entrar des del mòbil i ho va vore.

El guardià és `topquaranta/tests/test_csp_style_hashes.py`: recalcula
l'empremta de cada bloc i falla si no és a la CSP, dient-te quina cadena
has d'enganxar. També exigeix que els blocs siguen **estàtics**: una
etiqueta de plantilla dins d'un `<style>` faria que el que se serveix no
coincidira amb el codi font, i l'empremta seria correcta ací i falsa en
producció.

Els correus (`email_*.html`) queden fora: no viatgen mai per HTTP.

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

## Correu: ja no s'allotja ací

Del 27 d'abril al 18 d'agost del 2026 aquesta màquina va allotjar
**Stalwart Mail Server** per a les bústies de `topquaranta.cat` i
`cercol.team`. Ja no: les dues han passat a **Purelymail**, i de tot
aquell muntatge només queda el fitxer d'autoconfig que serveix Caddy des
de `mail.topquaranta.cat`; qualsevol altra petició d'eixe domini respon
un 410 amb els paràmetres nous.

El que hi havia i s'ha llevat: el servei, els listeners de 25/465/587/993,
`/etc/stalwart`, `/var/lib/stalwart`, i la parella
`stalwart-cert-sync.path` + `.service` que copiava el certificat de Caddy
cap a Stalwart.

Es conserven dues coses, a posta:

- [`deploy/stalwart-cert-sync.sh`](../../deploy/stalwart-cert-sync.sh),
  perquè el patró que resol —empényer un certificat renovat cap a un
  servei que no el rellig sol— tornarà a fer falta el dia que allotgem
  qualsevol cosa amb TLS propi.
- El post-mortem del certificat caducat
  ([`../post-mortems/2026-07-26-stalwart-cert-expirat.md`](../post-mortems/2026-07-26-stalwart-cert-expirat.md)),
  amb la lliçó que va deixar: **mesurar el certificat pel cable, mai
  llegint el fitxer del disc**. La comprovació de `music/health.py` que
  en va eixir és genèrica i continua activa per a qualsevol endpoint que
  es configure a `tls_endpoints_vigilats`.

Arquitectura de correu actual a [`../EMAIL.md`](../EMAIL.md).


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
