# Auditoria read-only de la superfície d'enriquiment Spotify — 2026-06-06

> Sessió **read-only** sobre prod (MCP `hetzner`, settings explícit, usuari `topquaranta`).
> Cap escriptura, cap fitxer al servidor. Arbre del servidor net (prod a `141d151`).

## Conjunt complet de writers de dades Spotify

| Command / cron | Escriu | Població | Cadència |
|---|---|---|---|
| **enriquir_spotify** (Process B) | `SpotifyMetadata.spotify_id`, `enrichment_status`, `Canco.spotify_id` | pendents (verificada=False) + verificats sense enriquir, ordre `ml_confianca DESC` | `0 3 * * *` `--limit 50 --throttle 1.0` |
| **enriquir_spotify_rebuigs** | `HistorialRevisio.artista_spotify_id` (tier orfe) + `SpotifyMetadata` (tier live) | **rebutjats**: shortlist d'homònims (deezer_ids amb ≥1 `desvincular_album`), oldest first | `0 5 * * *` `--shortlist-only --include-orfes` |
| **actualitzar_playlists_spotify** (Process A) | `SpotifyPlaylist.last_n_*` (consumidor; **no** escriu enrichment) | top + no-verif, llig `spotify_id` cache-only | `15 */2 * * *` daily; `0 10 * * 6` weekly |

Cap altre camí escriu `SpotifyMetadata`/`spotify_id` (la resta de matches eren lectures o
definicions de model).

## Salut de cada camí

### enriquir_spotify (Process B) — SA, lent a la cua de baixa confiança
- **Avança de veritat**: SpotifyMetadata `found` últims 1d=50, 3d=148, 7d=324. Cap cooldown actiu
  (`enriquir_spotify.status` del 03:03 d'avui, sense `.cooldown`).
- **Descomposició del creixement** (això aclareix el "+50/dia" reportat abans):
  | Finestra | total found | verificats | pendents | altres |
  |---|---|---|---|---|
  | 1d | 50 | 25 | 25 | 0 |
  | 3d | 148 | 79 | 66 | 3 |
  | 7d | 324 | 255 | 66 | 3 |
  → El **+50/dia és tot d'enriquir_spotify**, repartit ~meitat verificats / ~meitat pendents.
  El throughput de **pendents és ~25/dia**, vs intake ~20/dia → net positiu petit, drena lent.
- **Backlog pendent**: 643 pendents (tots amb ISRC); 204 enriquits, **434 encara no cercats**
  (252 stub `not_attempted` + 182 sense fila), només **5 `not_found`** a tota la pool.

### enriquir_spotify_rebuigs — MOLT SA, alt throughput
- **Població: rebutjats**, no pendents → **per això no va aparèixer a la triatge del no-verif**
  (la triatge mirava la pool de pendents que alimenta les playlists no-verif; els rebuigs no
  alimenten cap playlist, només la feature ML de ratio de rebuig per parell deezer/spotify).
- **Escriu a una taula DIFERENT** (`HistorialRevisio.artista_spotify_id`, tier orfe), per això el
  seu throughput **no apareix** al creixement de SpotifyMetadata.
- **Avança fort**: `spotify_lookup_at` últims 1d=**511**, 3d=1507, 7d=2699 (~385/dia mitjà).
  Controlador **AIMD** que ha pujat el límit 100→300→500 després d'un ban del 2026-05-29
  (`dies_sense_ban` 0→2). Hit-rate orfe ~95% (found 467 / processed 499 l'últim run). Cap cooldown.
- **Backlog**: HR total 15.370, omplerts 6.239 (40%) → ~9.131 per drenar a ~400/dia ≈ 3 setmanes.
- **Última feina real**: run d'avui 05:00, orfe processed=499 found=467.

### actualitzar_playlists_spotify (Process A) — SA
- Daily cada 2h; totes les playlists públiques verificades 82-100% de cobertura, sync d'avui 06:15.

### actualitzar_playlists_spotify_weekly — FUNCIONA; "WAITING" és un desajust de monitoratge
- El cron és `actualitzar_playlists_spotify --freq weekly` (Dt 10:00). `tq-run` etiqueta per **nom
  de comanda** → escriu `actualitzar_playlists_spotify.status` (compartit amb el daily). El
  `cron-meta.json` té una clau separada `actualitzar_playlists_spotify_weekly` que **mai obté el
  seu propi `.status`** → `tq-health` la reporta com a WAITING/mai-executat.
- **El job sí corre i funciona**: les 5 playlists `*-weekly` tenen `last_sync = 2026-05-30 10:00`
  (dissabte anterior); el pròxim run és avui 06-06 10:00 (encara no arribat quan he mesurat).
- **Veredicte**: ni nou-per-estrenar ni encallat. És una **llacuna de monitoratge benigna** (clau
  de meta sense productor de status), no un job aturat. (Possible neteja futura: tag dedicat, però
  no és un fix d'aquesta sessió.)

## Veredicte global
**Cap stall en cap camí d'enriquiment.** Tots avancen amb feina real recent i sense cooldowns
actius. El gradient del no-verif (96→0%) és **benigne**: backlog ordenat per `ml_confianca`
(enriquiment i chunks comparteixen ordre, així que la cua de baixa confiança va l'última) +
throughput de pendents lent (~25/dia) sobre una banda 0.0-0.3 de 546 cançons, amb només 5
irresolubles a tota la pool. → Habilita la recalibració de l'alerta (PART B) sense risc de tapar
un problema real.

### No verificat / límits
- Throughput estimat de `enriched_at`/`spotify_lookup_at`; aproximació.
- No he reproduït cap crida a Spotify (read-only).
