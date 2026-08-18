# SPEC — Recon read-only: Spotify /search rate-limit + columna ombra soft-cap

> Sessió **read-only** (2026-06-17). Cap commit/branca/push/edició de codi.
> Tot file:line llegit i verificat directament excepte on s'indica
> "(agent, corroborat per …)". Hipòtesis de memòria marcades com a tals.
> Cap proposta toca scoring ni dades sense aprovació explícita del Miquel.

---

# PART A — Rate limit de Spotify /search

## A.1 — Fets verificats (file:line + codi)

### Lectura del header i llindar
- `ingesta/clients/spotify.py:344` — lectura **literal** del header, sense
  cap càlcul nostre:
  ```python
  wait = int(resp.headers.get("Retry-After", 2))
  ```
  El `2` és només el fallback si el header falta. → **78600 és el valor
  literal que va enviar Spotify**, no derivat.
- `ingesta/clients/spotify.py:277` — `DEFAULT_MAX_RETRY_AFTER_S = 60`.
- `ingesta/clients/spotify.py:345` — comparació amb el llindar:
  ```python
  if wait > self._max_retry_after_s:
  ```
- `ingesta/clients/spotify.py:347-353` — el log que el Miquel ha vist
  (placeholders path / wait / tolerance):
  ```python
  logger.error("Spotify rate limited on %s with Retry-After=%ds "
               "(> %ds tolerance); aborting", path, wait, self._max_retry_after_s)
  ```

### Propagació de l'abort
- `ingesta/clients/spotify.py:354` — `raise RateLimitedError(wait, path)`.
- `ingesta/clients/spotify.py:218-234` — `class RateLimitedError(RuntimeError)`.
- Camí del 429 **curt** (≤60s): `spotify.py:355-369` → `time.sleep(wait)` +
  duplica el throttle adaptatiu (cap `MAX_ADAPTIVE_THROTTLE_S=30.0`,
  `spotify.py:280`) + `continue`. `MAX_RETRIES = 3` (`spotify.py:13`).
- Captura i cooldown a `ingesta/management/commands/enriquir_spotify.py`:
  - `:156` `resume_at = cd.active_resume_at()` (skip si encara en ban).
  - `:230` `except RateLimitedError as exc:`
  - `:240` `effective_cooldown_s = min(exc.retry_after_s, MAX_COOLDOWN_S)`
  - `:245` `cd.write(resume_at)`; `MAX_COOLDOWN_S = 86400` (`:79`).
  - L'abort **NO** és un crash: el run surt net (exit 0) després
    d'escriure el cooldown → per això `status=OK` al watchdog (vegeu A.3).

### Throttle / nombre de /search per run
- `spotify.py:274` `DEFAULT_THROTTLE_S = 0.2`; `spotify.py:335`
  `time.sleep(self._current_throttle_s)` abans de cada request.
- 1 `/search` per Cançó: `search_isrc` (`spotify.py:381`) i
  `search_isrc_principal_artist` (`spotify.py:393`), `limit=1`, sense
  paginació.

### Qui crida /search de veritat
- `enriquir_spotify.py:425` → `client.search_isrc(canco.isrc)`.
- `enriquir_spotify_rebuigs.py:548` → `client.search_isrc(...)` i
  `enriquir_spotify_rebuigs.py:516` → `client.search_isrc_principal_artist(...)`.
- **Procés A (playlists) NO toca /search** — verificat:
  `actualitzar_playlists_spotify.py:18` "It NEVER calls /v1/search",
  `:339` "Never calls /v1/search. Returns None for not_attempted /…".
  (Hi ha test que ho assereix — agent, corroborat per la docstring.)

### Crons (`deploy/cron.topquaranta`)
- `:123` `15 */2 * * *  actualitzar_playlists_spotify --freq daily` (cada 2h, **cache-only, sense /search**).
- `:131` `0 10 * * 6   actualitzar_playlists_spotify --freq weekly`.
- `:162` `0 3 * * *    enriquir_spotify --limit 250 --throttle 0.5` (Procés B, /search).
- `:198` `0 5 * * *    enriquir_spotify_rebuigs --shortlist-only --include-orfes` (Procés B backfill, /search).

### Persistència de l'abort entre runs
- Cooldown **compartit**: `ingesta/clients/spotify_metadata_cooldown.py:52`
  `SHARED_PATH = STATUS_DIR / "spotify_metadata.cooldown"`
  (`STATUS_DIR=/var/log/topquaranta/status`, `:46`). `write()` `:127`,
  `active_resume_at()` `:90`. Tant `enriquir_spotify` com
  `enriquir_spotify_rebuigs` el llegeixen/escriuen → un ban en un
  bloqueja l'altre fins que expira.
- AIMD controller del backfill: `ingesta/clients/spotify_backfill_controller.py`
  (escala el `--limit` de `enriquir_spotify_rebuigs`; estat a
  `enriquir_spotify_rebuigs.controller.json`).

### ADR
- ADR-0012 (`docs/decisions/0012-*.md`): /v1/search "200 OK, rate limited";
  batch endpoints 403; Spotify = identificador + desambiguació, no metadata.
- ADR-0013 (`docs/decisions/0013-*.md`): split Procés A (cache-only, mai
  /search) vs Procés B (one-shot per Cançó). Origen: ban de 24h del
  2026-05-22 per burst de /search amb cache freda.

## A.2 — Evidència de prod (read-only, output cru)

### L'incident d'AVUI (2026-06-17) ve del **backfill**, no del diari
`enriquir_spotify_rebuigs.status` (last_run 05:00):
```
[2026-06-17 07:00:05] Backfill controller: 3 days clean at limit=450; bumping to 650 (cap=800).
[2026-06-17 07:10:09] ERROR ingesta.clients.spotify: Spotify rate limited on /search with Retry-After=78600s (> 60s tolerance); aborting
[enriquir_spotify_rebuigs] cascade (limit=650, throttle=1.0, …): live_alive=1 orfe_shortlist=649 orfe_rest=0
[enriquir_spotify_rebuigs] rate limited; cooldown until 2026-06-18T03:00:09.807741.
[enriquir_spotify_rebuigs] done: orfe(processed=649 found=430) aborted=True
```
`enriquir_spotify.status` (diari, 03:00) el mateix dia: **sa**, només un
429 curt:
```
[2026-06-17 05:00:06] WARNING Spotify rate limited; sleeping 2s
[2026-06-17 05:00:08] Spotify throttle increased to 1.0s after rate limit
[enriquir_spotify] done: processed=250 found=240 not_found=10 aborted=False  status=OK
```
Fitxer cooldown ara: `cat spotify_metadata.cooldown` → `2026-06-18T03:00:09.807741`
(ban actiu fins demà a les 03:00). `controller.json`:
`limit_actual=650, dies_sense_ban=0, last_safe_limit=450, last_ban_at=2026-06-09T21:27:41`.

### Recurrència (aborts ERROR "aborting" per dia, tots els logs)
```
 27  2026-05-22
 37  2026-05-23
  1  2026-05-24
  1  2026-05-29
  1  2026-06-17
```
→ **No és diari.** Clúster gros el 22-23 maig (origen dels ADR-0012/0013),
després events **aïllats** (24-maig, 29-maig, avui). El patró: el ban salta
quan un run fa un **burst gran** de /search — sempre el **backfill**
`enriquir_spotify_rebuigs` quan l'AIMD ha pujat el límit (avui 650).

### Cobertura REAL d'enrichment (≠ 88% de playlist coverage)
ORM read-only, prod, 2026-06-17. Definició usada: `Canco.isrc` no buit.
```
TOTAL Canco amb ISRC: 5441
  activa=True: 3696
  activa=True i verificada=True: 3656

Canco ISRC + activa=True (3696):
  found                     3303
  not_attempted              304
  SENSE fila SpotifyMetadata  45
  not_found                   39
  manual                       5
Resolt (found+manual): 3308  → 89,5% de les actives amb ISRC
AMB fila SpotifyMetadata: 3651 | SENSE fila: 45
```
→ **89,5%** de les Cançons actives amb ISRC tenen id de Spotify resolt.
Gap real "mai resolt" = 304 `not_attempted` + 45 sense fila = **349 (9,4%)**;
a més 39 `not_found` (ISRC genuïnament no a Spotify). Aquest 89,5% és
**cobertura d'enrichment (Cançó→id)**, NO el 88% de playlist coverage.

## A.3 — El que NO s'ha pogut determinar (read-only)

1. **Mode de quota de l'app (development vs extended).** No documentat als
   ADR (grep buit). És **inferència**, no fet: bans de hores en bursts de
   ~650 /search i el fet que /search tingui el bucket més estret són
   **coherents amb development mode**, però no es pot confirmar sense el
   dashboard de Spotify (fora de l'abast read-only).
2. **Tendència temporal de la cobertura.** No hi ha cap gauge a
   `MetricaPipeline` per spotify/enrich (consulta distinct buida) → només
   tinc un punt (89,5% avui), no si el gap es tanca o està encallat.
3. **Semàntica exacta de l'AIMD controller.** `controller.json` mostra
   `last_ban_at=2026-06-09` i `dies_sense_ban=0` tot i el ban d'avui →
   sembla escrit a l'inici del run (05:00) abans del ban (07:10). El ban
   del 2026-06-09 que registra el controller NO surt al grep d'"aborting"
   (potser rotat amb wording diferent). Per precisar caldria llegir
   `spotify_backfill_controller.py` amb deteniment (no fet aquesta sessió).
4. **Correlació gap↔rate-limit quantitativa.** Qualitativament: els aborts
   afecten sobretot el **backfill d'orfes/rebuigs**, no l'enrichment de
   Cançons actives (avui el diari va completar 250/250). El gap de 349 en
   Cançons actives és un **backlog rodant** (~250/dia) més que víctima
   directa del rate-limit. No quantificable sense la sèrie del punt 2.

## A.4 — Proposta (NOMÉS per a aprovació; res s'aplica sense OK)

| # | Proposta | Tipus | Toca scoring/dades? |
|---|---|---|---|
| A-a | **Instrumentar** la cobertura: gauge a `snapshot_pipeline` (p.ex. `spotify_enrich_pct` + `spotify_not_attempted`) per tenir la sèrie temporal que ara falta. | **Additiu** (nou gauge) | No |
| A-b | **Visibilitat del ban**: avui un abort surt `exit 0`/`status=OK` i només deixa un ERROR al log; el watchdog no alerta. Afegir una línia a `tq-health` que llegeixi `spotify_metadata.cooldown` i marqui SKIP/avís mentre hi ha cooldown actiu. | **Additiu** (alerting) | No |
| A-c | **Reduir el burst del backfill**: baixar el sostre de l'AIMD (cap 800→p.ex. 400) o el step, perquè `enriquir_spotify_rebuigs` no dispari ~650 /search de cop. | **Config / canvi de comportament** | **Sí (throughput)** → requereix OK |
| A-d | Sol·licitar **extended quota mode** a Spotify (si l'app és en development — punt A.3.1). Acció externa, no de codi. | Externa | No (però cal confirmar mode) |

> Recomanació de prioritat: A-a + A-b (additius, zero risc) primer, per
> mesurar abans de tocar A-c. A-c i A-d només amb decisió explícita.

---

# PART B — Columna de reproduccions normalitzades a staff

## B.1 — Fets verificats (file:line)

### El soft-cap existeix, està MERGEJAT a main, i és INERT per defecte
- Definició: `ranking/algorisme.py:567-595` `def _soft_cap_knee(territori, cfg, today)`
  i `:598-607` `def _apply_soft_cap(plays, knee)`. Constants
  `_SOFT_CAP_WINDOW_WEEKS=10` (`:99`), `_SOFT_CAP_TOP_N=10` (`:100`).
- Integració al scoring: `ranking/algorisme.py:286`
  `soft_cap_knee = _soft_cap_knee(territori, cfg, today)` i `:298`
  `plays_eff = _apply_soft_cap(plays, soft_cap_knee)` →
  `:304 base_score = plays_eff * age_factor * past_top_factor`.
- **Gate**: `ranking/models.py:118-124` `soft_cap_actiu = BooleanField(default=False)`
  (comentari `:116` "Default OFF so deploying changes nothing; staff opts in").
  Camps acompanyants: `soft_cap_multiplicador` (`:125`, default 3),
  `soft_cap_floor_escoltes` (`:135`, default 500), `soft_cap_base_top_n`
  (`:148`, default 10).
- **Prova d'inèrcia**: `algorisme.py:578` `if not cfg.soft_cap_actiu: return None`
  → knee None → `_apply_soft_cap(plays, None)` retorna `plays` sense canvi
  (`:605-607`). Amb defaults, scoring idèntic al previ.
- **Git**: `56a43f4` "feat(ranking): adaptive per-territori soft-cap …
  (off by default) (#196)" **és ancestre de main** (verificat amb
  `git merge-base --is-ancestor`). Follow-ups també a main: `381442d`
  (#233, copy) i `35f1746` (#234, "apply soft cap in the score breakdown
  panel"). La branca `feat/soft-cap-escoltes-outlier` és un WIP separat amb
  un diff a `ranking/models.py` (un camp de `ConfiguracioGlobal` no
  relacionat) — **NO** és la font del soft-cap.

### Persistència del valor normalitzat
- `ranking/models.py` (TopSetmanal): `weekly_plays` (raw) es **persisteix**;
  el `plays_eff` (capat) **NO** es persisteix enlloc.
- `TopProvisional`: `escoltes_setmanals` (raw, IntegerField),
  `score_setmanal`, `age_factor`, `past_top_factor`, `monopoli_factor`.
  **Cap camp de plays normalitzades.** → Quan inert, el valor normalitzat
  no existeix; quan actiu, viu en memòria durant el càlcul i es descarta.

### Ja existeix un càlcul del valor normalitzat (per cançó, no a la llista)
- `web/api/canco_views.py:151-177` `_derive_plays_eff(rp)` — **NO recalcula
  el genoll**; **inverteix el score persistit**:
  ```python
  plays_eff = score_setmanal / (age · past_top · monopoli)
  soft_cap_aplicat = (plays_raw - plays_eff) > max(1.0, 0.005*plays_raw)
  ```
  Reconcilia exactament amb el score guardat. Exposat a `:198-199`
  (`weekly_plays_eff`, `soft_cap_aplicat`).
- Endpoint `cancons/<slug>/top-breakdown/` (`web/api/urls.py:646`,
  `canco_views.py:332 canco_top_breakdown`) + component
  `web-react/src/components/TopBreakdownPanel.jsx` (usa `soft_cap_aplicat`
  / `weekly_plays_eff`, `:102`, `:219`). Hi ha també un camí "live" que
  recalcula el genoll respectant el gate: `canco_views.py:287-289`
  (`_soft_cap_knee` + `_apply_soft_cap`).
- **Conclusió**: el valor normalitzat ja és visible **per cançó** (panell de
  transparència), però (a) NO a la **llista** de top provisional de staff, i
  (b) quan el gate està OFF surt `soft_cap_aplicat=False` i eff≈raw.

### La view de llista staff (on falta la columna)
- Endpoint: `web/api/staff/top.py:135-171 def top_list` (ruta
  `web/api/urls.py:285 staff/top/`, àlies `:288 staff/ranking/`). Llegeix
  `TopProvisional` (`:140`). Camps exposats per fila (`:151-166`): `pk`,
  `posicio`, `canco_*`, `artista_*`, `escoltes_setmanals` (raw),
  `age_factor`, `past_top_factor`, `monopoli_factor`, `score_final`.
  **No exposa cap valor normalitzat ni knee.**
- React: `web-react/src/pages/staff/StaffRankingPage.jsx` capçaleres
  `:119-129` (#, Cançó, Artista, **Escoltes 7d**, Antiguitat, Top passat,
  Monopoli, Score) i cel·les `:139-158`; `colSpan={9}` (`:134`).
  Ja hi ha copy explicatiu del soft-cap a `:92` (afegit per #233) però
  **sense columna**.

## B.2 — El que NO s'ha pogut determinar

- Res de bloquejant. Únic matís de disseny (no ambigüitat de fet): per a un
  valor **preview "what-if"** amb el gate OFF, el `_soft_cap_knee` actual
  retorna `None` (respecta el gate, `algorisme.py:578`), així que un preview
  hauria de **saltar el gate** explícitament. La via additiva (B-1) no ho
  necessita perquè inverteix el score.

## B.3 — Proposta de columna OMBRA (NOMÉS per a aprovació)

Dues lectures possibles del que el Miquel vol. Les separo perquè una és
trivial i sense risc, l'altra és un preview "what-if".

### Opció B-1 — Reflectir el valor EFECTIU real (additiu, reconcilia, recomanada)
- **Backend**: a `top_list` (`web/api/staff/top.py`), reutilitzar la funció
  existent `_derive_plays_eff` (ja a `canco_views.py`) per fila i afegir al
  payload: `weekly_plays_eff` + `soft_cap_aplicat`. Zero matemàtica nova,
  zero query nova (tot surt dels camps ja a la fila).
- **Frontend**: `StaffRankingPage.jsx` — afegir 1 `<Th>` "Escoltes norm."
  entre `:125` i `:126`, 1 `<Td>` corresponent entre `:154` i `:155`, i
  pujar `colSpan` 9→10 (`:134`). Mostrar el valor + etiqueta del pas
  ("soft-cap (genoll adaptatiu per territori)") quan `soft_cap_aplicat`.
- **Tipus**: **additiu, read-only, sense persistència, sense tocar scoring.**
- **Limitació honesta**: amb el gate OFF (estat actual), `weekly_plays_eff`
  ≈ `escoltes_setmanals` i `soft_cap_aplicat=False` a totes les files →
  la columna es veurà "plana"/redundant fins que s'activi el soft-cap.

### Opció B-2 — Columna PREVIEW "what-if" (mostra què faria el cap si s'activés)
- **Backend**: calcular el genoll **en viu ignorant el gate** (mateixa
  fórmula que `_soft_cap_knee` però sense el `return None` del gate) una
  vegada per territori, i `_apply_soft_cap(escoltes_setmanals, knee_preview)`
  per fila. Exposar `knee_preview`, `escoltes_preview`, i un flag.
- **Tipus**: **additiu i read-only al payload**, però **NO reconcilia** amb
  el score guardat (el genoll deriva del present, no del moment del càlcul);
  és purament **assessor/decisió**. Cal una funció nova que dupliqui la
  fórmula del genoll sense el gate (no reutilitzable tal qual perquè
  `_soft_cap_knee` talla al gate).
- **Tipus UI**: requereix **previsualització abans de mergejar**.

### Comú a B-1/B-2
- **Pin de no-regressió**: cap canvi a `algorisme.py`, `ConfiguracioGlobal`,
  `TopProvisional`/`TopSetmanal`, ni al càlcul del top. Test que asseguri
  que `top_list` no altera l'ordre ni els camps existents (només afegeix).
- **Cap migració** en cap de les dues opcions.
- Recomanació: **B-1** primer (fidel i sense risc); **B-2** com a eina de
  decisió separada si el Miquel vol avaluar activar el soft-cap, amb preview
  d'UI i etiquetatge clar de "simulació, no aplicat".

---

## Resum executiu

- **A**: l'error de 78600s és el `Retry-After` **literal** de Spotify
  (`spotify.py:344`), abocat per `enriquir_spotify_rebuigs` (backfill
  d'orfes) després que l'AIMD pugés el límit a 650; va escriure cooldown
  compartit fins **2026-06-18 03:00**. **No és recurrent diari** (clúster
  22-23 maig + events aïllats). El diari `enriquir_spotify` està sa.
  Cobertura d'enrichment real **89,5%** (3308/3696 Cançons actives amb
  ISRC). Procés A (playlists) **no** toca /search.
- **B**: el soft-cap **està entregat i mergejat a main, inert per defecte**
  (`soft_cap_actiu=False`, `models.py:118`). El valor normalitzat NO es
  persisteix, però ja es **deriva per cançó** invertint el score
  (`_derive_plays_eff`, `canco_views.py:151`) i es mostra al
  `TopBreakdownPanel`. A la **llista** de staff (`top_list`) NO hi és.
  Afegir-la és **viable i additiu** reutilitzant `_derive_plays_eff`
  (Opció B-1), sense persistir res ni tocar scoring.
