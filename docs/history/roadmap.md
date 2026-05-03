# ROADMAP.md — TopQuaranta

> Estat actual i propers passos. El detall fi viu al `git log` i als
> commits per sprint; la història de Phase 9 (auditoria d'excel·lència)
> al fitxer `docs/history/roadmap.md` (sprints A–J ter).
> Last updated: 2026-05-03.

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
- **DB**: PostgreSQL 14, 38 taules (nova `Album.last_album_check`).
  Volums actuals (2026-05-03): ~1.9k artistes aprovats, ~2.5k cançons
  verificades, 5 territoris amb top oficial actiu.
- **ML**: 79 features, ROC-AUC 0.9994 (post Whisper + MB).
- **Infra**: Caddy + gunicorn :8083 amb `ExecReload=HUP`.
- **Distribució**: 6 canals actius o configurables — Instagram,
  Mastodon, Bluesky (carrusel 4 imatges), Telegram (media-group),
  newsletter, RSS. Esborrat remot real per a tots des de
  `/staff/social`.

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

**Estadístiques per canal** (sense vulnerar el manifest):
- [ ] Camp nou `SocialPost.metrics_snapshot` (JSON) + cron diari
      `recollir_metrics` que demana a cada API el rendiment del
      post de la setmana anterior:
      - **Instagram**: `/{media-id}/insights?metric=reach,impressions,
        likes,comments,shares,saved` (Graph API).
      - **Mastodon**: `/api/v1/statuses/:id` retorna
        `reblogs_count`, `favourites_count`, `replies_count`.
      - **Bluesky**: `app.bsky.feed.getPostThread` per al `repost_count`,
        `like_count`, `reply_count`.
      - **Telegram**: `getMessage` per al view count (només si el bot
        és admin del canal).
      - **Newsletter**: open-rate/click-rate via Brevo `/v3/smtp/
        statistics/aggregatedReport` filtrat per tag setmanal.
      - **RSS**: comptador de hits a `/rss/{top,novetats}.xml` via
        GoAccess (Sprint K — analytics ètica).
- [ ] Pàgina staff `/staff/social/metrics` amb gràfica per canal
      (4 setmanes) + comparativa setmana actual vs mitjana.
- [ ] Email digest setmanal (dilluns) als admins amb el resum de
      la setmana publicada (top 3 posts + canal amb millor
      engagement, sense PII).

**Neteja de pendents col·labs brossa** (caçat 2026-05-03):
- [ ] Comand `netejar_pendents_no_ppcc` que rebutgi automàticament
      Artistes amb `font_descoberta=collaborador` + `aprovat=False`
      + sense localitats PPCC + sense cançons pròpies + sense
      activitat staff. Aplicar primer en dry-run; mostrar comptador
      al panell `/staff/estat`.
- [ ] A `_upsert_track` (i `obtenir_novetats._create_track`):
      saltar la creació automàtica de pendents col·lab quan
      l'artista origen té un Deezer profile mixt (heurística:
      `nb_album > 30` + diversos labels al primer mostreig). Així
      no inundem la cua MB amb soroll com el cas Àlex Pérez 1479910.

**Refinaments del renderer** (post-feedback usuari):
- [ ] **Slides de novetats**: re-aplicar el patró readability v3
      (font sizes + tighter top padding) a `_feed_album_slide` i
      `_feed_singles_slide`, que han quedat amb les mides antigues.
- [ ] **Stories CTA** (`_story_cta`): veure si la mida del títol
      «Top complet a» queda balancejat amb el nou volum del títol
      cançó (80 pt). Possiblement bumpar de 56 → 64.
- [ ] **Portada novetats**: aplicar el +54 px de marge esquerre
      també a `_feed_novetats_portada` *si* es decideix mantenir
      el patró (ara mateix ja està aplicat — verificar visualment).
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
- [ ] **Plantilla d'alt-text** més rica: ara «Top CAT, posicions
      1-10» — a11y guidelines diuen que cal donar context. Provar
      «Top setmanal de cançons en català de Catalunya — posicions
      1 a 10: 1 Tutu Turú de Siderland, 2 Estrelles de Max
      Navarro…». Fa l'alt-text més útil per a screen-readers.
- [ ] **Programació flexible**: avui el calendari és fix (Sat
      09:30 IG → 09:40 Mastodon → …). Posar el delay configurable
      a `ConfiguracioGlobal` perquè staff pugui escampar més o
      condensar segons el comportament observat (Insights diuen
      "publica al matí" o "no agrupes" segons cas).
- [ ] **Re-publicar amb correcció**: si una cançó del top resulta
      ser rebutjada *després* de publicar el post, hauríem de
      tenir un botó "Re-publicar" que (a) esborra el post remot,
      (b) re-genera amb el top corregit, (c) re-publica. Avui
      això és un seguit manual de Esborrar + Reset + Publicar.

**A11y + i18n**:
- [ ] Text alternatiu de les imatges al carrusel IG (l'API ho
      permet via `alt_text` al moment d'`upload_carousel_item`).
      Avui només Mastodon i Bluesky tenen alt-text.
- [ ] Verificar contrast de tots els colors de territori sobre
      les pastilles del slide list (alguna fila tinta vs
      `COLOR_TEXT_MUTED` pot quedar baix-contrast).

### 2. Sprint K — Analytics ètica (interna)

> Mètriques agregades sense vulnerar el manifest. GoAccess sobre
> logs Caddy + comptadors interns + UTM convention.

- [ ] GoAccess cron diari → `/var/www/analytics/index.html` (privat).
- [ ] Model `MetricaEsdeveniment(data, clau, comptador)` + middleware
      que incrementa pageviews per pàgina pública.
- [ ] `register_event(clau)` cridat des dels endpoints clau
      (registre completat, proposta enviada, feedback enviat).
- [ ] Pàgina staff `/staff/analytics` amb gràfics setmanals.
- [ ] Convenció UTM documentada (`?utm_source=instagram&utm_campaign=top-YYYY-wWW`).
- [ ] Documentació al `docs/product/definition.md` i `/legal/privacitat`
      sobre què mesurem internament.

### 3. Backlog menor

Items petits per fer en sessions curtes:

- [ ] Snapshot baseline del model RF abans del proper retrain (`cp
      ml_model.joblib ml_model.baseline-YYYY-MM-DD.joblib`) per A/B
      sobre el set de 48 clips si el nou retrain regredeix.
- [ ] Test coverage 52% → 70%. Gaps coneguts: `music/services.py`,
      `music/verificacio.py`, `ranking/senyal.py`. Sessions curtes a
      estones lliures.
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

## Sprints — completats

Resum d'una pantalla per sprint. Per ordre alfabètic per facilitar
la cerca; les dates al títol indiquen la cronologia real. Per al
detall fi: `git log` per fitxer o pel rang de dates.

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
