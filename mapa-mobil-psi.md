# /mapa mòbil — regressió PSI (95 → 71, LCP 6.8 s) · diagnòstic NOMÉS-LECTURA

> Recon del 2026-06-13. **Cap canvi fet.** El /mapa és l'única pàgina que
> incompleix la decisió 10 (cap cost de rendiment en mòbil) després del
> redisseny, ara en producció. Base (2026-06-12): mòbil **95 / LCP 2.6 s**.
> Post-flip (2026-06-13): mòbil **71 / LCP 6.8 s**. Desktop intacte (100).

## TL;DR de la causa

El coll d'ampolla **NO** és el que semblava (la cascada de dades ni el panell
de miniatures). És el **mapa SVG**: en carregar `paisos.json` (394 KB cru,
10 150 punts) es construeix la geometria SVG **al fil principal durant el
render**, i això —sumat a la transferència de ~146 KB i a l'intercanvi de la
font Anton del títol— retarda la pintura de l'element LCP en un mòbil amb la
CPU escanyada ×4. La cascada de dades i les miniatures **no hi tenen part**
(ho demostre avall). **Avís honest:** PSI lab és UNA mostra i sorollosa; part
del salt 95→71 pot ser variància. Cal una 2a lectura abans d'invertir.

## El que he comprovat (dades reals de prod)

### 1. Cascada de crides de dades — NO és la causa
El /mapa dispara **3 fetches**, tots en paral·lel (hooks independents, al
muntatge), cap bloqueja l'altre:

| Crida | Mida a prod (overview PPCC) | Comentari |
|---|---|---|
| `GET /geodata/paisos.json` | **146 KB** (zstd) / 394 KB cru | l'únic pesat |
| `GET /api/v1/mapa/stats/?level=territori` | **451 B** | trivial |
| `GET /api/v1/mapa/artistes-top/?…&territori=PPCC` | **2 B (`[]`)** | **buit a l'overview** |

- Cap és síncrona ni bloqueja el primer render: el hero es pinta abans que
  arribe `paisos.json` (fetch async via `useGeoJSON`).
- `paisos.json` **ja se serveix comprimit** (Caddy `encode zstd gzip`,
  `content-encoding: zstd`, `vary: Accept-Encoding`) → la compressió **no és
  el problema**. Però són ~146 KB a transferir + **parsejar 394 KB de JSON** +
  **construir l'SVG sobre 10 150 punts** (`geometryToPath`) al fil principal.

### 2. Panell de miniatures — NO és la causa (a l'overview)
- `/mapa/artistes-top` retorna **`[]`** al nivell territori (PPCC): el panell
  lateral **no té cap miniatura** a la càrrega inicial de /mapa. Les 60
  imatges només apareixen en fer drill-down a un territori.
- Quan n'hi ha, són `limit=60`, `deezerImg(…, 250)`, `loading="lazy"`,
  `aspect-square` (dimensionades). En mòbil el panell va **sota** el mapa
  (apilat) → fora de viewport → lazy no les carrega.
- **Idèntic abans i després del redisseny** (git `8f672db` vs `4733149`):
  mateix `limit=60`, mateix `deezerImg(250)`, mateix `loading="lazy"`.

### 3. Pes del GeoJSON — el cost dominant (igual abans i ara)
- `paisos.json`: **393 803 B cru, 8 features, 10 150 parells de coordenades**.
  zstd → ~146 KB a la xarxa.
- Aquest fitxer **no l'ha tocat el redisseny** (mateix fitxer que a la base).
- (Per drill-down: `comarques-CAT` 387 KB, `municipis-CAT` **1,2 MB** — no
  afecten l'overview mesurat, però són candidats al mateix problema en
  navegar.)

### 4. Element LCP en mòbil — el text del hero, no l'SVG
- A l'overview **no hi ha cap imatge** (miniatures buides; no hi ha portades).
- Un `<svg>` inline amb `<path>` **no és candidat a LCP** (l'spec només compta
  `<image>` dins SVG, no `<path>`). Per tant **el LCP és un bloc de TEXT**: el
  més gran és el hero **«EL MAPA» en Anton** (`clamp(46px,9vw,118px)`), o el
  subparàgraf.
- Mecanisme de la regressió: el hero pinta aviat amb la font de fallback
  (`font-display: swap`), però la pintura **final** (quan arriba Anton) es
  retarda perquè (a) el woff2 d'Anton competeix amb els ~146 KB de
  `paisos.json` per l'amplada de banda mòbil escanyada, i (b) quan el JSON
  resol, **construir l'SVG de 10 150 punts és un long-task** que bloqueja el
  fil principal. El LCP queda marcat a l'instant d'eixa pintura final tardana.

> ⚠️ **No he pogut capturar una traça Lighthouse real** en aquest pas
> només-lectura (no està instal·lat localment i no volia tocar res). La
> identificació de l'element LCP és per raonament estructural (cap imatge a
> l'overview + l'SVG no és candidat ⇒ text del hero). **Confirmeu-ho amb una
> traça PSI/Lighthouse** abans d'invertir en la correcció #2/#3.

## Per què la base era 95 i ara 71 (delta)
Dades, GeoJSON i miniatures són **idèntics** (git-confirmat). Els únics canvis
del redisseny en aquesta pàgina:
- Fonts noves (**Anton** al hero, Bricolage al cos) — woff2 addicionals que
  competeixen amb el JSON; el hero Anton és probablement el nou element LCP.
- Shell rd + contenidor de vidre fosc (en mòbil = sòlid, **sense blur ni
  gra** — la media query `≥901px` ho garanteix; ho he verificat al bundle).
- El long-task de construcció de l'SVG no ha canviat, però ara pot coincidir
  amb l'intercanvi de la font del LCP.
El blur/gra **no** hi són en mòbil, així que la decisió 10 es compleix en
l'estètica; el cost és de **càrrega/CPU** (JSON + SVG + font), no de pintura.

## Opcions de correcció (ordenades per impacte/cost) — SENSE implementar

1. **Confirmar soroll vs real (cost 0).** Esperar 1–2 lectures més del cron
   `recollir_metrics_psi`. Una sola mostra de 71 pot incloure variància de
   lab; la base 95 també era d'una mostra. Decidir amb 2+ punts.

2. **Diferir la construcció de l'SVG fora del camí crític (impacte ALT, cost
   baix-mitjà).** Pintar el hero + un placeholder lleuger immediatament i
   muntar/derivar la geometria pesada després del primer paint
   (`requestIdleCallback`/efecte diferit, o memoitzar `geometryToPath`). Així
   el long-task no bloqueja la pintura final del text LCP ni l'intercanvi
   d'Anton. No toca dades.

3. **Aprimar `paisos.json` (impacte ALT, cost baix).** 394 KB / 10 150 punts
   és molt per a 8 contorns de territori a un overview. Re-executar
   `scripts/simplify_geodata.py` amb una tolerància més agressiva NOMÉS per a
   l'overview (els contorns de país no necessiten detall municipal) →
   objectiu < 100 KB cru i ~2–3 k punts → menys transferència + parse + build.
   (Aplica també a `comarques-*`/`municipis-CAT` 1,2 MB per al drill-down.)

4. **No demanar `artistes-top` a l'overview (impacte baix, cost baix).** Ara
   es crida sempre i retorna `[]` al nivell PPCC — crida supèrflua. Disparar-la
   només en drill-down (quan hi ha territori) estalvia una connexió en el
   moment de càrrega.

5. **Font del hero (impacte baix, cost baix).** Anton ja es precarrega
   (fix #231). Es pot afegir un `size-adjust`/`ascent-override` al fallback
   per reduir el reflow de l'intercanvi i estabilitzar el LCP.

6. **Subconjunt de geometria per nivell (impacte ALT, cost mitjà).** Servir un
   `paisos-overview.json` molt simplificat per al nivell territori i carregar
   la geometria detallada només en fer drill-down. Millora overview I
   drill-down a la vegada; més feina que #3.

### Recomanació
Fer **#1 primer** (confirmar que no és soroll, cost 0). Si es confirma real,
**#2 + #3** són els bons palanquejaments (alt impacte, baix cost) i ataquen la
causa estructural (long-task + pes del JSON) sense tocar dades ni scoring;
**#4** és una neteja barata que va de passada.

---
*Recon acabat. Cap canvi al repo ni a prod.*
