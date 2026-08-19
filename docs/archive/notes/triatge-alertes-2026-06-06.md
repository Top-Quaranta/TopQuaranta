# Triatge d'alertes — 2026-06-06 (diagnòstic read-only, sense fixos)

> Sessió **read-only** sobre prod (MCP `hetzner`, `manage.py`/python per stdin, settings
> explícit, usuari `topquaranta`). **Cap escriptura**, cap fitxer al servidor. Arbre del
> servidor net abans i després (prod a `141d151`, deploy de #151 confirmat).
> No es proposa cap fix; només diagnòstic.

---

## Alerta 1 — `analitzar_whisper` FAIL (run d'avui 04:00 UTC)

**Veredicte: trencament REAL però transitori per run — OOM (out-of-memory). Risc recurrent.**
**Severitat: BAIXA-MITJANA** (impacte acotat a l'enriquiment d'àudio; s'autorecupera al pròxim run net).

### Evidència
- El run d'avui (06-06, 04:00 UTC = 06:00 local) va morir amb **exit 137 (SIGKILL)** als
  **3 intents** de `tq-run`. 137 = 128+9 = OOM-killer.
- `journalctl -k` i `dmesg` confirmen 3 esdeveniments de l'OOM-killer (04:00, 04:01, 04:06)
  matant el procés `python` de Whisper (UID 1000), cada cop amb **anon-rss ≈ 2,8-3,0 GB**
  (`total-vm:4355668kB, anon-rss:2838004kB`). Va morir **durant la càrrega del model**
  (no apareix ni la línia "Loading"/"Tracks to process" als 3 intents).
- **El primer OOM-killer el va invocar `packagekitd`** (procés del sistema) a les 04:00:31 →
  hi havia **pressió de memòria concurrent del sistema** competint amb la càrrega del model.
- Estat de memòria de la caixa: **RAM total 3815 MB**, **swap 2 GB ja ~1,7 GB ple en repòs**.
  El model `faster-whisper large-v3 (CPU, int8)` necessita ~2,8 GB RSS; en una caixa de 3,7 GB
  amb swap quasi ple, la càrrega del model va sempre al límit.
- Els **dies previs (05-31 → 06-05) van completar** (línies "Done. ok=N fail=10…"). Per tant
  no és un trencament de dependència/model/codi: és falta de RAM puntual quan coincideix amb
  altra pressió de memòria.

### Abast i recurrència
- `analitzar_whisper` només calcula el Whisper LID (idioma) i omple `whisper_lang`/`whisper_p`
  (features de l'ML). **No afecta ranking, ingesta, publicació ni res user-facing.** Els tracks
  no processats es reintenten al pròxim run (la cua "Tracks to process").
- **Recurrent**: la càrrega del model sempre demana ~2,8 GB; en una caixa 3,7 GB amb swap quasi
  ple, qualsevol procés que punxi a les 04:00 UTC (packagekitd, unattended-upgrades, etc.) la pot
  tornar a tombar. El SingletonLock `ram_heavy` evita la concurrència amb MusicBrainz, però **no**
  protegeix contra processos del sistema. Probable que es repeteixi de manera intermitent.

### Nota separada (no és l'alerta)
- El `fail=10` constant a cada run és un problema **separat i acotat** (10 tracks que fallen
  cada run, no creix; preexistent). No té relació amb l'OOM.

---

## Alerta 2 — Spotify coverage CRIT (no-verif-2=68% … no-verif-7=0%)

**Veredicte: NO és stall ni trencament. Backlog de recència + artefacte estructural de la
mètrica sobre la cua de baixa confiança. Severitat: BAIXA** (cap impacte a les playlists
públiques verificades).

### Què és la mètrica
- L'alerta (`music.health.check_spotify_coverage`) reporta `last_n_matched / last_n_tracks`
  per fila `SpotifyPlaylist`. "matched" = la cançó té `SpotifyMetadata.spotify_id` resolt.
- `no-verif-N` són chunks de 100 cançons **NO verificades** (candidates pendents), ordenades per
  **`ml_confianca DESC, -created_at`** (no per recència). Chunk 1 = més confiança; chunk 7 = menys.
- **`enriquir_spotify` (Process B) processa els pendents en el MATEIX ordre `ml_confianca DESC`** →
  la cua de baixa confiança s'enriqueix l'última. Per això el gradient.

### Estat real (read-only)
- **Playlists públiques verificades: totes sanes** — `top-cat/val/bal/ppcc(-weekly)` 82-100%.
  La integració de Spotify funciona.
- **Cap cooldown de rate-limit actiu.** **SpotifyMetadata creix**: +50/dia (últims 3d), +325/7d.
  Enriquiment **actiu, no encallat**.
- **Pendents (no-verif, actius, dins caducitat): 643, tots amb ISRC.**
  - per banda de `ml_confianca`: ≥0.3 **pràcticament tots enriquits** (0.3-0.6: 61/65;
    0.6-0.9: 27/27; 0.9-1.0: 5/5) → chunks 1-2, alta cobertura.
  - banda **0.0-0.3: 546 pendents** (el gruix): 111 enriquits, **434 encara NO cercats**
    (252 amb stub `not_attempted` + 182 sense fila), i **només 5 `not_found`** a tota la pool.
- Els **182 sense fila són 100% intake recent** (107 ≤7d, 182 ≤30d) → component de recència clar.
- **Throughput vs intake**: enriquiment ~23-25 pendents/dia; intake ~20/dia (244 en 30d), gairebé
  tot de baixa confiança. El net positiu és petit → la cua de baixa confiança (chunks 6-7) drena
  molt lentament i es manté prop de 0% de manera crònica.

### Causa
Combinació de tres coses, **cap d'elles un trencament**:
1. **Recència/backlog**: 434 pendents de baixa confiança encara no cercats; els no-fila són tots
   intake recent (≤30d). Es drenaran a mesura que `enriquir_spotify` avanci.
2. **Prioritització per `ml_confianca`**: enriquiment i chunks comparteixen ordre, així que la cua
   de baixa confiança va sempre al final → chunks 6-7 prop de 0%.
3. **Mètrica massa estricta per a la cua no-verificada**: el llindar CRIT <50% s'aplica a chunks
   de candidates de baixa confiança (playlists de descobriment, no públiques). Només **5 cançons**
   a tota la pool són realment irresolubles (`not_found` a Spotify).

### Per què no és stall
Enriquiment actiu (sense cooldown, SM +50/dia), alta confiança 100% enriquida, públiques 82-100%,
i el dèficit és quasi tot "encara no cercat" (434) i no "irresoluble" (5). La cua baixa es
mantindrà baixa per throughput limitat + intake continu de baixa confiança, però és benigne:
aquestes són playlists de candidates no verificats, no els tops públics.

---

## Resum per alerta
| Alerta | Transitori/esperat o trencament real | Severitat | Causa |
|---|---|---|---|
| `analitzar_whisper` | **Trencament real (OOM) però transitori per run; recurrent** | Baixa-mitjana | Càrrega del model large-v3 (~2,8 GB) en caixa 3,7 GB amb swap quasi ple, tombada per pressió de memòria concurrent (packagekitd a 04:00). Sense impacte user-facing; reintenta. |
| Spotify coverage | **Esperat/estructural + backlog de recència; NO stall** | Baixa | Enriquiment per `ml_confianca` deixa la cua de baixa confiança per al final; 434 pendents encara no cercats (només 5 irresolubles); intake ≈ throughput. Públiques verificades 82-100% sanes. |

### No verificat / límits
- No he reproduït la càrrega del model (seria consum de RAM real a prod); l'OOM està confirmat
  per kernel/dmesg, no inferit.
- Throughput d'enriquiment estimat de `SpotifyMetadata.updated_at`/`enriched_at`; aproximació.
- No he investigat la causa upstream del `fail=10` de Whisper (separat de l'alerta).
- No proposo cap fix (per indicació); això es decideix després.
