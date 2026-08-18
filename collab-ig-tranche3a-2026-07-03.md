# IG col·laboradors — tranche 3a (ADR-0015) — 2026-07-03 (referència local)

Nota local (no committada). Codi a main (PR #308, merge `fdae282`).
Cablejat fet, **tot gated i inert** (flag `ig_collaboradors_actiu` = False).

## Estat de la tranche 3a

- **Cablejat gated** a `publicar_social._publish_feed`: amb el flag ON
  construeix el pool (`artistes_pool` del payload), aplica la política pura
  i posa `collaborators=[…]` al container pare; guard de substitució
  (leave-one-out, wrap de create+FINISH); files `InvitacioColaboracioIG`
  només després de publicar (cap òrfena). Amb el flag OFF: no-op,
  `_collaborator_plan` → `([], 0, {})`, payload byte-idèntic.
- **Payload additiu**: `build_top`/`build_novetats` porten `artistes_pool`
  (`[{id, username}]`). Inert amb flag off.
- **`instagram_client.create_carousel`/`upload_image`**: param
  `collaborators` additiu (clamp 3, omès si buit → body idèntic).
- **`simular_colaboradors_ig`**: command dry-run només-lectura (`--json`,
  `--tipus`, `--territori`, `--data`). Funciona amb el flag off.
- **`collaboradors.candidate_status`**: `(categoria, elegible, motiu)`.
- Tests: no-regressió, guard (substitució/esgotat/no-orphan), clamp,
  dry-run, candidate_status. 371 tests de social verds.

## Smoke d'inèrcia a prod (fdae282 == origin/main == local)

- flag `ig_collaboradors_actiu` = False ✅
- `InvitacioColaboracioIG` = 0 files ✅
- `_collaborator_plan(top_ppcc)` amb flag off = `([], 0, {})` ✅
- `artistes_pool` present a les entries (additiu, inert) ✅
- cap migració nova · main == prod ✅

## Dry-run real a prod (setmana 2026-06-22, flag off, res enviat)

Slots efectius = 3. Registre buit → **cold start: tots categoria B** →
seleccionats els 3 primers per ordre de chart.

**top_ppcc** — pool de ~57 artistes amb username. **SELECCIONATS:**

| # | artista | username | categoria | motiu |
|---|---|---|---|---|
| 1 | Rosalía | `rosalia.vt` | B | SELECCIONAT (1r del pool) |
| 2 | Fades | `fadesfadesfades` | B | SELECCIONAT |
| 3 | Triquell | `_triquell` | B | SELECCIONAT |

Següents al pool (no seleccionats, "mai convidat (B)"): La Ludwig Band,
Ouineta, Mushkaa, Flashy Ice Cream, 31 FAM, Max Navarro, Maria Jaume,
Rigoberta Bandini, … (fins ~54 més).

**Descartats per falta d'username** (6): Arde Bogotá, El Tío la Careta,
En Tol Sarmiento, FERRXN, Josep Nadal, LA XICA.

**nous_albums / nous_singles:** "sense contingut" — la finestra de
novetats és buida (l'última publicació de novetats va ser avui 2026-07-03,
així que no hi ha estrenes noves des d'aleshores). Per veure candidats de
novetats cal córrer el dry-run en una setmana amb finestra oberta o amb
`--data` d'un divendres/dimarts de publicació.

## Contradiccions spec↔codi (cap bloquejant)

- Spec §5.2 deia pool = "el mateix del tagger". El tagger només porta URLs
  (`artistes_instagram_urls`, sense id); la política necessita l'artista_id
  per a l'històric. → Vaig afegir `artistes_pool` (id+username) additiu al
  payload, mateixa expansió/ordre que el tagger, només amb l'id. No canvia
  el tagger.
- Guard §5.3: la substitució treu del "pool ordenat" (reserva = pool no
  seleccionat, en ordre), no re-executa la política sobre els substituts
  (poden ser d'una categoria que la política no hauria triat). És el que
  diu literalment l'spec ("el següent candidat del pool ordenat").

## Què queda per a la tranche 3b (supervisada amb Miquel)

1. Flip de `ig_collaboradors_actiu` = True des de `/staff/configuracio/`.
2. Primera tanda real d'invitacions en una publicació de feed real →
   observar el comportament real del límit a `media_publish` (el probe
   create-only accepta 4; el límit documentat és 3).
3. Confirmar els valors reals d'`invite_status` de
   `GET /{media}/collaborators` i ajustar `reconcile_estat` si cal.
4. Vigilar la taxa d'acceptació a `MetricaPipeline` (`ig_collab_taxa_acceptacio`).
