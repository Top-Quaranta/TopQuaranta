# Sonda: baseline de plays i reedicions (delta inflat per fusió de scrobbles)

> Sessió **read-only** sobre prod. Data: 2026-06-06. Repo/prod a `fc22e8c`.
> Accés via MCP `hetzner` → `manage.py`/python per stdin (heredoc), settings explícit,
> usuari `topquaranta`, res al disc del servidor. **Cap escriptura** (ORM de lectura +
> crides pures a `_compute_weekly_plays`). Arbre del servidor net abans i després.
>
> **Honestedat**: `SenyalDiari` només arrenca el **2026-04-10**. On l'historial és massa curt
> (sobretot la setmana 2026-04-20) ho marco i no sobreafirmo.

---

## PAS 0 — Verificació de #148 (render PPCC abans/després)

Vaig renderitzar el mateix story-set PPCC (`render_stories_ppcc`, 7 slides, mateixes entries
deterministes) a `main` i al branch `chore/remove-dead-stories-top` (#148) i vaig comparar el
SHA-256 de cada JPEG.

**Resultat (una línia): els 7 slides són byte-a-byte idèntics → #148 no canvia gens el render
PPCC** (només va eliminar el camí territorial mort `render_stories_top`, que el set PPCC no usa).

### Resum en pla dels PRs oberts (per a OK del Miquel)
- **#147** — Puja `react-router-dom` 7.14→7.17 al SPA. Tanca les 3 alertes Dependabot
  (RCE, DoS, open-redirect), totes al mateix paquet. Bump menor, no trencador; build verd.
- **#148** — Esborra codi mort: `render_stories_top` + helpers privats orfes + la constant
  `STORY_TOP_TERRITORIAL` + el test legacy. Verificat: el render PPCC no canvia (Pas 0).
- **#149** — Divideix `social.md` (estava clavat a 400 línies, el límit del gate) extraient la
  secció de l'engine narratiu a `social-narrative.md`. Contingut mogut verbatim, res perdut.
- **#150** — Honestedat narrativa: (3a) guarda de cold-start perquè a1/a4/a9 no cantin "debut"
  ni "fora del top" quan no hi ha setmana anterior; (3b) fet `is_verified_recent_release`
  computat i testejat però **sense cablejar** (decisió de producte pendent).

---

## PAS 1 — Com s'estableix el baseline `playcount_fa_7_dies`

`_compute_weekly_plays` (`ranking/algorisme.py:280`), en ordre de prioritat:

1. **Sense senyals** → `0.0`.
2. **Fresh release** (`data_llancament > today − 7d`): assumeix baseline = 0 i retorna
   `playcount_today` **sencer**. És a dir, **tot l'acumulat de Last.fm es compta com a plays
   d'aquesta setmana**. Sense extrapolació (cap projecció de ritme).
3. **Delta rodant** (preferit): agafa el senyal més recent com a "avui" i el més proper a
   `today − 7d` dins de ±3 dies com a baseline; `delta × 7 / gap`. Negatius → 0. El baseline
   es filtra pel **track-switch guard** (`_same_recording`): només val si la identitat
   normalitzada de `lastfm_returned_track` coincideix amb la de "avui".
4. **Fallback antic** (qualsevol senyal ≥4 dies enrere, mateixa identitat).
5. **Sense baseline vàlid** → `0.0`.

**Quan una cançó NO té senyal ~7 dies abans (acabada d'ingerir):** si `data_llancament < 7d`
cau a (2) i **aboca l'acumulat**; si és més vella, cau a (4) o, si no hi ha cap senyal ≥4d
enrere amb la mateixa identitat, a (5) → **0** (mai s'extrapola la vida sencera; decisió
2026-05-07 documentada al codi).

### Com es consulta Last.fm i si la reedició hereta l'acumulat
- Mètode **`track.getInfo` per `track` (títol) + `artist` (nom)**, `autocorrect=0`, amb MBID de
  recording si el tenim (`ingesta/clients/lastfm.py:108-152`). **Mai per ISRC** (Last.fm no en té).
- `playcount` retornat = **scrobbles acumulats de tota la vida** d'aquell títol+artista.
  Per tant **una reedició hereta tot l'històric**: «Noia de Porcellana / Pau Riba» (tema de 1971,
  `data_llancament` de reedició 2026-04-24) retorna desenes de milers de scrobbles de dècades,
  no els del release del 2026.

### Reconciliació amb el track-switch guard — per què Pau Riba va entrar #1
El guard **només compara el NOM normalitzat del track** entre baseline i "avui"; **no detecta
salts implausibles del comptador quan el nom no canvia**. El que va passar amb Pau Riba (i
desenes més) no va ser ni el fresh-branch ni un canvi de nom, sinó un **salt sobtat de
l'acumulat amb el mateix nom**:

```
Pau Riba / Noia de Porcellana (SenyalDiari, playcount cumulatiu):
  05-10..05-20: 8112 → 8129   (estable, ~2 plays/dia)
  2026-05-21:   8129 → 16262  ← DUPLICACIÓ overnight (+8133 en un dia)
  05-22..06-05: 16262 → 16314 (estable de nou)
```

El rànquing de la setmana 2026-05-18 es va calcular el **2026-05-23** (post-salt). El delta
rodant va llegir `16272 − 8116 ≈ 8156` plays com si fossin d'una setmana → score 7816 → **BAL #1**.
El guard no ho va aturar perquè el nom («Noia de Porcellana») era idèntic abans i després; només
el comptador es va fusionar (Last.fm va reconciliar els scrobbles del tema cap a la gravació
canònica). **No va ser el primer delta ni el fresh-branch: va ser una fusió de scrobbles
injectada a mig sèrie i absorbida com a activitat setmanal.**

---

## PAS 2 — Casos (sèrie de SenyalDiari + delta que els va puntuar)

| Cançó / artista | dl | Patró | Setmana puntuada | weekly_plays | Mecanisme |
|---|---|---|---|---|---|
| **Noia de Porcellana** / Pau Riba (reedició) | 2026-04-24 | 8129 → **16262 el 05-21** | BAL #1 05-18 | **8156** | Fusió overnight (×2) |
| **Gràcies per Tant** / La Fúmiga | 2025-10-23 | 4365 → **8748 el 05-21** | VAL #1 05-18 | **4456** | Fusió overnight (×2) |
| **Divinize** / Rosalía | 2025-11-07 | creixement suau ~5-8k/dia | CAT #1 (totes) | 24.8k–50.8k | **Genuí** (cap salt) |
| **Tots Som Súpers** / SX3 (infantil) | 2026-05-29 | 0 → 4656 en 1 dia | CAT/PPCC #2 05-25 | **4656** | Fresh-branch **honest** (release real) |

- **Pau Riba i La Fúmiga es van duplicar el mateix dia (2026-05-21)** i tots dos van saltar a #1
  la setmana que el rànquing va capturar el salt. Abans del salt, La Fúmiga feia deltes de
  **50-90 plays/setmana** (posicions 7-34); el salt li'n va donar **4456** → #1.
- **Rosalía** és el contraexemple honest: cançó realment massiva (3,1 M scrobbles, ~25-50k/setmana
  reals), #1 sense cap salt artificial. Demostra que el sistema sí distingeix volum real.
- **SX3** és l'altre cas honest: el fresh-branch aboca l'acumulat (4656) però el release és
  genuïnament nou (1 dia) i infantil amb públic immediat → tots els plays són reals d'aquesta
  setmana. L'abocament aquí és correcte.

**Comparació acumulat vs delta que puntua:** per Pau Riba, l'acumulat de Last.fm (16.3k) és
"vell"; el delta que el va puntuar (8.2k) és exactament la meitat abocada de cop pel merge, no
una setmana d'escoltes. Per Rosalía, l'acumulat (3,1 M) és enorme però el delta (25k) és activitat
setmanal real i proporcionada.

---

## PAS 3 — Abast i connexió amb la concentració

### Quantes entrades del top s'expliquen per un salt de fusió
Heurística (finestra estricta: salt DINS dels 7 dies del delta, que domina ≥60% del weekly_plays,
≥40% de la base i ≥1000 plays absoluts), sobre **888 entrades territorials**:

- **74 entrades (8.3%) inflades per fusió**, de les quals **7 són #1**, 14 més al top 5, 13 al
  top 10, 40 a la cua (11-40).
- Concentració temporal en **dos esdeveniments**: **2026-05-21 (68 entrades)** i 2026-04-22 (6).
- Els 7 #1 artificials: La Gent de la Mediterrània (VAL/BAL/ALT, 04-20, salt 04-22); Estrelles
  (CAT), Gràcies per Tant (VAL), Noia de Porcellana (BAL), La Gent de la Mediterrània (ALT) —
  tots 05-18, salt 05-21.
- (PPCC no inclòs: és agregat, no reconstruïble així. Els seus #1 hereten els territorials.)

### Maria Jaume a BAL — spike vs presència sostinguda
| Setmana | Patró |
|---|---|
| 04-27 | #1 Sant Domingo Forever **350 plays** + 6 més (100-280) — **sostingut** |
| 05-04 | #1 343 + 8 més — **sostingut** |
| 05-11 | #1 335 + 8 més — **sostingut** |
| **05-18** | **8 entrades, TOTES spike** (8224, 6908, 7871, 4679, 3679, 3467, 3010, 2872 plays ≈ ×20) |
| 05-25 | #1 542 + 7 més (224-476) — **sostingut** |

Maria Jaume domina BAL de manera **genuïna i sostinguda** (és #1 cada setmana amb ~340 plays
reals; BAL és un territori petit, així que poca activitat ja basta). PERÒ la setmana **05-18 la
fusió del 05-21 li va multiplicar ×20 tot el catàleg de cop** → les seves 8 entrades d'aquella
setmana són magnituds artefacte. La seva **concentració** (nombre d'entrades) és real; les
**magnituds del 05-18** no.

---

## Resposta clara: el primer delta aboca l'acumulat històric?

**No en els casos que importen.** Cal distingir dos mecanismes:

1. **Fresh-branch (primer delta)**: SÍ aboca l'acumulat sencer com a plays de la setmana 1, però
   en aquesta finestra només va disparar per a **releases genuïnament nous** (SX3), on és
   **correcte**. Cap reedició de la finestra va explotar el fresh-branch (Pau Riba ja tenia 29
   dies quan va puntuar).
2. **Salt de fusió a mig sèrie (l'artefacte real)**: el **2026-04-22 i sobretot el 2026-05-21**,
   Last.fm va **duplicar overnight** l'acumulat de moltes cançons (reconciliació de scrobbles cap
   a la gravació canònica). El delta rodant de 7 dies va absorbir aquest salt d'un dia com una
   setmana sencera → **74 entrades inflades, 7 #1 artificials**. El track-switch guard **no ho
   atrapa** perquè el nom del track no canvia.

Per tant: per Pau Riba, La Fúmiga, Estrelles, etc., **el que els va puntuar NO va ser el primer
delta ni el fresh-branch, sinó un abocament d'acumulat històric injectat a mig sèrie per una
fusió de Last.fm**, llegit com a activitat setmanal.

### No verificat / límits
- `SenyalDiari` arrenca 2026-04-10 → per la setmana 04-20 (run 04-26) els baselines són curts i
  no veig el comportament pre-04-10; els salts (04-22, 05-21) sí són visibles dins la sèrie.
- L'heurística de detecció de salts (74 entrades) és una aproximació calibrada; el nucli (els 7
  #1 i els dos dies d'esdeveniment) és robust, la cua (11-40) pot tenir ±algun fals positiu/negatiu.
- No he investigat la CAUSA upstream del merge a Last.fm (per què el 05-21); només el seu efecte.
- PPCC exclòs de la reconstrucció (agregat).
