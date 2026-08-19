# Sonda read-only — quina textura de fets de grup és fonamentable per al brief de la newsletter

Data: 2026-06-07. Read-only (BD prod). Cap canvi de codi ni dades.

## Abast (cohort)

El top només existeix des de fa **8 setmanes** (2026-04-13 → 2026-06-01),
així que la cohort = **tot el top**: 157 artistes principals distints i
370 cançons distintes que han estat al TopSetmanal (qualsevol territori)
en aquestes 8 setmanes. "Últimes 8-12 setmanes" = tot l'històric.

---

## 1. Origen geogràfic + granularitat · COBERTURA ALTA

| Senyal | Valor (cohort=157 main) |
|---|---|
| Amb **municipi** (→ comarca + territori) | **155 (98.7%)** |
| Només `localitat_manual` (sense municipi) | 3 |
| Sense cap localitat | 0 |
| Amb territori (M2M) | 157 (100%) |
| Comarques distintes cobertes | **38** |
| Municipis distints | 73 |

**Granularitat: tenim COMARCA**, no només municipi/territori. La cadena és
`ArtistaLocalitat.municipi → Municipi.comarca` + `Municipi.territori`. El
cas "so riberenc" (Ribera Alta) és **plenament fonamentable**: el 98.7 %
dels artistes del top tenen municipi, d'on es deriva la comarca. Forat:
3 artistes només amb text manual (origen no-PPCC o override) i, per tant,
sense comarca estructurada.

---

## 2. Col·laboradors + el seu origen · COBERTURA MITJANA

| Senyal | Valor |
|---|---|
| Cançons del top amb ≥1 col·laborador | **106 / 370 (28.6%)** |
| Col·laboradors distints al top | 143 |
| Col·laboradors **amb municipi** (origen) | **84 / 143 (58.7%)** |
| Col·laboradors aprovats | 84 (= els mateixos amb origen) |

`Canco.artistes_col` ens dóna els col·laboradors per tema de forma neta.
L'angle "amics de tot arreu" és **parcialment fonamentable**: ~59 % dels
col·laboradors tenen origen conegut. **Forat clar:** els 59 col·laboradors
sense origen (143−84) són exactament els **pendents** (l'origen es cura en
aprovar), així que un tema amb un col·laborador pendent no tindrà l'origen
d'aquell col·laborador.

---

## 3. Història al top per artista · DERIVABLE NET de TopSetmanal

Per artista, agregant `TopSetmanal` (setmanes, millor posició, primera
aparició) surt net:

| Mètrica | Valor |
|---|---|
| Artistes amb història | 157 |
| Setmanes al top (mitjana / màx) | 3.1 / 8 |
| Debutaren a la setmana 1 (2026-04-13) | 92 |
| Debutaren a l'última setmana (2026-06-01) | 3 |

`setmanes_al_top = count(DISTINCT setmana)`, `millor_posicio =
min(posicio)`, `primera_aparició = min(setmana)` per artista — tot
derivable amb una sola agregació. **"Primera aparició des que existeix el
top"** és fiable PERÒ amb l'asterisc que el top només té 8 setmanes: 92
dels 157 "debutaren" a la setmana 1 simplement perquè és quan va néixer el
top (no és un debut real, és l'inici). Els debuts genuïns són els de
setmanes posteriors (p. ex. 3 a l'última setmana).

---

## 4. Data de llançament + marca de novetat · DATA 100%, "marca" NO existeix

| Senyal | Valor |
|---|---|
| Cançons del top amb `data_llancament` | **370 / 370 (100%)** |
| Cançons del top verificades | 370 / 370 (100%) |

`Canco.data_llancament` té **cobertura total** al top. **PERÒ no existeix
cap camp/propietat `is_verified_recent_release`** (ni cap marca de novetat
booleana persistida). La novetat es **deriva** a `social/payload.py::
build_novetats`: cançó `verificada=True` + `data_llancament` dins una
finestra mòbil (des de l'última publicació del mateix tipus fins a la data
de publicació). És fonamentable (data 100 % + verificada 100 %), però com
a **derivació**, no com a flag llest per llegir.

---

## 5. Etiqueta de gènere / escena · GAIREBÉ BUIT (excepte tags Last.fm)

| Senyal | Cobertura cohort | Fiabilitat |
|---|---|---|
| `Artista.genere` | **0 / 157** (1/2003 global) | inservible — pràcticament mai poblat |
| `Canco.ml_classe` (A 244 / B 79 / C 31 / buit 16) | 354/370 | **NO és gènere** — és la classe de confiança del verificador ML (aprovar/rebutjar); no usar com a escena |
| `Artista.lastfm_tags` | **110 / 157 (70%)** | proxy d'escena raonable però sorollós (crowd-sourced: pot incloure "seen live", "favourites"…) |
| `Artista.mb_tags` | 11 / 157 (7%) | massa escàs |
| `Artista.percentatge_femeni` | 50 / 157 (32%) | senyal de diversitat, no gènere |

**Conclusió punt 5:** l'única etiqueta d'escena amb cobertura útil són els
**`lastfm_tags` (70%)**, i amb reserves (soroll). `genere` està buit i
`ml_classe` NO és gènere (matís important: el nom enganya). Per a un brief,
els tags de Last.fm donen una pista d'escena per a ~2/3 dels artistes;
la resta, res estructurat.

---

## 6. Setmanes que fa que existeix el top

- **8 setmanes publicades** (DISTINCT setmana a TopSetmanal): 2026-04-13
  (primera) → 2026-06-01 (última).
- `music.dates.project_week_number` de l'última (dissabte 2026-06-06) ≈
  **setmana 40** del projecte (àncora: dissabte 2026-04-25 = wk34). Nota:
  el comptador de "setmana de projecte" està ancorat històricament i NO
  coincideix amb "setmanes que fa que existeix el top" (8); per al brief,
  el nombre rellevant de continuïtat real és **8**.

---

## Síntesi: què és fonamentable per al brief

| Punt | Fonamentable? | Granularitat | Cobertura | Forat |
|---|---|---|---|---|
| 1. Origen geogràfic | **Sí, fort** | **comarca** (+ municipi + territori) | 98.7% | 3 sense municipi |
| 2. Col·laboradors + origen | Parcial | municipi | 29% temes amb collab; 59% collabs amb origen | collabs pendents sense origen |
| 3. Història al top | **Sí, net** | per artista | 100% derivable | només 8 setmanes de base |
| 4. Data llançament | **Sí** (derivat) | per cançó | 100% data; cap flag persistit | `is_verified_recent_release` no existeix |
| 5. Gènere / escena | **Feble** | tags | lastfm_tags 70% (soroll); genere 0% | sense etiqueta neta; ml_classe ≠ gènere |
| 6. Antiguitat del top | **Sí** | — | 8 setmanes | base curta |

**Més sòlid per fonamentar:** origen comarcal (≈99 %), història al top
(net, 100 %), data de llançament (100 %). **Més fluix:** escena/gènere
(només Last.fm tags, sorollosos) i origen de col·laboradors (59 %).

Cap acció presa (read-only).
