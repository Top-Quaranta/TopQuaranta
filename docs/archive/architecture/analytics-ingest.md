# Analytics · com entren les dades

> Sub-àrea d'[`analytics.md`](analytics.md), separada el 2026-08-17
> quan el document principal va passar el llindar de 400 línies
> (`docs-maintenance.md` regla 3). Ací viu **qui escriu** a
> `MetricaEsdeveniment` i amb quines garanties; les taules, els
> panells i les superfícies de SEO es queden al document índex.

## Ingest paths

### 1. Django middleware → pageviews + UTM

**Two writers, and both must classify.** The middleware only sees paths
Django serves — the SEO pages, the auth screens, the sitemaps. Everything
a human actually browses is the React SPA, served straight from Caddy, and
it reports through the beacon at `/api/v1/analytics/pageview/`. Those rows
carried **no** `dimensio_2` until 2026-08-17, so the weekly digest — which
filters on `dimensio_2="human"` — excluded every real visit and reported
the Django leftovers. The week of 10/08 came out as **98 human visits**
(mostly sitemap fetches) when the honest figure was **399**.

The beacon now stamps `human` **by construction**: reaching it means the
SPA's JavaScript ran, which is what a visit is here. It reads nothing
about the caller, so the aggregate-only promise holds. The trade is that
a crawler executing JS on an SPA route counts as human; those crawlers
also hit Django for the server-rendered pages, where the UA check catches
them.

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
* **Sitemaps are not pageviews.** `_SKIP_PREFIXES` filters `/sitemap`,
  not `/sitemap.xml`: the index sits at that exact path but the real
  files are `/sitemap-artistes.xml`, `/sitemap-cancons.xml` and friends,
  and a dot is not a dash. Until 2026-08-17 they counted, and because an
  unrecognised UA classifies as `human`, crawler fetches of the sitemaps
  became the **entire** "top human pages" list in the weekly digest.

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
