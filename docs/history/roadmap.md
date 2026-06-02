# ROADMAP.md — TopQuaranta

> Estat actual i propers passos. El detall fi viu al `git log` i als
> commits per sprint; la història de Phase 9 (auditoria d'excel·lència)
> al fitxer `docs/history/roadmap.md` (sprints A–J ter).
> Last updated: 2026-06-02.

---

## Estat actual

- **Públic**: `https://www.topquaranta.cat/` — React SPA a l'arrel.
  Pàgines redissenyades amb llenguatge editorial (bandes alternants
  ink/blanc + Playfair) als sprints H/I bis/J bis: `/`, `/top`,
  `/artistes`, `/mapa`, `/comunitat`, `/com-funciona`. Tot WCAG AA
  (axe-core 0 violacions a 10 URLs auditades).
- **Staff**: `/staff/*` — 17 pàgines React + DRF. Taules amb scroll
  horitzontal a mòbil (Sprint J ter). Filter-panel pattern reutilitzat
  per la pàgina pública d'artistes.
- **Auth**: sessions Django + CSRF + TOTP 2FA per staff.
- **Pipeline**: nightly chain documentada a `docs/architecture/pipeline.md`.
- **DB**: PostgreSQL 14, 48 taules (nova `Album.last_album_check`).
  Volums actuals (2026-05-03): ~1.9k artistes aprovats, ~2.5k cançons
  verificades, 5 territoris amb top oficial actiu.
- **ML**: 79 features, ROC-AUC 0.9994 (post Whisper + MB).
- **Infra**: Caddy + gunicorn :8083 amb `ExecReload=HUP`.
- **Distribució**: 6 canals actius o configurables — Instagram,
  Mastodon, Bluesky (carrusel 4 imatges), Telegram (media-group),
  newsletter, RSS. Esborrat remot real per a tots des de
  `/staff/social`. Renders en JPG q90 (Step 3a). Story set PPCC
  reescrit a 7 slides editorials (intro → top 40-11 → top 10-4 →
  podi → #1 hero amb clímax Playfair → novetats → outro groc),
  ordenats cap al clímax del #1 (Step 3b, 2026-06-01) i amb el
  redisseny visual validat portat al renderer Pillow — noves
  famílies OFL Anton / Bricolage Grotesque / Instrument Serif /
  Playfair 800 a `social/fonts/` (redisseny Step 3b, 2026-06-02).
  Stories territorials encara pendents (seran el Step 3c). Detall a
  `docs/architecture/social.md`.
- **Analytics**: suite ètica completa (K1-K4 + GoAccess) a
  `/staff/analytics`. Pageviews, UTM, KPIs de pipeline, mètriques
  socials per post i per compte, GoAccess sobre logs Caddy darrere
  auth staff. Email digest setmanal als admins. Cap PII; cap
  third-party JS. Detall a `docs/architecture/analytics.md`.
- **Stack**: Python 3.12 + Django 6.0 + scikit-learn 1.8 (bumped
  2026-05-04 amb venv-swap calent, sense downtime). Vite 8.0.11 +
  postcss 8.5.14 (Dependabot 2026-05-07, 0 vulnerabilitats obertes).
- **CI**: 5 jobs a `.github/workflows/ci.yml` — `tests` (pytest, 269+),
  `lint` (black + isort), `frontend-tests` (vitest, 14), `migrations`
  (makemigrations --check), `destructive-migrations` (soft warning a
  PRs amb `RemoveField`/`DeleteModel`/`RenameField`/`RenameModel`).

Si vols més detall del que es va lliurar a cada sprint, vés a la
secció [Sprints — completats](#sprints--completats) més avall.

---

## Phase status

Cada **fase** és una era del projecte (estructural). Cada **sprint**
dins una fase és un lliurament concret. Les fases ja són totes ✅;
l'activitat des d'abril 2026 viu en sprints.

| Fase | Resum | Estat |
|---|---|---|
| 0 | Esquelet del projecte, settings split | ✅ |
| 1 | Importació legacy (taules buidades a Phase 8) | ✅ |
| 2 | Ingesta Last.fm | ✅ |
| 3 | Normalització Formula B (Phase 4 la va deprecar) | ✅ |
| 4 | Algorisme de top portat a Python (v1) | ✅ |
| 5 | Top provisional + revisió staff | ✅ |
| 6 | Pipeline metadata Deezer + lloc públic | ✅ |
| 7 | Panell `/staff/` propi | ✅ |
| 8 | Neteja legacy (taules, codi, serveis) | ✅ 2026-04-16 |
| Audit | Consolidació + reescriptura docs | ✅ 2026-04-16 |
| Ops | `tq-health` + backups diaris + settings | ✅ 2026-04-16 |
| 9 | **Excellence** — security + reliability + arch + culture | ✅ (history a `docs/history/roadmap.md` (sprints A–J ter)) |
| 10 | Migració React SPA + neteja Django UI | ✅ 2026-04-21 |
| 11 | Plataforma comunitat (Grup C) | ✅ 2026-04-21 |
| 12 | Sprints temàtics A–J ter (vegeu sota) | ✅ |

---

## Sprints — pendents

Per ordre de prioritat (no alfabètic). Quan se'n fa un, es mou a la
secció _completats_ amb la data i el detall.

### 1. Sprint — Distribució v2 (refinaments + estadístiques)

> Iteració sobre la infraestructura multi-canal del Sprint I bis.
> El renderer i els clients ja són sòlids; ara toca **mesurar què
> arriba al públic**, **netejar la cua de pendents col·labs** que
> el `_upsert_track` crea de manera massa generosa, i pulir
> detalls de format que han anat sortint en l'ús real.

> **Estadístiques per canal**: tot mogut a la suite analytics
> (Sprint K, completat 2026-05-04). `MetricaSocialPost` per
> publicació + dia, `MetricaSocialPlatform` per gauge de compte.
> Telegram per-post no és viable via Bot API (limitació del
> protocol, documentada). Newsletter/Brevo open-rate queda com a
> backlog menor. Vegeu `docs/architecture/analytics.md`.

**Neteja de pendents col·labs brossa** (caçat 2026-05-03):
- [x] Comand `netejar_pendents_no_ppcc` (lliurat 2026-05-06):
      descarta `font_descoberta in (collaborador, deezer_contributor)`
      + `aprovat=False, pendent_review=True` + sense cançons
      principals + sense localitats PPCC + sense `StaffAuditLog`
      target. Cap 500/run; cron Mon 02:15. Acció: `pendent_review=False`
      (descartat) + audit `pendent_descartar` amb `motiu=auto_no_ppcc`.
      Backlog inicial detectat: ~1830; drena en 4 setmanes.
- [x] **Diferir creació de col·laboradors fins a verificació**
      (lliurat 2026-05-07, commit `bfa594a`). En lloc d'una heurística
      sobre profile mixt, atac directe al símptoma: cap pendent
      `Artista` es crea durant la ingesta. Tots els contributors
      desconeguts (que no es troben per `ArtistaDeezer.deezer_id`)
      s'aparquen a `Canco.contributors_raw` (JSONField). Quan staff
      o ML auto-ML aproven la cançó, `processar_collaboradors_pendents`
      els materialitza com a `Artista(pendent_review=True)`. Cançons
      rebutjades mai arriben aquí — elimina ~76 % del soroll de la
      cua (és la quota d'`album_incorrecte` als rebuigs).

**Refinaments del renderer** (post-feedback usuari):
- [x] **Slides de novetats** (lliurat 2026-05-06): aplicada
      readability v3 a `_feed_album_slide` (artist 36 → 44, títol-
      cover gutter de 50 px → 20 px) i `_feed_singles_slide`
      (f_song 28 → 40, top padding y+12 → y+0). Mateixes
      proporcions de cover/icon/row_h que el feed_list_slide.
- [x] **Stories CTA** (`_story_cta`) bumpada 56 → 64 (shipped
      2026-05-07, commit `2b5ca0d`).
- [x] **Portada novetats**: +54 px marge esquerre ja aplicat a
      `_feed_novetats_portada` (verificat 2026-05-07, commit `2b5ca0d`).
- [ ] Mode dark/light per al story footer: ara mateix
      «topquaranta.cat» va sempre en `COLOR_TEXT_MUTED`. Verificar
      contrast sobre territoris de color clar (amber/yellow) si
      mai posem una targeta clara.

**Refinaments operatius**:
- [ ] Carrousel BS/Mastodon: actualment passa portada + 3 list
      slides. Si el top és del tipus `novetats` (singles/albums),
      el slide 0 és la portada de novetats (no llista) — s'haurien
      de tractar diferent? Decidir entre:
      (a) novetats també envien 4 imatges (portada + 3 album/single
          slides); o
      (b) novetats només envien la portada (singletons).
- [x] **Plantilla d'alt-text rica** (shipped 2026-05-07, commit
      `2b5ca0d`): alt-text per slide amb context i posicions
      explícites, alineat amb a11y guidelines.
- [x] **Programació flexible** (lot B, shipped 2026-05-07, commit
      `3df1b6a`): delay per canal configurable a
      `ConfiguracioGlobal`.
- [x] **Re-publicar amb correcció** (lot C, shipped 2026-05-07,
      commit `3df1b6a`): botó al panell social que esborra el
      post remot + regenera + republica en un sol pas.

**A11y + i18n**:
- [x] Text alternatiu al carrusel IG (shipped 2026-05-07, commit
      `2b5ca0d`): alt-text propagat via `upload_carousel_item` ara
      també a Instagram, alineat amb Mastodon i Bluesky.
- [ ] Verificar contrast de tots els colors de territori sobre
      les pastilles del slide list (alguna fila tinta vs
      `COLOR_TEXT_MUTED` pot quedar baix-contrast).

### 2. Sprint S — SEO Bloc D (CWV + off-page outreach)

> Estratègia documentada el 2026-05-06 a `docs/architecture/seo.md`.
> Blocs A+B+C executats el mateix dia. **GSC ja verificat + PSI cron
> actiu + `/genere/<slug>` lliurats després** (auditoria 2026-05-07);
> el que queda és Core Web Vitals + outreach manual.

**Decisions de l'sprint** (preses 2026-05-06):
- Templates SSR-bot estil **full alternative HTML** (no només meta) —
  utilitzable per usuaris amb JS desactivat (a11y win) a banda de
  servir per als crawlers.
- **OG image dinàmica** generada per Django per cada entitat (similar
  al renderer social), no estàtic.
- **Bot UA list inclou bots d'IA** (GPTBot, ClaudeBot, PerplexityBot,
  Bytespider) — apareixem al training data, és free reach.
- **`updated_at` com a `auto_now=True`** + backfill intel·ligent per
  model (Artista: mb_last_sync, Album: last_album_check, Canco:
  created_at).
- **304 Not Modified** quan l'entitat no ha canviat — estalvi de
  bandwidth + premia el crawl budget.
- **`hreflang="ca"`** als links alternates encara que només tenim
  un idioma (assenyala explícitament Catalan a Google internacional).
- **Política d'indexació**: només `verificada=True, activa=True` per
  cançons; `aprovat=True` per artistes; albums = aprovat OR té cançons
  verificades. **Quan staff desverifica una entitat, el SSR retorna
  404** (Google la treu del SERP en hores).

**Lliurat post-Bloc-C**:
- [x] **GSC monitoring**: domini verificat, dades arribant.
- [x] **PageSpeed Insights API**: cron `recollir_metrics_psi` 21:30.
- [x] **`/genere/<slug>`**: vista a `web/seo/views.py:652` amb
      `Artista.genere_canonical` data-driven.

**Bloc D pendent**:
- [ ] **Core Web Vitals**: parcialment fet (shipped 2026-05-07,
      commit `f29d06b`): JS chunk splitting (manualChunks per
      recharts) + preconnect + critical CSS inline. Pendent: WebP +
      LCP/INP/CLS verds confirmats al PageSpeed Insights.
- [ ] **Wikidata enrichment**: afegir `P5826` (TopQuaranta artist ID)
      property a Wikidata (procés manual via tutorial wikidata.org).
- [ ] **MusicBrainz outreach**: afegir el nostre URL com a `urls` a
      cada artiste de MB (procés manual o cron amb credencials MB).
- [ ] **Press kit page** (`/premsa`): logos, dossier PDF, contacte —
      atrau backlinks naturals.
- [ ] **Embed widget**: codi JS embedable (`<iframe>` o
      `<div data-tq-top="...">` + script.js) perquè blogs/festivals
      mostrin un mini-top a la seva web. Cada embed és un backlink.

### 4. Backlog menor

Items petits per fer en sessions curtes:

- ~~**Backups off-site**~~ — risc acceptat (decisió 2026-05-07,
      documentada a `docs/ops/runbook.md` §4). Reconsiderar només si
      l'audiència creix més enllà de hobbyist scale o la curació
      esdevé legalment rellevant.
- [ ] Snapshot baseline del model RF abans del proper retrain (`cp
      ml_model.joblib ml_model.baseline-YYYY-MM-DD.joblib`) per A/B
      sobre el set de 48 clips si el nou retrain regredeix.
- [ ] Test coverage 52% → 70%. Gaps coneguts: `music/services.py`,
      `music/verificacio.py`, `ranking/senyal.py`. Sessions curtes a
      estones lliures. (`obtenir_senyal` ja a 87 % — 2026-05-06.)
- [ ] **Centralitzar hardcodes** (auditoria 2026-05-06): part feta —
      `social/colors.py` i `social/constants.py` existeixen
      (`HTTP_TIMEOUT_S=60` ja consolidat). Pendent:
      `settings.API_PAGINATION` (~5 endpoints amb `page_size=N`
      hardcodejats), `settings.SITE_URLS` (URLs socials + newsletter),
      i auditoria final dels callsites residuals (~1 hex color encara
      al wild a `social/`).
- [x] `ArtistaQuerySet` managers (lliurat 2026-05-07):
      `.public()`, `.pendents()`, `.with_ppcc()`, `.with_mbid()`.
      13 callsites migrats. 6 tests unitaris.
- [x] **`web/api/serializers.py`** (lliurat 2026-05-06, commit `3f7bd86`):
      shared serializers + migració d'album/canco/top/home. Pendent
      ampliar a la resta d'endpoints quan toque.
- [x] **`useApi` hook** (lliurat 2026-05-06): a `web-react/src/hooks/useApi.js`.
      HomePage subcomponents, ArtistesPage, MapaPage, ComunitatPage,
      ComunitatPublicaPage, ComunitatPublicarPage, MissatgesPage,
      SolicitarGestio search ja migrats. Resta SPA pendent per migrar
      gradualment.
- [ ] **`BaseSignalCommand`** (auditoria 2026-05-06): per a `--dry-run`
      + `--limit` + `SingletonLock` (~12 commands). Encara no creat;
      `music/management_helpers.py` (commit `d8d3643`) ha extret
      l'argparse boilerplate compartit, però la classe-base com a tal
      queda pendent.
- [x] **Algorithm robustness — extrapolation gate** (lliurat 2026-05-07,
      commit `253faf2`): drop "lifetime extrapolation"; `algorisme.py`
      ara només compta senyal observat real.
- [x] **`corregit=True` exclòs del ranking** (lliurat 2026-05-07):
      `algorisme.py` ara filtra `error=False, corregit=False` al
      pull de senyal. Defensa contra contaminació a l'err=6 retry
      path quan `_detect_drift` flag-eja un artiste mismatched.
- [ ] **Alias double-count guard URL-based** (auditoria 2026-05-06):
      `_normalize_lastfm_url` ja existeix a `detectar_lastfm_aliases.py:56`
      però `get_track_info_literal:258` encara fa case-fold check propi.
      Pendent: importar i reutilitzar la versió URL-based (més robust).
- [x] **`StaffAuditLog.ACTION_CHOICES`** (lliurat 2026-05-07): afegit
      `artista_sync_mb`, `pendent_orphan_merged`, `feedback_resolt`,
      `usuari_esborrar`, `usuari_reenviar_verificacio`,
      `usuari_enviar_reset_password`, `<channel>_publicat` × 4.
      Migració 0067.
- [ ] **CSP `unsafe-inline`** (Caddyfile): migrar a nonce-based al
      build de Vite. Sprint dedicat de seguretat.
- [x] **Codi mort** (lliurat 2026-05-07): esborrats 9 fitxers
      buits/placeholders: `ingesta/pipeline.py`, `music/views.py`,
      `music/tests.py`, `ingesta/views.py`, `ingesta/models.py`,
      `ingesta/tests.py`, `social/views.py`, `social/admin.py`,
      `ranking/tests.py`. **`Album.cancons_obtingudes`** purgat per
      migració `0069_remove_album_cancons_obtingudes`. Pendent:
      `backfill_album_source.py` (cal verificar cua buida abans).
- [ ] **Watchdog silent-noop → tq-health** (auditoria 2026-05-06):
      `tq-run` retorna `status=OK` quan exit-code=0. El protocol
      WORK_DONE ja existeix (commit `c3d0f7d`) i les comandes el
      poden emetre, però `tq-health` encara no flag-eja "0 units of
      work" en runs consecutius. Pendent: connectar el protocol a
      `tq-health`.
- [x] **Secret rotation runbook** (lliurat — secció §9 a
      `docs/ops/runbook.md`).
- [ ] **Brevo open/click rate** per als emails de newsletter.
      Sprint K (analytics) va deixar les bases per a `MetricaSocial*`;
      Brevo exposa `/v3/smtp/statistics/aggregatedReport` amb
      `tags=newsletter-YYYY-wWW` si etiquetem cada enviament. Un cop
      fet, el dashboard `/staff/analytics` afegeix open-rate per
      setmana.
- [ ] **Botons de compartir** a `CancoPage`/`AlbumPage`/`ArtistaPage`
      (Web Share API + fallbacks copy-to-clipboard / Mastodon /
      Bluesky / Telegram). Amb l'allowlist `share_click` ja
      preparada al backend, només cal cridar
      `trackEvent('share_click', surface, network)` als handlers.
- [ ] **Reproductor de previews** (Deezer 30 s) als detall de
      cançó. Si s'afegeix, l'event `play_preview` ja és a
      l'allowlist.
- [ ] Valorar correu @topquaranta.cat: avui Sprint G va concloure
      "stay on cdmon"; revisitar si el volum d'enviaments puja.
- [ ] **Stalwart polish** (post Sprint I bis):
  - [ ] Habilitar port 587 STARTTLS submission (ara només 465 SMTPS).
        Útil per a clients mòbils que no accepten SMTPS implicit.
  - [ ] Crear alias `postmaster@topquaranta.cat` per a rebre els
        reports DMARC (`rua=mailto:postmaster@…`). El build OSS de
        Stalwart 0.16.1 actual no exposa `/api/principal*`; el camí
        és (a) servir el webadmin OSS (`stalwartlabs/webadmin`
        v0.1.37) afegint un `handle /webadmin/*` a Caddy o (b) parar
        el servei un moment i usar `stalwart -c … -o` (store
        console). Mentrestant, **quick-fix**: canviar `rua` del
        DMARC TXT a `admin@topquaranta.cat` (que ja existeix), via
        `dns-backup/cdmon_clean.py`-style script.
  - [ ] Integrar parsejat de DMARC reports al panell staff (gràfic de
        què passa SPF/DKIM en nom nostre + alertes de potencial
        spoofing). Alternativa: subscriure'ns a [dmarcian.com](https://dmarcian.com)
        free tier i delegar el parseig.
- [ ] **Gmail avatar** per `info@`/`admin@` quan se reseti el límit
      del telèfon (ara només `miquel@` té Google Account associat).
- [ ] (Quan Hetzner ens desbloca port 25 outbound) considerar treure
      els relays Brevo/Resend i fer entrega directa des de Stalwart.
      Implica warm-up d'IP de 4-8 setmanes + maintenance més pesat.

> **Sprint K — Capa editorial pública**: descartat. La intenció
> original (donar entrada clara a un visitant nou) la va cobrir
> Sprint H + `/com-funciona` + el redisseny editorial dels Sprints
> I bis i J bis.

---

### 5. Backlog: deute tècnic detectat 2026-05-11

Auditoria d'higiene del 2026-05-11. Baixa prioritat; un sol PR per
ítem o agrupats per àrea quan se'n decideixi atacar.

- [ ] **Frontend palette literals** (auditoria C2.3): hex codes
      hardcoded en lloc de `var(--color-tq-*)` a
      `StaffAnalyticsPage.jsx`, `MapaPage.jsx`,
      `TopBreakdownPanel.jsx`, `FilterPanel.jsx`, `Alert.jsx`,
      `CancoPage.jsx::TERRITORI_COLORS`. Recharts no admet `var()`
      directament; cal un `palette.js` central que exporti els
      tokens com a JS strings.
- [ ] **Business-policy `timedelta(days=…)` windows** (auditoria
      C1.1): 11+ punts amb significat semàntic (cooldowns album,
      finestres novetat/senyal/sitemap) escampats per
      `obtenir_novetats.py`, `algorisme.py`, `calcular_top.py`,
      `canco_views.py`, `sitemaps.py`. Centralitzar com
      `ALBUM_RECHECK_*`, `SENYAL_WINDOW_DAYS`, `NOVETAT_DAYS` a
      `music/constants.py`.
- [ ] **MusicBrainz rate constants** (auditoria C1.3):
      `RATE_LIMIT_SLEEP = 1.05` i `MAX_RETRIES = 3` viuen a
      `ingesta/clients/musicbrainz.py:27-28`; Deezer i Last.fm ja
      consumeixen les constants compartides. Afegir
      `MUSICBRAINZ_RATE_LIMIT` a `music/constants.py`.
- [ ] **Mòduls >900 LOC candidats a split** (auditoria C3):
      `music/models.py` (1311), `social/renderer.py` (1122),
      `web/api/staff/artistes.py` (961), `web/api/staff/estat.py`
      (920), `ingesta/management/commands/obtenir_novetats.py`
      (601). Cap és urgent; el split és ergonòmic, no funcional.

---

### 6. Backlog: deute tècnic detectat 2026-05-15

- [ ] **Sweep d'exception swallowing als management commands**:
      revisar tots els commands a `*/management/commands/*.py` per
      a patrons `try/except + return` que swallowen errors. Casos
      detectats fins ara: `tq-restore-test` (PR #17, fixat),
      `recollir_metrics_gsc` (PR següent, fixat). Hipòtesi: hi ha
      més. `tq-health` no els detecta perquè `tq-run` veu exit 0.
      Fer: `grep -rn "except Exception" --include="*.py"
      management/commands/` i revisar cada match per veure si el
      bloc fa `return` (swallow) o `raise` (propaga).

---

## Sprints — completats

### Sprint — Fase 4 PR 1: motor narratiu social (library) ✅ (2026-05-18)

Auditoria narrativa del 2026-05-18 va detectar el core 5-patrons
"sempre fires" als tops setmanals (A1/A2, A4, A5, A6, A7) i el banc
mínim per a copy variat sense repetir-se.

Aquest PR és **library work**; integració amb `captions.py` ha
seguit en PRs posteriors. **Estat actual (2026-05-21):** el motor
està WIREJAT a `captions.compose_for_channel` per a tipus
`top_ppcc`/`top_territorial` i expandit a **8 detectors** (a1-a8 +
fallback). Vegeu `docs/architecture/social.md` per a l'estat
canònic i `docs/post-mortems/2026-05-20-narrative-engine-collapsed.md`
per a les regressions detectades (IG `@handle` perdut a la nova path,
`#N` posicionals parsejats com a hashtags clicables).

* **`social/narrative/scenarios.py`**: 3 detectors universals sobre
  `TopSetmanal` — A2 (streak al #1), A4 (debut a ≤#3), A5 (artista
  amb 3+ cançons). Retornen `Scenario(code, severity, data)`.

* **`social/narrative/phrases.py`**: 45 plantilles (15 per escenari)
  × 3 longituds (short/medium/long). En català, colloquial, 1-2
  emojis. Plus `TERRITORY_HASHTAGS` per territori.

* **`social/narrative/registry.py`**: anti-repetició backed by
  nou model `social.NarrativePhraseUsage` (migration 0006). Filter
  per channel + territori en finestra de N setmanes. Fallback a la
  llista completa si tot exhaurit (post mai bloquejat).

* **`social/narrative/composers/`**: un fitxer per xarxa amb la
  signature comuna `compose(scenarios, entries, *, territori,
  setmana, rng=None) -> {text, hashtags, cta}`. Cada un aplica el
  seu pressupost de chars i la convenció de menció (`@handle` només
  a Instagram).

* **17 tests** a `social/tests/test_narrative.py` cobrint: detectors
  amb fixtures realistes (La Fúmiga 4 setmanes, Maria Jaume 5
  cançons), invariants del banc (3 longituds, interpolació sense
  KeyError), pressupostos de chars per composer, registry cycle
  (mark/filter/exhaustion/aïllament).

### Sprint — Quick Win: Deezer image sizing per slot ✅ (2026-05-18)

Resposta al PSI report del 2026-05-16: LCP 5.4 s amb 4.2 MiB
d'imatges Deezer 1000×1000 servides a slots de 40×40 i 176×176.

* **`web-react/src/lib/img.js::deezerImg(url, size)`**: utility
  pura que reescriu el segment `WxH` de l'URL del CDN Deezer al
  moment de consum. Pass-through per a URLs no-Deezer, null, o
  empty. Cap canvi al backend ni al model — `Album.imatge_url`
  segueix sent l'URL canònica 1000×1000.

* **Verificació empírica del CDN**: Deezer accepta arbitrari
  `WxH` fins a ~1400 (sizes 56, 80, 120, 250, 500, 1000, 1400
  retornen 200; 2000 retorna 403). Decisió: usar 120 / 250 / 500
  / 1000 segons slot.

* **14 slots tocats** a HomePage, TopPage, ArtistaPage, AlbumPage,
  CancoPage, ArtistesPage, MapaPage, StaffAlbumsPage,
  AlbumEditPage. Renderer social (1080×1080 IG feed,
  1080×1920 stories) **manté 1000** — té sentit a aquesta mida.

* **Tests**: `web-react/src/lib/img.test.js` (5 tests vitest) bloca
  el contracte: rewrite del segment, pass-through, defaults.

* **Estalvi estimat**: ≈4 MiB per pàgina pública (LCP/payload
  primer cop). PSI re-corregut post-deploy.

### Sprint — Fase 2: vista d'artistes sense Instagram ✅ (2026-05-18)

Pàgina staff dedicada per a omplir manualment `Artista.instagram_url`
sense haver de navegar a la pàgina d'edició completa. Auditoria
del 2026-05-18 va detectar 1836 / 2000 aprovats (91.8 %) sense
Instagram, 75 d'ells amb almenys una aparició al top.

* **Backend** (`web/api/staff/artistes.py::artistes_list`): nova
  flag `?include_n_top=1` activa l'annotation
  `Count("cancons__rankings", distinct=True)` AS `n_top` i la
  retorna a `_artista_card`. Suport per `?sort=-n_top` (desc).
  Cap canvi a `_artista_card` per al cas default — el camp
  `n_top` només apareix quan la flag està activa.

* **Frontend** (nou `StaffArtistesSenseInstagramPage.jsx`):
  pattern clonat de `PendentsPage`. Row amb state local
  `instagramUrl/busy/error`, validació mínima frontend (https +
  instagram.com), submit via `PATCH /api/v1/staff/artistes/<pk>/`.
  Optimistic remove on save. Link extern "Cercar a Google" amb
  query `site:instagram.com "<nom>"` (l'`/explore/search/` de
  IG requereix login el 2026 i no funciona consistentment).

* **Routing + sidebar**: nova route `/staff/artistes/sense-instagram`
  + entry al menú staff sota "Catàleg".

* **Tests**: 2 tests nous a `test_staff_endpoints.py`:
  `include_n_top` opt-in + `sort=-n_top` ordena correctament; el
  filter `instagram=no` retorna només rows amb camp buit.

* **Reutilització**: cap endpoint nou, cap migration. El filter
  `instagram=no` ja existia (auditoria 2026-05-18); l'endpoint
  PATCH `artista_detail` ja accepta `instagram_url` via
  `SOCIAL_LINK_FIELDS`. Cap signal/hook que es trenqui.

### Sprint — Fase 1.5.C: contingut definitiu dels mails + retroactiu ✅ (2026-05-18)

Substitució dels 6 templates placeholder de Fase 1.5.A per contingut
definitiu, més script one-shot per a notificar retroactivament
gestors aprovats abans de l'existència del layer.

* **Templates user-side**:
  - `email_user_solicitud_aprovada.html` — walkthrough complet:
    què pot editar (bio/gènere/percentatge_femení/12 URLs socials),
    què pot fer a la comunitat (publicar, DMs, dashboard,
    contactar staff via «Admin TopQuaranta» al directori), 2 FAQs
    (finestra de 365 dies, Deezer com a font del catàleg).
  - `email_user_solicitud_rebutjada.html` — motiu + convit a
    re-sol·licitar amb més context.
  - Anàleg per a `proposta_aprovada` / `proposta_rebutjada`.
  - `feedback_resolt` — text més calorós.

* **Templates admin-side**: mantinguts minimalistes. Inclouen
  el missatge de l'usuari (`sollicitud_text`, `justificacio`, cos
  del feedback) per a triatge ràpid.

* **`UserArtista.email_aprovacio_at`** (migration 0016): timestamp
  del moment que es dispatch del email d'aprovació. `notify_user_
  solicitud_resolta` el seteja a `aprovada`-send-success.

* **`notificar_gestors_retroactiu`** command: itera UserArtistes
  verificats sense `email_aprovacio_at` i envia el walkthrough.
  Flags `--dry-run` i `--exclude-user-id` (repetible). Idempotent.

* **Tests**: `test_notificar_gestors_retroactiu.py` (7 tests)
  cobreix idempotència, dry-run, exclude, edge cases (no email,
  ja notificat) i render real del template amb dades.

### Sprint — Fase 1.5.A: notification layer + UserArtista audit ✅ (2026-05-17)

Després de l'auditoria del 2026-05-17 sobre què pot fer un gestor
d'artista verificat al lloc. Aquest sprint tanca els bugs estructurals
i posa la base d'email transaccional; el contingut definitiu del
walkthrough arriba a 1.5.C.

* **Bugs estructurals tancats**:
  - `_gestor_check` (i el seu bessó a `auth_views`) ara requereixen
    `verificat=True AND estat='aprovat'`. Abans només mirava
    `verificat`, deixant un foradet quan `solicitud_rebutjar` flipava
    `estat` però no `verificat`.
  - `solicitud_rebutjar` ara també seteja `verificat=False`, accepta
    un `motiu` opcional al body i el desa a `motiu_rebuig`.

* **Camps d'auditoria a `UserArtista`** (migration 0015):
  `aprovat_at`, `aprovat_per`, `motiu_rebuig`. Backfill best-effort
  des de `StaffAuditLog` per als ja-aprovats.

* **`comptes/notifications.py` (nou)**: 6 funcions pairades
  (admin↔user) per als esdeveniments de moderació (sol·licitud
  gestió, proposta artista, feedback). Implementació best-effort:
  errors al sendmail no propaguen. 6 templates placeholder extenent
  `email_base.html` — el contingut definitiu (walkthrough + FAQ) ve
  a Fase 1.5.C.

* **Wire**: 6 call sites existents passen a invocar les funcions
  (`solicitud_crear`, `proposta_crear`, `feedback_crear`,
  `solicitud_toggle`, `solicitud_rebutjar`, `proposta_aprovar`,
  `proposta_rebutjar`, `feedback_resolve`).

* **Tests**: `comptes/tests/test_notifications.py` (10 tests)
  cobreix subject + recipient + validació d'argument + edge case
  "no staff configurat".

### Sprint — Distribució Fase 1: mencions per canal ✅ (2026-05-16)

Investigació del 2026-05-16 va revelar que `caption_short` (Mastodon,
Bluesky, Telegram, Newsletter) renderitzava `@instagram_handle`
literal igual que `caption_top` (Instagram). Només IG autolinka el
handle; als altres canals la sintaxi de menció és diferent
(`@user@instance`, `@user.bsky.social`, ...) i el text apareixia com
una menció trencada.

* **Refactor `social/captions.py`**: `_mention(handle)` →
  `_artist_label(entry, *, use_handle)`. El call site `caption_top` i
  `caption_novetats` passa `use_handle=True` (mode Instagram amb
  `@handle`); `caption_short` passa `use_handle=False` (mode pla,
  només `artista_nom`). Cap canvi a `publicar_canal.py` ni
  `publicar_social.py`.
* **Tests**: `social/tests/test_captions.py` nou amb 4 tests que
  bloquegen la regressió en ambdues direccions.
* **No s'han afegit camps de handle per xarxa al model** (Mastodon /
  Bluesky / Telegram URLs). Decisió: `instagram_url` ja cobreix només
  8.2 % dels aprovats; ampliar a 4 xarxes amb taxa de cobertura
  menor no aporta valor per ara.

### Sprint — Higiene de constants + ghost pages 404 + ops sweep ✅ (2026-05-11)

Sessió combinada de hardcodes, ghost pages SEO i pipeline GHA.

* **Centralització de territoris**: `TERRITORIS_FIXOS`,
  `TERRITORIS_AGREGATS`, `TERRITORIS_OPCIONALS`,
  `TERRITORIS_SITEMAP`, `TERRITORIS_PPCC_SOURCES` viuen a
  `music/constants.py`. `ranking/algorisme.py`, `web/sitemaps.py`,
  `web/api/staff/top.py`, `web/api/canco_views.py` consumeixen.
  `web/seo/meta.py` importa el `TERRITORI_NOMS` canònic amb
  override visitor-facing (`PPCC` → "Global"). SPA: `ArtistaPage`,
  `CancoPage`, `ComunitatDirectoriPage` importen
  `TERRITORI_NOM` d'`editorial.jsx`.

* **`SOCIAL_LINK_FIELDS`**: tupla canònica a `music/constants.py`
  (11 networks, sense Myspace). `Artista.SOCIAL_LINK_FIELDS` i
  `PerfilUsuari.SOCIAL_FIELDS` apunten ara a la mateixa font; les
  `URLField` individuals als models queden intactes.

* **Ghost pages SEO** (PR #18): `/album/<slug>` i `/artista/<slug>`
  retornen 404 quan no hi ha cap cançó verificada activa. Mateix
  filtre als sitemaps (`AlbumsSitemap`, `ArtistesSitemap`) i al
  JSON-LD de `artista_jsonld`. API `album_detail` també alineada.
  410 Gone per a la subdir legacy `/music/*`.

* **GHA deploy pipeline**: commits `64eaefe`, `bcf8a81`. Mac edit
  → push → CI + Deploy SSH a Hetzner que invoca `bin/tq-deploy`.
  `bin/tq-sync-infra` empeny `deploy/*` cap a `/etc/*` de forma
  idempotent (Caddyfile, cron, logrotate, systemd unit).

* **`tq-restore-test` silent-fail** (`e99c369`): SQL stale
  (`ranking_rankingsetmanal` → `ranking_topsetmanal`), ERR trap
  per a deixar status FAIL quan `set -e` aborta, bootstrap del log
  postgres-owned via `tq-sync-infra`. Drift threshold 5 % → 20 %
  perquè el backfill PPCC afegeix ~300 artistes/h.

* **SEO P3 `/com-funciona`** (`d3cf19c`): vista SSR + template +
  meta dedicat. **Last.fm bio fallback** per a `<meta description>`
  i schema.org quan `Artista.bio` és buida (98 % dels artistes
  aprovats afectats).

* **RFC 8058 unsubscribe + rate-limit** (`6940c0e`): header
  `List-Unsubscribe-Post` per a Gmail/Outlook one-click; rate-limit
  als 4 vectors d'abús (auth login, data export, newsletter
  unsubscribe, comunitat publicar).

* **Cron metadata JSON + `/staff/estat` redesign** (`8a52391`,
  `ecde209`, `ada1dbc`): `deploy/cron-meta.json` com a font única
  de descripció humana de cada cron, llegit per la pàgina
  d'estat amb threshold de freqüència i `silenced` flag per
  fallades acceptades.

* **Dependabot sweep**: 4 PRs mergeats (Django 6.0.5 + tres
  google-api libs). 0 vulnerabilitats obertes a Dependabot
  Security.

* **Roadmap drift**: marcats com a `[x]` els ítems Distrib v2
  Lot B/C, Stories CTA 56 → 64, portada novetats +54 px, alt-text
  ric, IG alt; CWV parcial.

Resum d'una pantalla per sprint. Per ordre alfabètic per facilitar
la cerca; les dates al títol indiquen la cronologia real. Per al
detall fi: `git log` per fitxer o pel rang de dates.

### Sprint — Distribució v2 lot A + lot D + Album.label ✅ (2026-05-07)

Refinaments multi-canal i atac al gran problema de la cua staff.

* **Alt-text ric per slide compartit** (`captions.slide_alts`):
  IG/Mastodon/Bluesky/Telegram tots reben labels descriptives
  ("Top setmanal de cançons en català de Catalunya. Posicions 1 a
  10: 1 Tutu Turú de Siderland, 2 Estrelles de Max Navarro, ...")
  en lloc del genèric "Top CAT, posicions 1-10". Handle complet de
  novetats (albums + singles) que abans no es cobria. 5 helpers nous
  + 5 tests de cobertura.

* **Tags IG disperses pel canvas**: el patró (0.5, 0.5)-cluster que
  Meta colapsava en una bombolla central s'ha substituït per Y per
  fila (0.18-0.88) + zigzag X de 3 columnes (0.30/0.50/0.70). Album
  slides ancoren a (0.50, 0.55) sobre la zona del nom de l'artista.
  4 tests.

* **`alt_text` IG**: `upload_carousel_item` + `upload_image` accepten
  ara el camp `alt_text` de Meta (cap 1000ch). Paritat amb Mastodon
  i Bluesky.

* **Story CTA** font 56 → 64 pt per balancejar amb el títol cançó
  redissenyat (80 pt, redesign 2026-05-03).

* **Verificat**: `_feed_novetats_portada` ja tenia +54 px left margin;
  story footer sempre sobre `COLOR_BG` (no toca territoris clars).

* **Lot D — Diferir creació de col·laboradors fins a verificació**
  (atac directe al 76 % de rebuigs `album_incorrecte`):

  - `Canco.contributors_raw` (JSONField) — contributors desconeguts
    de Deezer s'aparquen aquí en lloc de crear Artistas pendents.
  - `obtenir_novetats` + `obtenir_metadata` ara mai creen Artistas
    durant ingesta. Reusen via lookup ArtistaDeezer immediat o
    deferren via `_defer_contributor`.
  - `aprovar_canco` + `aprovar_canco_auto_ml` criden a
    `processar_collaboradors_pendents` que materialitza la llista.
  - Cançons rebutjades mai arriben a aquest path → els seus
    contributors mai es creen com a pendents.
  - 7 tests nous (4 services + 3 ingest).

* **`Album.label`**: Deezer ja ens donava `label` a cada album.get
  i mai el llegíem. Camp afegit (CharField max=200, db_index) i
  capturat tant a `obtenir_metadata._upsert_album` com a
  `obtenir_novetats._create_album`. Útil com a senyal ML futur
  (`same_label_as_approved`, `label_compartit_amb_PPCC`) i com a
  cue de curació staff. ML reentrenament queda pendent.

Migració 0070. Tests: 16 nous, 341 passing total.

### Sprint — Brand-logo robustesa + CI hardening + ops anti-stale-cron ✅ (2026-05-07)

Una sessió curta caçant traps que podrien tornar a passar i ancorant-los
amb tests + docs + CI perquè no es repetissin:

* **Brand-logo: tres traps documentats**. El logo del header
  renderitzava com un blob negre tot i tenir els colors de marca al
  SVG. Causa: el parser HTML preserva l'atribut `style` literal als
  `<path>` injectats via `dangerouslySetInnerHTML` però **no** populeix
  el `.style` property — `getComputedStyle(path).fill` retornava negre
  default. Fix a `TopQuarantaLogo.jsx::promoteStyleToAttributes()`:
  extreu `fill:X` i `stroke:X` de cada style inline i els promociona a
  atributs `fill="X"` / `stroke="X"` natius (que el parser **sí**
  cablefica). Anchorat amb 14 vitest cases a `TopQuarantaLogo.test.js`
  + doc nou `docs/architecture/brand-logo.md` cobrint els tres traps
  (cairosvg missing, parser quirk, mono-substitució flatten). Commits
  `5a29784` + `1c38766`.

* **CI frontend-tests job**: nou job a `.github/workflows/ci.yml` que
  corre `npm ci` + `npm test` (vitest) sobre `web-react/`. Ancora les
  regressions del logo i creix amb la suite SPA. Va requerir
  desacoblar `package-lock.json` del `.gitignore` i commit-lo (224 KB,
  reproducibilitat per `npm ci`). Comentari al `.gitignore` perquè
  ningú el torne a afegir. Commits `0e97be6` + `fcbd375`.

* **Ops anti-stale-cron-migration**: dia 06 el cron MB seguia generant
  `column does not exist` errors **post-migració** perquè un procés
  worker quedava a memòria amb el model vell. Caçat a la sessió. Avui
  he afegit (a) workflow `destructive-migrations` que detecta
  `RemoveField`/`DeleteModel`/`RenameField`/`RenameModel` als nous
  fitxers de migració d'una PR i avisa al GitHub Step Summary
  (non-blocking, soft warning amb pointer a runbook §10); (b) script
  `bin/tq-pre-migrate` per matar crons stale abans d'aplicar. Commit
  `4591236`.

* **`tq-health` email dedup signature-based**: abans enviava email
  cada hora si `overall != 0`. Amb 15 errors històrics MB no resolts
  al log d'errors, el correu sortia sempre. Ara el script hashea el
  resum de la fallada i només mailea quan el hash CANVIA (estat-en-
  state-file `/var/log/topquaranta/status/_health.alert_sig`). En
  recovery (overall=0) esborra el state per reset al pròxim error
  diferent. Vaig purgar també els 15 blocs d'error històric ja
  resolts del log (script Python amb regex). Commit `fcbd375`.

* **Dependabot tancat**: 4 vulnerabilitats GitHub. PR #11 vite
  `8.0.3 → 8.0.11` (3 alerts: 2 high + 1 moderate, tots dev-server
  only — no afecten producció), PR #12 postcss `8.5.8 → 8.5.14` (XSS
  moderate). Squash-merged els dos amb tots els checks verds. `npm
  ci` post-merge confirma `0 vulnerabilities`. Build clean en 2,4 s,
  14/14 tests passing en 646 ms.

* **`StaffAuditLog.ACTION_CHOICES`**: afegits 9 valors que ja
  existien al codi però no a la llista canònica (`artista_sync_mb`,
  `pendent_orphan_merged`, `feedback_resolt`, `usuari_esborrar`,
  `usuari_reenviar_verificacio`, `usuari_enviar_reset_password`,
  `<channel>_publicat` × 4). Migració 0067.

* **Algorithm — extrapolation gate**: `algorisme.py` deixa de fer
  "lifetime extrapolation" quan una Canco recent-verificada té dies
  de senyal-buit; ara només compta senyal observat real. Decisió
  Option A presa pel propietari. Commit `253faf2`.

* **`Canco corregit=True` exclòs del ranking**: `algorisme.py` ara
  filtra `error=False, corregit=False` al pull de senyal. Defensa
  contra contaminació al path err=6 retry quan `_detect_drift`
  flag-eja un artiste mismatched.

* **`ArtistaQuerySet` managers + codi mort**: `.public()`,
  `.pendents()`, `.with_ppcc()`, `.with_mbid()` (13 callsites
  migrats, 6 tests). 9 fitxers buits/placeholder esborrats
  (`ingesta/{pipeline,views,models,tests}.py`,
  `music/{views,tests}.py`, `social/{views,admin}.py`,
  `ranking/tests.py`).

Tests: 0 nous Python (la feina era ops + frontend). 14 nous vitest.
Build SPA verd. CI verd a tots tres últims pushes (frontend-tests +
tests + lint + migrations + destructive-migrations).

### Sprint S — SEO complet (Bloc A + B + C) ✅ (2026-05-06)

Tres commits seqüencials que converteixen el SPA de "5 URLs visibles a Google"
a "~7 320 URLs amb metadata rica + JSON-LD + dynamic OG cards + sitemap-index
+ IndexNow real-time push" — sense tocar ni una línia del bundle de la SPA.

* **Block A** (commit `5b435a4`): nucli SSR-for-bots.
  - `web/seo/` mòdul (`meta.py`, `jsonld.py`, `views.py`, `ogimage.py`).
  - 6 vistes Django pre-renderitzades (homepage, top, artistes, artista,
    album, canco, mapa) amb `@condition` (304 Not Modified), Vary:
    User-Agent stamped, indexability rules (un-approved → 404).
  - Templates HTML self-contained, mirroring the SPA palette via inline
    CSS, JS-disabled friendly.
  - JSON-LD: WebSite + Organization + MusicGroup + MusicAlbum +
    MusicRecording + MusicPlaylist + BreadcrumbList. Tots passen el
    Google Rich Results Test.
  - Dynamic OG image generator (1200×630 PNG amb fonts brand, cached
    per `updated_at`).
  - `Caddyfile` `@bot` matcher per UA + path: routes Googlebot, Mastodon,
    Bluesky, Telegram, WhatsApp, GPTBot, ClaudeBot, PerplexityBot, etc.
    cap a Django; humans van al SPA.
  - Migracions `music/0063` + `0064` per afegir `updated_at`
    `auto_now=True` amb backfill intel·ligent (Coalesce mb_last_sync /
    last_album_check / created_at).

* **Block B** (commit `930fa56`): discovery layer.
  - Sitemap-index propi (`/sitemap.xml`) referenciant 9 sub-sitemaps:
    static, artistes (1 979), albums (2 212), cançons (3 028),
    territoris, territoris_landing, comarques (61 auto), decades (6
    auto), top_historic (14 setmanes). Total: ~7 320 URLs.
  - `web/seo/indexnow.py`: protocol IndexNow per Bing/Yandex/consortium.
    Cada `aprovar_artista` / `aprovar_canco` dispara un push real-time;
    le quedem anuncïe al moment, no al sitemap recrawl.
  - Verification key file servit a `/<KEY>.txt` via TemplateView.
  - `react-helmet-async` cablejat al SPA: `<SeoHead entity slug>` mounted
    a les 7 pàgines públiques (Home, Top, Artistes, Artista, Album,
    Cançó, Mapa). Llegeix `/api/v1/seo/<entity>/<slug>/` per garantir
    paritat amb el SSR. Cap drift entre humans i bots.

* **Block C** (commit `18b65a6`): long-tail surface.
  - 4 noves rutes SSR: `/top/<territori>/setmana/<YYYY-WW>`,
    `/territori/<codi>`, `/comarca/<slug>`, `/decada/<XXX0>`.
  - Thin-page guards: comarca amb <3 artistes 404; dècada amb <5
    cançons 404; tot historic sense data 404. Sense pàgines buides al
    crawl.
  - 3 sub-sitemaps generats automàticament (territoris_landing,
    comarques, decades) amb els mateixos thresholds.
  - `docs/architecture/seo.md` (nou): 200 línies de referència
    arquitectural cobrint dynamic rendering rationale, mòduls,
    indexability rules, JSON-LD coverage, OG images, SPA Helmet parity,
    edge cases (Vary, 304, 404 vs 410), testing, Bloc D backlog.

Tests: 19 nous (per-entity titles únics, JSON-LD parses, indexability
404s, Helmet API match, hreflang ca, long-tail thin guards, sitemap-
index, IndexNow key file). Full suite **269 passing**.

Smoke real:
  - `curl -A Googlebot https://www.topquaranta.cat/artista/rosalia` →
    título "Rosalía — Música en català · TopQuaranta", MusicGroup
    JSON-LD amb 5 albums + 1 track + sameAs a MB/Insta/YouTube.
  - `curl -A Mozilla` mateix URL → SPA shell + Helmet pulla la mateixa
    metadata client-side.
  - `/sitemap.xml` → sitemap-index amb 9 seccions; cada subsitemap té
    real lastmod.
  - `/territori/CAT`, `/decada/2020`, `/top/CAT/setmana/2026-W17` tots
    serveixen rich HTML amb breadcrumbs + JSON-LD.
  - `/og/artista/rosalia` → 200 image/png 1200×630 generat on-the-fly.

### Sprint K — Suite analytics ètica completa + SPA wiring + UTM ✅ (2026-05-04)

Quatre commits seqüencials (K1-K4) + GoAccess + un fix de
soroll, una sola sessió de ~3 h. Suite construïda des de zero
respectant els constraints del manifest: cap PII, cap tracker
de tercers, cap fingerprint.

* **K1 fonament**: app `analytics/` amb dos models
  (`MetricaEsdeveniment` per a counters, `MetricaPipeline` per a
  gauges diaris), helper `events.register()` atòmic via `F()` +
  retry sobre `IntegrityError`, middleware Django per a pageviews
  + UTM landings, endpoints públics
  `POST /api/v1/analytics/{pageview,event}/` per a la SPA (que
  no passa per Django) amb allowlist tancada de claus, `register()`
  cablejat a registre/proposta/sol·licitud/feedback/social_publicat,
  cron `snapshot_pipeline` 23:00 amb 15 gauges, endpoint
  `/api/v1/staff/analytics/summary/` que torna tot el payload.
* **K2 ingesta social**: `MetricaSocialPost` i
  `MetricaSocialPlatform`. Cada client (`mastodon`, `bluesky`,
  `instagram`, `telegram`) guanya `get_post_metrics()` +
  `get_account_stats()`. Cron `recollir_metrics_social` 22:30
  amb `SingletonLock` i fail-open per plataforma. Smoke real al
  primer dia: IG 745 followers, top post 12 likes / 1 share /
  157 reach. Telegram per-post documentat com a "Bot API doesn't
  expose channel views" (limitació de Telegram, no nostra).
* **K3 UI**: `/staff/analytics` amb 5 pestanyes (Resum, Pipeline,
  Social, Web, Cohorts) — totes derivades d'una sola crida + chunk
  lazy de 14.7 KB gz. Window selector 7d/30d/90d/1a, deltes
  half-vs-half, insights automàtics, CSV export client-side al top
  posts/pageviews/UTM. **Bonus**: `/staff` (panell) reorganitzat
  amb les mateixes 8 seccions que la barra lateral
  (Visió general · Cua del dia · Catàleg · Top · Comunitat ·
  Distribució · Diagnòstic · Sistema).
* **K4 ops**: digest setmanal als admins (cada dilluns 08:00)
  amb KPIs vs setmana anterior, top 5 pàgines, top 5 fonts UTM,
  top 3 posts, snapshot del catàleg.
  `docs/architecture/analytics.md` amb la referència completa.
  `/legal/privacitat` amb una nova secció «Mètriques agregades»
  que detalla què comptem i què no. **Fix portabilitat**:
  substituït `.distinct("col")` (Postgres-only) per dedup
  Python `dict.setdefault` perquè els tests SQLite passin.
* **GoAccess (opció B)**: `apt install goaccess` + ACL Caddy
  logs perquè `topquaranta` user els puga llegir; comand
  `generar_goaccess` que converteix Caddy JSON → CLF amb un
  preprocessor Python (més portable que llegir JSON natiu) i
  produeix `/var/cache/topquaranta/goaccess/report.html`. Endpoint
  `GET /api/v1/staff/analytics/goaccess/` proxia l'HTML darrere
  `IsStaff` (sessió + 2FA) — el fitxer no és accessible
  públicament. Cron 23:30 cada nit. SPA: targeta nova al top de
  la pestanya **Web** amb botó «Obrir informe →».
* **Soroll fix**: `recollir_metrics_social` baixa de
  `logger.exception` (ERROR) a `logger.warning` per a hiccups
  d'API tercers. Resol l'email watchdog de tq-health que mostrava
  un fals "Django errors today: 1" persistent fins a mitjanit.
* **UTM al renderer social** (commit `296411e`): nou
  `social.captions.utm_url(channel, tipus, setmana, *, base,
  territori)` com a font única de la convenció. Cada `caption_short`
  rep `channel=` i el footer del post a Mastodon, Bluesky, Telegram
  i el CTA HTML del newsletter passen de `https://topquaranta.cat`
  nu a `https://topquaranta.cat/?utm_source=<canal>&utm_medium=
  social&utm_campaign=<tipus>-<YYYY>-w<WW>[-<territ>]`. El
  newsletter usa `utm_medium=email`. La pestanya Web del dashboard
  ara s'omplirà gradualment amb una taula real per (font,
  campanya) en compte d'una sola fila residual.
* **SPA beacon wiring** (commit `bd71d38`): `lib/analytics.js`
  amb `trackPageview` + `trackEvent` via `navigator.sendBeacon`
  (sobreviu a unloads, no bloca clics). Cablejat:
  `spa_route_view` global via `RouteAnalytics` listener,
  `escolta_click` a cada pill d'`ExternalListenLinks` (dim1=dsp,
  dim2=surface), `search_query` + `directori_filter` a
  `ArtistesPage`, `mapa_zoom` a cada drill-down de `MapaPage`,
  `newsletter_signup` a `ComptePerfilPage` en transició False→True
  (no fa doble-comptatge amb `registre_complet`). `share_click` i
  `play_preview` queden dormants a l'allowlist fins que la UI
  tinga els botons.

Tests: +27 a la suite (events helper, middleware, snapshot,
ingest, recollir social, digest). Total **243 passed**.

Tot el codi al `git log` 2026-05-04: commits `e8b5086` (K1),
`504c226` (K2), `c2d267f` (K3), `137d8dc` (K4), `4abf2ef`
(GoAccess + soroll).

### Sprint — Python 3.10 → 3.12 + Django 5.2 → 6.0 + scikit-learn 1.8 ✅ (2026-05-04)

Bumpat tot l'stack en una passada. Treball preparatori després de
descobrir que múltiples PRs Dependabot estaven blocats per la
versió antiga de Python.

* `.venv-py312-new` creat en paral·lel, `pip install -r requirements.txt`
  amb Django 6.0.4, scikit-learn 1.8, totes les altres deps al
  major actual. `pytest` sencer verd.
* Swap calent: `mv .venv .venv-py310-old && mv .venv-py312-new .venv`,
  `systemctl reload topquaranta-web` (gracefulwww), 0 segons de
  downtime. Reload de cron (`tq-run` apunta al venv via shebang).
* Fix collateral: 45 shebangs trencats al binari de `pip` interns
  després del rename → `sed` per actualitzar-los tots a `.venv/bin/`.
  Causa: el `mv` no actualitza els shebangs absoluts dels scripts
  generats per `pip install`.
* Regressions caçades i fixades: `ADMINS = [("name", "addr")]` ja
  no és vàlid a Django 7; canviat a `ADMINS = ["addr"]` (avisos
  RemovedInDjango70Warning silenciats). `datetime.utcnow()` deprecat
  a 3.12 — auditat, només dues ocurrències al codi de tests.
* CI workflow al `.github/workflows/ci.yml` també passat a 3.12.

Va anar acompanyat de drenar el backlog acumulat: refactors de
`compte_views`, `comunitat_views`, `staff/social` (tots 3 dividits
en subpaquets), index nou a `UserArtista`, ML retrain post-3.12,
i la disk-cleanup que va passar el sistema de 99% a 77% (purge de
`pip cache`).

Commits: `791e83b`, `ee3eade`, `1edb12a`, `e4e2825`, `c586209`.

### Sprint — APECAT cross-check + ingest robustness + social v3 ✅ (2026-05-03)

Sessió llarga arrencada per un cross-check del Top APECAT (rànquing
mensual de cançons en català més radiades, BMAT) contra el nostre
pipeline. Auditats 5 PDFs (anual 2025 + gener-abril 2026) ↔ 71
cançons úniques i 55 artistes. Va destapar tres classes de bug que
s'arrossegaven sense que `tq-health` les detectés.

**1. Ingest robustness (3 fixes a `obtenir_novetats` + `obtenir_metadata`)**

* **D5 self-collab**: `_create_track` i `_upsert_track` comparaven
  un contributor de Deezer contra `artista.deezer_id_principal` (un
  sol id). Quan un artista té múltiples perfils Deezer (autoedit +
  label, e.g. Àlex Pérez 121440332 + 1479910), Deezer pot retornar
  l'alternat com a contributor; el codi l'afegia a `artistes_col` →
  signal D5 `ValidationError` → cron mort. Comparem ara contra
  `set(artista.deezer_ids.values_list("deezer_id", flat=True))`.
  Hourly cron havia estat petant des del 2026-05-02 21:15 amb
  aquesta traça.
* **ISRC collision skip**: `obtenir_metadata._upsert_track`
  arrastrava la transacció sencera quan trobava un track amb un
  ISRC ja existent (single re-editat dins d'un LP, o un featuring
  llistat sota dos contributors). Capturem ara `IntegrityError`,
  log "ISRC collision skipped: …", `return False` per a continuar.
  Confirmat en Ginestà / Sexenni / Sr. Chen / Nil Moliner — totes
  són la mateixa gravació apareixent sota deezer_ids diferents,
  mai duplicats reals.
* **Multi-Deezer-ID per artista**: `_fetch_for_artist` només
  iterava `deezer_id_principal`. Catàlegs sencers d'artistes amb
  perfils múltiples (Àlex Pérez segell Música Global) eren
  invisibles. Ara loop a tots els `ArtistaDeezer` ordenats
  `principal-first`.

**2. P2 redesign (`obtenir_novetats`)**

L'antic gate `cancons_obtingudes=False` + el shortcut `album_old`
marcaven un àlbum OK quan Deezer retornava qualsevol llista de
tracks (inclosa una llista buida per fluctuació transitòria) si
l'àlbum tenia >30 dies. **Resultat: 3.679 àlbums "fantasma"**
marcats com a fets a la BD però amb 0 cançons associades, perquè
flake o quota_exhausted al moment equivocat es feia passar per
"no tracks".

Nou disseny: cada àlbum no descartat amb `deezer_id` es re-revisa
periòdicament. Cooldown segons edat:
| Edat (data_llançament) | Re-check cada |
|---|---|
| <30 dies | 24 h |
| 30-365 dies | 7 dies |
| >365 dies o sense data | 30 dies |

`Album.last_album_check` (DateTimeField, indexat). `NULL` = mai
revisat → màxima prioritat → els 3.679 fantasmes drenen
automàticament en ~6-7 hores. `descartat=True` és l'única exclusió
permanent. `cancons_obtingudes` queda com a camp deprecat.
Idempotència preservada pel dedup intern de `_create_track`
(`deezer_id` + ISRC). Migració `music 0060`.

**3. Social v3 — paritat multi-canal**

* **Carrusel a Bluesky + Mastodon**: ara publiquen 4 imatges
  (portada + 3 primers slides de llista via `embed.images` /
  `media_ids[]`) en lloc de només la portada. Per-slide alt text
  indicant rang de posicions. Es manté el 1024-char carrusel a
  Telegram via media-group.
* **Esborrar remot real per a tots els canals**: nou endpoint
  `/api/v1/staff/social/eliminar-remot/` que dispatcha per
  `post.platform`. Implementacions: `mastodon_client.delete_status`
  (`DELETE /api/v1/statuses/:id`), `bluesky_client.delete_post`
  (parsa AT URI → `com.atproto.repo.deleteRecord`),
  `telegram_client.delete_messages` + nou `send_media_group_full`
  per capturar tots els `message_ids` de la media-group al moment
  de publicar (Telegram no té delete-de-grup, cal id per id).
  Endpoint legacy `eliminar-instagram` es manté per back-compat.
* **Staff `/staff/social`**: columna **Data** primer (per
  `published_at` nulls-last), Setmana N segona; sort per data; tints
  per plataforma (IG rosa, Mastodon indigo, Bluesky cel, Telegram
  cian, newsletter ambre, RSS taronja); botó "Esborrar" amb label
  per plataforma.
* **Renderer readability v3** (post feedback iteratiu):
  * Posts list slide: número posició 38 → 54 pt, títol 28 → 40 pt;
    pastilla i alt-de-fila *intactes* (76 / 105) perquè el page
    indicator no es solapi. El guany visual ve del padding superior
    a 0 dins la cel·la.
  * Posts portada: logo + Setmana pills mogudes x=30 → x=84
    (+54 px = 5 % FEED_W); mantenim alineació esquerra. Aplicat
    a `_feed_portada` i `_feed_novetats_portada`.
  * Story canço: títol 44 → 80 pt (line-height 90), artista 34 → 44
    pt; nou peu "topquaranta.cat" a `STORY_H-90` en
    `COLOR_TEXT_MUTED` (4.5:1 sobre ink → AA).

**4. Comptes**

* **Newsletter opt-in al perfil** (`/compte/perfil`): backend
  `compte_views.perfil` GET exposa `vol_newsletter`, PATCH l'accepta,
  i en False→True estampa `consent_newsletter_at` (RGPD).
  Frontend amb checkbox + helper copy entre username i password.
* **Fix urgent `/api/v1/staff/usuaris/<pk>/`**: petava amb
  `NameError: name '_proposta_row' is not defined`. Imports oblidats
  després de la refactorització Sprint C. Importats des dels seus
  mòduls extrets.
* **Fix typografia**: barra esquerra staff "Panel" → "Panell".
* **Header "Distribució — Instagram" → "Distribució multi-canal"**
  al panell + targeta del dashboard.

Tests: 211 passing, 8 skipped (eren 207 pre-sprint).

### Sprint — Last.fm aliases + cron watchdog ✅ (2026-05-01)

Triga d'una sola sessió arran del cas «Delên» que reportes l'usuari:
mateix artista escrobllejat sota múltiples grafies a Last.fm
(diacrítics, apòstrof tipogràfic vs ASCII, capitalització) → la
senyal queda fragmentada en pàgines separades. Audit a
`scripts/lastfm_alias_audit.py` va trobar 35 (1,8 %) afectats; els
casos més greus perdent el 87-99 % de plays (Boira, Sabor de
Gràcia, Bèrnia, Efímer).

* **Models nous**:
  `ArtistaLastfmAlias(artista, nom, confirmat, rebutjat,
  playcount_canonical, playcount_variant, top_tracks_overlap)` —
  variants ortogràfiques que sumen al senyal quan estan
  confirmades. `ArtistaLastfmSimilar(source, target, last_seen,
  match)` — row-per-recommendation que substitueix l'antic
  comptador integer de `nb_similars_lastfm` (ara cache
  recomputada). Migracions `0057`, `0058`, `0059`.
* **Cron `obtenir_metadata_lastfm`** reescrit perquè:
  - resolgui similars de manera alias-aware (alias-of-approved
    bat un pendent literal),
  - dedupliqui variants per source,
  - reemplaci wholesale les rows de cada source (idempotent).
* **Cron `obtenir_senyal`** suma playcounts/listeners dels alies
  confirmats per a cada cançó, amb una salvaguarda contra el
  case-fold silenciós de Last.fm (autocorrect=0 NO impedeix el
  fold cap a la canònica; comparem la URL retornada amb la
  canònica i descartem si col·lapsa).
* **Comanda `detectar_lastfm_aliases`** com a port net del script
  inicial. Filtre top-tracks ≥50 % per evitar homònims; comparació
  de URL normalitzada (sense `+noredirect/`) per evitar
  case-fold false positives. Re-runnable.
* **Auto-absorbència de pendents duplicats**: en confirmar un
  alies (o afegir-ne un manualment), el sistema busca pendents
  amb el mateix nom literal, font_descoberta=lastfm_similar,
  sense cançons / Deezer / territoris / collabs, i els absorbeix
  cap al canònic (redirigint similar rows que poden col·lidir per
  unique(source, target)). Comanda one-shot
  `netejar_duplicats_lastfm` per al backfill.
* **UI staff**: nova `LastfmAliasesCard` a
  `/staff/artistes/<pk>` aparellada amb el `LastfmPanel`
  (esquerra editable + dreta info), patró equivalent al del
  MusicBrainz. Filtre nou `lastfm_alias=pendents/confirmats/
  rebutjats` a `/staff/artistes` + pills informatives a la llista.
* **Watchdog `tq-health`** schedulat per primera vegada (cron
  cada hora xx:15 amb `--email-on-fail`). En engegar-lo va
  destapar el bug del lock-skip que ens havia deixat 12 dies
  sense ingestió real de novetats. Refactoritzada la lògica de
  `tq-run` perquè exit-75 (lock contention) no actualitzi
  `last_run`; nou helper `music.locks.SingletonLock`. Panel
  `/staff/estat` ara mostra freqüència + llindar de cada cron i
  pill colored per estat (OK / SKIP / STUCK / STALE / FAIL +
  silenced flag).

Tests: 207 passing post-sprint, 8 skipped (eren 187 pre-sprint).
Auditoria a11y axe-core 0 violacions a les 17 pàgines staff.

### Sprint A — Tancar deute acumulat ✅ (2026-04-25)

Drop columnes mortes + renames + constants a config. Migracions
`ranking 0012` (drop `dies_en_top`, rename `lastfm_playcount` →
`escoltes_setmanals`); `PPCC_PENALITZACIO_PER_POSICIO` mogut a
`ConfiguracioGlobal`; magic numbers ML → `music/constants.py`.

### Sprint B — Whisper milestone + reentrenament ML ✅ (2026-04-25)

Backfill Whisper LID complet sobre la cua. Reentrenament RF amb
4 features Whisper noves (top-7 d'importància). 5-fold CV ROC-AUC
0.9994. A/B TF-IDF 60→30 max_features adoptat.

### Sprint C — Robustesa `staff_views` + tests ✅ (2026-04-25)

Split del `staff_views.py` monolític (3.330 línies) en 16 mòduls per
àrea sota `web/api/staff/`. Backward-compat shim a `staff_views.py`.
Nous tests (`web/tests/test_staff_endpoints.py`).

### Sprint D — Performance pública ✅ (2026-04-25)

`cache_for_anon` + ETag + Last-Modified als endpoints públics
(`/top`, `/artistes`, `/mapa/artistes-top`). LocMem `pagecache` per
worker. ~30× speedup en hits anònims; 304 ràpids per re-fetches.

### Sprint E — Transparència algorítmica pública ✅ (2026-04-25)

Nou `TopBreakdownPanel` exposant `age_factor`, `past_top_factor`,
`monopoli_factor` per cançó al `/canco/<slug>` i a la `CancoEditPage`.
Migració `ranking 0011`.

### Sprint F — Accessibilitat i mobile ✅ (2026-04-26)

Skip-to-content + `:focus-visible` global + landmarks correctes.
Auditoria axe-core sobre 6 pàgines: 4 violacions detectades, totes
corregides. Re-auditoria 0 violacions a 6 URLs.

### Sprint G — Gestors d'artista i correu ✅ (2026-04-26)

Bloc 1: nou camp `Artista.bio` + endpoint `PATCH /api/v1/compte/
artista/<pk>/editar/` per a `UserArtista.verificat=True`. Audit row
només quan canvia algun camp. Migracions `music 0052` + `0053`.
Bloc 2: anàlisi Hetzner Hosted Mail vs cdmon — recomanació "stay on
cdmon" (només +25 €/any d'estalvi vs cost del cutover).

### Sprint H — Comunicació del producte + onboarding ✅ (2026-04-26)

Hero + 3 blocs + CTA a HomePage; intros discrets a `/top`, `/mapa`,
`/comunitat`, `/comunitat/directori`; targeta amb 3 punts a
`/onboarding`; nova pàgina `/com-funciona` (6 seccions divulgatives);
ComptePage reestructurada amb guiatges contextuals.

### Sprint I bis — Redisseny editorial de la HomePage ✅ (2026-04-26)

Reescriptura completa: 10 seccions verticals amb bandes alternants
ink/blanc, Playfair, kicker tone-aware. Endpoints nous: `/api/v1/
stats/`, `/top/canco-destacada/`, `/artistes/destacat/`,
`/artistes/descoberta/`, `/albums/`. Rotació territori en focus,
compte enrere amb segons + "X cançons noves", notícies en 2 cols
pública/interna amb extracció d'imatge des del markdown.

### Sprint J bis — Redisseny editorial `/top` `/artistes` `/mapa` `/comunitat` ✅ (2026-04-26)

Aplicat el llenguatge editorial a totes les pàgines públiques.
Extreta primitiva compartida `web-react/src/components/editorial.jsx`
(`Section` / `SectionHeader` / `TerritoriBadge` / `TrendCue` +
`TERR_COLORS` + `TERRITORI_NOM` amb PPCC → "Global"). `/top` amb
navegador setmanal (prev/next), nous camps `prev_setmana`/
`next_setmana` a `/api/v1/top/`. Llenguatge intern eliminat de la
UI pública (verificada/aprovat/revisió humana).

### Sprint I — Distribució automàtica a Instagram ✅ (2026-04-26)

App nova `social/` (model `SocialPost` idempotent per
`(platform, tipus, territori, setmana)`); package `ingesta/social/`
amb `colors`, `fonts`, `cover_cache`, `calendari`, `captions`,
`renderer` (PIL, formats 1080×1350 feed + 1080×1920 stories),
`instagram_client` (Graph API v19; mode DRY_RUN automàtic quan
`INSTAGRAM_ACCESS_TOKEN` és buit/`"test"`). Commands
`autoritzar_instagram` (interactiu, code → long-lived 60 dies),
`publicar_social --data --tipus --platform --dry-run --force`,
`renovar_token_instagram`. Calendari amb 5 fases via
`ConfiguracioGlobal.fase_distribucio`: Fase 1 (default) només
dissabte; Fases 2-5 desbloquegen dimecres/dilluns/divendres/dimarts.
Kill switch a `instagram_actiu`. Story cap configurable
`story_max_cancons_ppcc` (1-40). Pàgina staff `/staff/social` amb
preview en viu, force-publicar, controls de fase + kill + token TTL.
Crons al `cron.topquaranta` per als 5 dies + token mensual. Fonts
Playfair + Roboto vendoritzades. Audit action `social_publicat`
afegida (migració `music 0054`). 12 tests nous (153 total).

> **Recordatori operatiu**: Fase 1 al començament. Pujar de fase
> requereix avaluar Insights Instagram durant 4 setmanes —
> llindars documentats al fitxer del sprint o al panell staff.

### Sprint I bis (post) — Redisseny renderer + multi-canal + email ✅ (2026-04-27)

Tres blocs grossos en una sessió:

**1. Redisseny editorial del renderer Instagram.** El primer disseny
era massa fosc + monocrom + esquemàtic. Reescrits els 4 tipus de
slide (top global, top territorial, nous singles, nous àlbums) +
stories (intro, cançó individual, CTA): logo SVG real (substitueix
"Top" + "Quaranta" sintetitzat), icones territorials (`vendor/mm-design/
icons/territories/`) recolorejades dinàmicament, paleta brand
mirrorejada a Python (`TERR_COLORS`), bin-packing dinàmic per a
singles (≤10 → 1 slide, 11–20 → 2 slides equilibrats), pill-system
amb format mm-design (`--mm-radius-lg`), cover full-bleed
(`ImageOps.fit`), eliminació de tot referència a "Països Catalans"
(sensibilitat política). Auto-tag d'artistes a feed posts via
`user_tags` Graph API. Captions en project-week numbering (`Setmana
N`) amb anchor a Sat 2026-04-25 = setmana 34, helper canònic a
`music/dates.py`. Finestra de novetats anclada a la última
publicació del mateix tipus (no "darrers 7 dies fix") per evitar
duplicats entre setmanes consecutives. Staff page amb Preview/
Veure slides/Reset/Esborrar IG buttons + project-week column +
filtre "últims 7 dies" a /staff/cancons.

**2. Distribució multi-canal.** Un sol comandament `publicar_canal
--channel <name>` per als 4 nous canals + el setup d'Instagram
existent. Models singletons per a cada credencial (`MastodonAuth`,
`BlueskyAuth`, `TelegramAuth`); kill switches independents a
`ConfiguracioGlobal.{mastodon,bluesky,telegram,newsletter,rss}_actiu`.
Endpoints staff per gestionar credencials (`/staff/social/{mastodon,
bluesky,telegram}/{,test/,clear/}`). Frontend amb panell unificat de
canals + toggles. RSS Atom 1.0 a `/rss/{top,novetats}.xml` (kill-
switched). Newsletter HTML setmanal via Brevo (utilitza la infra de
consentiment del Sprint J). Crons escalonats: Sat IG 09:30 → Mastodon
09:40 → Bluesky 09:50 → Telegram 09:55 → Newsletter 10:00. 8 tests
nous (160 passing).

**3. Email infrastructure** (necessari per verificar Mastodon/Bluesky/
Telegram, però va créixer molt). Stalwart Mail Server v0.16.1
configurat com a backend IMAP + receptor SMTP per `topquaranta.cat` i
`cercol.team`. TLS Let's Encrypt sincronitzat des de Caddy via
systemd path-watch. **Smarthost routing condicional** (Stalwart →
Brevo per `@topquaranta.cat`, Stalwart → Resend per `@cercol.team`)
configurat al panell amb 2 routes Relay + expressió `sender_domain ==
'cercol.team' ? 'resend-relay' : 'brevo-relay'`. Hetzner Cloud
Firewall configurat via API per obrir 25/465/587/993. CDMON DNS API
integrat (`dns-backup/cdmon_clean.py`): netejada massiva de 18
registres legacy (CDMON Micropla — imap/pop3/smtp/sogo/roundcube/
autodiscover/etc.). Apex A actualitzat de CDMON IP a `188.245.60.20`.
Brevo configurat com a relay outbound (DKIM via 2 CNAMEs `brevo*._
domainkey`, SPF inclou `spf.brevo.com`). Resend pendent de
verificació de domini cercol.team al panell Resend. BIMI publicat
sense VMC (avatar a Yahoo/Fastmail; per Gmail cal Google Account per
adreça). Autoconfig Mozilla Thunderbird a `https://mail.topquaranta.cat/
.well-known/autoconfig/mail/config-v1.1.xml`. Documentació exhaustiva
a `docs/EMAIL.md`.

> **Operativament**: Mastodon i Telegram credencials posades + cron
> actiu. Bluesky pendent de credencials. Newsletter pendent
> d'activació quan hi hagi subscriptors. RSS live ja.

### Sprint J — Privacitat, cookies i corpus legal complet ✅ (2026-04-26)

Paquet legal sencer (no només GDPR): 7 pàgines a `/legal/{avis-legal,
privacitat,cookies,termes,codi-conducta,llicencies,accessibilitat}` +
índex `/legal`. Banner de cookies informatiu (no bloquejant) amb
persistència a localStorage. Registre amb 3 checkboxes (termes
obligatori, edat ≥14 obligatori, newsletter opt-in opcional). Camps
nous a `PerfilUsuari` (`consent_termes_at`/`_versio`,
`vol_newsletter`, `consent_newsletter_at`) — migració `comptes 0013`.
Endpoints `POST /api/v1/compte/exportar-dades/` (RGPD art. 20, envia
JSON per email) i `GET /api/v1/compte/baixa-newsletter/?token=…`
(unsubscribe via signed token, sense login). Botó "Exporta les meves
dades" a `PerfilUsuariPage`. Identitat del titular: CVR 46414683
(Dinamarca), info@topquaranta.cat. Datatilsynet com a lead authority.
0 violacions axe-core a 9 URLs noves. **Esborranys legals; pendent
revisió jurídica humana abans de comunicació externa**.

### Sprint J ter — FilterPanel a `/artistes` + scroll mòbil a taules staff ✅ (2026-04-26)

`StaffTable.Table` ara embolcalla la `<table>` en `overflow-x-auto`
amb `min-w-[640px]` — scroll horitzontal a totes les taules staff
en mòbil. `ArtistesPage` migrada al `FilterPanel` staff (popover
amb badge de comptador).

### Sprint L — Metadata d'artista des de Last.fm ✅ (2026-04-25)

Nou cron `obtenir_metadata_lastfm` (diari 05:00 UTC). Camps nous a
`Artista`: `lastfm_url`, `lastfm_bio_*`, `lastfm_listeners`,
`lastfm_playcount_total`, `lastfm_image_*`, `lastfm_tags` (JSON),
`nb_similars_lastfm`. Migració `music 0050`.

### Sprint M — Naming consolidation: "ranking" → "top" ✅ (2026-04-25)

Renaming massiu UI/codi/migracions/scripts. Models `Ranking*` →
`Top*` amb àlies Python per backward-compat. URLs `/staff/ranking`
mantingudes com Navigate-alias a `/staff/top`. URLs públiques
intactes. Migració `ranking 0013`.

- Image generation (PIL) for ranking posters.
- Telegram / Instagram distribution.

Original assets (TTF fonts, SVG territory logos) were on a local machine
that is no longer accessible. The public website is the distribution
channel instead.

---

## Ground rules for future work

- Never commit without explicit request.
- Update this file at the end of each session.
- Follow the conventions in `CLAUDE.md` §9.
- No new parallel design systems — tokens come from mm-design.
- No raw SQL outside `ranking/algorisme.py` and migrations.
- When in doubt about a decision, check §5 of `CLAUDE.md`.
- Re-run axe-core (`/tmp/axe/run.js`) after touching any public page.
- After deploys: `sudo systemctl reload topquaranta-web` (graceful HUP).
