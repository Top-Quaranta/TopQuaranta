# SEO architecture

> Sprint S, May 2026. The public site is a React SPA; this document
> explains how we make every entity discoverable to crawlers and link-
> preview bots without bloating the SPA bundle.

## Goal

Every artiste, album, cançó, territori, comarca, dècada and weekly
top in the system is canonically findable on Google with rich snippets,
shareable on Mastodon/Bluesky/Telegram/WhatsApp/iMessage with a real
preview card, and indexable by AI crawlers (GPTBot, ClaudeBot,
PerplexityBot, Bytespider).

Pre-Sprint-S baseline: 5 URLs in the sitemap, every page returning the
same homepage `<title>` + OG card to all crawlers. Post-S baseline:
**~7 250 URLs across 9 sub-sitemaps**, per-entity metadata, schema.org
JSON-LD, dynamic Open Graph cards.

## Architecture: dynamic rendering

The SPA is served as static files by Caddy. JavaScript renders content
client-side, but most crawlers don't run JS — they see the bare shell.
We use **dynamic rendering** (a documented Google-blessed pattern) at
the reverse proxy:

```
Request
  │
  ├─ User-Agent matches @bot regex (Googlebot, Mastodon, GPTBot, …)?
  │     ├─ AND path matches /, /top, /artista/*, etc.?
  │     │     ▼
  │     │   reverse_proxy 127.0.0.1:8083  (Django SSR)
  │     │     ▼
  │     │   <html with rich head + JSON-LD + visible body>
  │     │
  │     └─ otherwise (e.g. /api/*) → Django passthrough
  │
  └─ Human (or unrecognised UA) → Caddy file_server dist/index.html
        ▼
       SPA mounts, runs Helmet, fetches /api/v1/seo/<entity>/<slug>/,
       and replaces the head with the same metadata the SSR served.
```

The `@bot` matcher is at `deploy/Caddyfile`. UA list covers search
engines, social link previews and AI crawlers. **Never** falls through
to dynamic rendering for `/api/*`, `/static/*`, `/staff/*` etc.

Why not full SSR (Next.js / Vite SSG) for everyone? Multiplied
maintenance, fragility, longer TTFB for the 99% of human visitors who
don't need it. Dynamic rendering for bots gets us 95 % of the value
with a tenth of the work.

## Modules

| Module | Purpose |
|---|---|
| `web/seo/meta.py`     | Single source of truth for `<head>` metadata. Used by SSR templates AND by the SPA Helmet hook. |
| `web/seo/jsonld.py`   | Schema.org JSON-LD builders: WebSite, Organization, MusicGroup, MusicAlbum, MusicRecording, MusicPlaylist, BreadcrumbList, CollectionPage (ItemList on editorial landings). |
| `web/seo/views.py`    | 10 SSR views (homepage, top, artistes-list, artista, album, canco, mapa, top-historic, territori, comarca, decada). All `@condition`-decorated for HTTP 304, `Vary: User-Agent` stamped, with strict indexability filters. |
| `web/seo/ogimage.py`  | Dynamic 1200×630 Open Graph cards generated from the entity data + brand fonts; cached on disk under `/var/cache/topquaranta/og/`. |
| `web/seo/indexnow.py` | IndexNow protocol pusher for Bing/Yandex/consortium real-time indexing on staff approval. |
| `web/sitemaps.py`     | 9 sub-sitemaps + sitemap-index. Lastmod from `Artista/Album/Canco.updated_at`. |
| `web/templatetags/seo_tags.py` | `safe_json` + `rel_url` template filters. |
| `web/templates/seo/`  | Self-contained HTML templates (no mm-design dependency, inline CSS, JS-disabled friendly). |
| `web-react/src/lib/seoHead.jsx` | `<SeoHead entity slug>` component that fetches the same `Meta` payload and injects via react-helmet-async on the SPA path. |
| `web/models.py` (`LandingProsa`) | Editorial prose for one landing, keyed by `(kind, clau)`. Empty by default; rendered as plain text (`linebreaks`, never `safe`). |
| `web/api/landing_routine.py` | Token-authed brief/prose endpoints for the SEO landing cloud routine (mirrors `newsletter_routine.py`, same bearer-token gate). |

## Editorial layer (Fase 2, 2026-06)

Three additive moves so the editorial landings stop being orphan/thin
and start ranking:

1. **Internal links INTO the landings.** The high-traffic entity pages
   (`artista`, `album`, `canco`) now emit an "Explora" block linking to
   the territori(s), canonical genre and (for album/canço) decade the
   entity belongs to (`web/seo/views.py::_editorial_links`). The decade
   link is emitted only when that decade page would actually resolve
   (≥5 verified cançons), so we never link into a 404. This de-orphans
   the editorial pages, whose ~zero search impressions (investigation
   2026-06) were attributed to having no inbound internal links.
2. **Richer structured data.** Territori / genere / decada pages now
   carry a `CollectionPage` whose `mainEntity` is an ordered `ItemList`
   of the featured artistes/cançons (`jsonld.collection_jsonld`), on top
   of breadcrumbs. Titles lean informational ("Top 40 i millors cançons
   en català de …", "Grups i cançons en català dels …").
3. **Editorial prose, filled asynchronously.** `LandingProsa` stores
   optional prose per landing. It is NEVER generated server-side: a
   cloud routine reads `GET /api/v1/landing-routine/brief/` (pending
   landings + `ConfiguracioGlobal.editorial_veu` + grounding samples)
   and writes back via `POST /api/v1/landing-routine/prosa/`, exactly
   like the newsletter routine. Empty prose degrades cleanly — the
   landing renders its structured content and the thin/noindex gate is
   untouched. Prose is plain text, rendered with `linebreaks` (never
   `safe`) so a compromised routine token cannot inject markup.

## Indexability rules

Hard rules, mirrored across SSR views, sitemaps, and IndexNow notify:

* **Artista** — only `aprovat=True`. When un-approved (or
  non-existent), SSR returns 404. An *approved* artiste with **no
  verified active cançó** is NOT a 404: it is served **200 + `noindex,
  follow`** (a thin page, `seo/artista_thin.html`, with a generated
  description and minimal `MusicGroup` JSON-LD). Rationale: returning
  404 for these made Google re-crawl previously-indexed URLs as errors
  (~4.8k/week) and discard accumulated authority; 200 + noindex
  de-indexes cleanly and the directive **drops automatically** the
  moment the artiste gains an indexable cançó. The `Meta.robots` field
  carries the directive; the thin/index decision lives in
  `web/seo/views.py::_artista_has_indexable`. Bio descriptions are run
  through `meta.clean_lastfm_bio`, which strips the
  "Read more on Last.fm" boilerplate so the placeholder never reaches a
  `<meta description>`.
* **Album** — parent artiste approved AND `descartat=False`.
* **Canco** — `verificada=True, activa=True`.
* **Territori / Comarca / Dècada** — only when the aggregation has
  enough content (≥3 artistes for comarca, ≥5 cançons for dècada).
* **Top historic** — only when `TopSetmanal` rows exist for that
  (territori, week).

When staff un-verifies a track or un-approves an artiste, the next
crawl from Google sees a 404 and removes the URL from the SERP. No
manual deindexing step required.

## Sitemap

`/sitemap.xml` is a sitemap-**index** referencing 9 sections:

| Section | URLs | Cadence | Priority |
|---|---|---|---|
| `static`              | 8     | weekly   | 0.8 |
| `artistes`            | 1979  | weekly   | 0.7 |
| `albums`              | 2212  | weekly   | 0.6 |
| `cancons`             | 3028  | weekly   | 0.5 |
| `territoris`          | 8     | daily    | 0.7 |
| `territoris_landing`  | 8     | weekly   | 0.6 |
| `comarques`           | 61    | monthly  | 0.5 |
| `decades`             | ~6    | monthly  | 0.4 |
| `top_historic`        | 14    | yearly   | 0.4 |

`lastmod` per entry comes from `updated_at` (`auto_now=True`) on the
underlying model. Smart-backfilled by migration `music/0064` from the
best per-model proxy (`mb_last_sync`, `last_album_check`, `created_at`).

Submission: GSC + Bing Webmaster Tools (manual, see Bloc D backlog).

## IndexNow

We push fresh URLs to Bing/Yandex+consortium within milliseconds of a
staff approval, instead of waiting for the next sitemap recrawl:

```
staff: aprovar Artiste X
  ↓ web.api.staff.pendents.pendent_aprovar
  ↓ web.seo.indexnow.notify_artista(a)
  ↓ POST https://api.indexnow.org/indexnow
       { host, key, keyLocation, urlList: [/artista/X, /album/Y, ...] }
  ↓ Bing/Yandex pull-recrawl within minutes
```

Verification: `https://www.topquaranta.cat/<KEY>.txt` returns the key
string. Key is committed at
`web/templates/seo/indexnow_key.txt` and routed via Caddy
`@django` matcher.

Failures are silently logged — IndexNow outages never block the staff
flow. Calls happen synchronously in the request because they're cheap
(~50 ms) and we don't want to wire a queue for one POST.

## JSON-LD coverage

Every SSR page emits at least one structured-data block plus a
BreadcrumbList:

| Page | Schema.org type |
|---|---|
| `/`                                        | WebSite + Organization (graph) |
| `/top`, `/top?territori=X`                 | MusicPlaylist (40 tracks) |
| `/top/<territori>/setmana/<YYYY-WW>`       | MusicPlaylist + Breadcrumbs |
| `/artista/<slug>`                          | MusicGroup (with discography + sameAs) |
| `/album/<slug>`                            | MusicAlbum (with track listing + ISRCs) |
| `/canco/<slug>`                            | MusicRecording (with ISRC + duration + AudioObject) |
| `/territori/<codi>` `/comarca/<slug>` `/decada/<XXX0>` | BreadcrumbList only |

All entities additionally carry an Open Graph image, Twitter card
metadata, hreflang `ca` + `x-default`, and a canonical URL.

Validation: every commit on the SEO surface MUST pass
[Google Rich Results Test](https://search.google.com/test/rich-results)
manually for at least one URL of each entity type.

## Open Graph images

Dynamic generation at `/og/<kind>/<slug>` produces a 1200×630 PNG per
entity, cached on disk under `/var/cache/topquaranta/og/<kind>/<slug>-<stamp>.png`.

* `home.png`            — static brand card
* `top/<TERR>.png`      — top of the week per territori
* `artista/<slug>.png`  — artiste card with name + territori + cançó count, blurred latest album cover as background
* `album/<slug>.png`    — album cover inset on a blurred-cover background
* `canco/<slug>.png`    — same pattern, for the song

Cache key includes `updated_at` so when an entity changes the OG image
URL changes too — every social share gets the latest card.

**Declared dimensions.** `Meta.og_image_width` / `og_image_height`
carry the real pixel size of `og_image` and are emitted as
`og:image:width` / `og:image:height` by both the SSR template and the
SPA `SeoHead`. Default is 1200×630 (the dynamic generator). Album and
cançó pages prefer the raw Deezer cover (`cover_xl`, square
**1000×1000**) as the card and declare 1000×1000 accordingly, so
social scrapers don't crop/mis-scale against a wrong aspect ratio.

## SPA parity

`react-helmet-async` is wrapped around the App tree. Each public page
mounts a `<SeoHead entity={...} slug={...} />` component that:

1. Fetches `/api/v1/seo/<entity>/<slug>/` (cached 5 min).
2. Receives the same `Meta` dataclass the SSR templates use.
3. Injects `<title>`, `<meta description>`, canonical, hreflang, OG and
   Twitter tags via `<Helmet>`.

Net effect: Google's JS-rendering crawler (which DOES execute JS)
sees the same `<head>` whether it hits the SSR path or the SPA path.
Humans with their browser tab title get a meaningful title that
matches the page they're on.

Drift prevention: there's only one source of truth (`web/seo/meta.py`)
— change a description there and both surfaces update on the next deploy.

## Edge cases

* **/top?territori=X** uses a query parameter, so the `URL` shown to
  Google differs from the `canonical_url` in the meta. Crawlers
  normalise URL params they recognise (`utm_*`) but `territori` is not
  in that list — Google indexes them as separate URLs, which is what
  we want (one chart per territori).
* **Vary: User-Agent** is critical because Caddy serves different HTML
  for the same URL based on UA. Without `Vary`, intermediate caches
  could cross over and serve the bot HTML to a human or vice-versa.
* **HTTP 304 Not Modified** triggers when a crawler's
  `If-Modified-Since` header is on or after the entity's `updated_at`.
  Saves bandwidth + premia el crawl budget. The `@condition` decorator
  takes care of the negotiation; we just provide `_artista_lm`,
  `_album_lm`, `_canco_lm` lookup helpers.
* **404 vs 410**: we use 404 when an entity loses indexability (decision
  2026-05-06). 410 (Gone) would deindex faster but the entity may regain
  approval later, so 404 is the safer default.

## Testing

`web/tests/test_seo.py` covers:

* Per-entity unique titles
* JSON-LD parses + has the right `@type`
* Indexability: 404 when un-approved / un-verified / discarded
* Helmet API matches SSR title
* Canonical absolute, hreflang `ca` present
* Long-tail thin-page guards (decade with no tracks → 404, comarca
  with <3 artistes → 404)
* Sitemap-index lists all 9 sub-sitemaps
* IndexNow key file serves correctly

19 SEO-specific tests. Full suite 269 passing.

## What's not here (Bloc D)

These need external dependencies that block automation:

* **Core Web Vitals**: WebP conversions, font preload, JS chunk
  splitting (recharts in its own chunk), critical CSS inline. Target:
  LCP/INP/CLS green per PageSpeed Insights.
* **Google Search Console integration**: domain verification (TXT DNS)
  + Service Account JSON key + GSC API enabled. Then a daily cron
  pulling impressions/clicks/CTR/positions and a new "SEO" tab on
  `/staff/analytics`.
* **PageSpeed Insights API**: API key from Google Cloud + a cron
  storing CWV per URL.
* **`/genere/<slug>`**: needs curated genre list + Artista.genere
  mapping; deferred until we groom the field.
* **Wikidata enrichment** (P5826), **MusicBrainz outreach** (artists
  URLs to TQ), **Press kit page**, **Embed widget**: off-page work.
