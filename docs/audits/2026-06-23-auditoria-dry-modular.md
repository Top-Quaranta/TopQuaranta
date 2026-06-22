# Auditoria DRY / modularitat / sobre-disseny — 2026-06-23

> Sessió de **només-lectura**. Cap font tocada; l'única escriptura és aquest
> informe. Worktree net eixit de `origin/main` @ `e95c726`.
> Eines: `jscpd 5.0.11` (detector de clons) i `ponytail@ponytail 4.7.0`
> (`/ponytail-audit`, sobre-disseny). Tota troballa porta `file:line` real;
> el que no s'ha pogut mesurar fidelment s'etiqueta **[NO MESURAT]**.

## Nota metodològica sobre les eines

- **`jscpd`** és la base quantitativa: 273 fitxers, 62 755 línies, **135 clons,
  5,23 % de línies duplicades**. Eixida crua a l'**Annex B**.
- **`/ponytail-audit`**: la comanda del plugin no queda registrada com a
  slash-command sense reiniciar la sessió de Claude Code. Per no inventar,
  s'ha executat **el prompt literal del `commands/ponytail-audit.toml`** (que
  es transcriu a l'Annex A) sobre tot l'arbre via agent de només-lectura. El
  pass de ponytail ha tornat **«Lean already. Ship.»** — un veredicte que
  **contradiu l'evidència mesurada** (orfes i duplicacions confirmades més
  avall). Es reporta tal qual a l'Annex A i es deixa constància de la
  discrepància: ponytail no va detectar ni l'orfe `feed-tokens.json` ni el
  preàmbul d'imports duplicat 16×. La part endevinatòria d'aquest pass NO es
  pren com a font; les troballes d'aquest informe estan totes verificades amb
  `grep`/`git`/`jscpd`.

---

## Bloc 1 — Duplicació i DRY

### 1.1 [ALT] Preàmbul d'imports duplicat verbatim a 17 dels 22 mòduls staff
`jscpd` marca `api/staff/_common.py:1-78` com a clon contra **pràcticament tots**
els altres mòduls de l'app: `pendents.py`, `audit.py`, `configuracio.py`,
`dashboard.py`, `feedback.py`, `historial.py`, `propostes.py`, `senyal.py`,
`solicituds.py`, `usuaris.py`, `albums.py`, `cancons.py`, `top.py`, `artistes.py`…
(≈78 línies cadascun).

Mecànica verificada: cada mòdul **repeteix el bloc d'imports sencer** (~60
línies, `django.db.models`, `django_otp`, `comptes.models`, `music.models`,
`ranking.models`…) — vegeu [web/api/staff/pendents.py:9-71](web/api/staff/pendents.py:9) —
**i a més** importa els helpers compartits reals de `_common`
([pendents.py:75](web/api/staff/pendents.py:75):
`from web.api.staff._common import IsStaff, _paginate, noms_amb_homonims`). És a
dir: `_common` ja existeix com a llar dels helpers, però el preàmbul s'ha
copiat-enganxat igualment. Recompte: **17/22** mòduls staff porten el bloc
`from music.models import …` complet al capdamunt.

Conseqüència: molts d'aquests imports no s'usen al mòdul concret (vegeu 1.2) i
qualsevol canvi al conjunt d'imports requereix tocar 17 fitxers.

### 1.2 [MITJÀ] Imports morts arrossegats pel copy-paste del preàmbul
Derivat de 1.1, l'scan automàtic reporta imports presents però no usats al
mòdul:
- `from django.core.paginator import Paginator` a ~16 mòduls staff (p.ex.
  [web/api/staff/artistes.py:18](web/api/staff/artistes.py:18)) tot i que la
  paginació real va pel helper `_paginate()` de `_common`.
- `from comptes.models import Feedback, PropostaArtista, Publicacio, UserArtista`
  a mòduls que no n'usen cap (p.ex. `albums.py`, `audit.py`, `senyal.py`).
- Re-import dels helpers de cerca `normalize_search_term`/`unaccent_field` des de
  `web.api.search_utils` a 14+ mòduls (p.ex.
  [web/api/staff/pendents.py:70-71](web/api/staff/pendents.py:70)) en lloc de
  reexportar-los des de `_common`.

**[NO MESURAT amb precisió]**: el recompte exacte d'imports morts per mòdul prové
d'un scan d'agent, no d'un linter executat; la xifra «~42 instàncies» s'ha de
confirmar amb `ruff --select F401` abans de cap neteja. Es deixa explícit.

### 1.3 [MITJÀ] Filtres de queryset escrits a mà en lloc dels managers existents
`music/models.py` ja exposa managers DRY (`Canco.objects.public()` a
[music/models.py:965](music/models.py:965), `.pendents()` a
[music/models.py:88](music/models.py:88), `.with_mbid()` a
[music/models.py:101](music/models.py:101)). Tot i això es repeteix la lògica
crua:
- `.filter(verificada=True, activa=True)` a
  [web/sitemaps.py:134](web/sitemaps.py:134),
  [web/api/staff/estat.py:487](web/api/staff/estat.py:487),
  [web/seo/meta.py:206](web/seo/meta.py:206),
  [analytics/management/commands/recollir_metrics_psi.py:73](analytics/management/commands/recollir_metrics_psi.py:73).
- `.filter(aprovat=False, pendent_review=True)` a
  [web/api/staff/pendents.py:211](web/api/staff/pendents.py:211) i
  [music/management/commands/purgar_pendents_buits.py:71](music/management/commands/purgar_pendents_buits.py:71).
- `.exclude(musicbrainz_id__isnull=True).exclude(musicbrainz_id="")` a
  [web/api/staff/artistes.py:124](web/api/staff/artistes.py:124) en lloc de
  `.with_mbid()`.

Risc real de deriva el dia que s'afegisca una tercera flag de publicabilitat.

### 1.4 [BAIX] Clons JSX intra-domini (no inter-domini)
Els 51 clons JSX de `jscpd` són gairebé tots **dins** d'un mateix domini
(públic↔públic o staff↔staff), no entre públic i staff. Mostres:
- Capçalera de pàgina de detall: [src/pages/AlbumPage.jsx:38-63](web-react/src/pages/AlbumPage.jsx:38)
  ↔ [src/pages/CancoPage.jsx:43-68](web-react/src/pages/CancoPage.jsx:43) (26 L).
- Bloc repetit dins el mateix fitxer:
  [src/pages/ArtistaDashboardPage.jsx:424-449](web-react/src/pages/ArtistaDashboardPage.jsx:424)
  ↔ `:570-595` (26 L) — i 5 parells més intra-fitxer al mateix Dashboard.
- Scaffolding de pàgina-llista staff replicat:
  [src/pages/staff/PendentsPage.jsx:24-45](web-react/src/pages/staff/PendentsPage.jsx:24)
  ↔ [src/pages/staff/StaffArtistesSenseInstagramPage.jsx:22-40](web-react/src/pages/staff/StaffArtistesSenseInstagramPage.jsx:22).
- Pickers paral·lels:
  [src/components/staff/ArtistaPicker.jsx:22-40](web-react/src/components/staff/ArtistaPicker.jsx:22)
  ↔ [src/components/staff/ArtistesColPicker.jsx:28-46](web-react/src/components/staff/ArtistesColPicker.jsx:28)
  (i 2 parells més entre ambdós).
- Panells de proveïdor bessons:
  [src/components/staff/LastfmPanel.jsx:17-38](web-react/src/components/staff/LastfmPanel.jsx:17)
  ↔ [src/components/staff/MusicBrainzPanel.jsx:11-32](web-react/src/components/staff/MusicBrainzPanel.jsx:11).

Aquest patró (clons **intra**-domini) és la prova quantitativa que **públic i
staff no comparteixen primitives**; cadascun duplica internament. Connecta amb
el Bloc 2.

### 1.5 [BAIX] Plantilles d'error Django gairebé idèntiques
`jscpd` marca el grup `markup` amb **38,28 % de línies duplicades**, concentrat a
les pàgines d'error: [templates/web/403.html:5-25](web/templates/web/403.html:5)
↔ `404.html` ↔ `500.html` (21/13/9 L). Candidates a un `_base_error.html` amb
bloc de missatge.

### 1.6 [INFORMATIU] Clons de tests
`jscpd` també marca clons entre fitxers de test (p.ex.
`tests/test_staff_analytics.py:25-44` ↔ `test_staff_analytics_quickwins.py:30-49`).
Són boilerplate de fixtures, no arquitectura; es llisten a l'Annex B però **no**
es prioritzen (els tests queden fora del gate de docs per disseny).

---

## Bloc 2 — Descentralització del disseny (públic vs staff)

**Veredicte de la hipòtesi «públic i staff conviuen com a dos dissenys perquè es
va perdre la centralització»: CONFIRMADA, amb una precisió que la reforça.**

Hi ha una font de tokens compartida —
[web-react/src/index.css](web-react/src/index.css) `@theme` (tq-yellow/ink,
`--color-terr-*`, `--font-crit/whisper/body`, classes `.rd-*`)— **necessària però
insuficient**: només defineix colors/fonts, no primitives de layout. Damunt
d'aquesta base hi conviuen **tres generacions de disseny**, no dues, evidenciat
per l'historial de git (dates reals verificades):

| Capa | Fitxer arrel | Afegit (git) | Estat |
|---|---|---|---|
| Tokens base | `src/index.css` | **2026-04-20** (`1af9988`) | viu, parcialment consumit |
| Staff | `components/StaffTable.jsx`, `StaffLayout.jsx` | **2026-04-20** (`3a6ae4d`/`e0b1ca9`) | viu; 36 pàgines |
| Públic editorial v1 | `components/editorial.jsx` | **2026-04-26** (`a8b1c8d`) | **encallat** (vegeu 2.2) |
| Públic redisseny v2 | `components/rd/primitives.jsx` | **2026-06-13** (`1671717`) | viu; 14 pàgines |

Lectura: el **staff va néixer primer (20-abr)** sobre Tailwind fosc + `StaffTable`;
el **públic es va re-plataformar dues vegades** (editorial 26-abr → redisseny
`rd/` 13-jun) sense mai retrofitar el staff. La «pèrdua de centralització» no és
un descuit puntual sinó el residu de re-plataformar només una meitat del producte.

### 2.1 [ALT] Cap primitiva de layout compartida entre públic i staff
- Públic consumeix `rd/primitives` (`Band`, `Glass`, `Btn`, `Kicker`, `Crit`,
  `TerrLogo`…): **14** pàgines l'importen.
- Staff consumeix `staff/StaffTable` (`TableCard`, `Table`, `Th/Tr/Td`, `Pill`,
  `Btn`, `Input`…): **36** pàgines l'importen.
- Intersecció = **0**. Les `.rd-*` (classes a `index.css`, ~360 línies sota
  `.rd-root`) **no** s'apliquen a cap pàgina staff (`grep` de `rd-` a
  `src/pages/staff/*` = 0). Hi ha dos sistemes de botó (`rd/primitives::Btn` vs
  `staff/StaffTable::Btn`) amb sistemes de `tone` diferents.

### 2.2 [ALT] `editorial.jsx` és una capa intermèdia encallada
`editorial.jsx` (la «font de veritat» que el `CLAUDE.md` encara cita per
HomePage/TopPage/etc.) ja **no** la importen les pàgines públiques —
`rd/primitives` les va substituir. Avui només l'importen **3** consumidors:
[src/components/CancoChart.jsx](web-react/src/components/CancoChart.jsx),
[src/components/rd/terr.js](web-react/src/components/rd/terr.js) i
[src/pages/staff/StaffAnalyticsPage.jsx](web-react/src/pages/staff/StaffAnalyticsPage.jsx).
És una capa morta-a-mitges: ni del tot pública ni de staff. **El `CLAUDE.md`
§5 (TERR_COLORS «single brand mapping» a editorial.jsx) està desactualitzat
respecte el codi.**

### 2.3 [ALT] Quatre paletes de territori divergents
El mateix concepte (color de territori) viu, amb **valors diferents**, a quatre
llocs:
- [src/index.css:152](web-react/src/index.css:152) `--color-terr-pri-deep: #2f5a2f`
- [src/components/rd/terr.js:17](web-react/src/components/rd/terr.js:17) `PAL.CAT = ['#2f5a2f','#7bbf7b']`
- [src/components/editorial.jsx:27](web-react/src/components/editorial.jsx:27) `TERR_COLORS.CAT = '#8a6900'`
- [src/pages/staff/StaffAnalyticsPage.jsx:42](web-react/src/pages/staff/StaffAnalyticsPage.jsx:42) `TERR_COLORS.CAT = '#c99b0c'`

Per CAT són **tres tons diferents** (#2f5a2f vs #8a6900 vs #c99b0c). index.css i
`rd/terr.js` coincideixen; editorial.jsx i StaffAnalytics divergeixen cadascun pel
seu compte. No hi ha un únic mapa de marca.

### 2.4 [MITJÀ] Hardcoding de color en lloc de tokens
- Staff: [src/pages/staff/StaffAnalyticsPage.jsx:42-72](web-react/src/pages/staff/StaffAnalyticsPage.jsx:42)
  manté taules pròpies de TERR/PLATFORM/SERIES colors hardcodejades;
  `StaffTable.jsx` (Pill/Callout) usa `rgba()` inline amb fallback a hex en lloc
  de `--color-tq-danger/success`.
- Públic: mescla `var(--color-tq-yellow)` amb hex inline (`#0a0a0a`, `#9aa0a6`) al
  mateix fitxer (p.ex. HomePage/TopPage/ArtistesPage).

**[NO MESURAT amb precisió]**: els recomptes «30+ (públic) / 61+ (staff)»
d'ocurrències de hex provenen d'un scan d'agent. Direcció fiable (staff hardcodeja
més), magnitud a confirmar amb `grep -rcE '#[0-9a-fA-F]{6}'`.

---

## Bloc 3 — Sobre-disseny i codi mort

### 3.1 [ALT] `feed-tokens.json` a l'arrel del repo és un orfe
Existeix `/feed-tokens.json` a l'arrel (afegit **2026-06-12**, `b2331f3`) **i**
el canònic `social/feed_design/feed-tokens.json` (afegit **2026-06-10**,
`0a58656`). El codi només carrega el segon —
[social/feed_redesign.py:44](social/feed_redesign.py:44)
`_TOKENS_PATH = _DESIGN_DIR / "feed-tokens.json"`. `grep` de `feed-tokens.json`
a tot l'arbre no troba cap càrrega de l'arrel; només referències al path
`social/feed_design/…` (codi + un help_text de migració). A més els dos fitxers
**divergeixen d'esquema** (l'arrel té claus en català `slides`/`brand_anchors`,
clau territorial `nor`; el canònic té `cover/album/singles`, valors `rgb()`
computats i territoris `alt`/`car`). L'arrel és una còpia vella i **morta**;
candidata a esborrar.

### 3.2 [MITJÀ] `top-tokens.json` declara compartició que no és real
[social/top_design/top-tokens.json:2](social/top_design/top-tokens.json:2)
(`_provenance`) afirma «Palette/fonts/grain/territory chips are SHARED with
feed-tokens.json + render_core», però el fitxer **no** defineix territoris (només
`ppcc`); en temps d'execució `top_redesign` delega a `feed_redesign.territori()`.
La paleta **sí** té una sola font (correcte: `feed-tokens.json` la posseeix), però
la `_provenance` indueix a error. És sobre-documentació, no sobre-codi.

### 3.3 [MITJÀ] `renderer.py` monolític amb asimetria feed/story
[social/renderer.py](social/renderer.py) = **1 676 línies**. El feed està
externalitzat a `feed_redesign.py` (606 L) i el TOP a `top_redesign.py`, però
**tot el render de stories segueix inline** dins `renderer.py`
(`_story_intro_ppcc` …`_story_outro_ppcc`, ~576 L entre les línies 922-1498).
Asimetria: feed/top fora, story dins. Externalitzar story a `story_redesign.py`
deixaria `renderer.py` a ~1 100 L i simetritzaria. **No** és duplicació de
primitives: `render_core.py` (431 L) està genuïnament centralitzat i tant
`renderer.py` com `feed_redesign.py` el criden sense reimplementar (verificat:
cap reimplementació de `star`/`grain`/`tile`/`radial_bg`).

### 3.4 [BAIX] Funcions staff molt llargues
[web/api/staff/artistes.py](web/api/staff/artistes.py) = **1 147 L**;
`artista_detail()` ~261 L (GET+PATCH+aliases+sync MB barrejats),
`artistes_list()` ~200 L (filtres+cerca+sort+paginació+serialització). Candidates
a extreure helpers de filtre/serialització. Igualment
[StaffAnalyticsPage.jsx](web-react/src/pages/staff/StaffAnalyticsPage.jsx) =
**1 601 L** (té 6 clons interns segons jscpd).

### 3.5 [INFORMATIU] El motor narratiu NO és codi mort
Tot i el post-mortem `docs/post-mortems/2026-05-20-narrative-engine-collapsed.md`,
`social/narrative/` (13 detectors a1-a13) està **cablejat i viu** via
`captions.py::compose_for_channel`. No hi ha detectors comentats ni desconnectats.
Es descarta com a candidat a esborrar.

### 3.6 Resultat del pass de sobre-disseny (ponytail)
El pass `/ponytail-audit` va concloure **«Lean already. Ship.»** (Annex A). Aquest
veredicte **no concorda** amb 3.1 (orfe), 2.2 (capa encallada) ni 1.1 (preàmbul
16×), totes verificades amb `grep`/`git`. Es reporta el resultat cru però no es
pren com a conclusió.

---

## Bloc 4 — Oportunitats de modularització

Ordenades per relació impacte/cost (no és pla d'implementació; només l'inventari):

1. **Preàmbul staff → un sol mòdul.** Moure el bloc d'imports comú a `_common.py`
   i que els 17 mòduls importen d'allà (o reexportar des de `_common`). Elimina
   ~60 L × 16 de duplicació i els imports morts de 1.2. (Bloc 1.1/1.2)
2. **Una sola paleta de territori.** Col·lapsar les 4 fonts (2.3) en una
   (preferible: derivar JS de `index.css` `--color-terr-*`, com ja fa
   `rd/terr.js`); eliminar `editorial.jsx::TERR_COLORS` i la taula de
   `StaffAnalyticsPage`. (Bloc 2.3/2.4)
3. **Decidir el destí d'`editorial.jsx`.** O bé migrar els 3 consumidors a `rd/`
   i esborrar-lo, o re-declarar-lo font de veritat — però no deixar-lo a mitges.
   Actualitzar `CLAUDE.md §5`. (Bloc 2.2)
4. **Esborrar `/feed-tokens.json` de l'arrel** (orfe confirmat). (Bloc 3.1)
5. **Primitiva de pàgina-llista staff.** Un `<StaffListPage header filters table
   pagination>` absorbiria l'scaffolding repetit (Pendents/SenseInstagram/
   Albums/Cançons/Usuaris…). (Bloc 1.4)
6. **Externalitzar story render** a `story_redesign.py` per simetria amb
   feed/top. (Bloc 3.3)
7. **`_base_error.html`** per a 403/404/500. (Bloc 1.5)
8. **Managers en lloc de filtres a mà** als 7 punts de 1.3.

---

## Límits de fidelitat (declarats explícitament)

- Recomptes exactes d'imports morts (1.2) i d'ocurrències de hex (2.4): direcció
  fiable, **magnitud pendent** d'un linter/grep dedicat. Marcats **[NO MESURAT]**.
- `/ponytail-audit` s'ha executat com a **prompt** (Annex A), no com a
  slash-command registrat; el seu veredicte «lean» es contradiu amb l'evidència i
  no es pren com a font.
- L'historial de git citat (Bloc 2) està **verificat** amb `git log
  --diff-filter=A`; les dates són reals (`1af9988`/`3a6ae4d`/`a8b1c8d`/`1671717`/
  `b2331f3`/`0a58656`).

---

## Annex A — Eixida crua de `/ponytail-audit`

Prompt executat (literal de `commands/ponytail-audit.toml`):

> Audit the entire repository for over-engineering only, not correctness. Scan
> the whole tree, not a diff. One line per finding, ranked biggest cut first:
> `<tag> <what to cut>. <replacement>. [path]`. Tags: delete, stdlib, native,
> yagni, shrink. End with the net lines and dependencies removable. If nothing to
> cut: 'Lean already. Ship.'

Resultat retornat:

```
Únic candidat avaluat: comptes/newsletter_utm.py::build_newsletter_url
solapa amb social/captions.py::utm_url — descartat: build_newsletter_url rep
`setmana` (int) explícit i utm_url la deriva d'un datetime.date; firmes
diferents, no unificables sense canvi d'API.

No lines to remove. No dependencies to eliminate.

Lean already. Ship.
```

> Nota de l'auditor: aquest veredicte és **incomplet**. El pass de ponytail no va
> detectar l'orfe `/feed-tokens.json` (§3.1), la capa encallada `editorial.jsx`
> (§2.2) ni el preàmbul d'imports duplicat 16× (§1.1), totes verificades
> independentment. Es conserva el text cru per fidelitat.

---

## Annex B — Eixida crua de `jscpd`

Comanda: `npx jscpd web web-react --min-lines 8 --reporters json,console`
(JSON complet a `/tmp/audit-out/jscpd/jscpd-report.json`, 135 clons).

### B.1 Taula resum per format

```
│ Format     │ Files │ Total lines │ Total tokens │ Clones │ Dup lines      │ Dup tokens        │
├────────────┼───────┼─────────────┼──────────────┼────────┼────────────────┼───────────────────┤
│ css        │ 3     │ 3311        │ 49431        │ 5      │ 46 (1.39%)     │ 412 (0.83%)       │
│ javascript │ 19    │ 1147        │ 5431         │ 0      │ 0 (0.00%)      │ 0 (0.00%)         │
│ json       │ 2     │ 5229        │ 16268        │ 2      │ 43 (0.82%)     │ 139 (0.85%)       │
│ jsx        │ 113   │ 23331       │ 135038       │ 51     │ 629 (2.70%)    │ 3930 (2.91%)      │
│ markdown   │ 1     │ 45          │ 244          │ 1      │ 29 (64.44%)    │ 1091 (447.13%)    │
│ markup     │ 30    │ 2803        │ 18351        │ 25     │ 1073 (38.28%)  │ 4991 (27.20%)     │
│ python     │ 104   │ 26844       │ 147570       │ 51     │ 1464 (5.45%)   │ 6774 (4.59%)      │
│ text       │ 1     │ 45          │ 223          │ 0      │ 0 (0.00%)      │ 0 (0.00%)         │
├────────────┼───────┼─────────────┼──────────────┼────────┼────────────────┼───────────────────┤
│ Total:     │ 273   │ 62755       │ 372556       │ 135    │ 3284 (5.23%)   │ 17337 (4.65%)     │
└────────────┴───────┴─────────────┴──────────────┴────────┴────────────────┴───────────────────┘
Found 135 clones.
```

### B.2 Top clons per línies (exclou SVG d'assets idèntics)

```
 81L python  api/staff/_common.py:1-81   <->  api/staff/pendents.py:1-75
 78L python  api/staff/_common.py:1-78   <->  api/staff/audit.py:1-77
 78L python  api/staff/_common.py:1-78   <->  api/staff/configuracio.py:1-77
 78L python  api/staff/_common.py:1-78   <->  api/staff/dashboard.py:1-77
 78L python  api/staff/_common.py:1-78   <->  api/staff/feedback.py:1-77
 78L python  api/staff/_common.py:1-78   <->  api/staff/historial.py:1-77
 78L python  api/staff/_common.py:1-78   <->  api/staff/propostes.py:1-75
 78L python  api/staff/_common.py:1-78   <->  api/staff/senyal.py:1-77
 78L python  api/staff/_common.py:1-78   <->  api/staff/solicituds.py:1-77
 77L python  api/staff/_common.py:1-77   <->  api/staff/usuaris.py:1-72
 67L python  api/staff/albums.py:13-79   <->  api/staff/estat.py:14-79
 58L python  api/staff/_common.py:15-72  <->  api/staff/albums.py:16-73
 54L python  api/staff/_common.py:1-54   <->  api/staff/cancons.py:1-52
 43L python  api/staff/_common.py:1-43   <->  api/staff/top.py:1-43
 38L python  api/staff/_common.py:41-78  <->  api/staff/artistes.py:47-80
 30L python  api/staff/_common.py:43-72  <->  api/staff/top.py:51-80
 26L jsx     src/pages/AlbumPage.jsx:38-63            <->  src/pages/CancoPage.jsx:43-68
 26L jsx     src/pages/ArtistaDashboardPage.jsx:424-449 <-> ArtistaDashboardPage.jsx:570-595
 22L jsx     src/components/staff/LastfmPanel.jsx:17-38 <-> MusicBrainzPanel.jsx:11-32
 22L jsx     src/pages/staff/PendentsPage.jsx:24-45   <->  StaffArtistesSenseInstagramPage.jsx:22-40
 21L markup  templates/web/403.html:5-25  <->  templates/web/404.html:5-25
 19L jsx     src/components/staff/ArtistaPicker.jsx:22-40 <-> ArtistesColPicker.jsx:28-46
 19L jsx     src/pages/AlbumPage.jsx:38-56 <-> src/pages/ArtistaPage.jsx:41-59
 19L jsx     src/pages/OnboardingPage.jsx:283-301 <-> src/pages/PerfilUsuariPage.jsx:206-217
 13L markup  templates/web/403.html:5-13  <->  templates/web/500.html:5-13
 13L markup  templates/web/403.html:13-25 <->  templates/web/500.html:13-25
```

(Els dos clons `markup` més grans —216 L i 175 L— són els SVG de logo
`src/assets/logo-topquaranta-rect*.svg` ↔ `static/web/img/logo-topquaranta-rect*.svg`:
el mateix asset de marca servit a banda SPA i banda Django; esperable, no és deute
de codi.)
