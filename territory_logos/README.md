# Logos territorials de TopQuaranta — export per a brief de Claude Design

Exportats 2026-06-10 des de `vendor/mm-design/icons/territories/territory-*.svg`
(rasteritzats amb cairosvg, **fons transparent**, costat llarg **512 px**).
Material per a un brief de disseny — **NO publicat enlloc**.

## Recompte: 10 territoris (confirmat — Miquel deia 10 ✓)

N'hi ha **exactament 10**, un per cada codi de territori de la BD
(`CAT, VAL, BAL, PPCC, ALT, CNO, AND, FRA, ALG, CAR`). Cap en falta, cap en
sobra. Són **icones monocromes** (`fill="currentColor"`), és a dir
**silueta recolorable** — el renderer les pinta amb el color del territori.
Aquí cada PNG va tintat amb l'accent de marca del seu territori perquè es vegen.

| Fitxer | Codi disseny | Codi BD/repo | Territori | SVG font | Tint usat |
|---|---|---|---|---|---|
| `pri.png` | pri | CAT | Principat (Catalunya) | **`territory-ppcc.svg` (senyera)** | `#7bbf7b` |
| `val.png` | val | VAL | País Valencià | `territory-val.svg` | `#e8a44d` |
| `bal.png` | bal | BAL | Illes Balears | `territory-bal.svg` | `#5cc0cc` |
| `nor.png` | nor | CNO | Catalunya Nord | `territory-cno.svg` | `#dd7882` |
| `fra.png` | fra | FRA | Franja de Ponent | `territory-fra.svg` | `#d8b257` |
| `and.png` | and | AND | Andorra | `territory-and.svg` | `#7595cf` |
| `alg.png` | alg | ALG | L'Alguer | `territory-alg.svg` | `#d986a0` |
| `ppcc.png` | ppcc | PPCC | Global / Països Catalans | `territory-ppcc.svg` (senyera) | `#427c42` |
| `alt.png` | alt | ALT | Altres | `territory-alt.svg` | `#9aa0a6` |
| `car.png` | car | CAR | (territori CAR) | `territory-car.svg` | `#9aa0a6` |
| `pri_alt_web_cross.png` | pri (alt) | CAT | Catalunya — **variant web** | `territory-cat.svg` (creu) | `#7bbf7b` |

## ⚠️ Nota Catalunya = senyera (el "canvi")

Catalunya té **DUES representacions** al repo:

- **`territory-ppcc.svg` = la SENYERA** (4 barres). El renderer **social/feed**
  fa servir la senyera per a CAT (`renderer.py::_STORY_ICON_CODI = {"CAT":
  "PPCC"}`), perquè `territory-cat.svg` és una **creu** poc adient. Per tant,
  per al feed, **el logo de Catalunya és la senyera** → és el que hi ha a
  **`pri.png`**.
- **`territory-cat.svg` = una CREU** (creu de Sant Jordi). És el que encara fa
  servir el **web** (`TerritoriBadge`). L'he exportat a banda com a
  **`pri_alt_web_cross.png`** per si el brief el vol, però **per al feed la
  senyera (`pri.png`) és la bona**.

A més, **PPCC (global) i CAT comparteixen la mateixa art de senyera** —
`pri.png` i `ppcc.png` són la mateixa silueta, només canvia el tint.

## Per al brief

- Són **siluetes monocromes recolorables** (no banderes a tot color): Claude
  Design pot aplicar-hi qualsevol color. El tint d'aquí és només per a
  visibilitat/identificació.
- Mides variables (relació d'aspecte de cada SVG); totes amb el costat llarg a
  512 px i fons transparent.
