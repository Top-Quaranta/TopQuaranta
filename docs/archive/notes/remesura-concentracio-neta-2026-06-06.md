# Remesura de concentració sobre dades NETES (delta robust) — 2026-06-06

> Sessió **read-only** sobre prod (MCP `hetzner`). Cap escriptura. Arbre del servidor net.
> Recàlcul read-only del top-40 de les 7 setmanes amb el **delta robust** (#151), replicant
> l'elegibilitat de l'algorisme, i comparant la concentració amb scores **inflats (OLD)** vs
> **nets (NEW)**. Focus BAL / Maria Jaume.

## Mètode
Per a cada setmana, replico `_top_for_territoris` (Canço verificada+activa dins caducitat, match
de territori per artista/col·laborador; senyals 14 dies; past-top només `setmana < S`; monopoli) i
construeixo el top-40 dues vegades: amb `_compute_weekly_plays` **OLD** (desplegat) i amb la versió
**NEW** (robusta, floor 300). Així aïllo l'efecte de netejar les fusions sobre la concentració.

**Limitació honesta**: el recàlcul no reprodueix exactament el top-40 emmagatzemat (la sèrie de
`SenyalDiari` ha crescut des de cada run; el `today` i l'estat difereixen lleugerament). Per això
comparo **OLD-recompute vs NEW-recompute amb elegibilitat idèntica** (que aïlla net la neteja), i
em recolzo en les setmanes SENSE fusió de la primera sonda com a evidència de concentració real.

## BAL — concentració OLD vs NEW (recompute, top-40)
| Setmana | OLD (n, màxArt, art≥3, top3Art, HHIart) | NEW (mateixes) | Maria Jaume top40 / top10 |
|---|---|---|---|
| 04-13 | 40, 7, 8, 0.45, 0.110 | **idèntic** | 0 / 0 |
| 04-20 | 40, 7, 7, 0.42, 0.098 | **idèntic** | 0 / 0 |
| 04-27 | 40, 7, 6, 0.47, 0.104 | **idèntic** | 7 / 4 |
| 05-04 | 40, 7, 6, 0.42, 0.094 | **idèntic** | 7 / 4 |
| 05-11 | 40, 7, 5, 0.45, 0.099 | **idèntic** | 7 / 4 |
| **05-18** (fusió) | 40, 5, 8, 0.33, 0.073 | **idèntic** | 5 / 3 |
| 05-25 | 40, 8, 6, 0.45, 0.103 | **idèntic** | 8 / 5 |

**La concentració per compte (cançons per artista, HHI, quota top-3, presència al top-10) és
IDÈNTICA amb scores inflats i nets a TOTES les setmanes**, inclosa la de fusió (05-18). La neteja
del delta robust **no canvia gens** la concentració estructural.

## Què era artefacte i què és real
- **Artefacte de fusió**: les **magnituds** (scores) i la **identitat del #1**. A BAL 05-18, el #1
  passava de «Noia de Porcellana» (Pau Riba, score inflat 8141) a «Sant Domingo Forever» (Maria
  Jaume, net 345) — això sí canvia (vegeu #151). La fusió va inflar scores i va falsejar el cim.
- **Real (no artefacte)**: la **concentració estructural**. Maria Jaume manté **7-8 de 40 places**
  i **3-5 del top-10** a BAL cada setmana activa, amb scores nets. Dues proves:
  1. OLD-recompute == NEW-recompute a totes les setmanes (la neteja no la toca).
  2. Les setmanes **SENSE fusió** (05-04, 05-11; mA9 a la primera sonda count-based) ja tenien la
     concentració màxima — la fusió (05-18) ni tan sols va produir el pic. La concentració existeix
     independentment de les fusions.

## Veredicte (BAL / Maria Jaume)
**La concentració real, ja sense spikes, SÍ es manté i és substancial.** No era un artefacte de
fusió: un sol artista domina estructuralment el xart d'un territori petit (BAL) ocupant ~1/5 del
top-40 i fins a la meitat del top-10, amb HHI ~0.10 i quota top-3 ~0.45. La fusió només va inflar
les magnituds i el #1 d'una setmana; treure-les no rebaixa la concentració. → Si es vol actuar
sobre la dominància d'un artista en territoris petits, és una **decisió editorial real** (no es
resol amb el fix de la fusió). **STOP de producte**: això ho decidiu vosaltres; jo només ho mesuro.

### Abast i límits
- Recompute centrat en **BAL** (el focus); CAT/VAL són difusos a la primera sonda (màx 3-5
  cançons/artista, HHI ~0.04-0.06) i la lògica robusta no els canvia (la fusió tampoc els
  concentrava). PPCC (agregat) i ALT (paraigua) exclosos del recompute directe.
- El recompute OLD no reprodueix byte a byte el top-40 emmagatzemat (drift de `SenyalDiari`); la
  comparació vàlida és OLD-recompute vs NEW-recompute (elegibilitat idèntica), que aïlla la neteja.
- Concentració mesurada per **compte** d'entrades (com la primera sonda). La fusió afectava
  magnituds, no comptes, així que el compte ja era real; el que aquesta remesura afegeix és la
  CONFIRMACIÓ que netejar no el rebaixa.
