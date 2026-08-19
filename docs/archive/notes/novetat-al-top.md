# «Novetat al cim» — dades reals o artefacte? (2026-06-10)

> Investigació NOMÉS-LECTURA contra prod. Cap escriptura, cap Spotify.
> Pregunta: els textos que diuen que una cançó *acabada d'eixir* arriba al
> capdamunt reflecteixen les dades, o són artefacte narratiu/algorísmic?

## Com es genera la frase

Els "beats" de frescor del motor narratiu són els detectors **a4** (`DEBUT FORT
AL TOP`), **a6** (`NOVETAT AL CIM` / `PUJA RÀPID AL #1`), a9/a10/a12
(`social/narrative/scenarios.py`). El lèxic de novetat-de-publicació viu a
`social/narrative/freshness.py::RELEASE_NOVELTY_MARKERS` (estrena, novetat,
acaba de sortir, …).

**Hi ha una guarda, i ESTÀ connectada** (contràriament al que diu el docstring
de `freshness.py`, que ha quedat desfasat — la connexió va entrar amb #150/#154):

- **a6** crida `is_verified_recent_release(canco, ref_date=setmana)` i retorna
  `None` (cap escenari) si no és recent-verificat (`scenarios.py:383`).
- **a4/a9/a10/a12** marquen `scenario.data["freshness_blocked"]=True`
  (`scenarios.py:131`) quan no és recent-verificat; aleshores `registry.pick_phrase`
  filtra les frases que asserten novetat-de-publicació (`registry.py:86,93`).

`is_verified_recent_release` exigeix les 3 condicions: (1) `data_llancament`
dins de 30 dies; (2) cap marcador de versió al títol (live/remix/remaster/
reedició/acústic/versió); (3) artista no mort abans de la data
(`Artista.mb_end_date`).

## Evidència (top 10 PPCC, 4 setmanes)

| Setmana | Entrada | Artista | `data_llancament` | edat | Veredicte de la guarda |
|---|---|---|---|---|---|
| 2026-06-01 | #8 Un Lloc | Socunbohemio | 2026-05-14 | 18 d | **FRESH-CLAIM** (plausible) |
| 2026-05-25 | #2 Tots Som Súpers | SX3 | 2026-05-29 | **−4 d** | **FRESH-CLAIM** (data futura) |
| 2026-05-25 | #6 Nexo 10.bona Nit | Nil Moliner | 2026-05-22 | 3 d | FRESH-CLAIM (plausible) |
| 2026-05-18 | #5 Noia de Porcellana | **Pau Riba** | 2026-04-24 | 24 d | **BLOQUEJAT** (`artist_deceased_before_release`) ✅ |
| 2026-05-11 | #2 Inigualable | Max Navarro | 2026-04-17 | 24 d | FRESH-CLAIM (plausible) |
| 2026-05-11 | #3 Amor Artificial | OBESES | 2026-05-15 | **−4 d** | **FRESH-CLAIM** (data futura) |

## Veredicte

**Majoritàriament REAL i raonablement guardat — no és un artefacte sistèmic.**

1. **La guarda funciona en el cas clar.** Pau Riba (mort el 2022) amb una
   reedició datada recent queda **correctament bloquejat** — exactament
   l'artefacte que es volia evitar. La guarda no és decorativa.
2. **El volum és baix:** 1-2 fresh-claims per top-10 i setmana, i la majoria
   són estrenes plausibles (3, 18, 24 dies). No és un degoteig constant de
   falses novetats.
3. **Risc residual 1 — reedicions "netes":** la plausibilitat es basa en el
   títol + `mb_end_date`. Una reedició digital amb títol net d'un artista viu
   (sense marcador de versió) passaria la guarda amb una `data_llancament` de
   reedició → fresh-claim sobre material no original. No n'apareix cap en aquesta
   mostra, però la mesura del projecte (`mesura-capa2-3`, 2026-06-05) ja avisa
   que `data_llancament` sovint és la data de **reedició**, no l'original.
4. **Risc residual 2 — dates futures:** "Tots Som Súpers" (SX3) i "Amor
   Artificial" (OBESES) tenen `data_llancament` **posterior** a la setmana del
   rànquing (edat −4 d, que la guarda *clampa a 0 = "màximament fresc"*). Una
   cançó que ja puntua #2/#3 amb setmanes de scrobbles però amb data oficial
   futura és **internament inconsistent**: o la data és incorrecta, o és un
   pre-release/filtració. La frase "acaba de sortir" és discutible però la DATA
   en què es basa no és de fiar.

**Conclusió:** el text NO és artefacte gratuït — hi ha una guarda real i
efectiva, i les afirmacions de frescor són rares i normalment certes. El punt
feble no és el motor narratiu sinó la **fiabilitat de `data_llancament`**
(reedicions amb data recent + dates futures). Dues millores possibles (decisió
teua, no fetes aquí): (a) tractar `edat < 0` com a sospitós en lloc de
"màximament fresc"; (b) consumir el senyal de plausibilitat extra que ja
calcula `freshness.py` però que encara no afina aquests dos casos.
