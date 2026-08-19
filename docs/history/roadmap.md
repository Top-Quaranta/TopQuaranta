# ROADMAP.md — TopQuaranta

> Estat actual i propers passos. El detall fi viu al `git log` i als
> commits per sprint; la història de Phase 9 (auditoria d'excel·lència)
> al fitxer `docs/history/roadmap.md` (sprints A–J ter).
> Last updated: 2026-08-19.

---

## Sprint 2026-08-19 bis — El correu de YouTube reparteix feina

El descobriment automàtic ja ha passat per tot el catàleg (98 % dels
artistes, 0 per provar): el que queda del buit —536 cançons sense cap
vídeo i 155 del punt cec— només el tanca una persona. El correu diari
passa de ser un panell d'estat a repartir **10 recerques al dia** amb la
cerca escrita i l'enllaç al lloc on desar la resposta; ordre: artista
sense cap canal → cançó cega → canal propi d'un artista que ja surt al
top. Perquè hi haja on desar-ho, la fitxa de cançó accepta un vídeo
enganxat (Art Track si no en té, carril extra si ja en té) i un tercer
estat `youtube_revisat` («mirat, no en té») que és el que fa que la cua
es buide en lloc de repetir-se. Correcció al pas: «connectada» ara vol
dir Art Track **o** carril propi, la mateixa regla que fa servir el
mesurador — abans la cobertura era pessimista i la llista demanava
cançons que ja es mesuraven. El correu també separa les files noves per
causa (per YT / pel terra / per ordre) i diu la data d'activació
(26/08) i el primer top oficial que la portarà (29/08) en lloc d'un
compte enrere.

**Pendent d'aquest fil:** decidir amb el provisional del 26/08 a la mà
si cal tocar res; i, si es vol anar a per les 155 del punt cec sense
vídeo, mesurar quantes es resolen de veres a mà abans d'invertir-hi
més matins.

## Sprint 2026-08-19 — Docs: només el que importa

Postura del Miquel: la documentació només diu el que és important; un
canvi toca un doc només si canvia una invariant; l'override de la porta
és el cas normal (75–90 % sa). Executat en 3 PRs (#446, #447, #448):
`docs/architecture/` 24 → 8 docs d'invariants (6.416 → ~800 línies, cada
invariant amb el test que la guarda); ADRs → `DECISIONS.md` (138) i
post-mortems → `LESSONS.md` (129, 40 incidents amb guarda verificada);
runbook fusionat amb infra/EMAIL/ssh-keys/retention/deprecation/
backup-offsite/identities (1.013 → 336, 10 contradiccions resoltes cap
al codi); CLAUDE.md 530 → 209; 65 notes de sessió de l'arrel + audits +
recon + roadmap narratiu + tot el que s'ha absorbit → `docs/archive/`
(140 fitxers, 26.400 línies, fora del mapa i del link-checker).
**Docs vius: 84 fitxers / 17.100 línies (+65 notes / 10.000 a l'arrel)
→ 25 fitxers / 3.100 línies.** Portes iguals (400 dur, sense
grandfathered; mapa 42 → 12 entrades). Política a
`conventions.md` §Documentation.

> Sprints completats i narrats: `docs/archive/sprints/roadmap-sprints-2026-05-to-2026-08.md`.

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
- **Pipeline**: nightly chain documentada a `docs/architecture/ingesta.md`.
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
  Stories territorials (CAT/VAL/BAL) portades a la mateixa estructura
  editorial (Step 3c, 2026-06-04). Detall a
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

> Estratègia documentada el 2026-05-06 a `docs/architecture/web.md`.
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
- [x] ~~**Stalwart polish**~~ — sense objecte des del 2026-08-18: Stalwart s'ha retirat i les bústies han passat a Purelymail. Vegeu `docs/ops/runbook.md (mail)`.
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

