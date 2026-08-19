# Auditoria de la suite de tests — 2026-08-18

> Inventari complet, test a test: `2026-08-18-auditoria-tests-inventari.md`.
> Arnés de mutació: `scripts/mutacio/` (README allà).

## Per què

En paraules del Miquel: 1.800 tests són massa coses on mirar, i la
meitat estan tan enganxats a un canvi concret que quan cal millorar
allò has d'esborrar-los i escriure'n de nous. Només hi eren per a
assegurar-se que les coses no funcionaren millor. Demostrat amb la
nostra història: `#41` (reset del motor narratiu) va esborrar 316
línies de test, `#322` 226, `#195` 94 — tots tres eren millores.

**La distinció que ho decideix** no és quants tests hi ha sinó a què
estan ancorats:

- *Promesa* → sobreviu a qualsevol millora («el pòster pesa < 1 MB»,
  «només Instagram converteix un nom en @handle»).
- *Implementació d'avui* → mor a cada millora («el buit d'ink és de
  −25 px ±8», «`sync()` s'ha cridat una vegada amb aquests args»).

**Pregunta diagnòstica:** *si algú millorara açò, el test fallaria?*
Si sí, no protegeix — impedeix.

## Inventari (abans de tocar res)

1.708 funcions de test llegides una a una i classificades:

| àrea | tests | P | D | M | fora+reescriu |
|---|---|---|---|---|---|
| social | 411 | 302 | 55 | 54 | 26 % |
| comptes | 147 | 106 | 18 | 23 | 27 % |
| topquaranta | 109 | 89 | 14 | 6 | 18 % |
| music | 212 | 175 | 23 | 14 | 17 % |
| analytics | 131 | 113 | 5 | 13 | 13 % |
| ranking | 72 | 62 | 5 | 5 | 13 % |
| ingesta | 280 | 254 | 8 | 18 | 9 % |
| web | 346 | 315 | 14 | 17 | 8 % |
| **total** | **1.708** | **1.416** | **142** | **150** | **17 %** |

P = promesa (es queda) · D = detector de canvis (fora) · M = promesa
mal ancorada (es reescriu perquè comprove la propietat, no la
coordenada).

**El que va dir de veres l'inventari.** No és «la meitat»: és un 17 %.
421 dels P porten una referència d'incident, ADR o post-mortem datat.
El problema estava *concentrat*: renders de `social/` (píxels, paletes
hex, ordre de builders), tautologies de model/`__str__`/dataclass, i un
patró recurrent de «promesa real afirmada via text exacte de
log/stdout, conjunt exacte de claus o `call_count`». Dels 31 pins de
forma de crida trobats amb grep, 12 eren P llegits de prop («no fa cap
crida extra si no hi ha MBID» és una promesa de quota, no un detector).

## Execució — 5 PRs per àrea

| PR | àrea | D fora | M reescrits | extres |
|---|---|---|---|---|
| #438 | comptes | 18 | 23 | forat RGPD: token de baixa newsletter > 1 any (el test que deia guardar-ho no enviava mai un token caducat) |
| #439 | music | 23 | 14 | `test_already_verified_skipped` reescrit perquè la guarda siga observable |
| #440 | social | 55 | 54 (50 + 4 fusionats) | test buit corregit (àncora a7, vegeu sota) |
| #441 | web + ingesta | 22 | 35 | forat RGPD: token avís-top > 1 any; contradicció de desempat sense-IG vs instagram-revisat resolta |
| #442 | analytics + topquaranta + ranking | 24 | 24 (23 + 1 fusionat) | 1 test fals esborrat (ranking) |
| **total** | | **142** | **150** (144 + 6 fusionats) | +1 esborrat, +2 corregits, +2 nous |

Cap fitxer de producció tocat en cap dels cinc.

## Verificació per mutació — regla: res es queda sense cridar

Cada test supervivent ha de fallar quan es trenca a posta el codi que
diu que vigila. Un test que passa no demostra res.

**Arnés** (`scripts/mutacio/mut.py`): cobertura per context de test
(`pytest-cov --cov-context=test`) → per a cada línia de producció, quins
tests l'executen → mutants AST (comparadors, `and/or`, `if` negat,
`return None`, constants ±1 / booleans / cadenes, crida esborrada) →
per a cada mutant, corre només els tests que cobreixen la línia
(`--no-migrations`, ~1 s d'arrencada) → un test queda «verificat» quan
cau davant d'algun mutant. Cua global de prioritats (comparadors i
`if` primer, cadenes al final), `urls.py`/`apps.py`/`admin.py`
exclosos. `mut2.py` cobreix el que la cobertura no veu: tests sobre
bancs de dades a nivell de mòdul (muta els mòduls que importa el
fitxer de test) i tests que llegeixen fitxers no-Python (esborra
línies dels fitxers que el test obri, capturats amb `sys.addaudithook`).

**Resultat:**

| àrea | casos | automàtic | segona passada / a mà | no verificables |
|---|---|---|---|---|
| social | 475 | 368 | 107 (94 casos d'un test de bancs + 13 lints de bancs) | 0 |
| web | 388 | 358 | 27 | 3 (`pg_only`, se salten en SQLite) |
| ingesta | 285 | 284 | 1 (constraint UNIQUE) | 0 |
| music | 206 | 202 | 4 (Meta/constants + guarda) | 0 |
| comptes | 133 | 133 | 0 | 0 |
| analytics | 140 | 137 | 3 | 0 |
| topquaranta | 109 | 51 | 55 | 3 (2 només amb `tq-health` a la caixa; 1 tautològic sota pytest-django) |
| ranking | 66 | 65 | 1 (constraint UNIQUE) | 0 |
| **total** | **1.802** | **1.598** | **198** | **6** |

Cada M reescrit també es va comprovar a mà pel qui el va reescriure
(mutació documentada al report del PR).

**Tests falsos que la mutació va traure a la llum** (tots «P» a
l'inventari — el lector no ho veu, l'arnés sí):

1. `ranking/test_compute_weekly_plays::test_robust_series_too_few_points_returns_none`
   — passava igual llevant les dues guardes de longitud (retornava
   `None` per un altre camí). **Esborrat.**
2. `social/test_afirmacions_verificables::test_a_phrase_with_the_number_anchors_it_to_the_release`
   — comprovava `"estrena" in frase` i el propi placeholder
   `{mesos_estrena}` conté «estrena»: passava sempre. **Reescrit**
   (àncores sobre la frase amb el placeholder substituït, sense
   distingir majúscules ni normalització Unicode).
3. `music/test_ml_auto_decide::test_already_verified_skipped` — la
   guarda `if canco.verificada` es podia negar sense que el test ho
   notara, perquè amb `ML_AUTO_APPROVE_SUBTIERS` buit mai s'aprova res.
   **Reescrit**: gradua A++ amb monkeypatch perquè la guarda siga
   l'única cosa que atura l'aprovació, i contrasta amb el cas pendent.

Altres tautologies detectades i anotades (no esborrades perquè la
resta del test sí que crida): `test_docs_coherence::test_yaml_loads_and_has_expected_keys`
afirma `"exclude" in cfg` però `load_map` fa `setdefault("exclude")`.

## Balanç

- Suite: 1.952 → 1.810 casos (1.708 → 1.560 funcions). Temps: ~75 s
  local amb `-n 4` (#437, ADR-0017); 61 s al runner.
- Esborrats: 142 D + 1 fals = 143. Reescrits: 144 M + 2 falsos = 146.
  Fusionats: 6. Nous: 2 (RGPD). Deixats: 1.416 P menys els 3 falsos.
- No verificats: 6 (llistats dalt, amb la raó).
- Cap àrea a mitges.

## Regla d'ara endavant

Anclar cada test nou a la promesa. Abans d'esborrar un test lleig,
mirar si és l'única xarxa d'un incident (`docs/post-mortems/`,
`docs/ops/runbook.md`): si ho és, es reescriu, no s'esborra. I tot test
que sobreviu a una auditoria ha de demostrar que crida:
`scripts/mutacio/mut.py <app>/tests <out_dir>`.
