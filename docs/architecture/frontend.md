# web-react — invariants

<!-- `web-react/` is the React 19 + Vite 8 + Tailwind v4 SPA that Caddy serves
for every path Django does not own (`/api/*`, `/compte/{2fa,login,registre,
activar}/*`, sitemap, robots, RSS, `/static/*`). One flat `<Routes>` tree in
`App.jsx`; all data through `lib/api.js` (`/api/v1/` prefix + `X-CSRFToken`),
same session cookie as Django. -->

## Invariants

### Design layers (which primitives you may build on)

- **Public pages build on `components/rd/primitives.jsx` (+ `.rd-*` CSS scoped under `.rd-root`); staff pages build on `components/rd/surface.jsx` (the "rd light canon": `TableCard`, `Table`, `Th/Td/Tr`, `Pill`, `Input`, `Select`, `Pagination`, `PageHeader`, `Field`, `Callout`, `EmptyState`, `Btn`).** Why: there is no single shared primitive set; the two live systems share only the `index.css @theme` tokens. `components/staff/StaffTable.jsx` is a back-compat shim re-exporting `rd/surface` — keep it until its importers are migrated, do not add to it.
- **`components/editorial.jsx` is LEGACY — do not build on it.** Its only live export is `TERRITORI_NOM`, imported by `CancoChart.jsx` and `rd/terr.js`; retirement is tracked in `docs/archive/audits/2026-06-23-auditoria-dry-modular.md` §2.2.
- **Territory palette has one source: `rd/terr.js::PAL` (deep/accent pairs; `terrChart(code)` = deep is the value every chart series uses), mirrored by `index.css --color-terr-*`.** Why: two divergent copies once produced different colours per chart. Both chart consumers (`CancoChart.jsx`, `StaffAnalyticsPage.jsx`) read it. Public labels: `TERRITORI_NOM` — PPCC is shown as «Global», never "PPCC"; the DB/API code stays `PPCC`.
- **Colours/fonts/spacing come from `var(--mm-*)` or Tailwind `tq-*` tokens; no hex literals in components.**
- **"rànquing" is vetoed in user-facing copy ("el top" / "la llista").** Guarded by: repo grep — note the dead `src/locales/*.json` still contain it (see Traps).
- **Staff shell stays the legacy yellow `Layout` (byte-unchanged); the dark `.rd-root` shell is public-only.** `Layout.jsx` switches on `pathname.startsWith('/staff')`.
- **Glass blur + grain are applied only at `@media (min-width: 901px)` with a `prefers-reduced-transparency` fallback; never JS sniffing.** Why: phones get flat solid surfaces (perf hard rule). Guarded by: `index.css` lines ~328/350.

### Components with a contract

- **`<Pagination>` must receive `meta` (`{page, num_pages, total, has_previous, has_next}`); it renders `null` when `meta` is falsy — wrong prop names paint nothing, silently.** Why: `/staff/artistes/sense-youtube` showed 50 of 400 rows for days (2026-08-17). Guarded by: `web/tests/test_paginacio_spa.py` (static grep over every call site).
- **Deezer cover URLs are resized at consumption via `lib/img.js::deezerImg(url, size)`; slot ≤ 48 px → 120, ≤ 128 → 250, ≤ 320 → 500; the stored `Album.imatge_url` stays the 1000×1000 `cover_xl`.** Why: 1000 px into 40 px slots was the main LCP driver (≈ 4.2 MiB/page). Deezer 403s above ~1400. Guarded by: `lib/img.test.js`.
- **`<Cover>` walks a self-hosted → Deezer fallback chain (`/portades/…-500.jpg` → `-250` → Deezer) one step per `onError`; the happy path fires no `onError`.** Guarded by: `components/Cover.test.jsx`; chain detail in `portades.md`.
- **`<TopQuarantaLogo>` (`variant="mono"|"color"`) injects the SVG via `innerHTML` after `normalise()` promotes each path's inline `style="fill:X;stroke:Y"` to `fill=`/`stroke=` attributes.** Why: the HTML parser keeps the `style` string but does NOT populate `.style` on SVG fragments inserted via `innerHTML`, so paths compute to black (2026-05-07: header rendered as a black blob). Guarded by: `TopQuarantaLogo.test.js` (14 cases). Verify on a real page: `getComputedStyle(path).fill` must never be `rgb(0, 0, 0)`.
- **The mono logo works only because the vendor SVG carries a stroked-outline layer over the filled layer; collapsing three colours to `currentColor` reads as outlines + filled wordmark. A regenerated export without strokes breaks mono.** Regenerate mono from `vendor/mm-design/icons/brand/logo-topquaranta-rect.svg` by substituting `#f1c22f`/`#cf3339`/`#0047ba` → `currentColor` AND stripping the root `style="color:#cf3339"` (else mono renders red). Copy the colour SVG to BOTH `vendor/` and `web-react/src/assets/`; the Django auth shell `{% include %}`s the SPA mono file (server-side, immune to the `innerHTML` trap).

### Routing, auth, bundle

- **Every `pages/staff/*` page (and `ChannelView`) is `React.lazy`; `recharts` is reached only through dynamic `import()` (staff pages, legal pages, `CancoChart` on `CancoPage`); `vite.config.js::manualChunks` pins React core in its own chunk evaluated first.** Why: without the pin a shared runtime module landed in the `recharts` chunk and every public page `modulepreload`ed ~110 kB gz of recharts. The anonymous bundle size is the metric to watch.
- **`<AdminRoute>` bounces an unverified staff session FULL-PAGE (not client-side) to `/compte/2fa/verificar/?next=` (or `/compte/2fa/configurar/` if no TOTP); the same cookie returns OTP-flagged and `IsStaff` API checks pass.** Why: the SPA login opens a session but never runs `otp_login()`; only the Django page can. Docstring in `components/AdminRoute.jsx`.
- **Staff navigation is one registry: `pages/staff/staffViews.jsx::STAFF_GROUPS` feeds both the sidebar and the panell tiles.** Why: two hand-mirrored lists had drifted (Instagram had a route in neither).
- **Adding a distribution channel view = extending `pages/staff/social/channelDescriptors.jsx`, not writing a page; a missing KPI paints a dash, never a fake 0.**
- **Fonts are self-hosted (`public/fonts/*`, `@font-face` in `index.css`, `latin` faces preloaded in `index.html`); `mm-design/tokens/typography.css` is deliberately NOT imported.** Why: its only effect was a Google Fonts `@import` (3-hop critical chain on the text LCP). The Django auth templates still use Google Fonts, so the Caddy CSP keeps `fonts.googleapis.com`/`gstatic` allowed — do not tighten it without moving them.
- **Vitest IS wired (`npm test`, run by `ci.yml`): `TopQuarantaLogo`, `img`, `Cover`, `ExternalListenLinks`, `Markdown`.** CLAUDE.md §9 and the `test_paginacio_spa.py` docstring say otherwise — they are stale; runtime-behaviour guards belong in Vitest, static-shape guards (prop names, call sites) may stay in Python.

## Traps

- `src/i18n.js` + `src/locales/{ca,es,en}.json` are dead: nothing imports `i18n.js`, `i18next` is not a dependency. Grep-based vetoes ("rànquing", "Països Catalans", "PPCC") must exclude or delete them — `ca.json` still says "rànquing".
- `cairosvg` missing in prod made the social renderer paste `None` silently (2026-05-07); it is pinned in `requirements.txt` — the brand SVG is consumed by three renderers (SPA `innerHTML`, Django `{% include %}`, Python cairosvg) and each has a different failure mode.
- The three brand colours are baked into the SVG (`#0047ba` blue, `#cf3339` red, `#f1c22f` yellow — NOT the SPA's `tq-yellow #facc15`); Inkscape does not parameterise them.
- `deezerImg` is a pass-through for non-`dzcdn.net` URLs — self-hosted covers must go through `portadaUrl`/`<Cover>`, not through it.
- `Cover`'s -500 variant may be missing on disk while -250 exists (audit 2026-06-22); never assume the first step loads.
- Public read endpoints are cached for anonymous hits (`web/api/utils.py::cache_for_anon`; authenticated requests bypass) — an SPA change that expects fresh data on an anon page must change the ETag root server-side, not add cache-busting query params.

## Where the detail lives

- code: `web-react/src/App.jsx`, `components/rd/{primitives,surface,terr}.js(x)`, `components/{AdminRoute,Layout,TopQuarantaLogo,Cover,CancoChart}.jsx`, `lib/{api,img}.js`, `pages/staff/staffViews.jsx`, `pages/staff/social/channelDescriptors.jsx`, `vite.config.js`, `index.css`
- tests: `web-react/src/**/*.test.{js,jsx}`, `web/tests/test_paginacio_spa.py`
- archived narrative: `docs/archive/architecture/frontend.md`, `docs/archive/architecture/brand-logo.md`
- related: `docs/architecture/ingesta.md` (cover chain), `web.md` (staff endpoints), `docs/archive/audits/2026-06-23-recon-disseny-unificacio.md`, `docs/archive/audits/2026-06-23-auditoria-dry-modular.md`
