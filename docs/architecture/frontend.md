# Frontend (web-react SPA)

The TopQuaranta site is a single-page React app served from
`web-react/dist/` by Caddy. Django stays behind it on `/api/*` plus a
handful of full-page flows (registration, 2FA, sitemap, RSS). This
doc covers the SPA layout, build, and the seam where it meets the
backend; for the visual design system see
`docs/architecture/brand-logo.md`.

## Stack

- React 19, react-router-dom 7.
- Vite 8 + `@vitejs/plugin-react`, Tailwind v4 via
  `@tailwindcss/vite`.
- `mm-design` consumed as a git npm dep
  (`github:miquelmatoses/mm-design`) for tokens and brand SVGs.
- `recharts` for staff dashboards AND the public CancoPage ranking
  chart — both lazy-loaded (the chart is split into
  `components/CancoChart.jsx` and pulled via `React.lazy`) so the
  public bundle does not pay for it, `react-helmet-async` for SEO head
  tags,
  `react-markdown` + `remark-gfm` for community rich text,
  `vitest` for unit tests.
- Node 22 is the build target. CI uses `npm ci` against
  `package-lock.json`; the server only consumes `dist/`.

A `sense-instagram`, una fila pot portar un avís roig («Instagram va
refusar @X — busca'n el compte nou»): és un artista que hi ha tornat
perquè Meta va rebutjar el seu handle en publicar i el camp s'ha buidat.
Sense eixe context, l'operador podria concloure «no en té».

La cua `sense-instagram` té una columna **Suggeriment** (provisional,
2026-08): el candidat dels escombratges amb enllaç al perfil, botó
«Accepta» (un clic → PATCH de la URL, consumeix el suggeriment) i «✕»
(descarta el candidat però l'artista continua pendent — refusar el handle
no és dir que no en té).

Les dues cues d'omplir dades (`sense-instagram` i `sense-youtube`)
comparteixen forma a posta: mateixes columnes (artista, presència al top,
cançons actives), mateix botó **«No en té»** i el mateix tercer estat al
model (`instagram_revisat` / `youtube_canal_revisat`). Sense eixe botó un
artista que genuïnament no té compte torna a la cua cada passada i es
revisa a mà per sempre.

### `/staff/artistes/sense-youtube` *(2026-08)*

Decisió humana sobre **un** canal oficial de YouTube per artista, el
segon carril de senyal. Clon de `sense-instagram` amb una diferència que
importa: la resposta té **tres** sortides, no dues — un id de canal, «no
en té» (final i vàlid: Malalts no en té), o pendent. Sense el botó de
«no en té», els artistes sense canal es quedarien a la cua per sempre.

Per què una persona i no una heurística: sondejar «Malalts»
automàticament retorna un canal de pàdel i una empresa d'esdeveniments.
Un canal equivocat no es veu equivocat aigües avall — es veu com una
cançó amb sospitosament moltes reproduccions.

El camp accepta **el que es pot copiar**: `youtube.com/@nom`, l'URL
`/channel/UC…` o l'id pelat. Exigir l'id feia la cua inservible, perquè
YouTube va deixar d'ensenyar-lo enlloc de la seua interfície; el resol el
backend per 1 unitat de quota i refusa amb 400 el canal automàtic
(«- Topic» / «- Tema»), que la cerca sol posar primer.

La columna «Art Track» té **tres** estats — *Trobat*, *No en té* i
*pendent* — perquè una cel·la buida es llegia com una absència quan
normalment vol dir que el descobriment encara no hi ha arribat (~90
artistes al dia sobre 520).

## Directory layout

```
web-react/
├── index.html              Vite entry; the only HTML file
├── package.json            scripts: dev, build, lint, preview, test
├── vite.config.js          dev proxy to Django, manualChunks split
├── vitest.config.js        unit-test config
├── public/
│   └── geodata/            Simplified GeoJSONs for /mapa (Caddy serves)
└── src/
    ├── main.jsx            Mounts <App /> + global providers
    ├── App.jsx             Single <Routes> tree (~76 routes)
    ├── i18n.js             ca-only labels (no library, plain map)
    ├── index.css           Tailwind imports + @theme tokens
    ├── assets/             SVGs and static images bundled by Vite
    ├── components/         Cross-page UI (Layout, AdminRoute,
    │                       editorial primitives, MmIcon, ...)
    │   ├── ui/             Buttons, inputs, modals
    │   └── staff/          Staff-only widgets (FilterPanel, panels, …).
    │                       The table/form house kit moved to
    │                       `components/rd/surface.jsx`; `StaffTable.jsx`
    │                       is now a back-compat shim re-exporting it
    │                       (Table/TableCard, Btn, Pill, Input, Select,
    │                       Pagination, Callout, …).
    ├── context/            React contexts:
    │                       - AuthContext (profile, login, refresh)
    │                       - FeedbackContext (toast bus)
    ├── hooks/              useApi (fetch wrapper + auth headers)
    ├── lib/                Pure helpers:
    │                       analytics, api, format, img, urls,
    │                       seoHead, strip-markdown
    ├── locales/            Catalan copy for legal pages + emails
    └── pages/              One file per route
        ├── HomePage / TopPage / ArtistesPage / MapaPage / ...
        ├── legal/          7 legal pages + LegalLayout
        └── staff/          Staff pages (StaffLayout)
            └── social/     Distribution sub-views: a shared,
                            descriptor-driven ChannelView template
                            (one page per simple channel)
```

Routing is centralised in `App.jsx`: a flat `<Routes>` tree with no
nested layouts beyond the per-section `<Layout>`, `<StaffLayout>`,
`<ComunitatLayout>` and `<LegalLayout>` wrappers.

## Public vs staff vs community

- **Public** (`Layout`): `/`, `/top`, `/artistes`, `/artista/:slug`,
  `/album/:slug`, `/canco/:slug`, `/mapa`, `/com-funciona`,
  `/legal/*`. Anonymous-cacheable for 300 s by Django (see
  `web/api/utils.py::cache_for_anon`).
- **Account flows** (handled by `ComptePage` and friends, plus
  Django full-page templates for registration and 2FA): `/compte`,
  `/compte/perfil`, `/compte/accedir`, `/compte/callback`,
  `/compte/artista/{proposta,gestio}`, `/spotify/callback`.
- **Community** (`ComunitatLayout`): `/comunitat`,
  `/comunitat/directori`, `/comunitat/u/:username`,
  `/comunitat/publicar`, `/missatges`.
- **Staff** (`StaffLayout` behind `<AdminRoute>`): everything under
  `/staff/...`. The route guard bounces unverified staff sessions
  full-page to `/compte/2fa/verificar`, so the same session cookie
  the SPA uses ends up OTP-flagged when it returns.

The `AdminRoute` 2FA handoff is the only architecturally interesting
auth seam; see the file's docstring for the rationale.

**Staff navigation is one registry** (`pages/staff/staffViews.jsx::STAFF_GROUPS`,
2026-06). Both the left sidebar (`StaffLayout`) and the panell tiles
(`StaffDashboardPage`) map this single list, so adding a view is one entry
and it shows up in both. Each item carries `to` / `label` (sidebar) /
`title` + `desc` (panell tile) / optional `badge` (sidebar live count),
`countKey` (panell queue count), `end`, and `inSidebar` / `inPanell`
opt-out flags (the `/staff` self-link is sidebar-only). Before this the
two lists were hand-mirrored and had drifted — the sidebar carried the
social sub-channels + Spotify while the panell didn't, and Instagram had
a route in neither.

The **distribution area** under `/staff/social` is being split from a
single monolithic page into homogeneous house-style views. `/staff/social`
is the cockpit (master switch + the six-channel grid); most
channels have their own page at `/staff/social/<canal>` (`instagram`,
`mastodon`, `bluesky`, `telegram`, `newsletter`), all sharing one
`pages/staff/social/ChannelView.jsx`
template that paints from `channelDescriptors.jsx` — adding a channel or
a credential field means extending the descriptor, not writing a new
page. The Instagram view (`InstagramSection.jsx`) also carries the
**collaborator-invitation registry** (ADR-0015 §5.5): a house-kit table
(artista, username, post, tipus, data, estat) with a single "Marcar
acceptada" action per non-accepted row — the only manual resolution;
expiry is automatic. The **unified publications table** lives at
`/staff/social/publicacions` (`StaffSocialPublicacionsPage` →
`PublicacionsTable`, fed by the paginated `social_list`): one house-kit
table with search, a FilterPanel (canal/estat/tipus/setmana), deep-link
query params, a per-row clickable link, and the lifecycle actions. Above
the table, a self-fetching `MetricsStrip` shows per-platform engagement
totals from `/staff/social/metrics-summary/` (renders nothing while
loading, on error, or before any post has a metric snapshot). The
channel views embed that same `PublicacionsTable` scoped to their
channel. Each descriptor also declares a **4-section schema** (`section1`
/ `kpis` / `control` / `analytics`), and `ChannelView` renders those
sections generically — a missing KPI/metric for a channel paints an
honest dash, never a fake 0. **Newsletter** is the first complete
instance: a first-class view at `/staff/social/newsletter` whose Section
1 (`NewsletterSection`) adds a live can-generate indicator + a
consolidated-week selector + on-demand "Generate (engine)" + the shared
`NewsletterDraftEditor` (extracted from the legacy
`/staff/social/esborrany` page, now a thin wrapper kept for the cron
email links). **Instagram** is also a first-class view at
`/staff/social/instagram` (3c): its bespoke controls (credentials with
test/clear + token TTL, and the "Què publica" matrix — the
`MatriuCanalToggles` table with the read-only calendar-derived day
indicator; the legacy distribution phase was removed 2026-06, and the
story-cap knob
`story_max_cancons_ppcc` moved to /staff/configuracio 2026-06) live in a
custom `InstagramSection` (the
NewsletterSection pattern — the generic credentials/control slots stay
null so they don't double-render). RSS is still managed in-page on the
cockpit, which keeps the transversal week calendar + slide-render button;
Spotify stays on its own page (whose header carries a catalog-wide
enrichment-coverage KPI from `spotify/estat`'s `enrichment_coverage`). The
**distribution matrix** (third gate, `MatriuPublicacio`) is edited per
channel, not in one central grid:
`pages/staff/social/MatriuCanalToggles.jsx` (`canal` prop) renders only
that channel's tipus rows over `/staff/social/matriu/` (fetched whole,
filtered client-side) + `/staff/social/matriu/toggle/`. Each row shows a
**read-only day indicator** (`dies_publicacio`, derived from the
calendar/cron — "Dissabte", "Dilluns i dimecres", "Diumenge" for the
newsletter, "—" where N/A) and the editable `actiu` checkbox (the only
control). It lives in each `ChannelView`'s "Què publica" section
(mastodon/bluesky/telegram + newsletter) and in the Instagram section of
the cockpit. An off cell renders inactive (never hidden); non-seeded
combos paint a blank dash.
Not to be confused with `/staff/publicacions` (community posts).

`StaffAnalyticsPage` carries a GoAccess card whose blurb describes what
the reader actually consumes — the live Caddy access log **plus** its
rotated `.log.gz` segments — and warns that the report states the
interval it really covered, which can be shorter than the 30 days
requested when rotation has eaten the tail. Keep that copy in step with
`docs/architecture/analytics-goaccess.md`.

## Backend seam

- All data goes through `lib/api.js` which prefixes `/api/v1/` and
  attaches the `X-CSRFToken` header from the `csrftoken` cookie.
  Same session cookie as Django, so DRF's `SessionAuthentication`
  works untouched; django-axes + django-otp also see the SPA traffic
  as normal session requests.
- DRF endpoints under `web/api/` (documented at
  `docs/architecture/api-versioning.md` and
  `docs/architecture/staff.md`). The SPA does not know about model
  internals; everything it consumes is a serialised payload.
- ETag + Last-Modified on the hot read endpoints
  (`/ranking`, `/artistes`, `/mapa/artistes-top`) means re-fetches
  return 304 in a few ms.
- `StaffRankingPage` (`/staff/top`) renders both raw and effective
  weekly plays — the `escoltes_setmanals` and `escoltes_efectives` /
  `soft_cap_aplicat` fields from `/staff/top/` (post per-territori
  soft-cap, reconciled with the per-cançó `TopBreakdownPanel`). See
  `docs/architecture/staff.md`.

## Build, dev, deploy

```
# Local dev (Vite + HMR, proxies /api to Django on :8083)
cd web-react && npm install && npm run dev

# Unit tests (vitest)
npm test

# Production build (writes to web-react/dist/)
npm run build
```

On the server, `bin/tq-deploy` runs `npm run build` only when the
incoming push touched `web-react/`. Caddy then serves
`web-react/dist/` for everything that is not under Django's owned
paths (`/api/*`, `/compte/{2fa,login,registre,activar}/*`,
`/sitemap.xml`, `/robots.txt`, `/rss/*`, `/static/*`). React Router
handles client-side 404.

## Code splitting

`vite.config.js` declares `manualChunks` for `react` (core), `recharts`
and `react-router-dom`. The dedicated `react` chunk is evaluated first
and pins React core (`react` / `react-dom` / `react-is` / `scheduler`)
so the shared React runtime is never co-located into a feature chunk —
without it, a shared runtime module landed inside the `recharts` chunk,
so the entry imported a symbol from it and every public page
`modulepreload`ed all of recharts (~110 kB gz) even though only the
lazy `CancoChart` uses it (LCP audit Task 1, 2026-05).

`recharts` is now reached ONLY through dynamic `import()`: the staff
page tree (`pages/staff/*`), the legal pages, and the public
CancoPage ranking chart (`components/CancoChart.jsx`). So an anonymous
visitor's first byte pays for the public surface only and recharts is
no longer in the entry `modulepreload` list.

## Fonts

Self-hosted (OFL), served from `public/fonts/*` on our own origin.
Replaced the Google Fonts `@import` (which added a 3-hop critical
chain — external CSS → `fonts.googleapis.com` CSS → `fonts.gstatic.com`
woff2 — with no preload, delaying the text LCP on home/top per LCP
audit Task 1).

- **Families:** Playfair Display (headings) + Roboto (body) for the
  legacy/staff surfaces; **Anton** (crits), **Instrument Serif** italic
  (whisper) + **Bricolage Grotesque** (body, variable `400 800`) for the
  redisseny public surface (see "Redisseny web" below). All variable
  except Anton/Instrument (single weight), one woff2 per family+subset.
- **Subsets:** `latin` + `latin-ext` only (latin-ext carries Catalan
  edge glyphs such as `ŀ`). No italic axis — italics stay synthetic,
  identical to before. Four files total (~132 kB; latin 38/43 kB,
  latin-ext 21/29 kB).
- `@font-face` blocks live in `src/index.css` with `font-display: swap`
  and the Google unicode-ranges preserved.
- **Preloaded** in `index.html` (`<link rel="preload" as="font"
  crossorigin>`): the two `latin` faces (`playfair-display-latin.woff2`,
  `roboto-latin.woff2`) — the above-the-fold text LCP. `latin-ext`
  loads on demand.
- `mm-design/tokens/typography.css` is intentionally NOT imported in
  `main.jsx`: its only effect was a Google Fonts `@import` (its
  `--mm-font-*`/`--mm-text-*` tokens are unused here). `colors.css` and
  `spacing.css` are still imported.
- The Django auth templates (`comptes/_base_auth.html`) still use Google
  Fonts — a separate, self-contained surface — so the shared Caddy CSP
  keeps `fonts.googleapis.com` / `fonts.gstatic.com` allowed.

## Redisseny web (network-kit language, 2026-06)

The public site was rebuilt in the visual language of the social kit
(dark ink + grain, Anton/Instrument Serif/Bricolage, yellow accent,
territory deep/accent palette, liquid-glass surfaces). Shipped as a
long-lived integration branch (`redisseny-web`) merged to `main` in one
flip; never deployed mid-way.

- **Design system** lives in `src/components/rd/`: `terr.js` (territory
  palette + `shade()`, reusing the conserved `TERRITORI_NOM` so PPCC
  stays "Global"), `primitives.jsx` (`Band`/`Glow`/`Glass`/`Btn`/
  `Kicker`/`Crit`/`Numeral`/`Move`/`TerrLogo`/`TerrChip`/`RdCover`),
  `Header.jsx`, `Footer.jsx`, `CookieBanner.jsx`. Tokens are additive in
  `index.css @theme` (`--color-tq-ink-2`, the `--color-terr-*` table,
  `--font-crit`/`--font-whisper`/`--font-body`); the `.rd-*` utility
  surface (bands, glass, grain, header/footer) is scoped under `.rd-root`.
- **Light mode (staff-unification option B, 2026-06-23):** `primitives.jsx`
  offers light-surface variants — `Glass tone="light"` (white card) and
  `Btn tone=primary|secondary|outline|danger|ghost` + `size` (sm|md) —
  whose class strings mirror the old `StaffTable` byte-for-byte. The staff
  table/form kit now lives at `components/rd/surface.jsx` (built on those
  variants); **all 36 staff pages consume it**, and
  `components/staff/StaffTable.jsx` is a back-compat shim re-exporting
  `rd/surface` (so public `Field`/`Select` + the shared `FilterPanel`/
  panels still resolve). The retrofit was an import-path swap, pixel-
  identical by construction — staff stays white.
- **PERF (hard rule):** glass blur + the fractal-noise grain are layered
  on **only at `@media (min-width:901px)`**, with a
  `prefers-reduced-transparency` fallback — phones get flat solid
  surfaces, no blur, no grain. Never JS sniffing.
- **Shell split** (`Layout.jsx`): public routes get the dark rd shell
  (full-bleed `<main>`, bands compose full width); `/staff/*` keeps the
  **legacy yellow shell, byte-unchanged**. The staff *pages* now consume
  the rd canon via the light mode (`rd/surface`, above) — pixel-identical,
  staff stays white — but the shell/layout is still the legacy yellow one;
  it is not on the dark rd `.rd-root` surface.
- **Vocabulary veto:** "rànquing" is banned from user-facing copy → "el
  top" / "el top complet" / "la llista". Repo-wide grep is clean.
- **Conserved:** all URLs (incl. SEO-nested) + `?t=`/`?s=` params, every
  `/api/v1/*` contract, AuthContext/2FA, FeedbackContext, CancoChart,
  ExternalListenLinks, Cover (whose self-hosted→Deezer fallback chain
  `-500 → -250 → Deezer` is detailed in `portades.md` § "Stepped
  fallback chain"), the countdown logic. Legacy `editorial.jsx`
  + Playfair/Roboto remain only because `ArtistaDashboardPage` (the
  verified-manager portal, reskinned post-flip) still uses them.
- **A11y:** axe (WCAG 2a/2aa/21a/21aa) = 0 violations across all public
  routes; the pre-redisseny artista/album contrast debt was resolved.
