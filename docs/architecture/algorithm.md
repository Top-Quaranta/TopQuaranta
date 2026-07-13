# CLAUDE_ALGORITHM.md — Ranking Algorithm

> Algorithm **v2.0** (2026-04-23). Python-first implementation in
> `ranking/algorisme.py`. Replaces the legacy 14-CTE SQL that was ported
> from the original PostgreSQL views.
>
> Motivation for the rewrite: the v1 pipeline relied on a pre-normalised
> `score_entrada` (percentile of daily playcount across the whole
> catalog) and mixed in heuristics for descent / novelty / smoothing.
> Those heuristics created a ranking that was hard to explain to the
> public and sensitive to ingestion gaps. v2.0 operates directly on the
> raw `lastfm_playcount` snapshots and keeps only the four factors we
> actually care about.

---

## 1. Inputs

For each territori the algorithm looks at:

1. **`SenyalDiari.lastfm_playcount`** — the raw cumulative Last.fm play
   count per (cançó, data). Ingested daily by `obtenir_senyal`
   (06:00 UTC). No normalisation; we consume it as-is.
2. **`TopSetmanal`** — every prior weekly ranking row for this
   (cançó, territori) at posicions ≤ 40. Used to compute the
   past-top-position penalty.
3. **`ConfiguracioGlobal`** — four editable coefficients:
   - `exponent_penalitzacio_antiguitat` (default **2.5**).
   - `coeficient_penalitzacio_top` (default **0.04**).
   - `penalitzacio_album_per_canco` (default **0.25**).
   - `penalitzacio_artista_per_canco` (default **0.2**).
   - `min_cancons_ranking_propi` (default 20) — optional-territori
     threshold.
   - `soft_cap_actiu` (default **False**), `soft_cap_multiplicador`
     (default **3**), `soft_cap_floor_escoltes` (default **500**),
     `soft_cap_base_top_n` (default **10**) — the adaptive outlier
     soft-cap (§2.1bis). All four are editable from /staff/configuracio.

---

## 2. Per-territori computation

```
base_score = weekly_plays × age_factor × past_top_factor
```

then post-process with monopoly multipliers, re-sort, top 100.

### 2.1 `weekly_plays`

Plays accumulated in the last 7 days:

```
weekly_plays = playcount_today − playcount_fa_7_dies
```

Casuístiques:

- **Release < 7 dies**: la cançó no existia fa una setmana, així que
  `weekly_plays = playcount_today` (tot el comptador és d'aquesta
  setmana). Sense extrapolation: projectar un ritme de 2 dies a 7
  fabricava xifres fantasma (decisió 2026-05-07).
- **Esglaó de fusió de Last.fm** (`_robust_weekly_from_series`,
  2026-06-06): Last.fm fusiona periòdicament els scrobbles d'una
  cançó cap a la gravació canònica i **duplica el comptador acumulat
  en una nit** amb el mateix NOM de track (events del 2026-04-22 i
  2026-05-21; la sonda en va trobar ~101 entrades inflades i diversos
  #1 falsos). El delta de 7 dies per extrems llegiria aquest esglaó
  com una setmana sencera. Quan dins la finestra estricta `(today-7,
  today]` hi ha un increment d'un sol dia que és alhora (a) ≥ 8× la
  mediana del ritme diari propi de la cançó, (b) ≥ 40 % de l'acumulat
  (una quasi-duplicació) i (c) ≥ 300 absoluts, s'**exclou** aquell dia
  i la setmana es reompli amb el ritme net dels altres dies. Una
  viralitat real s'escampa en diversos dies i no es toca. Actua només
  quan detecta l'esglaó; altrament cau al càlcul per extrems de sota
  (les setmanes sense fusió no canvien, i la setmana posterior a una
  fusió ja té l'esglaó al baseline, fora de finestra).
- **Track-switch guard** (2026-05-08): un baseline només val si es va
  mostrejar contra la MATEIXA gravació que el senyal d'avui
  (`lastfm_returned_track` normalitzat). Quan Last.fm canvia de track
  (live → studio, remix → original) el delta cru deixa de ser
  activitat setmanal; aquests casos cauen a 0 fins que SenyalDiari
  acumula un baseline nou. Diferent de l'esglaó de fusió (allà el nom
  NO canvia); els dos guards són additius.
- **Gap de dades** (no hi ha fila exactament a -7d): agafem la fila
  més propera dins d'una finestra de ±3 dies; si cap encaixa, caiem
  a qualsevol fila anterior ≥ 4 dies enrere i rescalem a denominador 7.
- **Diferència negativa** (Last.fm ha corregit scrobbles): es clampa
  a 0.
- Si no tenim prou dades per estimar (cap SenyalDiari recent):
  `weekly_plays = 0` i la cançó queda fora del ranking.

El `weekly_plays` cru es persisteix a `TopSetmanal.weekly_plays` (des de
2026-06-09) i és el que alimenta el sostre suau de §2.1bis i la mediana
històrica per territori.

### 2.1bis Sostre suau d'outliers (adaptatiu, per territori)

Problema: el score és lineal en `weekly_plays` i sense normalització, així
que un outlier de magnitud (p.ex. un artista mainstream amb ~20× els
scrobbles de qualsevol acte dels PPCC) domina el #1 durant mesos. Pujar
`coeficient_penalitzacio_top` actua sobre el TEMPS al top i castiga també
les cançons normals; el que cal és actuar sobre la MAGNITUD i només a la
cua alta.

Solució (off per defecte; `soft_cap_actiu`): comprimir les escoltes per
damunt d'un genoll `K`, deixant intacte tot el que hi queda per sota.

```
plays_eff = K · (1 + ln(plays / K))      si plays > K
          = plays                         si plays ≤ K
base_score = plays_eff × age_factor × past_top_factor
```

El genoll és **adaptatiu i per territori**, perquè cada territori juga en
una escala distinta (CAT charteja a centenars, VAL/BAL a desenes):

```
K_territori = max(soft_cap_floor_escoltes,
                  soft_cap_multiplicador × mediana(plays del top, W setmanes))
```

- **Població de la mediana**: les escoltes (`TopSetmanal.weekly_plays`) de
  les posicions ≤ `soft_cap_base_top_n` (camp config, default 10) sobre
  les últimes `_SOFT_CAP_WINDOW_WEEKS` (10) setmanes. S'usa el cap de la
  llista, no el top sencer: la cua arran de `min_escoltes_top` abaixaria
  la mediana i comprimiria hits ordinaris. La base és editable (no
  hardcodejada) perquè staff pugui afinar quanta llista defineix el
  "charting típic".
- **Multiplicador** (`soft_cap_multiplicador`, default 3): a partir de
  quantes vegades el charting típic del territori es considera outlier.
- **Terra** (`soft_cap_floor_escoltes`, default 500): genoll mínim. Protegeix
  els territoris menuts o sense prou historial (mediana inestable) i és el
  fallback quan encara no hi ha cap fila amb `weekly_plays`.

Propietats: la compressió és monòtona (preserva l'ordre entre outliers),
les cançons ≤ K no es toquen, i s'aplica per territori font ABANS de
l'agregació PPCC. L'eligibilitat (`min_escoltes_top`) es jutja sobre les
escoltes crues, no sobre les comprimides.

### 2.2 `age_factor`

```
age_factor = max(0, 1 − min(1, (dies / 365) ** exponent))
```

amb `exponent = exponent_penalitzacio_antiguitat` (2.5). Cançons
acabades de llançar ≈ 1.0; decreix lentament els primers mesos i
s'accelera cap als 365 dies.

### 2.3 `past_top_factor`

Penalització acumulada per aparicions prèvies al top setmanal.
Per cada fila de `TopSetmanal(canco=C, territori=T, posicio=N)`
amb N ≤ 40, suma:

```
penalty_N = coeficient_base / 2 ** (N − 1)
```

amb `coeficient_base = 0.04` per defecte. Exemples:

| Posició | Penalització |
|---|---|
| 1 | 4 % |
| 2 | 2 % |
| 3 | 1 % |
| 4 | 0.5 % |
| … | … (s'atenua ràpid) |

Totes les setmanes anteriors es sumen:

```
past_top_factor = max(0, 1 − Σ penalty_N)
```

Cap posició queda exempta, però les posicions baixes costen molt poc
per la divisió per 2ⁿ⁻¹. Si la penalització total supera 1 la cançó
surt del top (factor 0).

### 2.4 Monopoli (post-process)

Ordenem els candidats per `base_score` descendent i recorrem la llista.
Per cada cançó, comptem quantes cançons del mateix àlbum i quantes
del mateix artista principal han aparegut abans en aquesta mateixa
passada:

```
final_score = base_score
            × (1 − penalitzacio_album)    ** n_prev_mateix_album
            × (1 − penalitzacio_artista)  ** n_prev_mateix_artista
```

Defaults: àlbum **×0.75** per cançó prèvia, artista **×0.8** per
cançó prèvia. Multiplicatiu / exponencial, no additiu. Dos cançons
prèvies del mateix àlbum → ×0.5625, etc.

Després del monopoli reordenem per `final_score` i truncem a top 100.

### 2.5 `canvi_posicio`

Per visualització: diferència entre la posició actual i la posició a
la setmana immediatament anterior (TopSetmanal ordenat per
`-setmana`). NEW si no hi havia.

---

## 3. Agregació PPCC

PPCC no executa el càlcul per territori — agrega els resultats de
tots els territoris amb top propi (CAT, VAL, BAL, ALT +
opcionals amb prou volum):

1. Per cada fila, `score_global = score_setmanal × (1 − (pos − 1) × 0.04)`
   (penalització lineal del 4 % per posició al top d'origen).
2. Dedupliquem per `canco_id` conservant el `score_global` més alt.
3. Ordenem per `score_global` desc, top 100.

---

## 4. Suport territorial

- **Fixos** (sempre top): `CAT`, `VAL`, `BAL`.
- **Agregats** (sempre es generen): `ALT`, `PPCC`.
- **Opcionals**: `CNO`, `AND`, `FRA`, `ALG`, `CAR`. Només tenen top
  propi si arriben al llindar `min_cancons_ranking_propi` (default
  20) de cançons verificades actives dins la finestra `DIES_CADUCITAT`.
  En cas contrari les seves cançons entren dins d'`ALT`.

L'`ALT` funciona com a paraigües: acull artistes amb `territoris`
M2M = `{"ALT"}` + artistes de qualsevol territori opcional que no
arriba al llindar. Així cap cançó dels PPCC queda fora del sistema
encara que el seu territori natal tingui poca producció.

---

## 5. Config snapshot per reproducibilitat

Cada fila de `TopSetmanal` guarda `algorithm_version="v2.0"` i
`config_snapshot` amb els coeficients usats en aquell càlcul. Això
permet reproduir exactament el top d'una setmana històrica
encara que els defaults canviïn més endavant.
