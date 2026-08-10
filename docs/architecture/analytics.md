# Analytics suite

> Ethical, aggregate-only product analytics. No PII. No third-party JS.
> No fingerprinting. Built in May-2026 (sprints **K1–K4**).

This document describes how the analytics pipeline works end-to-end,
what each table holds, what gets shown where, and what we deliberately
don't measure.

## Design constraints

The hard rules every component below respects:

1. **No personal identifiers** — never `request.user.pk`, never IP,
   never Referer, never session keys. The User-Agent string is never
   *stored*; it is read transiently to classify a pageview as
   bot/human (a single low-cardinality label), then discarded.
2. **Aggregates only** — every row is a counter or a daily snapshot
   keyed by `(data, clau, dim*)`. Resolution is one row per day per
   bucket; we don't keep timestamps below day-granularity.
3. **Closed allowlists** — public ingest endpoints accept only known
   `clau` values (`web/api/analytics_ingest.py::_PUBLIC_EVENT_KEYS`).
   New events require backend code first; that's intentional schema
   discipline since these rows live forever.
4. **Fail-open** — analytics MUST NOT break a user-facing flow. Every
   bump is wrapped in `try/except` and silently logged on failure.
5. **No third-party JS** — no Google Analytics, no Meta pixel, no
   Plausible. Everything runs on our own backend.

## Tables

Both tables live in `analytics/models.py`. `dim*` slots are short
free-form strings (max 80 chars) that hold low-cardinality
discriminators only — never user identifiers.

### `MetricaEsdeveniment`

Atomic event counter.

| Field        | Notes |
|---           |---|
| `data`       | DateField; one row per day per bucket. |
| `clau`       | Event name, e.g. `pageview`, `registre_complet`. |
| `dimensio_1` | Optional bucket. For `pageview` it's the URL path; for `utm_landing` the UTM source; for `referrer` the acquisition bucket; for `social_publicat` the channel. |
| `dimensio_2` | Optional second bucket. For `pageview` it's the bot/human class (`bot`/`human`, empty on rows written before Fase 2); for `utm_landing` the UTM campaign; for `referrer` the referring host; for `social_publicat` the slot tipus. |
| `comptador`  | `PositiveIntegerField`, atomically incremented via `F("comptador") + 1`. |

Increments happen via `analytics.events.register(clau, dim1, dim2, n)`.
The helper:

* Uses `update_or_create` to insert on first occurrence.
* Uses `F()` expression on subsequent increments — concurrent gunicorn
  workers can't lose counts.
* Catches `IntegrityError` and retries with a pure `UPDATE` to
  recover from the race where two workers both try to insert the
  same row simultaneously.
* Is wrapped in a fail-open `try/except`.

### `MetricaPipeline`

Daily gauge snapshot of a pipeline-state metric.

| Field         | Notes |
|---            |---|
| `data`        | DateField. |
| `clau`        | Gauge name, e.g. `cancons_verificades`. |
| `dimensio_1`  | Optional discriminator (e.g. territori_codi for `cancons_per_territori`). |
| `valor_int`   | `BigIntegerField`, NULL when the metric is a float. |
| `valor_float` | `FloatField`, NULL when the metric is an integer. |

Both `valor_*` columns exist so a single table serves int + float
gauges without JSON. Snapshots are written by the
`snapshot_pipeline` cron at 23:00 daily; idempotent via the unique
constraint on `(data, clau, dimensio_1)`.

### `MetricaSocialPost` *(K2)*

Per-post engagement snapshot. One row per (SocialPost, day) so we keep
the engagement curve.

| Field              | Notes |
|---                 |---|
| `socialpost`       | FK → `social.SocialPost`. |
| `data`             | DateField. |
| `likes`/`replies`/`shares`/`reach`/`impressions`/`clicks` | Lowest common denominator across platforms. |
| `raw`              | JSONB with the full API response so the UI can surface platform-specific numbers (saves, total_interactions, quoteCount…) without a schema change. |

### `MetricaSocialPlatform` *(K2)*

Daily account-level gauge per platform. Free-form `metric` field so
new KPIs ship without a migration.

| Field      | Notes |
|---         |---|
| `data`     | DateField. |
| `platform` | `instagram`, `mastodon`, `bluesky`, `telegram`. |
| `metric`   | `followers`, `following`, `posts_total`, `members`. |
| `valor`    | `BigIntegerField`. |
| `raw`      | JSONB. |

## Ingest paths

### 1. Django middleware → pageviews + UTM

`analytics.middleware.AnalyticsMiddleware` records:

* `pageview` for every 2xx/3xx GET on a public Django path, with
  `dim2` = `bot`/`human`. The class comes from `analytics.bots.classify_ua`,
  which matches the request User-Agent against `BOT_UA_MARKERS` — the
  Python mirror of the Caddy `@bot` matcher in `deploy/Caddyfile`. The
  UA is read transiently and never stored. A parity test
  (`analytics/tests/test_bots.py`) keeps the Python list equivalent to
  the Caddyfile regex so the bot/human split matches how Caddy actually
  routes crawlers. Historic rows (pre-Fase 2) carry an empty `dim2` and
  are surfaced as "unclassified" — not reclassifiable, since the UA was
  never persisted.
* `utm_landing` whenever the request URL carries `?utm_source=…`.
* `referrer` for every **human** public pageview: `dim1` = acquisition
  bucket (`directe` / `cerca_organica` / `social` / `referral`), `dim2`
  = bare referring host. `analytics.referrers.classify_referrer` matches
  the host by DNS label (so `google.es`, `news.google.com` resolve
  without enumeration, and `client.com` isn't mistaken for the `t.co`
  shortener). Only bucket + host are stored — the Referer **path/query
  are dropped** (tokens could live there) and in-site (`intern`)
  referrers aren't recorded. Answers "where do humans come from?" for
  non-UTM traffic.

Skips `/api/`, `/static/`, `/media/`, `/favicon`, `/robots.txt`,
`/sitemap.xml`, `/staff/`, `/compte/2fa/`, `/health` — these would
either spam the table or duplicate work GoAccess does on Caddy logs.

### 2. SPA beacon → pageviews + curated events

The React SPA is served as static `dist/` files by Caddy and never
hits Django for navigation, so the middleware can't see SPA route
changes. Two POST endpoints fill that gap:

* `POST /api/v1/analytics/pageview/` — `{path, utm_source?, utm_campaign?}`
* `POST /api/v1/analytics/event/` — `{clau, dim1?, dim2?}` where
  `clau` ∈ `_PUBLIC_EVENT_KEYS` (closed allowlist).

Both return 204. Throttled per-IP at 60/min via the project default.
*(SPA wiring of these beacons happens in K3+ as the React pages add
share-click / escolta-click hooks.)*

Community funnel events (Slice E, 2026-06) added to the allowlist +
fired from the SPA: `onboarding_{inici,pas,complet,saltat}`,
`comunitat_directori_vista`, `comunitat_directori_filtre` (dim1=filter
key), `perfil_visible_toggle` (dim1=on/off). The connection events
`dm_enviat`, `denuncia_creada` (dim1=tipus) and `bloqueig_creat` are
fired SERVER-side via `register()` in the community endpoints (not via
the public ingest, so they're not in the allowlist).

### 3. Backend `register()` calls

The flows that already write to the DB also bump a counter:

| Where | Event |
|---|---|
| `web/api/auth_views.register_view` | `registre_complet` (dim1: `newsletter` or `no_newsletter`) |
| `web/api/compte_views/propostes.proposta_crear` | `proposta_crear` |
| `web/api/compte_views/propostes.solicitud_crear` | `solicitud_gestor_crear` |
| `web/api/compte_views/feedback.feedback_crear` | `feedback_crear` (dim1: target_type) |
| `social/management/commands/publicar_canal._handle` | `social_publicat` (dim1: channel, dim2: tipus) |
| `social/management/commands/publicar_social._publish_*` | `social_publicat` (dim1: platform, dim2: tipus) |

### 4. Daily snapshot cron

`analytics/management/commands/snapshot_pipeline.py` runs at 23:00 UTC.
Writes ~15 gauges in one short transaction:

* Catalog totals (verificades, pendents, rebutjades_acumulades).
* Coverage percentages (Whisper LID, MusicBrainz).
* Community gauges (usuaris actius, newsletter, directori).
* Per-territori catalog distribution (one row per territori).

### 5. Social metrics cron *(K2)*

`analytics/management/commands/recollir_metrics_social.py` runs at
22:30 UTC. Two passes:

1. Per-post engagement: every `SocialPost` published in the last
   30 days, fetched via `get_post_metrics()` on each platform's
   client. Upserted into `MetricaSocialPost(socialpost, data=today)`.
2. Per-platform account stats: one call per platform via
   `get_account_stats()`. Upserted into `MetricaSocialPlatform`.

Wrapped in `SingletonLock("analytics_metrics_social")` so two cron
instances can't double-spend rate-limit budgets. Fail-open per
platform: a Mastodon hiccup doesn't stop Bluesky/IG.

Telegram per-post engagement is **not supported** — the Bot API
doesn't expose channel-post views (would need MTProto via Telethon
or Pyrogram, not worth the dependency for one number). We mark
`raw.not_supported = "telegram_bot_api_lacks_post_views"` so the
dashboard can hide Telegram engagement instead of charting fake
silence.

## Dashboards

### Staff `/staff/analytics` *(K3)*

Single fetch to `GET /api/v1/staff/analytics/summary/?days=N` returns
the entire payload; five tabs derive client-side from that one call.

* **Resum** — KPI tiles with half-period-over-half-period deltas;
  auto-generated insights (pageview swings ≥10 %, top feedback
  surface, verification growth, best-performing post); joint
  pageviews + registres line.
* **Pipeline** — verificades / pendents / rebutjades line, cobertura
  whisper + MB, per-territori bar (using `terrChart`, the canonical
  territory deep from `rd/terr.js`), comunitat line.
* **Social** — followers KPI strip, followers daily series per
  platform (using `PLATFORM_COLORS`), publicacions per canal bar,
  top 10 posts table with CSV export.
* **Web** — daily pageviews bar, top 20 paths + UTM source/campaign
  tables, both with CSV export. The summary payload also exposes
  `pageviews_classified` (`human`/`bot`/`unclassified`/`total`) so the
  human-net pageview count sits next to the crawler-inflated total.
* **Cohorts** — five-line activity chart (registres, propostes,
  sol·licituds, feedback, publicacions); feedback distribution pie;
  raw counter audit table.

Window selector: 7d / 30d / 90d / 1a — re-fetches on change. CSV
export uses semicolons (Excel ca-ES default), quotes only when
needed, downloads in the browser without a server round-trip.

### Weekly admin digest — "Setmanari" *(K4, redesigned 2026-06)*

Every Monday at 08:00 UTC, `enviar_digest_setmanal` reports the **last
complete calendar week, Mon → Sun** (`today.weekday() + 7` back) against
the seven days before it. A rolling "last 7 days" would have ended on a
few hours of the current Monday and split the weekend publishing block
across two mails. Gauges read the *Sunday* snapshot; "Setmana N" is the
project week of the reported Monday, not of the send date. It emails
the `ADMINS`
recipients a **brand-coherent HTML** summary in the "redisseny" email
language (#060608, 640px, Anton/Bricolage/Instrument Serif; mirrors
`email_newsletter_top.html`), plus a text fallback. Sent via
`EmailMultiAlternatives` from `SERVER_EMAIL` (the "Josep Quaranta"
name). Sections, chosen for *this* project not generic web vanity:
(1) **Audiència humana** — human pageviews as the headline (bots split
via `pageview.dim2`), registres, newsletter, top human pages;
(2) **D'on venen** — acquisition buckets from the `referrer` event;
(3) **Pipeline del catàleg** — gauges + W-o-W deltas, moderation
decisions grouped from `StaffAuditLog`, Whisper/MB coverage, backlog
alert; (4) **Ranking per territori** — `TopSetmanal` entries per
territory; (5) **SEO i enllaços externs** — GSC impressions/clicks/
position, Bing inbound links, Core Web Vitals; (6) **Distribució
social** — publications, followers + deltas, top post, plus a
**calendari** grid (channel × day of the window, cell = content type,
`✕` = failed, dashed = omitted) built from `SocialPost`, the canonical
one-row-per-slot ledger — the headline count is derived from the same
grid so the two can't disagree; (7) **Incidències** — failed
`SocialPost` slots, crons in a bad state and the week's Django ERROR
records, gathered by `analytics/incidents.py`. A "frescor de dades"
line flags a stale snapshot. `--dry-run` prints text; `--html-out PATH`
renders the HTML for local preview without sending.

**Deltas are not always percentages.** `_delta()` reports the absolute
move (`+7`, `−4`) when the change rounds under 1 % or the base is under
10, an unchanged metric shows the `=` arrow with no number, and a
0-click SEO query falls back to its impressions. Before 2026-08 the
percentage was rounded *first* and a real change that rounded to 0 %
was then classified as "flat" — the KPI grid reported a week of
moderation work as a metric that hadn't moved.

**`analytics/incidents.py`** reads two files on the box, best-effort
(missing file → empty result, never an exception): `errors.log` (+
`errors.log.1`, logrotate is weekly with `delaycompress`), grouping
repeats by logger + digit-masked message; and the `tq-run` status tags,
classified by `health_report.gather_crons` — the function `tq-health`
runs hourly, so mail and watchdog can't disagree. Cron state is
point-in-time ("what is broken now"), not a history of the week.

## What we deliberately don't measure

* **No `request.user.pk` on any analytics row.** Login state matters
  for the action (e.g. `proposta_crear` requires auth) but the
  counter row stores no user reference.
* **No IP address.** Neither stored nor hashed. GoAccess on Caddy
  logs handles the rare cases where IP-level analysis is needed
  for ops/security; that data lives in `/var/log/caddy/` (perms
  0600) and never enters the Django DB.
* **No User-Agent stored.** Could fingerprint. It is read transiently
  to derive the `pageview` bot/human class and then discarded; the raw
  string never reaches the DB.
* **No Referer.** Could leak inbound URLs containing tokens.
* **No session-keyed deduplication.** "How many unique users"
  is a question we deliberately can't answer with this stack;
  use GoAccess (IP-based, separate, not in Django) for that.
* **No third-party JS.** No Google Analytics, no Meta pixel, no
  Plausible script, no Cloudflare Web Analytics. The only network
  calls the SPA makes for telemetry are POSTs to our own
  `/api/v1/analytics/*` endpoints.

## SEO surfaces: GSC + Bing + PSI

Three nightly crons poll external SEO APIs and persist thin daily slices
(all idempotent on their natural key, fail-open, skip cleanly when their
credential is absent so CI/local stay green):

- **GSC** (`recollir_metrics_gsc`, 21:00) -> `MetricaSEOQuery`
  (per query×page clicks/impressions/CTR/position). Credential:
  `GSC_OAUTH_*` / `GSC_SERVICE_ACCOUNT_FILE`.
- **Bing Webmaster** (`recollir_metrics_bing`, 21:15) -> `MetricaBing*`.
  Credential: `BING_WEBMASTER_API_KEY` + `BING_WEBMASTER_SITE_URL`
  (read from settings exactly like the GSC creds; never logged). The
  thin JSON REST API (`https://ssl.bing.com/webmaster/api.svc/json/<Method>`)
  has three quirks the parser handles: payload under the `"d"` envelope,
  `/Date(ms)/` date strings, and `Avg*Position` returned ×10 (divided by
  10). `GetUserSites` validates the configured site is a VERIFIED
  property first; if not, the command STOPS (no invented data). Methods
  pulled:
  `GetRankAndTrafficStats` (`MetricaBingTraffic`), `GetQueryStats`
  (`MetricaBingQuery`), `GetPageStats` (`MetricaBingPage`),
  `GetCrawlStats` (`MetricaBingCrawl`), `GetUrlLinks`
  (`MetricaBingLinks` - INBOUND LINK COUNTS, the authority signal GSC
  does not expose). Only the method name is ever logged, never the
  apikey or the request URL. No URL submission (IndexNow already covers
  Bing; `--submit-sitemap` is a dry-run stub only).
- **PSI** (`recollir_metrics_psi`, 21:30) -> `MetricaCWV` (Core Web
  Vitals per URL × form factor).

Both GSC and Bing feed the staff dashboard **SEO** tab
(`/api/v1/staff/analytics/seo/`): GSC panel + a parallel Bing panel
headlined by the inbound-link count.

## Operational details

### Cron lines

```
30 22 * * * topquaranta /home/topquaranta/bin/tq-run recollir_metrics_social >> /var/log/topquaranta/analytics.log 2>&1
0  23 * * * topquaranta /home/topquaranta/bin/tq-run snapshot_pipeline       >> /var/log/topquaranta/analytics.log 2>&1
0  8  * * 1 topquaranta /home/topquaranta/bin/tq-run enviar_digest_setmanal  >> /var/log/topquaranta/analytics.log 2>&1
```

### Failure surfacing

Both crons appear in `/staff/estat` via `CRON_META` entries. A miss
shows `STUCK(Nh, Nskips)` in red and triggers the `tq-health`
watchdog email at the next hourly tick.

### Health-report renderer (`analytics/health_report.py`)

Pure-stdlib module (no Django) that owns the PRESENTATION of the
`tq-health` report. `bin/tq-health` gathers the raw facts in shell and
pipes them here; this module classifies each cron (OK/STALE/STUCK/SKIP/
FAIL/WAITING/DISABLED — the last is a gated-off feature, gray, never an
anomaly, stale still wins — + watchdog/silenced), groups them by area
(`CRON_GROUPS`; unknown crons fall into "Altres"), renders an executive
summary + Anomalies block + Sistema/Spotify sections + a legend, and
localises timestamps to **CEST** (UTC stays in logs). It lives in the
analytics app purely for code organisation; it does not touch the DB.
It also exposes `anomaly_signature()` / a `--print-signature` CLI mode:
a STABLE dedup key over the anomaly identity (escalating crons by
`(name, state)` + per-threshold booleans, no ages/timestamps/counters)
that `tq-health` uses so a persistent failure emails once (2026-06-07).
See `pipeline.md` §7. Tested at `analytics/tests/test_health_report.py`.
Also renders a `CERTIFICATS TLS` block (2026-07-27) — see `docs/ops/runbook.md`.

Two coverage states beyond the bash original (auditoria 2026-06-07):

- **MISSING** — a cron declared in `cron-meta.json` whose status file is
  entirely absent. Benign only for genuinely-infrequent crons (weekly/
  monthly) that may not have hit their first run yet; those stay
  **WAITING**. For a frequent cron (`max_age_hours <= 48`,
  `WAITING_ESCALATE_MAX_AGE_H`) an absent tag means it was never
  written (cron line dropped, tag mismatch, tq-run broken) and
  escalates. We split on cadence because no timestamp exists to measure
  "how long absent".
- **ORPHAN** — the reverse reconciliation: a `*.status` file in the
  status dir with no `cron-meta.json` entry. `gather_crons` surfaces it
  (escalating) instead of ignoring it, so a tag written by an
  unregistered cron, or stale residue from a removed/renamed command,
  gets cleaned up (`rm` the file, or add the meta entry).

The watchdog WARN threshold (consecutive skips/fails before a still-
running or repeatedly-failing instance becomes suspicious) is **per-cron**
from the `skip_concern` field in `cron-meta.json` (daily crons declare 1,
hourly ones 3); CRIT stays a fixed 10. Before 2026-06-07 a uniform 3/10
was hardcoded and `skip_concern` was dead config.

### Pruning

We never delete from these tables. At current scale (~thousands of
rows/day worst case across all four tables) we have years of
headroom. When (and if) we ever need a retention cron, key it on
`data < today - INTERVAL '2 years'` and run it monthly.

### GoAccess (Caddy log analysis)

Moved to [`analytics-goaccess.md`](analytics-goaccess.md) (2026-07-31,
docs-size split — same pattern as `social-narrative.md`). In one line:
`generar_goaccess` (cron 23:30 daily) converts the Caddy JSON access
logs to Combined Log Format and runs `goaccess` into
`/var/cache/topquaranta/goaccess/report.html`, served only behind
`IsStaff` at `/api/v1/staff/analytics/goaccess/`.
