# Spike — renderitzar el feed via captura HTML headless vs port PIL (2026-06-10)

> NOMÉS-LECTURA. Cap commit, cap merge, cap branca, cap canvi a prod/flag.
> Spike local d'usar i tirar a `/tmp/feedspike` (NO committat). Informe local.
> Objectiu: decidir si val la pena renderitzar el feed capturant l'HTML de
> Claude Design amb navegador headless en lloc de reimplementar-lo en PIL.

## 1. Eina headless que ja existeix al repo

- **Driver: Puppeteer** + `@axe-core/puppeteer`, a `scripts/axe_staff.js`
  (`headless: 'new'`, `executablePath: '/usr/bin/chromium-browser'`). És el
  patró d'auditoria a11y axe-core del projecte: **Puppeteer governant el
  Chromium del sistema** (`/usr/bin/chromium-browser` al servidor Debian).
  `@axe-core/puppeteer` és dependència **de dev**, no de runtime de prod.
- **Spike local:** `puppeteer-core@23.11.1` apuntant al **Google Chrome
  149.0.7827.55** del sistema (mateix enfocament: core + browser del sistema,
  sense descarregar Chromium). La versió exacta de `/usr/bin/chromium-browser`
  al servidor no s'ha consultat (spike 100 % local); es pot comprovar a petició.

## 2. Muntatge del spike

Assets de Claude Design (a `~/Downloads/`): `TopQuaranta - Feed.html`
(multi-fitxer, referencia `feed-data.js` + `feed-{kit,cover,album,singles}.jsx`
— **els .jsx no hi són**) i dos **Standalone** auto-continguts. He usat el
**`Standalone (1)`** (versió curada: una placa per secció — *Portada ÀLBUMS
dimarts*, *Àlbum banda editorial*, *Graella de singles* — que coincideix amb els
noms dels PNG de referència).

Capturat a **1080×1350** (deviceScaleFactor 1) via `element.screenshot` de la
placa: **portada**, **àlbum amb portada**, **àlbum fallback (cover=null,
Cat. Nord)** i **graella de 10 singles**.

Troballa clau de muntatge: **el Standalone fa ZERO peticions externes.**
React, Babel i **totes les fonts** (Anton, Bricolage 500/700/800, Instrument
Serif, Playfair) van **inlinejades** (`document.fonts` → totes `loaded`, cap
CDN). Autocontingut de debò.

## 3. Mesures

Mètode: `puppeteer-core` + Chrome 149, viewport 1080-ample, `document.fonts.ready`
+ 600 ms de settle abans de capturar. Comparació amb el renderer PIL actual
(`social/feed_redesign.py`) executat in-process al venv.

| Mètrica | **HTML headless** | **PIL (actual)** |
|---|---|---|
| Llançament del motor | navegador **2,06 s** (procés nou) | import + setup ~0 (ja dins de Django) |
| Càrrega/compilació | **3,21 s** (Babel in-browser + render de la placa) | n/a |
| 1a imatge (freda) | ~**3,5 s** la 1a captura (raster inicial) | **0,89 s** (inclou càrrega de fonts) |
| Per imatge (calenta) | portada **0,78 s** · àlbum **0,22 s** · singles **0,21 s** | àlbum **0,17 s** · singles **0,20 s** |
| Tanda setmanal 12 img (calent) | **3,2 s** | **2,9 s** |
| Tanda 12 img des de fred (procés nou) | **~8,5 s** (2,06 + 3,21 + captures) | **~3,0 s** (in-process) |
| Memòria | headless Chrome **~220–400 MB** (procés a part) | desenes de MB dins del worker existent |
| Determinisme (2 càrregues) | **idèntic byte a byte** (maxDiff 0, 100 % px iguals) | determinista (seed de gra fix; tests byte-equal) |
| Fonts | `@font-face` inlinejat, totes `loaded`, sense CDN | TTF vendoritzats (PIL) |

**Determinisme** (el punt fort sorprenent de l'HTML): dues càrregues del mateix
HTML donen captures **byte-idèntiques** (`cmp` OK; meanAbsDiff 0,0000;
maxDiff 0). Res de jitter de fonts ni d'antialiasing entre execucions.

## 4. Fidelitat vs els PNG de referència de Claude Design

Captura headless (1080×1350) vs `social/feed_design/reference/*.png` (1080×1350):

| Placa (parella correcta) | meanAbsDiff | % px que difereixen >16 |
|---|---|---|
| **Fallback Cat. Nord** (placa sense gra random) | **0,96** | **0,93 %** |
| Portada (camp verd) | 8,40 | 6,57 % |
| Graella singles | 2,15 | 3,07 % |

Lectura: sobre una placa **sense el gra de paper aleatori** (el fallback, gairebé
pla), la captura és **pràcticament idèntica byte a byte (0,93 %)** al PNG de
referència. Les diferències de portada/singles (3–7 %) són **íntegrament** (a) el
**gra monocrom aleatori** (cada export usa una llavor diferent) i (b)
antialiasing sub-píxel del text — **no** layout, tipografia ni color. És el
resultat esperat: *capturar l'HTML reprodueix el disseny de Claude perquè ÉS el
mateix HTML*. Dins del nostre pipeline el gra quedaria fix (determinisme byte),
així que no hi hauria ni tan sols aquesta variació.

> Contrast: el PIL és una **reimplementació a mà**. Després de tot aquest sprint
> d'ajustos (overlap de la portada, fill-width, ombra, radial, noms complets,
> blind PPCC, pesos Bricolage…) s'hi acosta molt, però cada canvi de disseny
> requereix re-codificar; la captura HTML és fidel **per construcció**.

## 5. Cost d'integració al pipeline social

Què caldria per portar la captura HTML a producció:

- **Injecció de dades:** mapar el nostre payload (`social/payload.build_novetats`
  → `items[]`) a les props dels components (`window.FEED_DATA`). Via plantilla
  HTML o `page.evaluate` injectant `FEED_DATA` abans del mount. Cal **pre-buildar
  els .jsx** (esbuild/Vite) per treure el Babel-in-browser del runtime.
- **Portades Deezer + fallback:** avui PIL passa per `cover_cache.fetch` (Deezer
  + tile de fallback). En HTML, els `<img>` carregarien URLs de Deezer **en temps
  de render** (xarxa) o caldria pre-baixar-les i inlinejar-les com a data-URI per
  mantenir el contracte de fallback i el determinisme.
- **Idempotència / gating per canal:** **sense canvis.** Viuen a
  `publicar_social` / `publicar_canal` (SocialPost + matriu), no al renderer. El
  renderer només produeix PNG; la captura HTML hi encaixa igual que el PIL.
- **El que NO es reutilitzaria del sistema PIL:** TOT el renderer PIL de les
  **stories** (`render_stories_*`, builders PIL, `fonts.py`, `svg_assets`,
  `colors.py`) es queda — les stories NO es porten. Per tant la captura HTML del
  feed seria un **segon stack de render** al costat del PIL de stories: dues
  pipelines, dues configuracions de fonts (TTF PIL + `@font-face` CSS).

**Riscos operatius:**

- **Dependència de navegador a prod.** Puppeteer passaria de dev a **runtime de
  prod**. El servidor ja té `/usr/bin/chromium-browser` (axe), així que **no és
  una instal·lació nova** — baixa el cost.
- **Pressió de memòria al CX22 (4 GB).** Un headless Chrome són ~250–400 MB per
  tanda. El box ja té historial d'**OOM a 4 GB** (el `SingletonLock "ram_heavy"`
  Whisper/MusicBrainz existeix per això). Córrer Chrome al cron del dissabte pot
  xocar amb feines memory-heavy; caldria un lock compartit o moure el render fora
  de la finestra crítica.
- **Modes de fallada nous:** Chrome pot penjar-se / timeout; calen timeouts +
  retries que el PIL (pur Python, in-process) no necessita.

## 6. Taula de decisió i recomanació

| Criteri | PIL-port (actual) | HTML-captura headless |
|---|---|---|
| **Fidelitat al disseny** | Bona, però reimplementada; cada canvi = re-codi | **Pixel-fidel per construcció** (0,93 % en placa sense gra) |
| **Esforç de manteniment** (disseny canviant) | Alt: re-codificar cada ajust | **Baix: re-exportar l'HTML** |
| **Rendiment / tanda setmanal** | **2,9 s in-process** | 8,5 s des de fred (procés + browser) |
| **Memòria** | **desenes de MB (worker existent)** | 250–400 MB (Chrome a part) |
| **Determinisme** | Sí (seed fix) | **Sí (byte-idèntic)** |
| **Dependències de prod noves** | **Cap** (Python pur) | Puppeteer runtime + build JS (chromium ja hi és) |
| **Risc al CX22 4 GB** | **Cap** | Pressió de memòria (historial d'OOM) |
| **Modes de fallada** | **Mínims** | Browser hang/timeout → retries |
| **Stack** | **Un de sol** (comparteix PIL amb stories) | **Dos** (HTML feed + PIL stories) |

### Recomanació: **mantenir el port PIL ara; reservar la captura HTML per a quan canviï el context**

Motius:
1. **El port PIL ja està fet** i, després d'aquest sprint, s'acosta molt a les
   referències. El delta de fidelitat que aporta l'HTML és real però petit i
   decreixent.
2. **Zero risc operatiu nou** a un box de 4 GB amb historial d'OOM. El PIL corre
   in-process, és més ràpid en absolut (2,9 s) i no afegeix un segon stack.
3. La captura HTML brilla en **fidelitat garantida** i **manteniment baix si el
   disseny canvia molt** — però el preu és un navegador a prod, memòria, i dues
   pipelines.

**Quan reconsiderar i passar a HTML-captura:**
- Si el **churn de disseny** del feed esdevé alt (re-codificar PIL cada setmana
  cansa) → el "re-exportar HTML" guanya clarament.
- Si el render es **mou fora del CX22** (un worker/CI o un box amb més RAM on
  Chrome no competeixi) → desapareix el risc de memòria i la captura HTML passa a
  ser l'opció millor (fidelitat per construcció).
- **Híbrid viable:** PIL al cron setmanal on-box per a producció; captura HTML en
  CI/preview per a revisió de disseny (comparar el PNG real amb la referència
  automàticament). Així es valida la fidelitat sense posar Chrome al camí crític.

### Números nets per decidir

- HTML: motor +2,06 s, càrrega +3,21 s, ~0,2–0,8 s/imatge, **byte-determinista**,
  **0,93 % de diff** vs referència (placa neta), **autocontingut sense CDN**,
  ~250–400 MB.
- PIL: **0,89 s** fred, ~0,18 s/imatge, **2,9 s** tanda, in-process, sense
  dependències noves, fidelitat "molt a prop" després de l'sprint.

Cap canvi al repo ni a prod. Spike a `/tmp/feedspike` (esborrable). FI.
