# Backlog complet — TopQuaranta · inventari 2026-06-13

> **Recon NOMÉS-LECTURA.** Inventari fiable de tot el pendent, extret de la
> font de veritat (codi, repo, docs, notes), no de memòria. Cap canvi al
> codi, cap branca creada. L'únic fitxer escrit és aquest informe.
>
> **Sense priorització** — l'ordre és per font de recollida i, dins de
> cada item, s'etiqueta `[categoria · risc]`. La priorització la fa Miquel.
>
> Categories: `producte` · `dades` · `scoring` · `tècnic` · `seguretat` ·
> `neteja` · `docs`. Risc/cost: `baix` · `mitjà` · `alt`.
> Estat: **VIU** (treball obert real) · **STALE** (sembla ja resolt/obsolet,
> el comentari/nota no es va actualitzar) · **PER-DECISIÓ** (depèn d'una
> decisió de producte de Miquel, no és feina d'enginyeria pendent).

---

## Resum executiu (recompte)

- **Issues GitHub obertes:** 0. **PRs oberts/draft:** 0. **Milestones:** cap.
- **Branques remotes amb feina NO mergejada:** **2** (`redisseny-tail`,
  `feat/routine-esborrany-setmana`). La resta (~74) són squash-merged sense
  podar → neteja.
- **Alertes Dependabot obertes:** **1** (severitat *low*: `torch`). Cap branca
  de bump de dependència oberta (totes mergejades i podades).
- **Marcadors de codi genuïns VIUS:** 3 (+1 STALE, +1 parcial).
- **Codi mort d'alta confiança:** 2 blocs (tots dos al SPA React).
- **Residu obert a docs + notes:** extens (vegeu §4) — la major part és
  diagnòstic read-only i decisions de producte, no bugs en viu.
- **Regressió en viu a prod:** `/mapa` mòbil PSI (pendent 2a lectura cron).

---

## 1. CODE — marcadors als comentaris i docstrings

Cercat `TODO/FIXME/XXX/HACK` + `pendent/de moment/provisional/per fer/future
work/workaround` a `.py` i `.js/.jsx`, excloent tests, migracions, node_modules,
dist, .venv. **Cap marcador literal `TODO/FIXME/XXX/HACK`** real al codi de
producció (els únics substrings són placeholders d'exemple: `AQXXXXX`,
`fill:#XXX`, `/decada/<XXX0>`, la constant `MASTODON`). Marcadors genuïns:

### VIUS

| Item | On viu | Categoria · Risc |
|---|---|---|
| `monopoli_artista_pct` està fixat a `0.0`; separar penalització àlbum vs artista requereix re-córrer el pas per-track. "left as future work". | `web/api/canco_views.py:205` | `scoring` · baix |
| Forat NULL `data_llancament`: `netejar_caducades` salta els NULL, així que cançons amb data buida s'acumulen a la cua d'staff indefinidament. Reconegut com a follow-up obert. | `ingesta/caducitat.py:35` | `dades` · mitjà |
| El cos de publicacions de comunitat es renderitza com a `pre-wrap`; un renderitzador markdown real és un "nice-to-have follow-up". | `web-react/src/pages/ComunitatPublicarPage.jsx:11` | `producte` · baix |
| Newsletter no té endpoint d'engagement per-post; s'omet la recollida a nivell de post (per disseny, però és un buit real). | `analytics/management/commands/recollir_metrics_social.py:109` | `tècnic` · baix |

### STALE / parcial / a verificar

| Item | On viu | Lectura |
|---|---|---|
| "Templates are placeholders for now. Fase 1.5.C will replace them…" | `comptes/notifications.py:21` | **STALE** — Fase 1.5.C ja va substituir les plantilles (els fitxers `email_user_solicitud_aprovada/_rebutjada.html` existeixen). Només cal actualitzar el docstring. `[docs · baix]` |
| Copy d'staff: "Sprint K integrarà… De moment mira-les cada dilluns" (Instagram Insights manual a Meta Business Suite). | `web-react/src/pages/staff/StaffSocialPage.jsx:407` | **Parcial** — Sprint K (mètriques de panell + followers_series) ja existeix, però la integració per-post inline que promet no s'ha fet; el copy quedà desfasat. `[producte · baix]` |
| "(the link 404s for now, which is fine — Google retries)." | `web/sitemaps.py:164` | **A VERIFICAR** — depèn de si la ruta "Block C" `/top/<territori>/setmana/<YYYY-WW>` ha enviat. `[seo/docs · baix]` |

> **No pendent** (notes de disseny permanents, no feina oberta — registrades
> perquè no es re-flaguegin): `comptes/models.py:21` (AbstractUser sense camps
> extra), `comptes/views.py:73` (raó d'evitar django-ratelimit),
> `web-react/src/components/Layout.jsx:5` (límit d'abast permanent del
> redisseny), workarounds GSC (`production.py:91`, `recollir_metrics_gsc.py:42`),
> `spa-redirect.js:1`, i les cadenes de caption catalanes de
> `social/narrative/banks/hero.py` (falsos positius de "de moment").

---

## 2. GITHUB — issues, PRs, milestones, branques

- **Issues obertes:** cap (`gh issue list --state open` → `[]`).
- **PRs oberts o draft:** cap (`gh pr list --state open` → `[]`). Tot el
  treball recent es va mergejar via squash.
- **Milestones:** cap definida.

### 2b. Branques — feina VIVA no mergejada a main

| Branca | Data | Què és | Categoria · Risc |
|---|---|---|---|
| `origin/redisseny-tail` | 2026-06-13 | Cua del redisseny, **retinguda esperant OK de Miquel**: elimina `web-react/src/components/editorial.jsx` (inline de `TERRITORI_NOM` a `rd/terr.js`), reskin de `ArtistaDashboardPage` + modal "Corregir", rewire de `CancoChart`/`FeedbackButton`. Verificat: `editorial.jsx` encara existeix a main; el contingut de PR #232 hi és absent. Inclou un commit-trigger de CI a descartar al merge. | `producte/neteja` · mitjà |
| `origin/feat/routine-esborrany-setmana` | 2026-06-08 | Afig el paràmetre opcional `?setmana=<dilluns iso>` a l'endpoint `esborrany()` de la rutina de newsletter (simètric amb `brief?setmana=`) + test + nota a comptes.md. Verificat: a main `esborrany()` encara fixa `current_monday()`. 3 fitxers, +122/-8. | `producte` · baix |

### 2c. Branques mortes (squash-merged, no podades) — neteja

**~74 branques** que ja són a main (squash-merge sense podar). Apareixen com
"no mergejades" perquè el squash reescriu història; el contingut hi és. Candidat
de neteja en bloc (`git push origin --delete <branca>` per a cadascuna).
`[neteja · baix]`. Inclou: tota la família `feat/playlists-*`, `feat/spotify-*`,
`feat/social-*`, `feat/narrative-*`, `feat/ml-*`, `feat/docs-gates-*`,
`feat/matriu-*`, `chore/*`, `fix/*`, `hotfix/login-explicit-backend`,
`perf/deezer-image-sizing`, `refactor/enrich-split`, i el punter estancat
`redisseny-web` (0 commits per davant de main). Llista completa verificada al
triatge de branques.

> Nota: les branques `rd/*` (slices del redisseny), `dependabot/*`, `deps/*`,
> `refactor/story-tokens` i `test/narrative-regression-guard` **ja s'han
> esborrat del remot** (un `git fetch --prune` les va retirar dels refs locals
> perquè ja no existeixen a GitHub). No cal fer-hi res.

---

## 3. DEPENDABOT / SEGURETAT

- **Alertes Dependabot obertes (API):** **1**, severitat **low** — `torch`
  (paquet Python). `[seguretat · baix]`. Única alerta viva; cap moderada/alta/
  crítica oberta.
- **Branques de bump de dependència:** cap oberta. Totes les actualitzacions
  recents ja són a main i podades: scikit-learn (#172), soundfile (#171),
  **django 6.0.5→6.0.6** (#170), react-router-dom (#147), pillow-avif (#120),
  google-api-python-client (#119), requests (#90), vitest (#126), torch (#37),
  gunicorn (#35), etc.
- **Deute de seguretat documentat (no és alerta, ve de docs):** CSP
  `unsafe-inline` → migrar a nonce és un "sprint de seguretat dedicat" pendent
  al roadmap. `[seguretat · mitjà]`

---

## 4. DOCS — seccions de pendent/backlog/futur + residu de les notes

### 4a. docs/ (arbre de documentació)

**`docs/history/roadmap.md` — "Sprints — pendents"** (backlog canònic obert):

- **Distribució v2 — 3 items cosmètics/a11y** VIUS: contrast del footer de
  story sobre targetes clares; decidir carrusel 4-imatges vs portada-only per a
  novetats a BS/Mastodon; verificar contrast de color de territori als pills de
  la slide-llista. `[producte · baix]`
- **Sprint S — SEO Bloc D** VIU (5): CWV (WebP + confirmar verd a PSI),
  propietat Wikidata `P5826`, outreach URL a MusicBrainz, pàgina `/premsa`,
  widget incrustable. `[producte/seo · mitjà]`
- **Backlog menor** VIU (mostres): snapshot del baseline del model RF abans del
  pròxim retrain `[scoring · baix]`; cobertura de test 52%→70%
  (`music/services.py`, `music/verificacio.py`, `ranking/senyal.py`)
  `[tècnic · baix]`; centralitzar hardcodes restants (`API_PAGINATION`,
  `SITE_URLS`, hex solt a `social/`) `[tècnic · baix]`; classe base
  `BaseSignalCommand` (argparse extret, classe no construïda) `[tècnic · baix]`;
  guarda contra doble-comptatge d'àlies per URL (`get_track_info_literal:258`)
  `[scoring · baix]`; eliminar `backfill_album_source.py` (verificar cua buida)
  `[neteja · baix]`; connectar el watchdog silent-noop a tq-health
  `[tècnic · mitjà]`; botons de compartir a Cançó/Àlbum/Artista (`share_click`
  a punt) `[producte · baix]`; reproductor preview Deezer 30s (`play_preview` a
  punt) `[producte · baix]`; polish Stalwart (587 STARTTLS, alias `postmaster@`
  per DMARC, parsing d'informes DMARC) `[tècnic · baix]`.
- **Deute tècnic (2026-05-11 i 2026-05-15)** VIU: literals hex de paleta al
  frontend (`palette.js` central per Recharts); finestres `timedelta(days=…)`
  de política de negoci escampades; constants de rate de MusicBrainz no
  compartides; mòduls >900 LOC candidats a split (`music/models.py` 1311,
  `social/renderer.py` 1122); **escombrat de `except Exception + return`** que
  empassen errors a les management commands (tq-health no els veu — n'hi ha més
  per trobar). `[tècnic · mitjà el de les excepcions, resta baix]`

**ADRs:** ADR-0011 (cron Spotify) segueix en estat **Proposed** i el seu
cron-meta `actualitzar_playlists_spotify_weekly` mai rep status → WAITING
perpetu (gap de monitoratge benigne) `[tècnic · baix]`. ADR-0013 descriu un
drenatge de backlog Process-B en marxa (operacional, no defecte).

**`docs/EMAIL.md` "Pendents documentats":** verificar `cercol.team` a Resend;
crear bústia/alias `postmaster@` per a informes DMARC (ara encuats sense
destí); habilitar 587 STARTTLS; comptes Google addicionals per `info@`/`admin@`.
`[tècnic · baix]` (solapa amb "Stalwart polish").

**Polítiques/archive:** fixture de smoke E2E encara no creada (backlog obert a
`conventions.md`/`identities.md`); documentar la comanda d'auth de Mastodon
(TODO a `identities.md`); chore recurrent `chore/docs-decay-2026-Q2` amb venciment
**2026-06-15** (imminent). `[docs · baix]`

**Doc-drift detectat:** CLAUDE.md i `docs/architecture/social.md` diuen "8
detectors a1-a8" però el codi en té **13 (A1–A13)**. `[docs · baix]`

### 4b. Residu obert de les notes a l'arrel (~/Claude/TopQuaranta/*.md)

**Monitoratge / ops:**
- `auditoria-monitoratge-2026-06-07.md` — **VIU, el més substancial.** 5 patrons
  oberts: (2) **ALTA** — la signatura de dedup d'alertes es calcula sobre text
  que varia → re-email cada hora (fatiga d'alerta); (4) **ALTA** —
  `tq-backup` èxit/fallada **invisible a tq-health** (gap crític de la xarxa de
  seguretat); a més: derivació de tags amaga variants de comanda
  (`playlists weekly` invisible, `publicar_canal` 4 canals s'emmascaren),
  constants mortes/derivades (`skip_concern`, `enrich_per_hour=50` ~24×
  optimista), WAITING conflou 3 estats i mai escala. `[tècnic/seguretat · alt]`
- `triatge-alertes-2026-06-06.md` — Whisper OOM real però transitori (mitigat
  per swap; recurrència possible; constant `fail=10` sense tocar); mètrica de
  cobertura Spotify massa estricta per a la cua no-verificada. `[tècnic · mitjà]`
- `diagnostic-git-drift-2026-06-10.md` — drift benigne (merge docs-only saltat
  pel deploy, s'auto-cura). Opcional no aplicat: que el check ignori diffs
  només-docs per reduir soroll. `[tècnic · baix]`
- `infra-swap-whisper-oom-2026-06-06.md` — mitigació EXECUTADA (swap 5 GB).
  Obert: confirmar efecte al pròxim tick 04:00; swappiness a 60; `fail=10`
  separat. `[tècnic · baix]`

**Dades / catàleg (PER-DECISIÓ de Miquel majoritàriament):**
- `crim-split-2026-06-09.md` — Deezer `347962` conflou TRES artistes (9 tracks
  enriquits). **PER-DECISIÓ:** triar camí de separació (recomanat: desvincular/
  rebutjar els 4 tracks forans, conservar els 5 en català). `[dades · mitjà]`
- `conflacions-aprovades.md` — zero conflacions estil-Crim a cançons aprovades
  (router arxivat). Obert: neteja de pendents duplicats de mateixa ubicació
  (Alosa/Erm/Fat Chets/Vadebo) + decidir sobre el 2n Crim (pk=3663, 11 cançons
  verificades, sense deezer). `[dades · baix]`
- `deezer-compartit-recon.md` — gap estructural: un homònim que comparteix
  deezer_id s'atribueix malament i staff NO té manera de separar-lo (UNIQUE
  bloqueja el 2n artista). 40 artistes actius amb dispersió>1. Opcions (cap
  construïda): router + cua de desambiguació manual abans de relaxar UNIQUE.
  `[dades · alt si s'aborda]`
- `informe-2a-forat-ingesta` + `informe-provinenca-orfes` — verdicte: **cap
  font en viu d'orfes** (149 tracen a l'episodi d'abril, 0 nous en 30d; reject
  cobert per #159). Residu: decisió arquitectònica de si la guarda va a ingest
  vs cua. `[dades · baix — no urgent]`

**Scoring / narrativa (diagnòstic, decisions de producte):**
- `concentracio.md` + `remesura-concentracio-neta-2026-06-06.md` — concentració
  BAL (Maria Jaume + Joan Miquel Oliver = 37,5% de slots) és **real**, no
  artefacte. **PER-DECISIÓ:** cap dur per artista/àlbum, penalització més
  agressiva, o acceptar (recomanat gated/off-by-default si es canvia).
  `[scoring · baix eng, decisió editorial]`
- `mesura-baseline-reedicions-2026-06-06.md` — inflació per merge de scrobbles
  (Last.fm va doblar comptadors 04-22 i 05-21 → 74 entrades inflades, 7 #1
  artificials). Fix #151 mitiga; residu: la guarda no detecta salts de comptador
  implausibles si el nom no canvia. `[scoring · mitjà]`
- `mesura-rankings-2026-06-05.md` — "debuts al cim" barreja real + artefacte
  narratiu; criteri A4 "debut" = sense-setmana-prèvia conflou debut/re-entry/
  catàleg vell; plantilles A1/A4 fixen afirmacions de frescor falses. Doc-drift
  8 vs 13 detectors. `[scoring/producte · mitjà]`
- `novetat-al-top.md` — verdicte: la guarda de frescor funciona. Residu (Miquel):
  tractar `edat<0` (data_llancament futura) com a sospitós; consumir el senyal
  extra de plausibilitat que `freshness.py` ja calcula. `[scoring · baix]`
- `mesura-capa2-3-2026-06-05.md` — informatiu: `data_llancament` no distingeix
  original de reedició (camps MB buits → només ~7% detectable); monopoli és la
  penalització més extensa (46% d'entrades). `[scoring · baix — informatiu]`

**Distribució / social (proposta read-only):**
- `informe-auditoria-vistes-distribucio` + `informe-mapa-vistes-canal-4seccions`
  + `informe-mapa-distribucio` — refactor proposat de la UI de distribució a 4
  sub-vistes de patró-casa (`StaffSocialPage` és un monòlit de 1162 línies;
  `StaffSocialSpotifyPage` amb paleta invertida; sense filtres/cerca/paginació a
  la llista de SocialPost). Codi nou necessari: endpoint `POST
  /staff/newsletter/esborrany/generar/?setmana=`, endpoint de filtre per-canal de
  `MetricaSocialPost`. STOP/decisió: matriu editable canal×tipus = nou model +
  migració. El botó "Kill switch global" només escriu `instagram_actiu`
  (etiqueta enganyosa); no hi ha pausa global ni "últim enviament per canal".
  `[producte · mitjà]`
- `recon-imatges-2026-06-09.md` — oportunitat de disseny (no bug): pujar les
  slides feed-novetats al nivell editorial de les stories ("Sèrie 7").
  `[producte · baix]`
- `spike-html-render-feed.md` — verdicte: mantenir el port PIL ara, reservar
  captura HTML-headless per a més tard (risc OOM CX22). Decisió diferida amb
  condicions de re-avaluació. `[tècnic · baix]`

**Newsletter / caràtules:**
- `informe-2c-caratules-newsletter-2026-06-07.md` — bug confirmat: les caràtules
  de newsletter cauen al logo quan el JPG auto-allotjat encara no s'ha generat,
  ignorant `cover_url`. Obert: afegir nivell de fallback a URL Deezer (com
  `Cover.jsx onError`) abans del placeholder. `[producte · baix]`
- `recon-2026-06-09.md` — obert: pont newsletter→`Publicacio` (post públic) no
  existeix; **`docs/platform-overview.md` molt desfasat** (8 afirmacions
  falses/velles). `[docs · baix]`

**Rendiment (EN VIU a prod):**
- `mapa-mobil-psi.md` + `redisseny-web-estat.md` — **`/mapa` mòbil PSI 95→71,
  LCP 6,8s** després del redisseny (en prod). *Actualització d'avui:* la sèrie
  diària del cron PSI marca **92/2,72s** el 06-13, a prop de base → apunta a
  soroll; confirmació neta amb la lectura de **demà 06-14**. Palanques no
  aplicades: diferir build SVG, aprimar `paisos.json` <100KB, no demanar
  `artistes-top` a l'overview. `[tècnic · mitjà — pendent 2a lectura]`

**Staff perf (N+1):**
- `informe-2b-lentitud-vistes-staff-2026-06-07.md` — 5 problemes oberts:
  `localitats.first()` per fila + prefetch absent a llista de cançons (clars,
  baix risc); fan-out de counts al dashboard estat; N+1 a `_homonym_suspects`;
  subqueries correlacionades de `n_top` (cal índex primer). `[tècnic · baix-mitjà]`

**Repo / espai:**
- `disc-90.md` — neteja EXECUTADA (90%→79%). Obert (Miquel): PR `git rm` per
  treure `scripts/model_comparison` (14 fitxers, 88K) del repo. `[neteja · baix]`

> Notes purament històriques/resoltes (sense residu viu):
> `auditoria-spotify-enriquiment` (no hi ha stall), `cobertura-spotify` (només
> deixar córrer el cron), `informe-2d-disc` (superat per disc-90),
> `redisseny-web-pla` (execució tracada a estat).

---

## 5. CODI MORT / NETEJA — candidats d'alta confiança

**Costat Python: net.** Cap mòdul/camp mort d'alta confiança. Els dos camps
"deprecats" que CLAUDE.md menciona ja estan resolts al codi:
`Album.cancons_obtingudes` el va eliminar la migració `music 0069` (només
sobreviu un comentari històric a `obtenir_novetats.py:181`) — **CLAUDE.md és
STALE en aquest punt**. Tots els mòduls sospitosos tenen importadors vius.

**Costat React SPA — 2 blocs confirmats morts** (residu de l'era editorial
substituïda per `rd/primitives`):

| Item | On viu | Evidència | Categoria · Risc |
|---|---|---|---|
| Exports `Section`, `SectionHeader`, `TerritoriBadge`, `TrendCue`, `FOCUS_TERRITORIS`, `TERR_COLORS` | `web-react/src/components/editorial.jsx` (27/58/64/77/99/113) | Els únics imports de `./editorial` a tot el SPA són `{ TERRITORI_NOM }` (a `CancoChart.jsx:29` i `rd/terr.js:14`). Cap dels 6 símbols s'importa ni s'instancia enlloc. `StaffAnalyticsPage` té el seu propi `TERR_COLORS` local. | `neteja` · baix |
| Export `TerrChip` | `web-react/src/components/rd/primitives.jsx:126` | `grep TerrChip` retorna només la definició + el docstring; els 14 imports de `primitives` no l'agafen mai. | `neteja` · baix |

> **Important:** aquesta neteja del SPA **és exactament el que fa la branca
> viva `redisseny-tail`** (§2b) — elimina `editorial.jsx` i reapunta els
> consumidors. Llançar `redisseny-tail` resol el candidat #1. `TerrChip`
> (#2) queda fora i és una eliminació trivial independent.
>
> Caveat del subagent: la detecció Python no va enumerar exhaustivament el
> cablejat de cron de cada management command; no es va trobar cap morta, i
> es reporta cap en lloc d'especular.

---

## Apèndix — traçabilitat

- Issues/PRs/milestones: `gh issue list`, `gh pr list`, `gh api …/milestones`.
- Branques: `git for-each-ref refs/remotes/origin` + classificació per
  contingut vs main (squash-merge detection).
- Dependabot: `gh api repos/Top-Quaranta/TopQuaranta/dependabot/alerts`.
- Marcadors de codi: ripgrep sobre `.py/.js/.jsx` (exclòs tests/migracions),
  amb inspecció manual de cada coincidència per descartar falsos positius.
- Docs + notes: lectura directa de `docs/` i dels 30 informes `.md` a l'arrel.
- Codi mort: cerca de referències per símbol/fitxer al SPA i al backend.

*Inventari acabat. Cap canvi al codi ni a prod; únic fitxer escrit: aquest.*
