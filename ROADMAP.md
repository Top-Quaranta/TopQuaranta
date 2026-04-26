# ROADMAP.md — TopQuaranta

> Estat actual i propers passos. El detall fi viu al `git log` i als
> commits per sprint; la història de Phase 9 (auditoria d'excel·lència)
> al fitxer `CLAUDE_EXCELLENCE.md`.
> Last updated: 2026-04-26.

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
- **Pipeline**: nightly chain documentada a `CLAUDE_PIPELINE.md`.
- **DB**: PostgreSQL 14, 37 taules. Volums actuals (2026-04-26):
  ~1.9k artistes aprovats, ~2.4k cançons verificades, 5 territoris
  amb top oficial actiu.
- **ML**: 79 features, ROC-AUC 0.9994 (post Whisper + MB).
- **Infra**: Caddy + gunicorn :8083 amb `ExecReload=HUP`.

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
| 9 | **Excellence** — security + reliability + arch + culture | ✅ (history a `CLAUDE_EXCELLENCE.md`) |
| 10 | Migració React SPA + neteja Django UI | ✅ 2026-04-21 |
| 11 | Plataforma comunitat (Grup C) | ✅ 2026-04-21 |
| 12 | Sprints temàtics A–J ter (vegeu sota) | ✅ |

---

## Sprints — pendents

Per ordre de prioritat (no alfabètic). Quan se'n fa un, es mou a la
secció _completats_ amb la data i el detall.

### 1. Sprint J — Privacitat i cookies (GDPR)

> Posar el lloc al dia amb el RGPD/LOPDGDD.

**Per què primer**: és el risc legal real del projecte. El SPA no
fa tracking de tercers (no Google Analytics, no píxels), però
seguim sense política de privacitat publicada ni banner de cookies
informatiu (la cookie de sessió és funcional, però convé documentar-ho).

- [ ] Pàgina `/privacitat` amb política completa (dades que es
      guarden, finalitat, base legal, drets de l'usuari, contacte).
- [ ] Pàgina `/cookies` amb la llista de cookies usades (sessionid,
      csrftoken, axes_*) i la seva finalitat. Al SPA, **no** s'usen
      cookies de tercers ni analytics.
- [ ] Banner discret la primera visita amb "Entès" + link a la
      política. No bloquejant.
- [ ] Endpoint `POST /api/v1/compte/exportar-dades/` (right to data
      portability) que envia un correu amb un fitxer JSON amb tot
      el que el sistema sap de l'usuari.
- [ ] L'auto-eliminació via correu ja existeix (Sprint G), enllaçar-la
      des de la política.
- [ ] Textos legals en català, revisió per algú amb formació jurídica
      abans de publicar.

### 2. Sprint I — Instagram automàtic

> Distribuir els tops setmanals automàticament al canal d'Instagram.

**Per què**: tracció gratuïta cada dissabte. Cost moderat. Requereix
un compte business i decidir API oficial vs solució no-oficial.

- [ ] Definir format visual del post setmanal (carrousel? imatge
      única amb top 10?). Generar via PIL/Cairo o html-to-image.
- [ ] Crear/configurar el compte Instagram business + Facebook page
      requerida per l'API oficial de Meta.
- [ ] Cron dissabte 09:30 UTC (post `calcular_top` setmanal) que
      publica el carrousel al feed.
- [ ] Decidir si afegim també `Stories` o només feed.

### 3. Backlog menor

Items petits per fer en sessions curtes:

- [ ] Demucs → Whisper pipeline com a recall booster per les ~3-4
      false negatives on Whisper sent `es` a tracks catalans
      (Jonatan Penalba × 2, Adrien Broadway). Cost ~3× més lent;
      només val la pena si surt un cluster significatiu després
      del backfill.
- [ ] Auditar les 39 prediccions `ja` (japonès) de Whisper —
      sospitós, probablement vocalitzes/instrumentals/scat.
- [ ] Snapshot baseline pre-Whisper RF abans del proper retrain
      per A/B sobre el set de 48 clips.
- [ ] Decidir què fem amb `/root/TopQuaranta/` (1.4 GB Wagtail
      legacy): tar.gz a backup off-site o `rm -rf`.
- [ ] Test coverage 52% → 70%. Gaps: `music/services.py`,
      `music/verificacio.py`, `ranking/senyal.py`. Sprint C ja en
      va cobrir part.
- [ ] Valorar correu @topquaranta.cat: avui Sprint G va concloure
      "stay on cdmon"; revisitar si el volum d'enviaments puja.

> **Sprint K — Capa editorial pública**: descartat. La intenció
> original (donar entrada clara a un visitant nou) la va cobrir
> Sprint H + `/com-funciona` + el redisseny editorial dels Sprints
> I bis i J bis.

---

## Sprints — completats

Llistat per ordre alfabètic per facilitar la cerca; les dates dels
títols indiquen cronologia real. Cada bloc inclou les verificacions
finals (`manage.py check`, `pytest`, `npm run build`, axe-core).

### Sprint A — Tancar deute acumulat ✅ (2026-04-25)

> Deixar el codi sense columnes mortes ni constants hardcoded ni
> documentació desfasada.

- [x] Drop `RankingProvisional.dies_en_top` (sempre NULL des de v2.0).
      Migració `ranking 0012`.
- [x] Rename `RankingProvisional.lastfm_playcount` → `escoltes_setmanals`.
      Migració `ranking 0012` (RenameField). Lectors/writers a
      `staff_views`, `calcular_ranking._save_provisional`, tests i UI
      (StaffRankingPage, RankingBreakdownPanel) actualitzats.
- [x] Drop `Artista.deezer_no_trobat` — la columna ja s'havia eliminat
      a `music 0044`. CLAUDE_MODELS depurat (entrada de la taula i
      paràgraf explicatiu).
- [x] Moure `PPCC_PENALITZACIO_PER_POSICIO` a `ConfiguracioGlobal`
      (camp nou `ppcc_penalitzacio_per_posicio`, default 0.04).
      `_calcular_ranking_ppcc` el llegeix de la config.
- [x] Magic numbers de l'heurístic ML → `constants.py`:
      `TFIDF_MAX_FEATURES`, `RATIO_PRIOR_K`, `RATIO_PRIOR_P`,
      `MB_AUTO_MATCH_SCORE`. `music/ml.py` i `music/mb_sync.py` els
      importen.
- [x] `CLAUDE_MODELS.md` ja no menciona `lastfm_mbid` (cap referència
      activa). Migrations footer actualitzat fins a `ranking 0012`.
- [x] `/root/TopQuaranta/` arxivat a
      `/home/topquaranta/backups/legacy-wagtail-archive-20260425.tar.gz`
      (4.9 MB comprimits) i esborrat. (Eren 16 MB reals, no 1.4 GB
      com deia el plan inicial.)

### Sprint B — Whisper milestone i reentrenament ML ✅ (2026-04-25)

> Tancar el cicle del backfill Whisper i decidir si simplifiquem el
> model amb les noves dades.

- [x] Whisper backfill ja completat (2026-04-25).
- [x] Baseline desat: `music/ml_{model,tfidf,directions}.pre_whisper.joblib`
      (snapshot del model anterior al re-entrenament).
- [x] Re-entrenat sobre 7.602 mostres (1.958 aprovades + 5.644
      rebutjades) amb cobertura Whisper 75.8 % del catàleg.
- [x] Feature importances post-train: **4 de 4 features Whisper són
      al TOP-7** (`whisper_p_ca` #2, `whisper_p_es` #4,
      `whisper_margin_ca` #6, `whisper_p_en` #7). Estructurals
      sumen 95.6 % del senyal; TF-IDF només 4.4 % (60 features).
- [x] **Follow-up TF-IDF retall** ✅ (2026-04-25). 5-fold CV A/B
      sobre 7 730 decisions:

      | Mètrica  | max=60 (A) | max=30 (B) | Δ (B−A) |
      |---|---|---|---|
      | ROC-AUC  | 0.9998 ± 0.0001 | 0.9998 ± 0.0001 | +0.0000 |
      | F1       | 0.9895 ± 0.0017 | 0.9908 ± 0.0031 | +0.0013 |
      | Accuracy | 0.9947 ± 0.0009 | 0.9953 ± 0.0016 | +0.0006 |

      Model B iguala AUC i millora marginalment F1 + Accuracy.
      Adoptat: `TFIDF_MAX_FEATURES = 30` a `music/constants.py`,
      model i tfidf de producció re-entrenats sobre 7 912 mostres
      (49 features = 19 estructurals + 30 TF-IDF). De pas, fixat un
      bug latent a `_tfidf_features` (no padejava quan el vocab era
      més petit que el cap, cosa que provocava `ValueError:
      inhomogeneous shape` quan `min_df=2` retallava la cua).

### Sprint C — Robustesa staff_views i tests ✅ (2026-04-25)

> Trencar el monòlit de `staff_views.py` i pujar la cobertura de
> tests de l'API.

- [x] Split de `web/api/staff_views.py` (3.330 línies) en el paquet
      `web/api/staff/` amb 16 mòduls per àrea (`_common`,
      `dashboard`, `pendents`, `artistes`, `cancons`, `albums`,
      `ranking`, `propostes`, `solicituds`, `senyal`, `historial`,
      `configuracio`, `audit`, `usuaris`, `feedback`, `estat`).
      `staff_views.py` queda com a shim de 18 línies que re-exporta
      el paquet via `from web.api.staff import *`. Cap canvi a
      `urls.py` ni a `comunitat_views.py`.
- [x] Tests d'integració (`web/tests/test_staff_endpoints.py`):
      auth gate, estat (full payload shape), ranking_list, cancons_list,
      artistes_list (exerceix la cadena d'imports cross-module
      artistes → pendents._artista_card → estat._homonym_suspects_qs),
      i regressió del shim legacy.
- [x] Cobertura `web/api/staff/*` ara **47 %** (era 0 %), amb pics
      a `estat` (87 %) i `dashboard` (97 %). Total tests del projecte:
      112 → 118 (+6). Cap regressió.

### Sprint D — Performance pública ✅ (2026-04-25)

> Reduir càrrega Postgres a hores punta amb cache HTTP a les rutes
> més consultades.

- [x] Helper `web/api/utils.py::cache_for_anon` — cache 60 s a
      `pagecache` (LocMem per worker, ja existent des de Phase 9)
      només per a usuaris anònims; els autenticats sempre veuen
      dades fresques. Emmagatzema l'`HttpResponse` ja renderitzat
      via `add_post_render_callback` perquè els hits cached siguin
      bytes purs.
- [x] `@condition` (Django) amb ETag + Last-Modified a:
      - `/api/v1/ranking/` → `RankingProvisional.data_calcul` ↦
        fallback `RankingSetmanal.created_at`.
      - `/api/v1/artistes/` → `Artista.created_at` (Max).
      - `/api/v1/mapa/artistes-top/` → `SenyalDiari.data` (Max).
      ETag pesat amb el query string perquè cada combinació de
      filtres rebi el seu propi 304.
- [x] Mesures (intra-host, 5 hits consecutius, 2 workers):

      | Endpoint | Cold | Cached | 304 (If-None-Match) |
      |---|---|---|---|
      | `/api/v1/ranking/?territori=CAT` | ~410 ms | **15 ms** | **5 ms** |
      | `/api/v1/artistes/?per_page=40` | ~520 ms | **18 ms** | (ETag funciona) |
      | `/api/v1/mapa/artistes-top/?territori=CAT` | ~145 ms | **15 ms` | (ETag funciona) |

      Speedup ~30× a hits servits des de cache; ~80–100× quan el
      client envia ETag i el servidor pot retornar 304 sense cos.
- [x] Sense invalidació activa: la cache de 60 s és curta enough
      perquè els ~daily cron writes (provisional 07:00, setmanal
      dissabte) es propaguin sols. La capa ETag/Last-Modified actua
      com a contracte segon: si el `data_calcul` no ha canviat el
      304 protegeix amplada de banda fins i tot durant els 60 s de
      stalebess potencial.

### Sprint E — Transparència algorítmica pública ✅ (2026-04-25)

> Donar als visitants la mateixa visió que té l'staff sobre per què
> una cançó està on està.

- [x] Endpoint `GET /api/v1/cancons/<slug>/top-breakdown/` amb
      payload diferenciat per permís: anònim/usuari sense relació
      veu només els territoris on la cançó és al `TopProvisional`;
      staff i `UserArtista.verificat=True` sobre l'artista
      principal veuen també els territoris elegibles on la cançó
      no està al top, amb factors i score teòric calculats sobre
      la marxa via `_compute_weekly_plays`, `_age_factor` i
      `_past_top_factor` (`canco_views.py::canco_top_breakdown`).
- [x] Component nou `web-react/src/components/TopBreakdownPanel.jsx`
      (compartit, no només staff). Toggle "Per què està aquí?"
      (anon) o "Com ho fa al top?" (elevated). Selector de
      territoris quan n'hi ha més d'un. Frases divulgatives en
      català per a cada penalització: antiguitat, top passat,
      monopoli àlbum/artista. Quan la cançó no és al top mostra
      la puntuació teòrica i ho explica.
- [x] Unificat amb el panell d'staff: `RankingBreakdownPanel.jsx`
      eliminat. `CancoEditPage` ara fa servir el mateix component
      (passant `slug`), eliminant la duplicació.
- [x] `CLAUDE_STAFF.md` documenta el nou endpoint i la lògica de
      permisos diferenciada.

### Sprint F — Accessibilitat i mobile ✅ (2026-04-26)

> Passar WCAG AA i validar el SPA en dispositius reals.

**Fets globals (afecten totes les pàgines)**:
- [x] Skip-to-content link al `Layout.jsx` ("Salta al contingut
      principal") — `sr-only` per defecte, visible en focus, jumpa
      a `<main id="main-content">`. Compleix WCAG 2.4.1 (Bypass
      Blocks).
- [x] `<main id="main-content" tabIndex="-1">` — destí del skip
      link, focusable programàticament des del cop.
- [x] `:focus-visible` global a `index.css` amb 2px outline groc
      (sobre superfícies fosques) o ink (sobre groc/blanc) +
      offset 2px. Compleix WCAG 2.4.7 (Focus Visible). Usa
      `:focus-visible` perquè els clics de ratolí no mostrin
      l'outline (només navegació per teclat).
- [x] Auditoria estàtica de patrons comuns sense violacions
      crítiques trobades:
      - Cap `<img>` sense `alt` (revisat tot `web-react/src`).
      - Inputs amb `<Field label>` wrapper (`PerfilUsuariPage`,
        `ComptePerfilPage`, `ProposarArtistaPage`).
      - Pills sempre amb text (no només color).
      - Landmarks ja correctes a `Layout.jsx`: `<header>`, `<nav
        aria-label>`, `<main>`, `<footer>`.
      - Hamburger button té `aria-label` + `aria-expanded`.
      - Cap `text-tq-yellow` directament sobre `bg-white` (el groc
        de marca sempre va sobre fons fosc).

**Auditoria axe-core a producció (2026-04-26)**:
Instal·lat `chromium-browser` (snap) + `@axe-core/puppeteer` a
`/tmp/axe/`. Executat amb tags `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa`
sobre 6 pàgines públiques (`/`, `/top`, `/artista/zoo`,
`/canco/zoo-tot-anira-be`, `/comunitat`, `/compte/accedir`).

**Violacions trobades i corregides (4)**:
- [x] `/` — 3 nodes color-contrast a les targetes de territori
      (CAT `#c99b0c` 2.56:1, CNO `#0891b2` 3.68:1, FRA `#ea580c`
      3.55:1 sobre blanc). Substituïts per CAT `#8a6900` (5.08:1),
      CNO `#0e7490` (4.78:1), FRA `#c2410c` (4.84:1).
      `web-react/src/pages/HomePage.jsx` `COLORS`.
- [x] `/top` — 31 nodes color-contrast en els números de posició
      (`var(--color-tq-yellow)` sobre blanc, 1.53:1; el llindar
      WCAG AA per text gran és 3:1). Canviats a `text-tq-ink`
      (21:1). La icona de tendència manté el color de marca, així
      que la identitat visual es preserva sense violar contrast.
      `web-react/src/pages/TopPage.jsx`.
- [x] `/artista/zoo` — 1 node color-contrast a la metadada any
      de col·laboracions (`text-gray-400` `#99a1af` sobre blanc,
      2.6:1). Pujat a `text-gray-600` (5.7:1).
      `web-react/src/pages/ArtistaPage.jsx`.
- [x] `/compte/accedir` — `aria-required-children` al pill toggle
      (`role="tablist"` sense fills `role="tab"`). Afegit
      `role="tab"` + `aria-selected` + `tabIndex` al `TabButton`.
      `web-react/src/pages/AuthPage.jsx`.

**Re-auditoria final**: `0 violations` a les 6 pàgines auditades.

**Follow-up (no bloquejant)**:
- [ ] Pàgines staff a WCAG A — auditoria cas per cas pendent (no
      són públiques; volum baix d'usuaris).
- [ ] Verificació de mides de toc 44×44 px en touch devices —
      regla CSS global descartada per ser massa disruptiva sense
      review per component (inflaria pills de `StaffTable.Btn` i
      altres elements compactes per disseny).
- [ ] Testing visual mòbil 375 px en dispositiu real.

### Sprint G — Gestors d'artista i correu ✅ (2026-04-26)

> Donar agència als artistes verificats per editar-se directament i
> avaluar la infraestructura de correu.

**Bloc 1 — Correccions de camp per gestors d'artista**:
- [x] Nou camp `Artista.bio` (TextField, blank). Distingit dels
      `lastfm_bio_*` que el cron sobreescriu — aquest l'edita el
      gestor verificat. Migració `music 0053_artista_bio`.
- [x] Nova entrada al taxonomia `StaffAuditLog.ACTION_CHOICES`:
      `gestor_edita_artista` ("Artista: edició per gestor"). Migració
      `music 0052_add_gestor_edita_artista_action`.
- [x] Endpoint `GET/PATCH /api/v1/compte/artista/<pk>/editar/`
      (`web/api/compte_views.py::gestor_artista_editar`). Requereix
      `UserArtista(usuari, artista, verificat=True)`; 403 si no.
      PATCH escriu només els camps a la llista blanca:
        - text lliure: `bio`, `genere`
        - choices: `percentatge_femeni` (validat contra
          `Artista.PERCENTATGE_FEMENI_CHOICES`)
        - URL: tots els 12 `Artista.SOCIAL_LINK_FIELDS` (Spotify,
          Viasona, Web, Bandcamp, Myspace, YouTube, Viquipèdia,
          SoundCloud, TikTok, Facebook, Instagram, X) — validats amb
          `HTTP_ONLY_URL` (només http/https).
      Camps fora de la llista (nom, slug, deezer_ids, localitats,
      aprovat, MB lockouts) s'ignoren silenciosament. L'audit
      s'escriu **només** quan algun camp realment canvia
      (`metadata={camps: [...], usuari: pk}`).
- [x] Nova ruta SPA `/compte/artista/:pk/editar` →
      `GestioArtistaEditPage.jsx`. Formulari amb tres fieldsets
      (Sobre l'artista / Xarxes / botons), diff client-side perquè
      el PATCH només envia camps modificats, re-hidratació des de
      la resposta canònica del backend, errors per camp i missatges
      `Cap canvi per desar.` / `Desat. Camps actualitzats: …`.
- [x] Targeta `ArtistaCard` a `ComptePage.jsx` ara mostra un botó
      "Editar" als artistes verificats que ho enllaça. El payload
      `_serialize_user_artista` ara exposa `artista.pk` perquè el
      SPA pugui construir l'URL.
- [x] Tests: `web/tests/test_gestor_artista_editar.py` — 7 casos
      (anon, no-manager, GET, PATCH valid, camps crítics ignorats,
      URL invàlida, PATCH no-op no audita). 125 passed, 8 skipped.

**Bloc 2 — Valoració Hetzner Hosted Mail**:

Hetzner no ven el correu com a producte solt; va dins els plans
**Webhosting** (S/M/L/XL) amb mailboxes il·limitades, IMAP/SMTP+TLS,
webmail, CalDAV/CardDAV, DKIM/SPF/MX personalitzat. **Webhosting S**:
~€1,90–€2,50/mes + setup únic ~€9, 10 GB compartits. Per a 3-5
comptes: **€25-35/any tot inclòs**.

Comparativa cdmon actual:
- **Micropla** (l'actual): inclòs amb el domini, 1 mailbox, 100 MB,
  100 enviaments/dia. Cost addicional: €0 (ja paguem el `.cat`).
- **cdmon Standard Hosting Mail**: €4,95/mes (~€59/any), però
  mínim **10 mailboxes**, 5 GB cadascuna, DKIM/SPF/IMAP/SMTP/webmail
  complets.

**Recomanació: continuar amb cdmon, no migrar a Hetzner ara.**
L'estalvi (~€25/any) no compensa el canvi d'MX, refer SPF/DKIM/DMARC,
el setup fee, ni el risc de deliverability del `noreply@` durant la
transició. Quan es superi el límit de 100 enviaments/dia de Micropla
o calguen comptes addicionals, el següent salt natural és cdmon
Standard (els 10 slots no són un problema — s'utilitzaran).

**Comptes addicionals que tindrien sentit** quan es faci el salt:
- `info@` — contacte públic genèric (peu de pàgina).
- `premsa@` — premsa i festivals.
- `gestio@` — sol·licituds de gestió d'artista (ara no hi ha
  adreça d'entrada per a aquest flux).
- `hola@` — alias amistós per a comunitat/feedback.
- `noreply@` — es manté per a transaccionals (registre, activació, 2FA).

### Sprint H — Comunicació del producte i onboarding ✅ (2026-04-26)

> Que qualsevol visitant nou entengui immediatament què és
> TopQuaranta, què pot fer aquí i com començar. Cap pàgina nova de
> documentació estàtica: el contingut viu integrat a les pàgines
> existents. El document públic divulgatiu és part del SPA.

**Pàgines tocades**:

- [x] **HomePage (`HomePage.jsx`)** — afegida secció hero sota la
      graella de territoris: títol "El punt de trobada de la música
      en català", 2 línies de pitch, **3 blocs visuals** (icona +
      títol + 2 línies) per al top setmanal, mapa i comunitat. Cada
      bloc usa una icona de `mm-design/icons/ui/` (`icon-ranking`,
      `icon-mapa`, `user`) i una halo del color territorial real
      (BAL blau, VAL roig, CAT ambre) per ancorar la identitat
      geogràfica. **2 CTAs**: "Escolta el top" → `/top` i "Vols fer
      música amb algú?" → `/compte/accedir?mode=registre` per
      anònims o `/comunitat` per autenticats.
- [x] **TopPage (`TopPage.jsx`)** — afegit text introductori discret
      (3 línies, `text-xs text-white/60`) sobre el selector. No
      competeix visualment amb el rànquing.
- [x] **MapaPage (`MapaPage.jsx`)** — afegit panell d'introducció a
      sobre del grid del mapa. Explica què mostra, com navegar (clic
      → zoom, panell lateral) i la freqüència d'actualització.
- [x] **ComunitatPage (`ComunitatPage.jsx`)** — `IntroPanel`
      destacat a sobre del feed amb pitch ("Un espai per a músics i
      amants de la música en català…") i un únic CTA dependent
      d'estat: "Activa el teu perfil" si `visible_directori=False`,
      "Explora el directori" si ja hi és.
- [x] **ComunitatDirectoriPage (`ComunitatDirectoriPage.jsx`)** —
      capçalera amb dues frases: "Músics i creadors de música en
      català oberts a connectar i col·laborar" + suggeriment de
      filtres. La línia tècnica sobre activar la casella es manté.
- [x] **ComptePage (`ComptePage.jsx`)** — reestructurada amb
      guiatges contextuals (`GuidanceCard`) que apareixen i
      desapareixen segons l'estat:
        - Sense artistes verificats → "Tens un artista o grup?
          Proposa'l per aparèixer al top i al mapa." + botó.
        - Amb artistes verificats → cada targeta mostra "Millor
          posició al top: #N" o "Encara no està al top." + dos
          botons "Editar perfil" + "Veure al mapa".
        - `visible_directori=False` → "Vols que altres músics et
          trobin? Activa el teu perfil al directori." + botó
          "Activar perfil".
        - `visible_directori=True` → línia "✓ El teu perfil és
          visible al directori. Editar perfil →".
- [x] **OnboardingPage (`OnboardingPage.jsx`)** — abans dels camps
      del formulari, targeta amb 3 punts ("Què pots fer com a usuari
      registrat") explicant proposar/gestionar artistes, activar el
      perfil al directori i publicar a la comunitat. El botó
      "Saltar" es manté visible i accessible.
- [x] **ComFuncionaPage (`ComFuncionaPage.jsx`)** — pàgina **nova**
      a `/com-funciona`, accessible des del peu de pàgina, sense
      requerir autenticació. Sis seccions divulgatives en català (1)
      Què és TopQuaranta, (2) Com funciona el top — quatre factors
      en llengua planera, sense fórmules, (3) Què compta com a
      música en català — versió simplificada de `docs/DEFINITION.md`,
      (4) Qui decideix — staff + ML acceleratiu mai decisiu, (5) El
      que no farem mai — extracte del `MANIFEST.md`, (6) Com
      participar — enllaços a propostes, gestió, perfil, "Corregir"
      i GitHub. Disseny editorial: targetes blanques sobre fons
      ink, icones `mm-design/icons/ui/` per cada secció, tipografia
      Playfair per títols + Roboto per cos, accent groc de marca.

**Backend touchpoints**:
- [x] `/api/v1/compte/dashboard/` (`web/api/compte_views.py`) ara
      inclou un bloc `perfil` amb `visible_directori`,
      `onboarding_complet` i `nom_public`. Permet a la `ComptePage`
      i a la `ComunitatPage` mostrar guiatges sense un segon round-
      trip a `/comunitat/perfil/`.

**Routing + footer**:
- [x] Nova ruta `<Route path="/com-funciona" element={<ComFuncionaPage />} />`
      a `App.jsx` (a sobre dels routes autenticats — pàgina pública).
- [x] Enllaç "Com funciona" afegit al `FooterLine` de `Layout.jsx`,
      en primera posició abans d'"Open source · GitHub · Privacitat".

**Disseny — criteris seguits**:
- Cap hex hardcoded; tot via tokens (`tq-yellow`, `tq-ink`,
  `tq-yellow-deep`) o el palette territorial existent del
  `HomePage.COLORS`.
- Icones via el component `MmIcon` existent (mascarat CSS sobre SVGs
  de `vendor/mm-design/icons/`), pickup de `currentColor` per
  inheritance.
- Tipografia: Playfair (`font-display`) per títols/destacats, Roboto
  per cos. Jerarquia respectada.
- Densitat: textos introductoris a `text-xs`–`text-sm` amb
  `text-white/60`–`text-white/80` perquè no competeixin amb el
  contingut principal de cada pàgina.
- To: primera persona del plural, directe, sense paternalisme.

**Verificacions**:
- `manage.py check`: ✅ net.
- `pytest -q`: 125 passed, 8 skipped (cap test trencat).
- `npm run build`: ✅ net (1.11 MB JS / 309 kB gz; +6 kB respecte
  Sprint G per la nova pàgina + hero + intros).
- `systemctl reload topquaranta-web`: ✅ tres pàgines noves
  responen 200 (`/`, `/top`, `/mapa`, `/com-funciona`, `/comunitat`).

### Sprint I bis — Redisseny editorial de la HomePage ✅ (2026-04-26)

> Convertir `/` d'una pàgina-selector de territoris a una portada
> editorial vertical en deu seccions, inspirada en FACT/Bandcamp/RA.
> El selector de territoris desapareix de la home (queda al `/top` i
> al `/mapa`). Cada secció té un propòsit narratiu propi.

**Backend — endpoints nous** (`web/api/home_views.py`):
- [x] `GET /api/v1/stats/` — `{cancons_verificades, artistes_aprovats,
      territoris_actius, setmana}`. `cache_for_anon(60s)`.
- [x] `GET /api/v1/top/nova-setmana/` — entrada amb `posicio_anterior=null`
      i menor `posicio` al darrer top oficial PPCC.
      `cache_for_anon(3600s)`.
- [x] `GET /api/v1/artistes/destacat/` — artista amb `UserArtista.verificat=True`
      que ha tingut la millora de posició més gran al PPCC respecte
      la setmana anterior; tie-breaker per nombre de cançons
      verificades. Inclou `bio_curta` truncada a 120 caràcters i
      imatge `lastfm_image_large`. `cache_for_anon(3600s)`.
- [x] `GET /api/v1/artistes/descoberta/?limit=6` — artistes
      `aprovat=True` aprovats els darrers 30 dies amb almenys una
      cançó verificada que mai han aparegut a `TopSetmanal`. Capat
      a 12. `cache_for_anon(3600s)`.

**Backend — extensions a endpoints existents**:
- [x] `GET /api/v1/albums/` (nou llistat — abans només existia
      `/api/v1/albums/<slug>/`). Filtres: `ordering=-data_llancament`
      o `data_llancament`, `amb_verificades=true|false`, `limit≤24`.
      Retorna `n_verificades` i `imatge_url` per àlbum.
- [x] `GET /api/v1/top/?oficial=true&limit=N` — força resposta des
      de `TopSetmanal` (sense fallback a `TopProvisional`); buida
      explícitament si encara no hi ha top oficial. `limit` capat a
      `MAX_POSICIONS_TOP` (40).

**Frontend — `HomePage.jsx` reescrita completament**:
Deu seccions verticals amb fons alternat ink/blanc per crear ritme
sense línies divisòries. Tots els colors via tokens `tq-*` o
`var(--mm-color-*)`; els colors territorials viuen al diccionari
`TERR_COLORS` (mapping de marca documentat al fitxer).
1. **Hero** — pitch principal, 3 blocs (top/mapa/comunitat) amb
   icones `mm-design/icons/ui/`, 2 CTAs i link discret a
   `/com-funciona`.
2. **Stats** — tres números prominents amb tipografia editorial.
3. **Top oficial PPCC** — primeres 10 entrades amb cue de tendència
   (`badge-new`, `arrow-up-trend`, `arrow-down-trend`, `dash-stable`).
4. **Cançó nova de la setmana** — targeta gran amb caràtula 280px.
5. **Artista destacat** — imatge circular, badge territorial amb
   icona pròpia, bio truncada.
6. **Últims llançaments** — grid 3×2 d'àlbums amb caràtula i
   recompte de cançons verificades.
7. **Artistes en descoberta** — grid 3×2 amb territoris i gènere.
8. **Territori en focus** — rotació setmanal mitjançant
   `isoWeek(now) % FOCUS_TERRITORIS.length`. Mostra el badge SVG
   territorial gros + top-3 oficial d'aquell territori + recompte
   d'artistes aprovats. Link a `/artistes?territori=<codi>`.
9. **Notícies de la comunitat** — només autenticats; 3 publicacions
   més recents en estat `publicat` via `/comunitat/publicacions/`.
10. **Compte enrere** — peu discret amb temps fins el proper
    dissabte a les 9h, amb estats per dissabte/diumenge.

**Llenguatge i to**:
- "Vols fer música amb algú?" → "Vols trobar algú amb qui fer música?"
  a la CTA del hero (`HomePage.jsx`).
- Resta de textos del Sprint H revisats; ja eren en primera persona
  del plural i to comunitari.

**Verificacions**:
- `manage.py check`: ✅ net.
- `pytest -q`: 125 passed, 8 skipped.
- `npm run build`: ✅ net (1.12 MB JS / 312 kB gz; +2,5 kB respecte
  Sprint H per la nova home).
- `systemctl reload topquaranta-web`: ✅. Smoke test 200 a `/` i
  resposta vàlida a tots els endpoints nous (`/api/v1/stats/`,
  `/api/v1/top/nova-setmana/`, `/api/v1/artistes/destacat/`,
  `/api/v1/artistes/descoberta/`, `/api/v1/albums/?...`,
  `/api/v1/top/?...&oficial=true`).

### Sprint J ter — FilterPanel a /artistes + scroll mòbil a taules staff ✅ (2026-04-26)

> Petit follow-up: portar el patró de FilterPanel staff al públic de
> /artistes i resoldre que les taules staff no es desplaçaven a mòbil.

- [x] `StaffTable.Table` ara embolcalla la `<table>` en un `div`
      `overflow-x-auto` amb `min-w-[640px]`, donant scroll horitzontal
      a totes les pàgines staff a mòbil sense canvis per pàgina.
- [x] `ArtistesPage` reescrita per fer servir `FilterPanel` staff
      (popover amb badge de comptador + Apply / Restablir / Cancel·lar).
      Cerca + botó "Cercar" segueixen inline al hero. Cascada
      territori/comarca/municipi i 3 toggles dins el panell.
- [x] Re-auditoria axe-core: 0 violacions a 10 URLs.
- [x] `pytest -q`: 132 passed / 8 skipped.

### Sprint J bis — Redisseny editorial /top, /artistes, /mapa, /comunitat ✅ (2026-04-26)

> Aplicar el llenguatge editorial de la HomePage (bandes
> alternants ink/blanc, kicker + títol Playfair, tone-aware) a la
> resta de pàgines públiques. Extreure primitives compartides per
> reduir duplicació i evitar regressions.

**Components compartits nous** (`web-react/src/components/editorial.jsx`):
- `<Section tone>` — banda full-bleed amb fons ink/blanc.
- `<SectionHeader kicker title>` — kicker tone-aware (groc sobre
  ink, ink/60 sobre blanc) + títol Playfair.
- `<TerritoriBadge codi>` — SVG monocrom via mask, hereta
  `currentColor`.
- `<TrendCue posicio posicio_anterior>` — cue de tendència estàndard
  per a totes les llistes de top.
- `TERR_COLORS`, `TERRITORI_NOM`, `FOCUS_TERRITORIS` — taules de
  marca exposades una vegada.

`HomePage.jsx` i `TopPage.jsx` migrades a aquests imports;
~120 línies de duplicació eliminades.

**Backend**:
- [x] `/api/v1/top/` ara retorna `prev_setmana` + `next_setmana`
      (ISO o `null`) calculats sobre el territori resolt després
      del fallback. Permet al SPA habilitar/deshabilitar les
      fletxes del navegador setmanal de manera correcta.

**TopPage** (`/top`):
- Hero ink: kicker "El nostre top setmanal" + títol gegant
  ("Top {territori}", e.g. "Top Global"), pills de territori,
  navegador setmanal amb fletxes ←/→ deshabilitades als límits +
  link "Tornar a l'última →" quan no estàs a la setmana actual.
  Pill "Provisional" si el top és provisional.
- Llista en banda blanca: 40 entrades en 2 columnes (1-20 / 21-40)
  amb `TopRow` compartit.
- Banda peu ink discreta amb link a `/com-funciona`.
- URL: `?t=<codi>` + `?s=<YYYY-MM-DD>` (totes dues opcionals).

**ArtistesPage** (`/artistes`):
- Hero ink: kicker "Directori", títol "Artistes", recompte total.
  Filtres dins el hero: cerca per nom + pills territorial + dropdowns
  cascada (comarca / municipi) + 3 toggles (amb dones / llançaments
  últim any / amb cançons al top) + "Netejar filtres".
- Resultats en banda blanca: grid de 4 columnes amb `ArtistaCard`
  (caràtula quadrada o monograma de territori, nom, localitat,
  badges de territori amb icona, gènere). Paginació al peu amb
  botons ink.

**MapaPage** (`/mapa`):
- Hero ink: kicker "Mapa" + títol "La música al territori" + 3
  línies d'explicació concisa de la interacció.
- Mapa + panell lateral en banda blanca, sense canvis funcionals.
- Eliminat el panell d'introducció en línia (quedava redundant).
- KPI principal del panell ara `text-tq-ink` en comptes de
  `text-tq-yellow-deep` (era 3.6:1 sobre blanc — fail WCAG AA per
  text gran serif).

**ComunitatPage** (`/comunitat`):
- Sense bandes full-bleed (la pàgina viu dins `ComunitatLayout`
  amb sidebar; les bandes ink/blanc xocarien).
- Targeta-hero al capdamunt amb pitch + CTA dependent d'estat
  (Activar perfil / Explora directori).
- Pills de filtre amb `role="tablist"`/`role="tab"`/`aria-selected`.
- Vista anònima amb la mateixa shape (targeta-hero + dos botons
  Feed públic / Registra't).
- Estat-badges del feed amb tons que passen 4.5:1 sobre blanc.

**ComunitatDirectoriPage** (`/comunitat/directori`):
- Targeta-hero al capdamunt (mateixa shape que `ComunitatPage`).
- Tots els controls de filtre amb `<label>` (alguns `sr-only`
  perquè la primera opció ja fa de label visualment).

**Llenguatge i a11y**:
- "Catalunya" / "País Valencià" / etc. mantinguts. Només "PPCC" →
  "Global" al text visible. Els camps i query params interns es
  mantenen com `PPCC`.
- 5 violacions de contrast detectades i corregides per la auditoria
  axe-core sobre 10 pàgines públiques (color-contrast a `text-white/40`
  sobre ink, `text-tq-ink/40`/`/50` sobre blanc, `text-tq-yellow-deep`
  sobre blanc, `text-white opacity-80` sobre brand colors,
  brand colors com text d'enllaç sobre tq-ink).
- Re-auditoria final: **0 violacions a 10 URLs** (`/`, `/top`,
  `/top?t=cat`, `/artistes`, `/mapa`, `/comunitat`,
  `/comunitat/public`, `/com-funciona`, `/artista/zoo`,
  `/compte/accedir`).

**Tests**:
- Nou `web/tests/test_home_views.py` — 7 casos cobrint stats,
  destacada (fallback a #1, biggest-climber tie-breaker),
  descoberta (diversitat per territori), destacat (requereix
  gestor verificat), top oficial sense fallback, prev/next
  setmana. **132 passed, 8 skipped** total.

**Verificacions**:
- `manage.py check`: ✅ net.
- `pytest -q`: 132 passed / 8 skipped.
- `npm run build`: ✅ net (1.13 MB JS / 313 kB gz).
- `systemctl reload topquaranta-web`: ✅ 200 a totes les URLs
  públiques esmentades.
- axe-core (puppeteer): 0 violacions sobre 10 URLs.

### Sprint M — Naming consolidation: "ranking" → "top" ✅ (2026-04-25)

> Unificar el lèxic del projecte sota un sol mot canònic ("top",
> alineat amb la marca TopQuaranta) sense trencar dades, URL públiques
> ni APIs externes.

- [x] **Pas 1 — UI** (5 strings, 4 fitxers): "Ranking prov." → "Top
      provisional"; "rànquing" → "top" al `RankingBreakdownPanel`;
      títols staff actualitzats.
- [x] **Pas 2 — URLs API**: `/api/v1/top/` (canònica) + 301 des de
      `/api/v1/ranking/` (GET-only, query string preservat).
      Endpoints staff (`/staff/top/`, `/staff/top/accio/`,
      `/staff/cancons/<pk>/top/`) amb alias POST-safe a les rutes
      antigues. SPA route `/staff/top` + `<Navigate>` legacy.
- [x] **Pas 3 — Fitxers Python**: `ranking_views.py` →
      `top_views.py`, `web/api/staff/ranking.py` → `staff/top.py`,
      `scripts/simular_ranking.py` → `simular_top.py`. Imports
      actualitzats.
- [x] **Pas 4 — Funcions/constants**: `calcular_ranking_territori`
      → `calcular_top_territori`, `_calcular_ranking_ppcc` →
      `_calcular_top_ppcc`, `_ranking_for_territoris` →
      `_top_for_territoris`, `territoris_amb_ranking_propi` →
      `territoris_amb_top_propi`, `ranking_list/_accio` →
      `top_list/_accio`, `canco_ranking_breakdown` →
      `canco_top_breakdown`, `RANKING_TERRITORIS` →
      `TOP_TERRITORIS`, `_ranking_last_modified/_etag` →
      `_top_last_modified/_etag`. Aliases legacy a
      `staff/__init__.py`.
- [x] **Pas 5 — Models** (alt risc, fet amb `pg_dump` previ +
      migració manual `ranking 0013_rename_models_to_top` amb
      `RenameModel` ops): `RankingSetmanal` → `TopSetmanal`,
      `RankingProvisional` → `TopProvisional`. Taules SQL renombrades
      via `ALTER TABLE … RENAME TO …` (502 files preservades sense
      pèrdua). Aliases legacy a `ranking/models.py`. App label
      `ranking` mantingut intencionalment (renaming-lo afecta
      ContentType i 30+ migracions; sprint propi futur).
- [x] **Pas 6 — Command** `calcular_ranking` → `calcular_top`.
      Cron + tq-recover actualitzats. Status files antics queden
      orfes a `/var/log/topquaranta/status/` (logrotate els netejarà).
- [x] **Pas 7 — Logs**: `provisional.log` → `top-provisional.log`,
      `ranking.log` → `top.log`. Symlinks de compatibilitat per
      preservar historial. logrotate.d actualitzat.
- [x] **Pas 8 — Icona**: `icon-ranking.svg` no s'usa al SPA — cap
      canvi necessari.
- [x] **Pas 9 — Documentació**: substituïdes les ocurrències de
      "rànquing"/"ranquing" a CLAUDE_*.md, ROADMAP.md, README.md.

**Mètriques globals**:
- Fitxers tocats: ~30 (codi + docs + ops).
- Ocurrències canviades: ~150+ (textos UI: 5; URLs SPA: 8; Python:
  112 imports/refs; cron/log: 6).
- Migracions noves: 1 (`ranking 0013_rename_models_to_top`).
- Tests: 118/8 (sense regressions).
- Backup pre-rename: `/tmp/topquaranta_pre_rename_*.sql` (28 MB).

**Coses no canviades intencionalment**:
- App label `ranking` (cost desproporcionat: ContentType + 13
  migracions + cascada FKs reverse).
- Carpeta `ranking/` (lligada a l'app label).
- Prefix DB tables `ranking_*` (idem).
- Related-name `Canco.rankings` (back-reference; canviar-lo trenca
  filters arreu del codi).
- Comentaris i docstrings amb la paraula "ranking" en context
  algorítmic (terme tècnic correcte en anglès).
- `CLAUDE_EXCELLENCE.md` i `CLAUDE_LEGACY.md` deixats parcialment
  intactes (referència històrica, prioritat baixa).

### Sprint L — Metadata d'artista des de Last.fm ✅ (2026-04-25)

> Enriquir les fitxes d'artista amb dades públiques de Last.fm i
> aprofitar la xarxa de `getSimilar` per descobrir artistes
> propers als nostres aprovats.

- [x] 14 camps `lastfm_*` nous a `Artista` + `nb_similars_lastfm`
      (migració `music 0050`).
- [x] Client Last.fm ampliat amb `get_artist_info(artist_name)` i
      `get_artist_similar(artist_name, limit=100)`. Mateix patró
      retry/rate-limit que `get_track_info`.
- [x] Nou command `obtenir_metadata_lastfm` (`--limit`,
      `--artista-id`, `--refresh-days`, `--dry-run`). Cua de
      prioritat aprovat → pendent → discartat, oldest sync first.
      Idempotent per recencia (no toca dues vegades el mateix
      artista en menys de 7 dies).
- [x] Cron diari 05:00 UTC (`obtenir_metadata_lastfm --limit 500`),
      en paral·lel amb Whisper. ~3 minuts per cua plena.
- [x] Staff: columna `Similars LFM` a `StaffArtistesPage` i
      `PendentsPage`; filtre `font_descoberta=lastfm_similar` i
      sort `?sort=similars_lastfm` a Pendents; nou panell
      `LastfmPanel` (lectura) a `ArtistaEditPage` amb url, bio,
      listeners, playcount total, ontour, tags, imatges, last sync.
- [x] Documentació: `CLAUDE_MODELS.md` (camps + migració),
      `CLAUDE_PIPELINE.md` (§3.8 + cron table), aquest ROADMAP.

---

## Shelved indefinitely

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
