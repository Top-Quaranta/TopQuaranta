# Auditoria de la capa de vistes staff — redisseny de la distribució

Data: 2026-06-08. Read-only (codi). Cap canvi de codi ni dades.

---

## 1. CASA — el patró canònic de les vistes de llista staff

Referència: `web-react/src/components/staff/StaffTable.jsx` (+ `FilterPanel.jsx`,
`StaffLayout.jsx`). Adoptants canònics: `StaffCanconsPage.jsx`,
`StaffArtistesPage.jsx`. **27 de 29 pàgines staff importen aquest kit.**

### Esquelet de pàgina (de dalt a baix)
Dins `StaffLayout` (pane `px-6 lg:px-12 py-6` sobre `bg-tq-ink`), una pàgina
de llista és un `<section>` amb aquest ordre fix:
1. `<PageHeader title subtitle right />` — h1 blanc sobre el fons fosc; `subtitle` = recompte de files o `'Carregant…'`; slot `right` per a accions.
2. **Barra de filtres** — `flex flex-wrap items-center gap-2 mb-3`: `<Input className="flex-1 min-w-[14rem]">` (cerca) + chip ràpid opcional + `<FilterPanel>`.
3. **Barra d'accions massives** (condicional) — `bg-tq-yellow/90 text-tq-ink rounded p-2`, només si hi ha files seleccionades.
4. **Missatge d'estat** — `text-sm text-white/80 mb-3`.
5. **Taula** — `<TableCard><Table>…</Table><Pagination meta onPage/></TableCard>`.

### Components compartits (tots a `StaffTable.jsx`)
- `TableCard` — superfície blanca `bg-white text-tq-ink rounded-lg border border-black/5`.
- `Table` / `THead` (`bg-tq-ink/5 text-[11px] uppercase`) / `Th` / `Td` / `Tr` (hover `bg-tq-yellow/10`, cursor si `onClick`).
- `Pill {tone}` — tons semàntics via vars mm-design: `green` (aprovat/verificat), `red` (rebutjat/inactiu), `yellow`/`gray`/`ink`. **Mai hex hardcoded.**
- `Btn {tone,size}` — `primary` (ink+yellow), `secondary`, `outline`, `danger` (red-600), `ghost`.
- `Input` / `Select` — `border-tq-ink/20 focus:ring-2 focus:ring-tq-yellow`.
- `Pagination {meta,onPage}` — Anterior/Següent + "Pàg X de N · T entrades"; null si 1 pàgina.
- `PageHeader`, `EmptyState` (`px-3 py-6 opacity-60 text-center`), `Field` (label de filtre).
- `FilterPanel` — calaix col·lapsable amb badge groc del nº de filtres actius; Restablir/Cancel·lar/**Aplicar** explícit (no fetch per tecla); tanca amb clic-fora/Escape.

### Convencions
- **Filtres → query params**: `DEFAULTS` a nivell de mòdul; `applied` sembrat des de l'URL (`useSearchParams`), deep-links compartibles; fetch construeix `URLSearchParams({q, …filtres, sort, page})`. Params típics: `verificada`, `ml_classe`, `whisper`, `aprovat`, `territori`, `sort`. Chip ràpid per al filtre més comú (p. ex. "Últims 7 dies").
- **Cerca**: `Input` lligat a `q`, reseteja `page=1`; les pàgines canòniques NO fan debounce (sí `PendentsPage` amb `useDebounced 250`).
- **Paginació**: backend `_paginate` (`web/api/staff/_common.py`) → `paginate` (`web/api/utils.py`), default 50, **tope 200**; meta `page/num_pages/total/has_next/has_previous`.
- **Ordenació**: no hi ha capçaleres clicables; `<Select name=sort>` dins el FilterPanel amb tokens d'ordre del backend (`-data_llancament`, `nom`, …). Columna condicional segons el sort actiu.
- **Càrrega**: sense spinner; `data=null` fins al primer fetch, subtitle `'Carregant…'`, maps guardats amb `data?.results?.map`.
- **Buit**: fila `colSpan=N` amb `<EmptyState>Cap …</EmptyState>` (català curt).
- **Tokens**: `tq-ink` `#0a0a0a`, `tq-yellow` `#facc15`, `tq-yellow-deep`. Text blanc sobre fons fosc; cards blanques. Muted: `opacity-60`/`text-tq-ink/70`/`text-white/70`. Cel·les `px-3 py-2`; gaps `mb-3`/`mb-4`/`gap-2`. `tabular-nums` a columnes numèriques. Tot `<Select>`/checkbox amb `aria-label`.

---

## 2. DIVERGÈNCIA — on la distribució se separa de la casa

### `StaffSocialPage.jsx` — 1162 línies, un sol component monolític
Importa només `{Table, Select, Input}` del kit (línia 17); **ignora** `PageHeader`, `TableCard`, `THead/Th/Tr/Td`, `Pill`, `Btn`, `Pagination`, `EmptyState`, `FilterPanel`, `Field`. ~10 àrees de concern en una sola ruta: credencials IG, banner mestre, fase, story-cap, graella de 6 canals, credencials Mastodon/Bluesky/Telegram, nota newsletter/RSS, calendari setmanal (taula bespoke), enllaç Insights, `<pre>` de stdout, **llista de SocialPost**, galeria de slides.

**Visual (classes ad-hoc en lloc de Pill/Btn token-driven):**
- `STATUS_TONE` paleta crua (`bg-emerald-100/text-emerald-900`, `bg-red-100`, `bg-yellow-100`, `bg-gray-200`) + `StatusBadge` propi (línies 19-35) en lloc de `Pill`.
- `EFECTIU_TONE` paleta crua (38-42).
- Botons mestre `bg-red-700/bg-emerald-700` (594-595); toggles de canal igual (711-712); "Esborrar" `bg-red-700` (502); save `bg-tq-yellow…hover:bg-tq-yellow-deep` (555, 759, 802, 846) en lloc de `Btn`.
- **Tints per plataforma** `bg-pink-50/indigo-50/sky-50/cyan-50/amber-50/orange-50` (983-991) — una paleta que no existeix enlloc més del panell.
- Accions de la llista com a spans-botó `bg-gray-100/amber-100/red-100` (1028-1086).
- `<input border-gray-300>` cru a credencials IG (530, 547) tot i que el mateix fitxer usa `Input` més avall (incoherent intern).

**Estructural:**
- Sense `PageHeader`: header fet a mà (455-463), títol fosc-sobre-blanc dins un `<section>` blanc (454) en lloc del header blanc-sobre-ink de la casa.
- La llista de SocialPost usa `<Table>` (959) però amb `<thead>/<tr>/<th>` i `<tr>/<td>` crus (960-1095) → perd l'estil de capçalera `bg-tq-ink/5` i el hover/cursor de `Tr`.
- Calendari setmanal: `<table>` bespoke a part (884-920), ni embolicat en `<Table>`.
- Buit fet a mà `<p>` (1108-1112) en lloc de `EmptyState`.
- Sub-rutes existeixen (`/social/esborrany`, `/social/spotify`) però control+credencials+llista+preview segueixen fusionats a la ruta pare.

**UX:**
- La llista de SocialPost **NO té filtres, ni cerca, ni ordre, ni paginació** — es bolca sencera (`results`, 972). Les llistes de la casa sempre tenen FilterPanel + Pagination.
- Concerns barrejats: kill-switch + fase + 4 formularis de credencials + 2 taules + consola stdout + galeria, amb la llista operativa enterrada sota ~900 línies de config.
- Galeria de slides com a fila `colSpan` expansible dins la taula (1096-1102) — layout que la `Table` de la casa no fa mai.

### `StaffSocialSpotifyPage.jsx` — 419 línies, **la divergència més gran**
Una de les **dues úniques** pàgines staff que NO importen `StaffTable`. Usa una altra família (`components/ui/Alert` + `components/ui/Button`) i està construïda **blanc-sobre-fosc** (`text-white`, `bg-tq-ink-soft`, `border-white/10`) — l'invers de la convenció casa (card blanca sobre ink). Dues taules bespoke (`PlaylistRow`/`PlaylistTable`, 48-112) amb `<table>`/`<th>`/`<td>` crus. Badges `bg-green-600/red-600/white-20` (183-194). Sense `PageHeader`/`TableCard`/`Pill`/`Table`.

### `NewsletterDraftPage.jsx` — 236 línies, la més propera
Importa només `Input`; `ESTAT_TONE` paleta crua (17-21), header a mà (111-117), badge cru (120-125), `bg-red-700` cancel (210). Usa els tokens tq-* però salta els components compartits. Diverge, menys greu.

**Resum:** la distribució és el racó menys homogeni del panell. `StaffSocialPage` és un monòlit de 1162 línies que reimplementa a mà gairebé tot; `StaffSocialSpotifyPage` usa una família de components i una paleta invertida diferents; `NewsletterDraftPage` és la més alineada però encara salta el kit.

---

## 3. DADES PER A UNA TAULA DE PUBLICACIONS (estil casa)

**Font canònica única: `SocialPost`** (`social/models.py:17-93`). Una fila per `(platform, tipus, territori, setmana)` (unique_together). **Tots els canals hi escriuen, inclosa la newsletter** (`enviar_newsletter.py:117-135` fa `get_or_create(platform=newsletter)`, `status=publicat`, `published_at`, `metadata={summary,editat}`). El `NewsletterDraft` és NOMÉS estat editorial, no s'ha de comptar com a publicació.

| Columna taula | Camp SocialPost | Notes |
|---|---|---|
| Data | `published_at` (o `publication_date` derivat a `_serialize`) | clau d'ordre principal |
| Canal | `platform` (6 valors + `TERRITORI_LABEL` PPCC→"Global") | RSS NO hi és (pull-based) |
| Estat | `status` (`pendent`/`publicat`/`error`/`omes`) | → `Pill` tons green/gray/red/gray |
| Objectiu | `tipus` (`top_ppcc`/`top_territorial`/`nous_albums`/`nous_singles`) + `territori` | |
| Setmana | `setmana` (dilluns ISO) | |
| Enllaç | `metadata.external_id` (complet) / `instagram_media_id` (truncat 80) | **veure forat** |

**Endpoints existents reutilitzables:**
- `social_list` (`web/api/staff/social/posts.py:32`) — `results=[_serialize(p)][:200]`, ordre `published_at desc nulls_last`. **Tope 200, sense paginació/filtres** → caldria afegir `_paginate` + filtres per a la taula casa.
- `social_estat_canals` (`posts.py:98`) — últim enviament per canal + estat de pausa, amb fallback `StaffAuditLog *_publicat` a prova de reset.
- `_serialize` (`_common.py:36-59`) ja emet `pk, platform, tipus, territori, territori_label, setmana, publication_date, project_week, status, instagram_media_id, error_msg, scheduled_at, published_at, metadata`.

**Forat (enllaç):** no hi ha cap URL clicable normalitzada. Per plataforma: Mastodon = URL directa; **Bluesky = AT URI** (`at://…`, cal convertir a `bsky.app/profile/<did>/post/<rkey>`); Telegram = `metadata.url` (+`message_ids`); **Instagram = media id** (cal crida Graph extra per al permalink); Newsletter = cap. Una taula unificada necessita un constructor d'URL per plataforma (lògica ja parcialment present al path de delete, `posts.py:524-551`).

---

## 4. SPOTIFY — dades i estat existents

| Dada | On viu | Què expressa |
|---|---|---|
| Identitat OAuth (`SpotifyAuth`, `music/models.py:1416`) | `spotify_estat` (`web/api/staff/social/spotify.py:226`) → pàgina §1 | refresh-token, user id, scope, `product` en viu (gate premium), display_name/country |
| Sync per playlist (`SpotifyPlaylist:1451`) | `_playlist_payload` (`spotify.py:155`) → §2 | last sync time/ok/msg, matched/tracks, cobertura post-sync + `target_coverage` predictiu, `spotify_url` |
| Enriquiment per Canço (`SpotifyMetadata:1535`) | `_target_coverage` (`spotify.py:85`, per playlist) + `_spotify_enrichment_stats` (`web/api/staff/estat.py:440`, catàleg) | `found/not_found/not_attempted`; `LOCKED_STATUSES`=pushable; cobertura public vs pending; ETA backlog (`not_attempted/50-dia`) |
| Cron silenciat | `_read_cron_silenced` (`spotify.py:187`, llig `deploy/cron-meta.json`) | si les alertes de `actualitzar_playlists_spotify` estan mutades |

`SpotifyPlaylist.kind`: `top`/`novetats`/`no_verificades`/`novetats_per_verificar`; `freq` `daily`/`weekly`.
**Forat:** la cobertura d'enriquiment catàleg (`_spotify_enrichment_stats`) es mostra al dashboard `estat`, **NO** a `StaffSocialSpotifyPage` (que només mostra KPIs de sync per playlist + identitat). "Incloure Spotify" pot voler dir: (a) estat OAuth/premium, (b) salut de sync de les playlists, (c) cobertura d'enriquiment del catàleg — tres coses distintes que avui viuen en dos llocs.

---

## 5. PROPOSTA — subdividir la distribució en sub-vistes coherents

Encaix amb la navegació actual (grup "Distribució" a `StaffLayout.jsx:95-107`, avui Social + Spotify). Proposta de 4 sub-rutes germanes sota `/staff/social/*`, totes amb el patró-casa (`PageHeader` + `TableCard`/`Table` + `Pill`/`Btn` + `FilterPanel`/`Pagination`):

1. **Controls i canals** (`/staff/social` — cockpit aprimat)
   Només els controls operatius: banner mestre (`distribucio_activa`), graella dels 6 canals amb estat efectiu + últim enviament (de `social_estat_canals`), fase IG, story-cap. Mou les **4 formularis de credencials** a una secció col·lapsable o a `/staff/social/credencials` (treu ~350 línies del cockpit). Tot amb `Pill`/`Btn`.

2. **Publicacions** (`/staff/social/publicacions` — la taula casa, NOVA)
   Taula de TOTES les publicacions des de `SocialPost` via `social_list` ampliat amb `_paginate` + filtres (`FilterPanel`: canal, estat, tipus, setmana) + cerca + ordre + `Pagination`. Columnes: Data · Canal (Pill) · Tipus/Objectiu · Setmana · Estat (Pill) · Enllaç (constructor d'URL per plataforma) · Accions (`Btn`: re-publicar/eliminar-remot/reset). Substitueix la llista bolcada actual.

3. **Esborrany & newsletter** (`/staff/social/esborrany` — ja existeix, alinear)
   Mantén la pàgina de revisió + vista prèvia; aplica-hi `PageHeader`/`Pill`/`Btn` (avui salta el kit). Opcionalment una mini-llista d'esborranys per setmana (de `NewsletterDraft`) amb `Table`.

4. **Spotify** (`/staff/social/spotify` — ja existeix, reescriure a casa)
   Reescriure de la família `ui/Alert`+`ui/Button` (blanc-sobre-fosc) al kit casa: `PageHeader` + `TableCard`/`Table` per a les playlists, `Pill` per a OK/cobertura, `Btn` per a Authorize/Sync. **Afegir-hi** la cobertura d'enriquiment del catàleg (`_spotify_enrichment_stats`), avui només al dashboard.

**Ordre de feina suggerit (cap aquí, per a un futur PR):** (1) extreure components compartits ja existeixen — només cal usar-los; (2) la taula de Publicacions és la peça de més valor i la més "casa"; (3) Spotify és la reescriptura més gran (família + paleta diferents). Cada sub-vista és un canvi acotat amb guard de no-regressió (snapshot de columnes / `assertNumQueries` al `social_list` paginat).

Cap acció presa (read-only).
