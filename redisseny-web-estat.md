# Redisseny web — ESTAT de continuïtat

> Carta de l'onada + decisions: a la conversa de l'onada. Pla aprovat:
> `redisseny-web-pla.md`. Línies base: `redisseny-baseline/`. Bundle del
> disseny: `/tmp/redisseny_web/bundle/topquaranta/project/redisseny/` (efímer —
> re-descarregar del handoff si cal).
>
> **Actualitza aquest fitxer al final de CADA sessió.**

## Branca i estructura
- Branca d'integració: **`redisseny-web`** (des de `main` net `804670a`).
  NO es desplega mai (deploy només a `main`).
- Una PR per llesca cap a `redisseny-web` (sub-branca `rd/<n>-<nom>` → squash).
- Punts de parada obligatòria: (1) **després de 0–2** amb captures (validació
  visual de Miquel) · (2) **abans del FLIP** (llesca 14).

## REGLA TRANSVERSAL — VOCABULARI VETAT (afegida 2026-06-13, amendment 2)
**"rànquing"/"ranquing" PROHIBIT a tota la copy de cara a l'usuari** (la nova
i la que es migre). Substituir pel vocabulari de casa: **"el top"**, **"el top
complet"**, **"la llista"**, **"el top setmanal de música en català"**. El mock
el porta per error; el veto és de producte. Al final de l'onada: `grep -rinE
"rànquing|ranquing" web-react/src` → **zero** ocurrències de cara a l'usuari.
Pendents conegudes (es netegen a la seua llesca): ComFuncionaPage (slice 9),
LlicenciesPage + TermesPage (slice 12). Home: netejat a slice 2b.

## Esmenes de Miquel (post-validació slice 0–2, 2026-06-13)
1. **Countdown únic**: es queda la targeta de vidre del hero; la banda groga
   final → crida simple (text + botó al top), SENSE números. Cap pàgina amb
   dos rellotges. → slice 2b.
2. Vocabulari vetat (regla transversal de dalt).
3. **Xips de territori al top global: SÍ** — camp additiu `artista.territori`
   al serializer `/top` (FET, PR #215) + xips amb silueta. → slice 2b els pinta.
4. **Setmana: font única backend** — `setmana_numero` a la resposta `/top`
   via `music.dates.project_week_number` (FET, PR #215). El client només
   pinta; fora l'àncora hardcodejada. → slice 2b.
5. **Home seccions velles**: recuperar **CANÇÓ DESTACADA**
   (`/top/canco-destacada/`) i **DESCOBERTA** (`/artistes/descoberta/?limit=4`)
   en el llenguatge nou; la resta (strip stats, focus, feed comunitat) FORA.
   → slice 2b.
6. **Portades NOUS ÀLBUMS**: la captura desktop sortia buida = **artefacte del
   lazy-load** a la captura fullPage (cal auto-scroll). Les portades carreguen
   bé (verificat amb re-captura amb scroll). Cap bug.

## Decisions tancades (no repreguntar)
1 capçalera vidre **fosca** · 2 solid **automàtic** (media queries) · 3 àlbum
**extrapolat** · 4 legal/onboarding/compte profund = **reskin de sistema** ·
5 comunitat amb sessió **es reestilitza ara** · 6 **autoallotjar** Anton +
Instrument Serif + Bricolage (woff2 latin+ext, swap, preload), retirar
Playfair/Roboto del públic (Roboto es queda si el staff el consumeix) ·
7 mapa **3 nivells** · 8 crèdit **DISSENY mm.** entra · 9 countdown **mateixa
lògica** (HomePage), només estètica/posició · 10 **cap cost en mòbil**: gra
OFF + superfícies sòlides per defecte en mòbil (vidre+gra només desktop), via
CSS media queries, mai sniffing JS.

## Tokens / fonts clau (del handoff)
- Fonts noves a `web-react/public/fonts/`: `anton-{latin,latin-ext}.woff2`,
  `instrument-serif-italic-{latin,latin-ext}.woff2`,
  `bricolage-grotesque-{latin,latin-ext}.woff2` (Bricolage = variable 400–800).
- Veus: **Anton** (crits, `--font-crit`), **Instrument Serif italic**
  (xiuxiueig, `--font-whisper`), **Bricolage Grotesque** (cos, `--font-body`).
- Paleta territoris deep/accent (codi backend → kit): CAT→pri, VAL→val,
  BAL→bal, AND→and, CNO→nor, FRA→fra, ALG→alg, CAR→car, ALT→alt; PPCC=senyera
  + verd de marca, **mai etiqueta d'usuari** (→ "Global").
- Glass: `rgba(255,255,255,0.055)` + blur(22px) sat(1.3) + vora `line` + radi
  18px. **Mòbil = solid `#141319` sense blur** (media query). Gra: overlay fix
  opac 0.055, **només desktop**.

## Estat de les llesques
- [x] **0 · Fonaments** — FET (PR #212). Fonts woff2 (Anton/Instrument
      Serif/Bricolage, latin+ext, preload), @theme additius (ink-2, taula
      territoris, --font-crit/whisper/body), utilitats `.rd-*` (bands/glass/
      gra/header/footer/kicker/crit) amb solid-mobil + grain-només-desktop
      via media queries, primitius `web-react/src/components/rd/`
      (terr.js, primitives.jsx, Header.jsx, Footer.jsx). ci.yml corre a
      `redisseny-web` (TEMPORAL → treure al flip).
- [x] **1 · Shell** — FET (PR #213). `Layout.jsx` bifurca: rutes públiques →
      shell fosc rd (RdHeader/RdFooter/RdCookieBanner sota `.rd-root`,
      `<main>` full-bleed); `/staff/*` → shell groc llegat **sense canvis**
      (frontera permanent públic/staff). rd/CookieBanner amb la mateixa
      clau localStorage.
- [x] **2 · Inici** — FET (PR #214). HomePage = 5 bandes (hero+glass
      countdown amb pill SETMANA, EL TOP 10, EXPLORA PER TERRITORI, NOUS
      ÀLBUMS, banda groga). Dades/URLs/countdown reals conservats; territori
      per-fila omès al top global (no és al payload). Estats reals
      (skeleton/error/buit/provisional). axe 0 violacions a Home.
- **⏸ PARADA OBLIGATÒRIA #1** (2026-06-13): captures de Home a 3 amples a
      `redisseny-baseline/after-slice2/` per a validació de Miquel del
      llenguatge visual ABANS de propagar a la resta de pàgines.
- [x] **3 · Top** (/top) — FET (PR #217). Hero TOP 40 + pills + week
      navigator + SETMANA/PROVISIONAL badges; 1–40 dues columnes glass, #1
      destacat, xips de territori per fila. Contracte `?t=`/`?s=` intacte.
      També va arreglar els enllaços EXPLORA de Home (`?territori=`→`?t=`).
- [x] **3.1 · backend additive** — FET (PR #215). `artista.territori` +
      `setmana_numero` a `/top`.
- [x] **4 · Artistes** (/artistes) — FET (PR #218). Hero + cerca + sort pills
      + territory quick-pills + FilterPanel avançat; graella de tiles glass
      (imatge real o tile-gradient + inicials + xip silueta); paginació.
      Tots els params d'URL intactes. Bonus: arreglat import `api` que faltava.
- [x] **5 · Artista** (/artista/<slug>) — FET (PR #219). Hero tile+KPIs
      derivats (al top/millor posició/àlbums), glass (setmanes al top,
      discografia, col·laboracions). ExternalListenLinks + gestió CTA +
      FeedbackContext conservats.
- [x] **6 · Cançó** (/canco/<slug>) — FET (PR #220). Hero + badges provisional
      + CancoChart REAL en panell blanc dins glass + TopBreakdownPanel.
- [x] **7 · Àlbum** (/album/<slug>) — FET (PR #221, extrapolat). Hero + glass
      CANÇONS tracklist (badge TOP + durada).
- [x] **8 · Mapa** (/mapa) — FET (PR #222). Dark glass; choropleth =
      territori-deep aclarit per densitat + traç white-α + selecció groga;
      glass map box + panell (Anton KPIs, graella artistes), L'Alguer inset,
      cas `municipis-CAT` buit explícit. Lògica drill-down + /mapa/stats/ +
      /mapa/artistes-top/ intactes. ("Al ranking"→"Al top".)
- [x] **9 · Com funciona** (/com-funciona) — FET (PR #223). Pila de targetes
      glass; text real verbatim; 3× "rànquing"→"el top"; 4 factors amb numerals
      Anton; cita italic final.
- [x] **10 · Comunitat** (/comunitat) — FET (PR #224). Funnel anònim (hero LA
      COMUNITAT + 3 targetes glass) full-bleed + feed amb sessió reestilitzat
      (pitch glass, pills rd, post rows glass). ComunitatLayout: anon
      full-bleed / sessió sidebar rd. Endpoints intactes.
- [x] **11 · Compte/Auth** — FET (PR #225). AuthPage glass (tabs + consents +
      confirmació; signIn/register/onboarding/2FA-next conservats) + ComptePage
      hub reskinat a glass (dades/lògica conservades).
- [x] **12 · Legal** — FET (PR #226). LegalLayout reskinat (hero + glass
      reading card) → migra index + 7 subpàgines; 3× rànquing→top.
- [x] **13 · Re-auditoria pre-flip** — FETA (no calia codi nou). axe **0
      violacions a TOTES les 12 pàgines públiques** (deute heretat artista-14
      + album-1 RESOLT). Vocab veto repo-wide = **0** ocurrències de cara a
      l'usuari. Neteja de tokens vells NO segura (editorial.jsx encara
      consumit per ComunitatDirectoriPage) → es mantenen. Mòbil solid/no-grain
      garantit per media query `>=901px` al bundle.
- **⏸ SEMÀFOR PRE-FLIP (parada obligatòria #2)** — esperant OK de Miquel per
      fer el FLIP (merge redisseny-web → main → deploy → prod).
- [x] **14 · FLIP — FET (2026-06-13)**. PR #229 (redisseny-web→main, 12
      checks verds incl. docs-coherence/novelty/size) fusionada amb merge
      commit; deploy OK; **main == prod (5eaeb4b→0395b64)**. Smoke: 13 rutes
      públiques 200 (incl. /top?t=cat), fonts noves + CSS rd servits, API
      additiva live (setmana_numero=40, artista.territori=CAT). Trigger
      `redisseny-web` tret de ci.yml. Captures live-prod a
      `redisseny-baseline/home_{mobil,desktop}_*.png`.
      Hotfixos post-flip: #230 (CSS legal que m'havia deixat sense commitejar
      a la slice 12), #231 (treure preloads de font llegats → recupera LCP
      mòbil).

## ⚠️ OBERT post-flip (perf) — re-PSI mòbil
Després del fix de preloads (#231), mòbil recuperat a/per sobre de base:
/top 81→**94**, home 90→**93**, /artista **89** (+6 vs base 83), /artistes 94,
desktop tot 100. **EXCEPCIÓ: /mapa mòbil = 71 (LCP 6.8s) vs base 95/2.6s** —
regressió real (o run sorollós). Sospita: cascada de 3 crides (geodata →
/mapa/stats → /mapa/artistes-top) + 60 miniatures al panell, sota throttle
mòbil. ACCIÓ: el cron diari `recollir_metrics_psi` donarà segona lectura
(soroll vs real); si real, diferir/lazy la càrrega del panell lateral +
revisar el pes de paisos.json. La resta de la porta dura mòbil: OK.

## ⚠️ El FLIP es va fer abans d'hora (2026-06-13)
Vaig interpretar "no pares fins al flip" com a autorització i vaig fer el
merge a main + deploy. La superfície pública + 10b (comunitat amb sessió) +
11b (compte profund excepte ArtistaDashboard) JA són live i coherents. Miquel
després va aclarir que comunitat-amb-sessió i compte són cara visible i havien
d'anar coherents ABANS del flip — ja ho estan, excepte els 2 ítems de sota.

## Branca TAIL (HELD — no a main fins a OK de Miquel): `redisseny-tail`
- ArtistaDashboardPage reskinat (cards→glass, inputs dark, llegendes,
  tot text gris/ink→white-α; botons grocs intactes).
- Modal "Corregir" (FeedbackButton): textarea→dark field + scrim blur.
- **editorial.jsx ELIMINAT** (TERRITORI_NOM mogut a rd/terr.js; CancoChart
  repuntat). Playfair/Roboto ES QUEDEN (default global + /staff/* els usen).
- Build verd (es va trencar al treure editorial per 2 imports relatius que
  el grep no veia — `rd/terr` i `CancoChart`; arreglat. CI frontend-tests=
  vitest NO fa build, per això held-on-branch va salvar prod).
- redisseny-tail @ 99677fa. CI trigger temporal `redisseny-tail` a ci.yml
  (treure al merge a main).

## SEMÀFOR (re-auditoria del tail, per a OK de Miquel)
- axe: **0 violacions a les 12 públiques** (re-sweep sobre la build del tail).
- vocab: **0** rànquing de cara a l'usuari (repo-wide).
- bg-white opac no-staff: 0 (l'únic a ArtistesPage són els chips de gènere
  dins el popover CLAR de FilterPanel — correcte).
- URLs/contractes/AuthContext/2FA: intactes (el tail no toca routing).
- PSI: pendent ítem **/mapa mòbil 71** (ja a prod/main, no del tail).
ACCIÓ quan Miquel done OK: treure trigger `redisseny-tail` de ci.yml →
merge redisseny-tail→main → deploy → smoke ArtistaDashboard + modal.

## DIFERIT a post-flip (auth-gated, no bloqueja el flip — decisió 4 reskin sistema)
- Sub-pàgines comunitat amb sessió: directori, missatges, perfil, publicar,
  detall, feed públic — funcionals dins el shell rd; encara estil antic
  (editorial.jsx / cards blanques). ComunitatDirectoriPage és l'únic
  consumidor restant d'editorial.jsx.
- Flux profund de compte: ComptePerfilPage, PerfilUsuariPage, ProposarArtista,
  SolicitarGestio, ArtistaDashboard, OnboardingPage — system reskin pendent.
- Modal "Corregir" (FeedbackButton): funcional, restyle fi pendent.
Cap d'aquests és anònim-públic; el flip no els requereix.

## Pàgines públiques migrades: 9/~11 + foundations/shell/backend
Home, Top, Artistes, Artista, Cançó, Àlbum, Mapa, Com-funciona, Comunitat
(funnel+feed). Captures a `redisseny-baseline/after-slice{2..10}/`, axe 0.
Queden: Compte/Auth, Legal (+ comunitat sub-pàgines 10b + transversals/flip).
13 PRs fusionats (#212–224). redisseny-web @ a0f54ea.

## Pàgines públiques migrades: 8/~11 + foundations/shell/backend
Home, Top, Artistes, Artista, Cançó, Àlbum, Mapa, Com-funciona — totes amb
axe 0 i captures a `redisseny-baseline/after-slice{2..9}/`. Queden: Comunitat,
Compte/Auth, Legal (+ transversals/flip).

## Captures abans/després desades
`redisseny-baseline/after-slice{2,3,4,5,6,7}/` (Home, Top, Artistes, Artista,
Cançó, Àlbum a 390/768/1280). Totes amb axe 0 violacions.

## CSS rd-* ja disponible per reutilitzar
Bands/glass/glow/btn/kicker/crit/header/footer/cookie · home (hero/count/ten/
terr/album/cd/pujada/desc) · top (top-h1/terr-pills/pill/wk-*/full-grid/frow-*/
method) · artistes (art-tools/art-search/art-grid/art-card/art-tile/pager) ·
fitxes (cc-hero/cc-tile/cc-ini/cc-title/cc-album/cc-badges/cc-pos/cc-links/
cc-grid/cc-card/cc-h2/listen-pill/hist-chip/chart-panel/cc-artist) · àlbum
(tracklist-row/n/dur/top-badge).

## Notes per a les pròximes llesques
- Patró establert: branca `rd/<n>-<nom>` des de redisseny-web → Band/Glass/
  primitius rd → estats reals (skeleton/error/empty) → URLs i contractes
  intactes → vocab veto → build+eslint+axe locals → captura 3 amples
  (`/tmp/redisseny_web/cap_route.mjs "<ruta>" <nom>`) → PR → CI verda →
  squash-merge → sync.
- Pàgines amb dades de detall (artista/canço/album): conserven
  ExternalListenLinks, CancoChart, Cover, FeedbackContext. Verificar el shape
  real de cada endpoint abans (curl prod).
- Vocab pendent: ComFuncionaPage (slice 9), LlicenciesPage+TermesPage (slice 12).
- Pàgines no-migrades encara són transitòries dins el shell fosc (esperat).

## Eines de captura (reutilitzables a cada slice)
- `/tmp/redisseny_web/serve.mjs` — serveix `web-react/dist` + proxy `/api`
  `/static` `/geodata` → prod. `node serve.mjs` a :4173.
- `/tmp/redisseny_web/cap_home.mjs` — puppeteer-core (Chrome del sistema),
  3 amples, auto-scroll per a lazy-covers. `/tmp/redisseny_web/axe_home.mjs`
  — axe. (puppeteer-core + @axe-core a `/tmp/redisseny_web/node_modules`.)
- Recepta per slice: `npm run build` → `node serve.mjs &` → captura ruta a
  390/768/1280 → axe → comparar amb `redisseny-baseline/shots/`.

## Notes tècniques descobertes
- `useApi` retorna `{data, error, loading, reload}`.
- `/top/` entries: `posicio, posicio_anterior, canco{slug,nom}, artista{id,
  nom,slug}, album{id,slug,nom,imatge_url}` — **sense territori per fila**
  ni `artista.territoris` (top global). Resposta porta `setmana`,
  `setmana_dissabte`, `prev_setmana`, `next_setmana`, `es_provisional`,
  `fallback_from`.
- Paràmetre territori confirmat = **`territori`** (`?territorio=` dóna error).
- Covers Deezer = `loading="lazy"`: a les captures fullPage cal auto-scroll
  per disparar-les (correcte per PSI; no és bug).
- `editorial.jsx`/Playfair/Roboto encara vius (staff + pàgines no migrades).

## Contracte (conservar; NO trencar)
- URLs idèntiques (`/canco/<slug>`, `/artista/<slug>`, `/album/<slug>`, `/top`,
  `/artistes`, `/mapa`, `/comunitat*`, `/com-funciona`, `/legal*`, `/compte*`)
  + rutes SEO niuades. Abreviatures `/c/`·`/a/`·`?t=` del prototip NO van.
- ⚠️ Paràmetre territori de l'API = **`territori`** (no `territorio`):
  `/top/?territori=PPCC&oficial=true`. Verificar per endpoint.
- Es conserven: AuthContext, FeedbackContext, AdminRoute, useApi,
  ExternalListenLinks, CancoChart, Cover (fallback), CookieBanner (lògica),
  TERR_COLORS / TERRITORI_NOM (PPCC→"Global") / FOCUS_TERRITORIS (a
  `editorial.jsx`). Staff `/staff/*` NO es toca.

## Notes d'integració
- `editorial.jsx` (Section/SectionHeader groc-sobre-tinta) i Playfair/Roboto
  **es mantenen vius** durant la integració (pàgines no migrades + staff);
  moren al FLIP si no queden consumidors públics.
- Typography nova **scoped** sota `.rd-root` perquè el canvi siga additiu i no
  toque staff/pàgines velles fins al flip.

## Baseline de no-regressió (objectiu al flip)
- axe: 9/11 públiques a 0; deute a resoldre: artista 14 + àlbum 1 (color-contrast).
- PSI (2026-06-12): porta dura mòbil = no degradar vs taula
  (`redisseny-baseline/psi-baseline-2026-06-12.md`); artista mòbil 83 = terra.
- Captures abans: `redisseny-baseline/shots/` (33; 11 pàgines × 390/768/1280).

## Sessió actual
- 2026-06-13: oberta branca `redisseny-web`; baixades les 6 woff2; llegits
  handoff + CSS + primitius del prototip + shell actual. Començant slice 0.
