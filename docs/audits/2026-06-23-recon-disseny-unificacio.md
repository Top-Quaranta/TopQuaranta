# Recon de disseny — unificació cap a `rd/primitives` com a canon (2026-06-23)

> Sessió de **només-lectura** sobre codi de producció (worktree net @ `1a58ecd`).
> Cap component de prod tocat; l'única escriptura és aquest informe i l'artefacte
> de preview `2026-06-23-preview-paleta-territori.html` (tots dos inerts).
> Les troballes de l'auditoria `2026-06-23-auditoria-dry-modular.md` es tracten
> com a **hipòtesis a re-confirmar**; on el codi actual ja no quadra, es marca
> **[CORRECCIÓ vs auditoria]** amb `file:line`.

---

## Estat d'execució (afegit post-recon)

- **Fase 1 completada (PR #298, mergejada 2026-06-23):** la paleta de
  territori està unificada 5→1 a `rd/terr.js` (`terrChart` = deep);
  CancoChart (públic) i StaffAnalyticsPage (staff) hi llegeixen.
- **Capa light de rd ja existeix** (branca `feat/rd-light-mode`, additiu,
  zero-píxel): `rd/primitives.jsx` exposa `Glass tone="light"` + `Btn
  tone/size` (variants light que reflecteixen `StaffTable` byte-a-byte).
  És **opció B** (staff es queda blanc; rd guanya mode light). Encara
  **no la consumeix cap pàgina**: el retrofit staff pàgina-a-pàgina ve
  després, amb revisió visual per pàgina.

---

## Pas 1 — Inventari verificat de `rd/primitives` com a canon

### 1.1 Què exporta `rd/primitives.jsx` (10 primitives) — `web-react/src/components/rd/primitives.jsx`

| Primitiva | Línia | Rol | Valors/contracte clau |
|---|---|---|---|
| `Band` | `:17` | Banda full-bleed | `tone: ink\|ink2\|hero\|top-hero\|yellow`; embolcalla `.rd-band` + `.rd-wrap` |
| `Glow` | `:28` | Glow de color decoratiu | `variant a/b`, `color` (territori deep) |
| `Glass` | `:36` | Superfície liquid-glass | classe `.rd-glass` (sòlid mòbil, blur desktop) |
| `Btn` | `:42` | Botó pill | `variant: hot\|ghost`; `<a>` si hi ha `href` |
| `Kicker` | `:49` | Whisper Instrument Serif | `.rd-kicker` |
| `Crit` | `:58` | Veu Anton majúscules | `as` (h2 def.), `size`, `color` |
| `Numeral` | `:67` | Xifra tabular Anton | `font-family: var(--font-crit)`, `tabular-nums`, def. `color #fff` |
| `Move` | `:81` | Indicador moviment (5 estats) | colors de `MV` (terr.js): up/down/new/eq/re |
| `TerrLogo` | `:116` | Silueta territori | color = `terr(code).accent`; CAT→senyera |
| `RdCover` | `:128` | Coberta/àlbum amb fallback | `tint`, `shade()` per al gradient |

Tokens canònics que consumeix: `--font-crit` (Anton), `--font-body` (Bricolage),
i la paleta de `rd/terr.js`. Les regles visuals viuen a `index.css` sota `.rd-*`.

### 1.2 Font de paleta canònica — `web-react/src/components/rd/terr.js`

- `PAL` (`:17-28`): parells **deep/accent** per codi backend (LIVE; el consumeixen
  `terr()`/`TerrLogo` a ~8 pàgines públiques: HomePage, TopPage, ArtistaPage,
  ArtistesPage, MapaPage, CancoPage, ComunitatDirectoriPage…).
- `MV` (`:38-41`): semàntica de moviment (`up #7bbf7b`, `down #dd7882`,
  `new #facc15`, `eq rgba(255,255,255,.40)`, `re #e8a44d`).
- `shade()` (`:62`), `terr()`/`terrAccent()`/`terrDeep()` helpers.

### 1.3 Què usa el staff i el gap de primitives compartides

`web-react/src/components/staff/StaffTable.jsx` exporta **16 primitives de
TAULA/FORMULARI** (categoria diferent de les de layout de `rd/`):
`TableCard:8`, `Table:30`, `THead:46`, `Th:54`, `Td:69`, `Tr:77`,
`EmptyState:92`, `Callout:101`, `Pill:129`, `Btn:173`, `Input:210`,
`Textarea:222`, `Select:234`, `Pagination:248`, `PageHeader:273`, `Field:290`.
`web-react/src/components/StaffLayout.jsx:70` és l'únic export (el shell).

**Gap confirmat:** `grep` de `rd/primitives`/`rd/terr` a `web-react/src/pages/staff`
i `web-react/src/components/staff` → **0 imports**. El staff **no** comparteix cap
primitiva de layout de `rd/` (Band/Glass/Glow/Kicker/Crit/Numeral/Move/TerrLogo/
RdCover). La hipòtesi de l'auditoria («0 primitives de layout compartides
públic↔staff») **es CONFIRMA per la direcció rd→staff**.

**[CORRECCIÓ vs auditoria]** La intersecció **NO** és literalment 0: la
compartició existeix en sentit **públic→staff**, no staff→rd —
`web-react/src/pages/ArtistesPage.jsx:15-16` importa `FilterPanel` i
`Field`/`Select` de `components/staff/StaffTable`; `OnboardingPage.jsx:18`,
`PerfilUsuariPage.jsx:11` i `ProposarArtistaPage.jsx:24` importen `LocationCascade`
de `components/staff`. És a dir, algunes pàgines públiques reutilitzen widgets de
formulari del staff; el que no passa és que el staff adopte `rd/`.

### 1.4 Primitives de `rd/primitives` SENSE equivalent al staff

| `rd/` primitiva | Equivalent staff? | Nota |
|---|---|---|
| `Band` `:17` | **cap** | staff fa contenidors manuals/`TableCard` |
| `Glow` `:28` | **cap** | — |
| `Glass` `:36` | **cap** | staff usa `TableCard` (blanc sòlid) |
| `Kicker` `:49` | **cap** | — |
| `Crit` `:58` | **cap** | staff usa `PageHeader` (títol pla) |
| `Numeral` `:67` | **cap** | — |
| `Move` `:81` | **cap** | (domini-específic; staff no mostra moviment) |
| `TerrLogo` `:116` | **cap** | staff pinta hex cru (sense silueta) |
| `RdCover` `:128` | **cap** | staff usa `<img>` cru / `deezerImg` |
| `Btn` `:42` | **`StaffTable.jsx:173`** | mateix nom, **sistema diferent** (`hot/ghost` vs `primary/secondary/…`) → candidat #1 a unificació |

Inversament, `rd/primitives` **no té** cap primitiva de taula/formulari
(`Table`, `Pill`, `Input`, `Pagination`, `Field`, `Callout`, `PageHeader`…): una
unificació real demana que `rd/` GUANYE aquesta capa, o mantenir `StaffTable` com
la capa de domini staff sobre tokens compartits (vegeu Pas 4).

---

## Pas 2 — Paleta de territori: fonts divergents (re-confirmades)

### 2.1 [CORRECCIÓ vs auditoria] No són «4 fonts», són **5**, en **2 famílies**

L'auditoria deia 4 fonts (index.css, rd/terr.js, editorial.jsx,
StaffAnalyticsPage). El codi actual en té **5**, i l'estructura real és:

**Família A — parells deep/accent (CANON, AGREEN exactament):**
- `web-react/src/index.css:152-160` `--color-terr-*` (CSS; claus `pri/val/bal/nor/
  fra/and/alg/alt/car`, on `pri`=CAT/PPCC i `nor`=CNO).
- `web-react/src/components/rd/terr.js:17-28` `PAL` (JS; LIVE a ~8 pàgines).

**Família B — un sol hex per territori (color de sèrie de gràfic):**
- `web-react/src/components/editorial.jsx:27-38` `TERR_COLORS` —
  **[CORRECCIÓ] MORT: 0 importadors.** Cap fitxer fa `import { TERR_COLORS }`;
  l'únic import d'`editorial` a tot el SPA és `TERRITORI_NOM` des de
  `rd/terr.js:14`. L'auditoria el comptava com a «3 importadors»: avui el seu
  `TERR_COLORS` no el renderitza **ningú**.
- `web-react/src/pages/staff/StaffAnalyticsPage.jsx:42-52` `TERR_COLORS` —
  **LIVE**, còpia local hardcodejada (el comentari `:40` diu «Sourced from
  editorial.jsx» però ha divergit). Consum: `:492` `<Cell fill={TERR_COLORS[...]}>`.
  **Sense CAR** → fallback `#0a0a0a`.
- `web-react/src/components/CancoChart.jsx:34-38` `TERRITORI_COLORS` —
  **[CORRECCIÓ — font que l'auditoria NO mencionava]**, **LIVE i PÚBLICA**
  (gràfic d'evolució de la cançó; stroke de línia). **Idèntica** a la de
  StaffAnalytics (mateixos hex, també sense CAR).

Resum: **2 canòniques que coincideixen + 1 morta (editorial) + 2 vives idèntiques
(StaffAnalytics + CancoChart) que divergeixen del canon i de l'editorial.**

### 2.2 Taula before → after per territori (hex REALS grepejats)

Canon = parell deep/accent de `rd/terr.js`/`index.css`. Llegat-viu = el de
StaffAnalytics+CancoChart. Per a colors de sèrie sobre fons blanc es recomana el
**deep** (l'accent és massa clar); decisió deep-vs-accent = **pendent del teu OK**.

| Codi | editorial (MORT) | chart VIU ★ | → canon deep | → canon accent | Canvi visible? |
|---|---|---|---|---|---|
| PPCC | `#427c42` | `#427c42` | `#2f5a2f` | `#7bbf7b` | sí (verd→verd subtil) |
| CAT  | `#8a6900` | `#c99b0c` | `#2f5a2f` | `#7bbf7b` | **★ sí (ambre→verd)** |
| VAL  | `#cf3339` | `#cf3339` | `#8a4a1e` | `#e8a44d` | ★ sí (roig→marró/ambre) |
| BAL  | `#0047ba` | `#0047ba` | `#1f5a63` | `#5cc0cc` | ★ sí (blau→teal) |
| AND  | `#7c3aed` | `#7c3aed` | `#2c3f63` | `#7595cf` | ★ sí (lila→navy) |
| CNO  | `#0e7490` | `#0891b2` | `#7a2730` | `#dd7882` | ★ sí (cian→roig) |
| FRA  | `#c2410c` | `#ea580c` | `#6e5520` | `#d8b257` | ★ sí (taronja→oliva/or) |
| ALG  | `#db2777` | `#db2777` | `#7a3340` | `#d986a0` | ★ sí (rosa→granat) |
| ALT  | `#525252` | `#6b7280` | `#33373d` | `#9aa0a6` | ★ sí (gris→gris fosc) |
| CAR  | `#525252` | _absent→`#0a0a0a`_ | `#4a4034` | `#bda988` | ★ sí (negre→marró) |

### 2.3 Superfícies que canviarien visiblement → **requereixen el teu OK**

- **`CancoChart.jsx` (PÚBLICA)** — `web-react/src/components/CancoChart.jsx:34-38`
  + ús stroke a `:66+`. Tots els colors de línia del gràfic d'evolució canvien.
  És públic: **prioritat alta de revisió** (l'auditoria/usuari es centraven en
  staff, però aquesta superfície és pública i també afectada).
- **`StaffAnalyticsPage.jsx` (STAFF)** — `:42-52` + `<Cell fill>` a `:492`. Tots els
  colors de barra canvien; explícitament el que vas marcar: **CAT `#c99b0c` →
  canon** (deep `#2f5a2f` o accent `#7bbf7b`).
- **`editorial.jsx::TERR_COLORS` (MORT)** — canviar-lo/esborrar-lo **no té cap
  efecte visible** (0 consumidors); no és un canvi que requerisca OK, és neteja.

**Nota honesta:** la paleta **NO viu a `ConfiguracioGlobal`**
(`ranking/models.py:31`, 35 camps, cap de color/terr/palette). Tot és en codi → no
hi ha valor de prod a llegir; el before/after és íntegrament codi-vs-codi.

---

## Pas 3 — Artefacte de preview

`docs/audits/2026-06-23-preview-paleta-territori.html` (i còpia a
`~/Claude/TopQuaranta/`). Swatches before/after per territori i per font, amb una
fila de barres «llegat viu → canon» sobre fons blanc. **Tots els hex provenen del
`grep` del Pas 2; cap inventat.** Inert, sense dependències, obre's amb doble clic.

---

## Pas 4 — Pla per fases (planificació, **no** implementació)

### Fase 1 — mòdul únic de tokens en codi (mata la divergència 5→1)

Objectiu: una sola font de la paleta + primitives compartides, en codi (encara no
a prod-config). Passos proposats, en ordre:

1. **Promoure `rd/terr.js` a font única** de la paleta de territori. Derivar-ne (o
   alinear) `index.css --color-terr-*` perquè CSS i JS surten del mateix lloc
   (avui ja coincideixen, però es mantenen a mà en dos llocs).
2. **Reemplaçar les 2 còpies de gràfic** (`StaffAnalyticsPage::TERR_COLORS`,
   `CancoChart::TERRITORI_COLORS`) per un helper derivat de `rd/terr.js`
   (p.ex. `terrChart(code)` → deep o accent segons fons). **Aquest pas és el que
   canvia color visible → requereix OK previ** (Pas 2.3).
3. **Esborrar `editorial.jsx::TERR_COLORS`** (mort) i moure `TERRITORI_NOM`/
   `FOCUS_TERRITORIS` a un mòdul net si cal, perquè `rd/terr.js` ja no depenga
   d'`editorial`. Sense efecte visible.
4. **Unificar `Btn`**: decidir un sol sistema (rd `hot/ghost` + tons staff) i fer
   que `StaffTable::Btn` en derive. Risc mitjà (toca tot el staff).

### Fase 2 — promoure la paleta a `ConfiguracioGlobal` + API (editable des de staff)

Només **després** de la Fase 1 (una sola font en codi):

1. Afegir camp(s) a `ConfiguracioGlobal` (p.ex. `paleta_territori` JSON) amb
   default = els valors canònics actuals; migració additiva.
2. Endpoint staff de lectura/escriptura + validació (hex, contrast AA).
3. Fer que `rd/terr.js` (o el seu equivalent servit) llija la config amb fallback
   al default en codi. Aquí sí hi hauria «valor de prod» a llegir.

### Seqüència de retrofit del staff cap a `rd/primitives` (ordre + risc)

**No implementat ara.** Ordre recomanat (de menor a major risc / per dependència):

| # | Pàgina/àrea staff | Per què aquest ordre | Risc |
|---|---|---|---|
| 1 | `StaffAnalyticsPage.jsx` (paleta) | aïllat, 1 sol `<Cell fill>`; el canvi de color ja necessita OK | Baix-mitjà (visible) |
| 2 | `CancoChart.jsx` (públic, paleta) | mateix helper que #1; públic → validar contrast | Mitjà (públic, visible) |
| 3 | Botons (`StaffTable::Btn` → sistema unificat) | toca moltes pàgines però mecànic | Mitjà |
| 4 | Capçaleres (`PageHeader` → `Crit`/`Kicker`) | canvi tipogràfic, no estructural | Mitjà |
| 5 | Contenidors (`TableCard` → `Glass`/`Band`) | canvi visual gran del shell staff | Alt |
| 6 | `StaffLayout` (shell + sidebar) | últim: afecta totes les pàgines alhora | Alt |
| 7 | Taules (`Table/Tr/Td`) | mantenir-les com a capa de domini sobre tokens; retipar només si cal | Alt (densitat de dades) |

Recomanació: Fase 1 passos 1+3+4 (sense canvi visible) es poden fer sense OK;
el pas 2 (paleta de gràfics, #1-#2 del retrofit) **espera el teu OK** perquè canvia
colors observables en una superfície pública i una de staff.

---

## Annex — eixida crua dels greps clau

```
# Famílies de paleta (5 fonts)
index.css:152-160        --color-terr-*  (deep/accent)        [CANON CSS]
rd/terr.js:17-28         PAL             (deep/accent)        [CANON JS, LIVE ~8 pàg]
editorial.jsx:27-38      TERR_COLORS     (1 hex)              [MORT: 0 importadors]
StaffAnalyticsPage:42-52 TERR_COLORS     (1 hex, sense CAR)   [LIVE: <Cell fill> :492]
CancoChart.jsx:34-38     TERRITORI_COLORS(1 hex, sense CAR)   [LIVE públic: stroke :66+]

# Importadors d'editorial (només TERRITORI_NOM, mai TERR_COLORS):
rd/terr.js:14: import { TERRITORI_NOM } from '../editorial'

# rd imports al staff:
(cap)  → 0 primitives de layout compartides staff→rd  [gap CONFIRMAT]

# public→staff (refuta intersecció=0):
ArtistesPage.jsx:15-16  FilterPanel, {Field,Select} from components/staff/StaffTable
OnboardingPage.jsx:18 / PerfilUsuariPage.jsx:11 / ProposarArtistaPage.jsx:24  LocationCascade

# ConfiguracioGlobal: 35 camps, cap de color/terr/palette  → paleta NO a prod-config
```
