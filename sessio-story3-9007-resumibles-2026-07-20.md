# Story-3 9007 + stories resumibles — dl 2026-07-20 (PRs #337 → #338)

> Nota local de referència (untracked), escrita 2026-07-20 al Mac.
> Arrenca del fallo `story 3/6 failed for top_territorial VAL` del cron
> `publicar_social` de dl 09:30 UTC (11:30 CEST). Continua el fil de
> stories iniciat a `verificacio-stories-mencions-2026-07-15.md` (#323,
> mencions user_tags) i `sessio-collab-ig-tancament-2026-07-13.md`
> (#319, disciplina d'exit non-zero per canal).

## El fallo (recon només-lectura)

- **Story 3/6** del set territorial **VAL** va fallar a
  `publish_container` amb Graph API **9007 / subcode 2207027**
  ("Media ID is not available", *"not ready for publishing, please wait
  for a moment"*). Carrera de readiness: `wait_until_finished` va veure
  `FINISHED` i ~221 ms després `media_publish` encara deia "not ready".
  **Transitòria** (les altres 5 stories del run van sortir bé, incloses
  dues amb 20 tags). **No** era un username invàlid — l'únic handle
  problemàtic (`wazooo`) el va gestionar el guard de mencions en una
  ALTRA story (#323 degradant amb gràcia, com toca).
- **Rentat d'exit code.** El fallo parcial marcava igualment
  `STATUS_PUBLICAT`; el retry de `tq-run` trobava `PUBLICAT`, saltava, i
  el status file gravava `exit 0` → panell verd i la pàgina que faltava
  no es reintentava mai. Contradeia la disciplina del #319.

## Fix i retirada (dos PRs el mateix dia)

- **PR #337** (`feat`, `d29c282`): dos mecanismes darrere de flags
  `ConfiguracioGlobal` **default OFF** (merge inert). Activats a prod el
  mateix 2026-07-20 (~18:22 UTC) amb OK explícit del Miquel.
- **PR #338** (`chore`, `3dfee35`): retirats els dos flags-selector; els
  mecanismes passen a **comportament estàndard i únic**. Migració
  `ranking/0037` = drop de les dues columnes booleanes (schema-only, cap
  implicació de dades editorials).

## Estat vigent (main == prod == `3dfee35`)

Comportament **estàndard, sense flags**:

1. **Retry 9007** — `instagram_client.publish_container` re-polleja el
   contenidor i reintenta la publicació en 9007/2207027. Només eixe
   subcode; qualsevol altre error propaga igual.
2. **Stories resumibles** — un set parcial queda `STATUS_ERROR` (no
   `PUBLICAT`) amb les slides ja publicades a `metadata.published_slides`
   (`{idx, name, sid}`, al costat de `story_ids`). `handle()` alça
   `CommandError` (exit ≠ 0) → el retry de `tq-run` reentra a
   `_publish_story`, salta les slides registrades i publica **només el
   gap**; `PUBLICAT` només quan el set és complet. `--force` ignora
   l'estat de resume i republica tot (semàntica legacy). Sense estat nou:
   `STATUS_ERROR` és el marcador natural de resume.

### Tunables (es queden a ConfiguracioGlobal — són paràmetres, no interruptors)

- `ig_retry_9007_intents` — reintents després del primer 9007. Default
  **2**. `0` = un sol tir (desactiva el retry sense flag).
- `ig_retry_9007_backoff_s` — segons entre reintents (backoff curt fix).
  Default **3**.

Prod (verificat 2026-07-20): `intents=2`, `backoff_s=3`. Les dues
columnes booleanes (`ig_retry_9007_actiu`, `ig_stories_resumibles_actiu`)
ja **no existeixen** (dropades per `0037`).

## Primer run que exercirà els camins nous

**⚠ Pendent:** l'únic run de `publicar_social` de dl 20/07 va ser el de
09:30 UTC, **anterior** a l'activació → encara **cap run** ha exercit el
retry ni el resume. El primer serà el de **dimarts 21/07 a les 10:00 UTC
(12:00 CEST)** (slot `0 10 * * 2`, territorial).

Com verificar-lo (només-lectura al box):

- **Status file:** `cat /var/log/topquaranta/status/publicar_social.status`
  → `status=OK`/`exit_code=0` amb `attempts=1` = set complet a la
  primera. `attempts>1` acabant OK = retry de tq-run va backfillar un gap.
- **Log:** `grep -E "story [0-9]+/[0-9]+|9007 not-ready|ja publicada, salta|stories pendents" /var/log/topquaranta/social.log`
  - `IG 9007 not-ready; re-poll + retry` = retry actuant.
  - `story N/M ... ja publicada, salta` = re-entrada resumible.
  - `stories pendents; re-intent al proper run` = set incomplet en
    `STATUS_ERROR` esperant backfill (ja NO grava verd fals).

## Docs canòniques (al repo, ja actualitzades pels PRs)

- `docs/architecture/social-stories.md` §"Publish robustness — standard".
- `docs/architecture/social.md` (pointer).
