# Redisseny web pública — PLA (FASE 1, recon · NOMÉS-LECTURA)

> Estat: **recon completa, cap codi, cap branca.** Font de veritat: el bundle de
> Claude Design `redisseny/TopQuaranta - Web (Redisseny).html` + el handoff
> `design_handoff_redisseny_web/README.md` (exhaustiu: 11 pantalles, tokens,
> mapa secció→endpoint). Bundle desat a `/tmp/redisseny_web/bundle/` (efímer);
> el handoff README és la referència canònica.
>
> Línies base de no-regressió desades a `redisseny-baseline/` (33 captures a 3
> amples + `axe-summary.json` + `psi-baseline-2026-06-12.md`). Data: 2026-06-12.

---

## 1. ABAST DEL DISSENY

El bundle redissenya **la cara pública** de topquaranta.cat portant-la al
llenguatge del kit de xarxes (tinta + gra, Anton/Instrument Serif/Bricolage,
groc `#facc15`, paleta de territoris deep/accent, superfícies de "vidre").
Tots els components del prototip són **responsive** (README §Responsive: 1
columna ≤900px, nav→hamburguesa, graelles 2col→1col, ajustos ≤540px), o siga
**desktop + mòbil** per a cada pantalla coberta.

### Pàgines COBERTES (amb fitxer de prototip)

| # | Pantalla | Ruta producció | Prototip | Desktop | Mòbil |
|---|---|---|---|---|---|
| 1 | Capçalera (persistent) | (shell) | `tq-app.jsx` | ✅ | ✅ (hamburguesa) |
| 2 | Inici | `/` | `tq-home.jsx` | ✅ | ✅ |
| 3 | Top 40 + setmanes | `/top` | `tq-top.jsx` | ✅ | ✅ |
| 4 | Directori d'artistes | `/artistes` | `tq-artistes.jsx` | ✅ | ✅ |
| 5 | Mapa SVG 3 nivells | `/mapa` | `tq-mapa.jsx` | ✅ | ✅ |
| 6 | Comunitat (funnel anònim) | `/comunitat` | `tq-comunitat.jsx` | ✅ | ✅ |
| 7 | Com funciona | `/com-funciona` | `tq-comunitat.jsx` | ✅ | ✅ |
| 8 | Fitxa de cançó | `/canco/<slug>` | `tq-canco.jsx` | ✅ | ✅ |
| 9 | Fitxa d'artista | `/artista/<slug>` | `tq-artista.jsx` | ✅ | ✅ |
| 10 | Accés/Registre + compte | `/compte/accedir`, `/compte` | `tq-compte.jsx` | ✅ | ✅ |
| 11 | Transversals: footer, cookie, modal "Corregir", indicador de moviment, fallback de portada | (globals) | `tq-app/ui/compte` | ✅ | ✅ |

> **Mostra (MOSTRA, mana l'API real):** dades de la setmana 39 (`top-data.js`),
> la trajectòria de la cançó, la setmana anterior "reconstruïda", la sessió
> simulada, i les xifres del mapa per **comarca/municipi** (el prototip només
> porta dades reals a **nivell de territori** — nota honesta al panell). El
> nivell **municipi del mapa** no s'inclou al prototip (geometria pesada); la
> SPA actual SÍ que el té → es manté.

### Pàgines de la SPA actual que el disseny NO cobreix

| Ruta(es) | Què és | Tractament proposat |
|---|---|---|
| `/album/<slug>` (`AlbumPage`) | **Fitxa d'àlbum** | ❌ **Cap mock.** Extrapolar del llenguatge de cançó/artista (vegeu §7 Q3). |
| `/legal`, `/legal/{avis-legal,privacitat,cookies,termes,codi-conducta,llicencies,accessibilitat}` | 8 pàgines legals | ❌ Cap mock. **Reskin de sistema** (tokens + vidre + tipografia), sense disseny a mida. |
| `/com-funciona` | text real | El disseny la cobreix com a **pila de targetes**; el **text** és el real de `ComFuncionaPage.jsx` (es manté). |
| `/onboarding` (`OnboardingPage`) | alta primer cop | ❌ Cap mock. Reskin de sistema. |
| `/compte/perfil`, `/comunitat/perfil` (`ComptePerfilPage`, `PerfilUsuariPage`), `/compte/artista/{proposta,gestio}`, `/compte/artista/<slug>` (dashboard) | flux de compte profund | ❌ Cap mock. Integrar amb el llenguatge nou (CTA "Sol·licita'n la gestió" SÍ que apareix a la fitxa d'artista). |
| `/comunitat`, `/comunitat/{perfil,missatges,directori,publicar,public,:pk,:pk/editar}` **amb sessió** | feed/directori/DM reals | El disseny només dissenya el **funnel anònim**; amb sessió diu "substituïu per les vistes reals existents **reestilitzades**". |
| `/staff/*` (≈45 rutes) | tot el panell staff | ❌ **Fora d'abast.** Sistema visual propi (`StaffLayout` + mm-design). No es toca. |
| `/compte/callback`, `/spotify/callback`, `/staff/social/spotify/callback` | callbacks OAuth | Mecàniques, sense UI rellevant. |

---

## 2. FORATS D'ESTATS (el disseny porta dades de mostra; la SPA real necessita més)

Els components del prototip **no gestionen cap estat asíncron** (verificat:
0 referències a loading/error/empty a `tq-home/canco`, 1 a `top/artista/
artistes`, 4 a `mapa` —i són la nota "dades de mostra"). Cada forat és una
**decisió**: *Extrapolar* del sistema de disseny (recomanat per defecte) o
*Demanar peça* a Claude Design.

### Transversals (totes les pàgines)
| Estat | Disseny? | Decisió |
|---|---|---|
| Carregant (skeleton/spinner) | ❌ | **Extrapolar**: skeletons de vidre amb el mateix radi/espaiat. |
| Error d'API | ❌ | **Extrapolar**: targeta de vidre amb missatge + reintentar. |
| `prefers-reduced-motion` | parcial (README ho menciona) | **Extrapolar**: desactivar translacions/compte enrere animat. |
| Fallback de rendiment (`surfaces-solid`) | ✅ (variant al CSS) | Implementar amb `prefers-reduced-transparency` (vegeu §7 Q2/Q10). |

### Per pàgina
- **Inici**: compte enrere **post-dissabte 9h** ("Top publicat avui" — ja existeix a `HomePage`); stats a zero/absents; setmana encara **provisional** (`es_provisional`); feed de comunitat **buit**. → Extrapolar (la lògica ja viu a `HomePage`).
- **Top**: setmana **buida**/provisional (badge); **top curt** (<40 i <10 files); **`fallback_from`** (territori sense rànquing propi que cau a un altre — l'API ho retorna, cal avís visible); navegador de setmana als **límits** (sense prev/next); territori **sense dades**. → Extrapolar; el `fallback_from` mereix copy explícit.
- **Artistes**: cerca **sense resultats**; paginació carregant; filtres que donen **buit**; artista **sense imatge** (inicials — el disseny ja ho cobreix); gèneres absents. → Extrapolar.
- **Artista**: **sense foto** (inicials — cobert); **sense cançons al top**; **sense àlbums nous**; sense bio/gènere/xarxes; estats del CTA gestió (ja gestionat / pendent). → Extrapolar.
- **Cançó**: **sense portada** (fallback tile — cobert); **sense trajectòria** (entrada nova: el prototip mostra mostra → cal estat buit real); "també al top" **buit**; territori desconegut. → Extrapolar.
- **Àlbum** (`/album`): **cap disseny de partida** → l'estat sencer és extrapolació (§7 Q3).
- **Mapa**: territori **sense dades**; **`municipis-CAT.json` no existeix** (README ho marca → estat buit explicatiu, mai error); KPIs comarca/municipi carregant; **L'Alguer** en inset; zona **sense artistes**. → Extrapolar; el cas `municipis-CAT` és obligatori.
- **Comunitat**: anònim vs **amb sessió**; directori **buit**; feed **buit**. → Reestilitzar vistes reals.
- **Compte/Auth**: error de login; **rebot 2FA staff** (a pàgina Django); carregant. → Integrar amb `AuthContext`/flux existent.

---

## 3. INVENTARI DE L'ACTUAL

### 3.1 Rutes i URLs públiques (CAP es pot trencar)
Públiques (sense auth): `/` · `/top` · `/artistes` · `/artista/:slug` ·
`/album/:slug` · `/canco/:slug` · `/artista/:artistaSlug/:albumSlug` (SEO) ·
`/artista/:artistaSlug/:albumSlug/:cancoSlug` (SEO) · `/mapa` · `/com-funciona`
· `/legal` + 7 subpàgines (`/legal/{avis-legal,privacitat,cookies,termes,
codi-conducta,llicencies,accessibilitat}`) · `/privacitat`→redirect ·
`/compte/accedir` · `/comunitat` + `/comunitat/public` + `/comunitat/:pk`.
Auth/compte: `/compte`, `/compte/perfil`, `/compte/artista/{proposta,gestio}`,
`/compte/artista/:slug`, `/onboarding`, callbacks OAuth.
Staff: `/staff/*` (≈45, darrere `AdminRoute` + 2FA).

> ⚠️ El prototip fa servir **abreviatures** (`/c/…`, `/a/…`, `?t=codi`); a
> **producció es mantenen les rutes actuals** (`/canco/<slug>`, `/artista/<slug>`,
> `/top?territori=…`) i les **rutes SEO niuades**. Cap canvi d'URL.

### 3.2 Sistema d'estils actual vs disseny
- **Actual**: Tailwind v4 amb `@theme` a `web-react/src/index.css`. Tokens
  `--color-tq-{yellow,ink,…}`, semàntics (success/warning/danger/neutral amb
  variants `-deep` AA), `--font-display: 'Playfair Display'`,
  `--font-sans: 'Roboto'` (**woff2 autoallotjats**, latin + latin-ext,
  `font-display: swap`, preload a `index.html`). Importa `mm-design`
  `colors.css`+`spacing.css` (no `typography.css`). Sense CSS modules ni
  styled-components. Tema groc via `body[data-theme="yellow"]`.
- **Disseny**: mateix patró (Tailwind v4 `@theme`) però **canvia el llenguatge
  sencer**: fons **tinta + gra**, **3 famílies noves** (Anton/Instrument
  Serif/Bricolage — al prototip via Google Fonts; **a producció s'han
  d'autoallotjar** com Playfair/Roboto), taula de **territoris deep/accent**,
  superfícies **vidre**. Tokens nous a afegir al `@theme`: `--color-tq-ink-2`,
  `--color-terr-{pri,val,bal,nor,fra,and,alg,alt,car}-{deep,accent}`,
  `--font-crit` (Anton), `--font-whisper` (Instrument Serif), `--font-sans`
  (Bricolage). **Additiu**: els tokens vells (Playfair/Roboto) es mantenen
  mentre hi haja consumidors (staff), i moren al flip si no en queden.

### 3.3 Components reutilitzables vs a substituir
- **Es mantenen (contracte, no UI)**: `AuthContext`, `FeedbackContext`,
  `AdminRoute` (2FA), `useApi`, `ExternalListenLinks` (pills d'escolta reals),
  `CancoChart` (trajectòria — recharts), `Cover` (fallback), `CookieBanner`
  (lògica localStorage), `MmIcon`/siluetes de territori (`vendor/mm-design/
  icons/territories/territory-*.svg`, `fill=currentColor`).
- **Se substitueixen (llenguatge visual)**: `editorial.jsx`
  (`Section`/`SectionHeader`/`TerritoriBadge`/`TrendCue` groc-sobre-tinta) →
  primitius nous (Header, Footer, Glass, Numeral, Kicker, TerrLogo, Move,
  Cover-fallback). **Es conserven els mapatges de dades** d'`editorial.jsx`:
  `TERR_COLORS`, **`TERRITORI_NOM` (PPCC→"Global")**, `FOCUS_TERRITORIS`.
- **Layout**: `Layout.jsx` (shell públic) → capçalera/peu/gra nous.
  `ComunitatLayout`/`StaffLayout` són sistemes a part.

### 3.4 Contractes amb l'API que NO es toquen
`/top/?territori=…&oficial=true[&setmana=]` (retorna `entries[]` amb
`canco/artista/album` niuats + `posicio`, `posicio_anterior`, `setmana`,
`prev_setmana`, `next_setmana`, `es_provisional`, `fallback_from`) ·
`/top/canco-destacada/` · `/artistes/?q,territori,comarca,municipi,genere,
amb_dones,nou,al_top,sort,page` · `/artistes/:slug/` · `/artistes/descoberta/`
· `/albums/:slug/` · `/cancons/:slug/` · `/stats/` ·
`/mapa/stats/?level&parent&territori` · `/mapa/artistes-top/?territori,comarca,
municipi,limit` · `/localitzacio/{comarques,municipis}/` · `/auth/me|login|
logout` · comunitat/missatges/feedback existents · GeoJSON estàtic a
`web-react/public/geodata/`.

> ⚠️ **Mismatch de paràmetre a verificar**: el handoff escriu `territori=`; la
> API en viu accepta `territori=` (confirmat: `?territorio=` dóna error). Els
> filtres d'artistes també usen `territori`. Confirmar nom exacte per endpoint
> a la implementació (no trencar el contracte).

---

## 4. LÍNIES BASE DE NO-REGRESSIÓ (capturades ara — `redisseny-baseline/`)

### 4.1 axe (WCAG 2a/2aa/21a/21aa, desktop 1280) — `axe-summary.json`
**9 d'11 pàgines públiques: 0 violacions.** Deute existent (no empitjorar; el
sistema nou té contrast AA documentat → idealment **resoldre-ho**):
- **`/artista/<slug>`**: 1 regla `color-contrast` (serious), **14 nodes**.
- **`/album/<slug>`**: 1 regla `color-contrast` (serious), **1 node**.
- 0 violacions: home, top, artistes, canço, mapa, comunitat, com-funciona,
  accedir, legal.

### 4.2 PSI / CWV (servidor `MetricaCWV`, 2026-06-12) — `psi-baseline-2026-06-12.md`
| URL | desktop (score/LCP/CLS) | mòbil (score/LCP/CLS) |
|---|---|---|
| `/` | 99 / 968ms / 0.036 | 93 / 2820ms / 0.000 |
| `/top` | 100 / 533ms / 0.032 | 96 / 2552ms / 0.047 |
| `/artistes` | 100 / 807ms / 0.000 | 95 / 2565ms / 0.000 |
| `/artista/<slug>` | 98 / 1064ms / 0.040 | **83 / 4216ms / 0.078** |
| `/canco/<slug>` | 100 / 773ms / ~0 | **89 / 3506ms / 0.021** |
| `/mapa` | 100 / 536ms / 0.004 | 95 / 2589ms / 0.000 |

Punts febles a vigilar: **artista mòbil 83 (LCP 4.2s)** i **canço mòbil 89**.
Riscos nous de rendiment: **gra a tota la pàgina + `backdrop-filter: blur(22px)`**
(vidre) en mòbil.

### 4.3 Captures abans/després — `redisseny-baseline/shots/` (33 PNG)
11 pàgines públiques × 3 amples (**mòbil 390 · tauleta 768 · desktop 1280**):
home, top, artistes, artista (`/artista/rosalia`), canço
(`/canco/rosalia-divinize`), àlbum (`/album/lux`), mapa, comunitat,
com-funciona, accedir, legal. Aquestes són el "abans" per al abans/després.

---

## 5. ESTRATÈGIA D'INTEGRACIÓ (proposada)

### 5.1 Com es fa el tall sense convivència visible
**Branca d'integració de llarga vida `redisseny-web`** amb llesques internes
(una PR per llesca cap a la branca d'integració), i **UN sol flip a `main`** al
final, quan **tota la superfície pública** estiga convertida. Motiu: la
capçalera/peu/gra nous viuen al **shell compartit `Layout.jsx`** que també
embolcalla legal/compte/comunitat; si es fes pàgina a pàgina cap a `main`,
es veuria capçalera nova + cos vell dins una mateixa pàgina (convivència). El
flip mou tot el shell + totes les pàgines públiques alhora.

- Els **tokens nous són additius** (`@theme`): les pàgines no-redissenyades i
  el staff segueixen funcionant durant la integració.
- Les pàgines **sense mock** (àlbum, legal, onboarding, compte profund) reben
  un **reskin de sistema** (tokens + vidre + tipografia via els primitius nous)
  perquè el flip no deixe cap pàgina pública amb l'estil vell.

### 5.2 Ordre de llesques proposat
0. **Fonaments**: estendre `@theme` (ink-2, taula de territoris, 3 famílies
   autoallotjades woff2 latin+latin-ext), utilitats `.glass`/gra (+ variant
   `solid`), primitius nous (Header, Footer, Glass, Numeral, Kicker, TerrLogo,
   Move, Cover-fallback). Sense flipar cap pàgina.
1. **Shell**: Header + Footer + `Layout` (gra, cookie banner reestilitzat).
2. **Inici** · 3. **Top** · 4. **Artistes** · 5. **Artista** · 6. **Cançó** ·
   7. **Àlbum** (extrapolat) · 8. **Mapa** (SVG real + correcció d'aspecte
   `x·cos(41.5°)≈0.745`, cas `municipis-CAT` buit) · 9. **Com funciona** (text
   real) · 10. **Comunitat** (funnel anònim + reskin vistes amb sessió) ·
   11. **Compte/Auth** (pestanyes + hub + reskin flux profund) ·
   12. **Legal** (reskin de sistema).
13. **Transversals + tancament**: modal "Corregir", `prefers-reduced-motion`,
    fallback `surfaces-solid`, **re-auditoria axe**, **re-PSI**, neteja de
    tokens/components vells sense consumidors.
14. **FLIP**: `redisseny-web` → `main` (squash o fast-forward), després
    eliminar `editorial.jsx` vell + Playfair/Roboto **només si** no queden
    referències (el staff pot dependre de Roboto → comprovar i, si cal,
    mantindre).

### 5.3 Com es revisa
Servidor de dev local (`npm run dev` a `web-react/`) + **captures
multi-viewport** (els mateixos 3 amples) a cada PR de llesca, **abans/després**
contra `redisseny-baseline/shots/`. axe per pàgina a cada llesca pesada.

### 5.4 Un sol sistema d'estils al final (DRY)
Els **tokens del disseny** (a `index.css @theme`) són la **font única**;
`editorial.jsx` vell i els tokens Playfair/Roboto **moren al flip** si no
queden consumidors públics. El staff (`StaffLayout` + mm-design) roman com a
**sistema a part** (fora d'abast). Resultat: la web pública = un sol
llenguatge; el panell staff = el seu.

### 5.5 Estimació honesta
- Fonaments + shell: **1–2 sessions**.
- Pàgines pesades (home, top, artistes, artista, canço, mapa): **~0,5–1
  sessió cadascuna** (mapa la més arriscada per la projecció + estats).
- Reskins lleugers (àlbum, legal, compte profund, comunitat amb sessió):
  **~0,5 sessió cadascun**.
- Tancament (transversals + re-auditoria + flip): **1 sessió**.
- **Total realista: ~9–13 sessions** fins al flip net.

---

## 6. REGLES DURES A VERIFICAR (a cada llesca + abans del flip)

1. **URLs idèntiques.** `/canco/<slug>`, `/artista/<slug>`, `/album/<slug>`,
   `/top`, `/artistes`, `/mapa`, `/comunitat*`, `/com-funciona`, `/legal*`,
   `/compte*` + rutes SEO niuades. Les abreviatures `/c/`·`/a/`·`?t=` del
   prototip **no** van a producció.
2. **PPCC mai com a etiqueta d'usuari** → "Global" via `TERRITORI_NOM`; mai una
   fila/pill de territori (usa l'art de la senyera + verd de marca).
3. **Accessibilitat ≥ línia base.** 9/11 pàgines a 0 violacions: mantindre-ho;
   **resoldre** els `color-contrast` d'artista (14) i àlbum (1). Vigilar el
   text de baixa opacitat nou (`txt-60`/`txt-45`) i accent-sobre-tinta → AA.
4. **PSI sense degradació significativa** vs la taula §4.2; atenció especial a
   **artista/canço mòbil** i al cost de **gra + blur** (oferir `solid`).
5. **El mapa segueix funcionant**: GeoJSON real, 3 nivells, `/mapa/stats/` +
   `/mapa/artistes-top/`, cas `municipis-CAT` buit sense error.
6. **La comunitat segueix funcionant**: feed/directori/DM reals, només
   reestilitzats; el funnel anònim no trenca el flux amb sessió.

---

## 7. PREGUNTES OBERTES per a Miquel (decisions de producte)

1. **Capçalera per defecte**: el disseny per defecte és **capçalera de vidre
   fosca**; hi ha una variant Tweak "**capçalera groga**" (continuïtat amb la
   web actual). Quina és la de producció — fosca o groga?
2. **Superfícies vidre vs solid**: el "vidre" (blur 22px) per defecte té cost
   en mòbil. Volem detectar-ho automàticament (`prefers-reduced-transparency`
   / gamma baixa → `solid`) o **un interruptor d'usuari**? (El `tweaks-panel`
   és només del prototip.)
3. **Fitxa d'àlbum** (`/album/<slug>`): **no té disseny**. Extrapolar del
   llenguatge de cançó/artista (recomanat) o **demanar peça** a Claude Design?
4. **Legal + onboarding + compte profund**: n'hi ha prou amb un **reskin de
   sistema** (tokens + vidre, sense mock a mida)? O alguna mereix disseny propi?
5. **Comunitat amb sessió** (feed/directori/missatges): **reestilitzar-ho tot
   ara** dins aquesta onada, o mantindre-ho funcional i reestilitzar en una
   onada posterior?
6. **Tipografies**: confirmes **autoallotjar** Anton + Instrument Serif +
   Bricolage (latin + latin-ext) i **retirar Playfair/Roboto del públic**?
   (Roboto el pot usar encara el staff → si és així, es manté per al staff.)
7. **Mapa — nivell municipi**: la SPA actual ja té 3 nivells (territori→
   comarca→municipi). El prototip va ometre la geometria municipal (pes). Es
   manté el comportament actual de 3 nivells amb la pell nova, oi?
8. **Crèdit "DISSENY mm."** al peu (blau `#6f96e8`, enllaç al portfolio): entra
   a producció tal com el descriu el handoff?
9. **Compte enrere**: objectiu **dissabte 09:00 local**, i en dissabte ≥9h
   l'estat "Top publicat avui" (com a `HomePage` actual). Confirmes?
10. **Mòbil — gra/blur**: acceptem el cost de rendiment, o **per defecte
    desactivem el gra i caiem a `solid` en mòbil** (i el restaurem en desktop)?

---

*FASE 1 acabada. Cap codi, cap branca, cap canvi al repo. Següent pas: validar
aquest pla i respondre les preguntes obertes abans d'obrir la branca
`redisseny-web`.*
