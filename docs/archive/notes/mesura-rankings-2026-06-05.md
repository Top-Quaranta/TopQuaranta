# Mesura: «debuts al cim» — artefacte narratiu vs efecte algorísmic

> Sessió **read-only** sobre prod. Data: 2026-06-05. Repo a `fc22e8c` (main), igual a prod.
> **Cap escriptura**: només ORM de lectura (`.objects.filter/values/count`) + crides pures als
> detectors narratius (que llegeixen `TopSetmanal` però no escriuen). Verificat: `git status`
> del working tree del servidor **net** abans i després.
>
> **Accés a prod**: via MCP `hetzner` → `sudo -u topquaranta DJANGO_SETTINGS_MODULE=
> topquaranta.settings.production .venv/bin/python - <<heredoc`. Scripts passats per **stdin**,
> cap fitxer escrit al disc del servidor. Cap management command, cap `.save/.create/.delete`,
> cap migració.
>
> **Font**: `TopSetmanal` (oficial). **Finestra**: les **7 setmanes** que existeixen a la taula
> (no n'hi ha 8). `setmana` és el **dilluns ISO** de la setmana (publicació real dissabte):
> `2026-04-13, 04-20, 04-27, 05-04, 05-11, 05-18, 05-25`. Territoris amb dades: **CAT, VAL, BAL,
> PPCC, ALT** (els altres 5 codis del projecte no tenen rànquing en aquesta finestra). ALT té
> tops molt curts (0–10 entrades).

---

## 0. Orientació al codi (read-only)

### TopSetmanal — què es persisteix (`ranking/models.py:260-318`)
Per entrada: `canco` (FK SET_NULL), `territori`, `setmana` (DateField, dilluns ISO), `posicio`,
`score_setmanal` (**float, score FINAL**), `canco_nom_snapshot`, `artista_nom_snapshot`,
`algorithm_version`, `config_snapshot` (JSON amb els coeficients del moment), `created_at`.

**No es persisteix**: ❌ posició de la setmana anterior · ❌ cap flag de debut/reentrada ·
❌ score cru (pre-penalització) · ❌ weekly_plays. → Limitacions importants per a (a) i (c).

### calcular_top — `ranking/algorisme.py::calcular_top_territori` (comando `calcular_top`)
`final_score = weekly_plays × age_factor × past_top_factor × monopoli_factor`
- `weekly_plays`: delta absolut de `lastfm_playcount` en finestra ~7 dies (clamp ≥0).
- `age_factor = 1 − min(1, (dies/365)^exponent)` → com més nova la cançó, més a prop d'1.
- `past_top_factor = max(0, 1 − Σ coef/2^(pos−1))` sobre aparicions prèvies al top.
- `monopoli = (1−pen_album)^(àlbums_previs) × (1−pen_artista)^(artistes_previs)`, aplicat
  **després** d'ordenar per base_score (els ja rankejats "veuen" els posteriors).
- Floor: `final_score ≥ 1.0` per persistir; arrodonit a 2 decimals.

### Motor narratiu — `social/narrative/scenarios.py`
**13 detectors A1–A13 + fallback** (⚠️ el `CLAUDE.md` diu «8 detectors a1-a8»: **desactualitzat**,
el codi en té 13). `detect_all(territori, setmana)` crida tots, ordena per `severity` desc; el
compositor agafa el de més severity com a **hero**. Els detectors **llegeixen `TopSetmanal`
directament** (no reben `entries`) → re-executables read-only només amb `(territori, setmana)`.

**Detector "debut al cim" = A4 `detect_a4_debut_alt` (línia 228)**:
> cançó amb `posicio ≤ 3` que **no apareixia al `TopSetmanal` de la setmana anterior**.
> Severity = `10 − posicio`. **Cap comprovació d'edat real de la cançó.** El criteri de "debut"
> és purament *no-hi-era-la-setmana-passada*.

Altres amb sabor de "debut/arribada al cim": A1 (salt al #1 des de fora del top), A6 (cançó
≤30 dies al top 10), A10 (artista per primer cop en la història del territori), A9 (debut #4–40).

**Persistència del hero/text**: ❌ **NO es persisteix** ni l'escenari triat ni el text generat.
`SocialPost.metadata` només guarda `{slides, caption_len}`. `NarrativePhraseUsage` només guarda
IDs de frase (anti-repetició). → Les frases hero d'aquest informe estan **regenerades** amb
crida pura (etiquetades com a tal), no llegides de la BD.

### Inventari de contrapesos
| Paràmetre | Origen | Default |
|---|---|---|
| `exponent_penalitzacio_antiguitat` | **ConfiguracioGlobal** (editable staff) | 2.5 |
| `penalitzacio_album_per_canco` | **ConfiguracioGlobal** | 0.25 → ×0.75 |
| `penalitzacio_artista_per_canco` | **ConfiguracioGlobal** | 0.20 → ×0.80 |
| `coeficient_penalitzacio_top` | **ConfiguracioGlobal** | 0.04 |
| `min_escoltes_top` | **ConfiguracioGlobal** | 5 |
| `ppcc_penalitzacio_per_posicio` | **ConfiguracioGlobal** | 0.04 |
| Llindars detectors narratius (≤3, ≤30d, ≥180d, climb≥10, sev) | **HARDCODED** a `scenarios.py` | — |
| Criteri de "debut" (= no-prev-week) | **HARDCODED** a A4/A9 | — |
| `DIES_CADUCITAT=365`, floor score 1.0, finestra ±3d | **HARDCODED** | — |

Els contrapesos de l'**algorisme** són editables des de staff. Els llindars i el criteri de
"debut" del **motor narratiu** són hardcoded (requereixen codi).

---

## (a) Edat de la cançó vs posició, i debuts reals

Edat = `setmana − data_llancament` (dies). Edats negatives = release datat pocs dies després del
dilluns-àncora (publicació dissabte, novetats del divendres). 1.168 entrades, 0 amb edat NULL.

### Distribució per bucket d'edat (totes les setmanes i territoris)
| Bucket | Totes | Top 5 (170 slots) | Top 1 (34 slots) |
|---|---|---|---|
| ≤7 dies | 92 | 12 | **0** |
| 8–14 | 40 | 1 | 0 |
| 15–30 | 120 | 17 | 5 |
| 31–90 | 535 | 96 | 16 |
| >90 | 381 | 44 | 13 |

- **Top 5 ocupat per cançons ≤30 dies: 30/170 (18%)**; per ≤7 dies: **12/170 (7%)**.
- **Top 1 ocupat per ≤30 dies: 5/34 (15%)**; per ≤7 dies: **0/34 (0%)**.
- → El cim és **majoritàriament catàleg**: 82% dels slots del top 5 i 85% del top 1 són cançons
  de >30 dies. El #1 **mai** l'ocupa una cançó de ≤7 dies en aquesta finestra.

### Debuts
Criteri usat (com el detector): *cançó no present al `TopSetmanal` de la setmana anterior, mateix
territori*. Exclosa la 1a setmana (2026-04-13) per manca de baseline → **6 setmanes comptades**.
També calculo "true-first" = mai vista abans en cap setmana de la finestra.

- **Total debuts: 445** · true-first: 333 · **re-entrades: 112** (25% dels "debuts" són cançons
  que ja havien estat al top i hi tornen — el criteri no-prev-week les compta com a debut).
- **Debuts directament al #1: només 4** en 6 setmanes, edats **164, 164, 59, 24 dies** (cap fresc):
  CAT/PPCC 04-20 (164d), BAL 04-27 (59d), BAL 05-18 (24d).
- **Debuts al top 5: 38**. Edats molt disperses: moltes >90 dies (164, 298, 215, 220, 171, 158…).
- Edat dels debuts (bucket): ≤7d:70 · 8-14:17 · 15-30:44 · 31-90:152 · >90:**162**.

⚠️ **Artefacte d'arrencada en fred (2026-04-20)**: 18 dels 38 debuts-al-top5 cauen aquesta
setmana, perquè la setmana anterior (04-13) va ser **el primer rànquing mai calculat**. Són
cançons velles (164, 298, 215d) que "debuten" només perquè el tracking acabava de començar. Sense
04-20, els debuts genuïns al top 5 amb material recent són pocs.

### Velocitat i volatilitat
Cap debut al #1 era de material fresc (mín. 24 dies). Cas de volatilitat net (debut fresc fort i
caiguda): **BAL 2026-05-18**, debut al **#1** (edat 24d) — la setmana següent (05-25) ja no és al
top 5. Material fresc que entra fort i no aguanta. La majoria de moviment fort al top prové de
**re-entrades de catàleg** i de la setmana d'arrencada, no d'un flux sostingut de novetats.

---

## (b) Escenaris narratius vs realitat

Hero (escenari de més severity) per `(territori, setmana)`, re-executant `detect_all` read-only.
**A4 mai surt com a hero en cap de les 35 combinacions.** Heroes dominats per a1/a6/a8.

### Heroes realment publicats (`SocialPost status=publicat`, tipus top_*)
PPCC es publica cada setmana + 2 territorials rotatius. 15 headlines top reals:

| Setmana | PPCC | territorials publicats (hero) |
|---|---|---|
| 04-20 | — | CAT **a1** (Rosalía «Divinize» arrabassa #1) |
| 04-27 | **a8** (pujada) | BAL **a1**, VAL **a10** (first-ever) |
| 05-04 | **a6** (recent) | BAL **a8**, CAT **a6** |
| 05-11 | **a6** | CAT **a6**, VAL **a8** |
| 05-18 | **a10** (first-ever) | BAL **a8**, VAL **a8** |
| 05-25 | **a6** | BAL **a5**, CAT **a6** |

Recompte headlines publicats: **a6 ×5, a8 ×5, a1 ×2, a10 ×2, a5 ×1; A4 ×0.**
→ **9 de 15 (60%)** dels headlines top asserteixen arribada/frescor/first-ever al cim (a1+a6+a10).

### A4 ("debut al cim") — falsos positius / negatius
Per construcció **A4 dispara ⇔ existeix pos≤3 no-present-la-setmana-anterior**, així que no té
"falsos positius" respecte el seu propi criteri. Els problemes són uns altres:

1. **Fals positiu estructural a l'arrencada (4 casos)**: 2026-04-13 (PPCC, CAT, VAL, BAL) A4 dispara
   "debuta al #1" tot i **no existir cap setmana anterior**. Sense baseline, *tota* la llista és
   trivialment "nova". La plantilla A4 ho verbalitza com **"a la primera setmana"**.
2. **A4 etiqueta catàleg vell com a debut**: els debuts top≤3 inclouen edats de 164, 298, 215 dies.
   La plantilla afirma frescor que sovint és falsa.
3. **Fals negatiu de messaging**: A4 **mai** guanya el hero (0/35). Quan hi ha un debut fresc real al
   #1 (BAL 2026-05-18, edat 24d), el headline publicat parla d'una **altra** cançó (a8, salt de
   Júlia Colom). El debut queda enterrat.

### Frases hero literals (regenerades — NO persistides)
- PPCC 04-20 · hero **a1**: *«Rosalía arrabassa el 1r del top general amb "Divinize": la setmana
  anterior estava fora del top. 🚀»* — però **no hi havia setmana anterior comparable** (post-arrencada).
- CAT 04-13 · hero **a1**: *«Ouineta arrabassa el 1r de Catalunya… la setmana anterior estava fora
  del top.»* — **fals**: 04-13 és la primera setmana, no existeix anterior.
- PPCC 05-25 · hero **a6**: *«Cançó nova de pes: "Tots Som Súpers", de SX3, ja és al 2n del top
  general amb només 1 dia des de la publicació. 🆕»* — **cert**, debut genuïnament fresc.
- BAL 05-18 · hero **a8** (a8 guanya); **A4 hauria dit**: *«Pau Riba debuta al 1r de les Illes
  Balears amb "Noia de Porcellana" a la primera setmana. 🆕»* — clàssic re-editat; "a la primera
  setmana" enganya sobre la novetat real.

---

## (c) Concentració per artista i àlbum

Artista = **principal** (`canco.artista_id`; no compto `artistes_col`). HHI = Σ(quota²).

| Setmana·Terr | tot | màx art | art≥3 | quota top3 art | HHI art | màx àlb | HHI àlb |
|---|---|---|---|---|---|---|---|
| 04-13 CAT | 40 | 2 | 0 | 0.15 | 0.030 | 2 | 0.026 |
| 04-20 BAL | 40 | **7** | 5 | 0.47 | 0.107 | 5 | 0.069 |
| 04-20 VAL | 40 | 6 | 5 | 0.45 | 0.100 | 6 | 0.094 |
| 05-04 BAL | 40 | **9** | 5 | 0.57 | 0.141 | 9 | 0.113 |
| 05-11 BAL | 40 | **9** | 6 | 0.53 | 0.138 | 9 | 0.101 |
| 05-25 BAL | 40 | 8 | 6 | 0.45 | 0.100 | 8 | 0.080 |
| 05-25 PPCC | 40 | 5 | 2 | 0.25 | 0.049 | 5 | 0.040 |
| 05-25 CAT | 40 | 3 | 3 | 0.23 | 0.041 | 3 | 0.034 |
| 05-18 ALT | 9 | **6** | 1 | 0.89 | 0.481 | 6 | 0.481 |
| 05-25 ALT | 10 | 7 | 1 | 0.90 | 0.520 | 7 | 0.520 |

(taula abreujada; valors representatius de la tendència, estable al llarg de les 7 setmanes)

- **PPCC i CAT difusos**: màx 3–5 cançons/artista, HHI ~0.04–0.06.
- **BAL molt concentrat**: un sol artista arriba a **9/40** (22%), quota top3 0.45–0.57, HHI 0.10–0.14.
- **ALT degenerat**: top de 7–10 entrades dominat per **un sol artista** (6–7 slots), HHI 0.48–0.78.
  Efectivament és el xart d'un artista. (top_territorial ALT no s'arriba a publicar.)
- Tendència: estable; lleugera baixada de concentració a la setmana d'arrencada (04-13, màx 2).

### Score cru vs final — **LIMITACIÓ**
`TopSetmanal` només guarda `score_setmanal` (**final**). No hi ha score cru ni `weekly_plays`
persistits → **no es pot aïllar quant mouen les penalitzacions**. No ho invento.
Evidència **indirecta** (consistent amb monopoli d'àlbum, no prova): PPCC 05-25, **Maria Jaume**
té **5 cançons del mateix àlbum** (id 14466) a posicions 7/12/19/24/40 amb scores finals en
cascada **439 → 248 → 157 → 102 → 26**. La caiguda monòtona dins d'un sol àlbum és compatible amb
`(1−0.25)^N` acumulant-se, però sense el cru no es pot quantificar.

---

## Lectura preliminar (sense proposar arreglos)

**Tots dos, amb pesos diferents segons el canal.**

**Component algorísmic REAL.** El motor de `weekly_plays × age_factor` permet genuïnament que una
novetat punxi amunt de pressa: SX3 al #2 amb 1 dia, 12 slots del top 5 amb cançons ≤7 dies, un
debut fresc al #1 (BAL 05-18). La volatilitat del material nou és real i mesurable. El detector
a6 ("cançó recent al cim") quan dispara **diu la veritat**.

**Component ARTEFACTE narratiu.** Tres mecanismes manufacturen sensació de "debut al cim" on no
n'hi ha:
1. **Criteri de "debut" = no-present-la-setmana-anterior** (A4/A9). Conflא debut genuí, re-entrada
   de catàleg (112/445 = 25%) i cançó vella que entra al tracking. El cim és 82% catàleg >30 dies,
   però el criteri etiqueta de "debut" coses de 164–298 dies.
2. **Plantilles que afirmen frescor falsa**: A4 diu sempre **"a la primera setmana"**; a1 diu
   **"la setmana anterior estava fora del top"** — fals a l'arrencada (no hi havia anterior) i
   enganyós per a re-entrades. A l'arrencada (04-13) això dispara per a 4 territoris alhora.
3. **Obligació de headline setmanal**: el motor *sempre* tria el hero de més severity i a8 (salt)
   i a6 (recent) pesen alt, de manera que fins i tot setmanes dominades per catàleg reben un titular
   de novetat/moviment. La sensació de rotació permanent és més intensa que la rotació real.

**Matís clau sobre A4**: el detector literal de "debut al cim" **mai s'ha publicat com a headline**
en aquesta finestra (0/35). El "cant de debuts al cim" que es veu publicat ve sobretot de **a6**
(que és majoritàriament veritat) i de **a1** (veritat tret de l'arrencada). El risc gros d'A4 és
**latent**: si algun dia guanya el hero, proclamarà "debuta a la primera setmana" sobre catàleg vell.

**On mirar després** (no és proposta, és on apunten les dades): el criteri no-prev-week com a
definició de "debut"; les afirmacions de frescor hardcoded a les plantilles A1/A4; i la
concentració estructural de BAL/ALT (un sol artista domina), que el motor narratiu encara no toca.

### Notes d'honestedat / no verificat
- Frases hero **regenerades** amb crida pura, no llegides de BD (el text no es persisteix). El text
  exacte publicat pot diferir (selecció aleatòria entre variants + anti-repetició).
- `setmana` = dilluns ISO; edats calculades contra el dilluns, no contra el dissabte de publicació
  (±5 dies, irrellevant per als buckets).
- La 1a setmana (04-13) i bona part de 04-20 estан contaminades per l'arrencada en fred; marcat.
- Edats negatives (release post-àncora) comptades al bucket ≤7; són novetats reals.
- No s'ha pogut aïllar l'efecte de les penalitzacions (no hi ha score cru persistit).
- Heroes calculats per a tots els territoris; la taula de "publicats" es limita als `SocialPost`
  amb `status=publicat`, que és el que va sortir de veritat.
