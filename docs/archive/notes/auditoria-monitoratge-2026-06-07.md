# Auditoria de la capa de monitoratge i alertes — 2026-06-07

> Sessió **read-only** (diagnòstic, cap fix). Repo en lectura; prod només lectura
> (`tq-health`, status files, `ls`/`cat`). Arbre git de l'app net abans i després. Cap PR ni commit.
> Honestedat: el que no he pogut verificar ho marco.

## Mapa de la superfície

- **`bin/tq-run`** — wrapper de cada cron. Executa la comanda (reintents 3× backoff 60/300s),
  i escriu `/var/log/topquaranta/status/<tag>.status` (key=value + heredoc `last_output`).
  Deriva el **tag** del nom de comanda; única excepció: `--provisional` → `<cmd>_provisional`.
  exit 75 (lock) → `status=SKIPPED_BY_LOCK`, NO refresca `last_run`, incrementa `consecutive_skips`.
  Altrament escriu `status=OK|FAIL`, `consecutive_failures`, i opcionalment `work_done`/`consecutive_zero_work`.
- **`deploy/cron-meta.json`** — font de veritat de metadades (29 crons): `frequency_label`,
  `max_age_hours`, `skip_concern`, `silenced`/`silenced_reason`, `description`.
- **`deploy/cron.topquaranta`** — la taula real. Tot va per `tq-run` EXCEPTE `tq-backup`,
  `tq-recover`, `tq-health` i `tq-restore-test` (executats directament com a postgres/topquaranta).
- **`bin/tq-health`** (cron `15 * * * *`) — recull fets (status files + cron-meta + disc + web smoke
  + Spotify + migracions + errors Django + git drift) i delega la presentació + exit code a
  **`analytics/health_report.py`**. Amb `--email-on-fail` envia a admin@ via `mail_admins` quan
  `overall!=0`, amb **dedup per signatura sha256**.
- **`analytics/health_report.py`** — classifica cada cron (OK/SKIP/WAITING/WARN/STALE/STUCK/FAIL),
  agrupa, i calcula `overall`. Itera **només les claus de cron-meta**.
- **`web/api/staff/estat.py`** — la vista `/staff/estat`. Llegeix cron-meta + escaneja els status
  files (inclou orfes sense metadades). Exposa dades crues + ETAs al frontend.
- **Watchdog**: a `health_report.classify_cron`, `persistent = max(skips, fails)`; `>=10`→CRIT
  (escala), `>=3`→WARN (escala només si `silenced`).

---

## Causa arrel — patrons sistèmics

### Patró 1 — La derivació de tag ignora les variants de comanda (CODE) · Severitat MITJANA · 2 instàncies
`tq-run` només distingeix `--provisional`. Qualsevol altra variant de la mateixa comanda comparteix
el tag base → una variant sobreescriu o amaga l'estat de l'altra.
- **`actualitzar_playlists_spotify --freq weekly`** comparteix tag amb `--freq daily`. El run weekly
  escriu `actualitzar_playlists_spotify.status` i el daily (cada 2h, següent a :15) el sobreescriu
  en 15 min. La clau de cron-meta `actualitzar_playlists_spotify_weekly` **no rep mai status** →
  WAITING perpetu (confirmat live) i la variant weekly **no es monitora** (un fall del sync weekly
  és invisible).
- **`publicar_canal --channel {mastodon,bluesky,telegram,newsletter}`** — els 4 canals comparteixen
  el tag `publicar_canal`. Com que corren escalonats (mastodon→bluesky→telegram→newsletter), només
  l'últim que escriu queda registrat: un canal que falla sistemàticament queda **emmascarat** per un
  de posterior que té èxit. (No verificat quin canal queda últim cada dia; el risc és estructural.)

### Patró 2 — La signatura de dedup d'alerta es computa sobre text de presentació que canvia cada tick (CODE) · Severitat ALTA · sistèmic (afecta tota anomalia persistent)
`tq-health` calcula la signatura com `sha256(grep -E "STALE|STUCK|FAIL|DRIFT" <<<REPORT | head -3) + errors=N`.
Les línies capturades **inclouen valors que canvien cada hora**, així que la signatura **mai
s'estabilitza** per a una anomalia persistent → re-email cada hora (l'objectiu del dedup queda
anul·lat). Fonts de variació:
1. La línia de **resum executiu** ("🔴 N anomalies: … · DD/MM HH:MM CEST") conté el **timestamp
   actual** i és la primera que casa el grep → canvia cada tick.
2. La línia de grup del cron inclou l'**edat** ("fa Xh"), que augmenta cada hora.
3. `STALE({age_h}h)` / `STUCK({age_h}h, {skips}skips)` — comptadors que pugen cada hora.
4. `errors=${ERRORS_COUNT}` — recompte d'errors Django d'avui, que creix durant el dia.

Aquest és el motiu pel qual un fall d'un cron **diari** (whisper OOM) es reenvia **cada hora**: el
watchdog corre cada hora i la signatura difereix a cada execució. És alert-fatigue → es perden les
alertes reals.

### Patró 3 — Constants i llindars operatius duplicats que han derivat de la font (CONFIG + CODE) · Severitat BAIXA-MITJANA · 3 instàncies (+1 ja arreglada)
Valors copiats a codi/config que haurien de seguir una única font (la taula de cron o la població).
- **`skip_concern`** (cron-meta, 29 entrades) és **config morta per al watchdog**: `health_report`
  usa llindars **hardcoded 3/10** i no llegeix `skip_concern`. El `_doc` afirma que `tq-health` el
  llegeix "via jq" — **stale** (tq-health ja no usa jq; el renderer Python l'ignora). El llindar
  per-cron declarat no té cap efecte; s'aplica un 3/10 uniforme a tot. *(Possible ús al frontend
  Estat — no verificat.)*
- **`estat.py::enrich_per_hour = 50`** etiquetat "per hora", però el cron `enriquir_spotify` és
  **nocturn** (50/dia des de 2026-05-24). L'ETA del backlog al dashboard surt **~24× optimista**.
- **`estat.py::WHISPER_DAILY_LIMIT = 100`**, però el cron usa **`--limit 200`** (pujat 2026-05-05).
  L'ETA de Whisper surt **2× pessimista**.
- *(Ja arreglat, exemplar del sub-patró "llindar uniforme sobre població no uniforme": la cobertura
  no-verif de Spotify, segmentada al #152. Mateixa família.)*

### Patró 4 — Forats de cobertura: la feina fora del contracte tq-run/cron-meta és invisible (CONFIG/CODE) · Severitat ALTA (backups) / BAIXA (resta) · 4 instàncies
El watchdog només vigila el que està **declarat a cron-meta**; `health_report` itera les claus de
cron-meta, no els status files.
- **`tq-backup`** corre com a `postgres` directament (no `tq-run`, no a cron-meta) → l'èxit/fracàs
  del **backup de Postgres no apareix** ni a tq-health ni a Estat. Forat crític (els backups són la
  xarxa de seguretat).
- **`tq-recover`** (sweep de recuperació, cada 30 min) — sense status, no monitorat.
- **`tq-health`** — no es monitora a si mateix (inherent; acceptable).
- **`backfill_album_source.status`** — status file **orfe**: existeix però no té entrada a cron-meta
  ni línia a cron.topquaranta. Apareix a `/staff/estat` (sense metadades) però és **invisible a
  tq-health**. Revela una **inconsistència entre els dos consumidors** (Estat escaneja status files;
  tq-health només llegeix cron-meta) i, en la direcció oposada, que un cron afegit a la taula amb
  `tq-run` però no a cron-meta correria sense que el watchdog l'alertés.

### Patró 5 — WAITING conflà tres estats i mai escala (CODE) · Severitat BAIXA-MITJANA · 2 instàncies (solapen 1/4)
`classify_cron` retorna WAITING quan falta el status file i **mai escala** ("awaiting first run").
Barreja: (a) cron nou que encara no ha corregut, (b) cron que va córrer abans que existís el dir de
status, (c) cron el tag del qual no s'escriu mai.
- **actualitzar_playlists_spotify_weekly** — WAITING **per sempre** (cas b/c del Patró 1): mai surt
  de WAITING perquè el tag no s'escriu → permanentment silenciós.
- **arxivar_senyal_vell** — WAITING perquè el dir de status (Apr 21) és més nou que el seu darrer run
  trimestral (1 abr); "awaiting first run" és **enganyós** (sí que ha corregut). Benigne: passarà a
  OK/FAIL l'1 jul.

---

## Recompte i classificació

| Patró | Tipus | Severitat | Instàncies |
|---|---|---|---|
| 1. Tag ignora variants | CODE | Mitjana | 2 (playlists weekly, publicar_canal ×4 canals) |
| 2. Dedup sobre text time-varying | CODE | **Alta** | sistèmic (tota anomalia persistent) |
| 3. Constants duplicades derivades | CONFIG+CODE | Baixa-Mitjana | 3 (skip_concern mort, enrich_per_hour, WHISPER_DAILY_LIMIT) |
| 4. Forats fora de tq-run/cron-meta | CONFIG/CODE | Alta (backup) / Baixa | 4 (tq-backup, tq-recover, tq-health, backfill_album_source orfe) |
| 5. WAITING conflà i no escala | CODE | Baixa-Mitjana | 2 (weekly, arxivar) |

## Estat live (07/06 09:16 CEST)
29 crons, **0 anomalies** segons el report; 2 WAITING ⚪ (arxivar_senyal_vell,
actualitzar_playlists_spotify_weekly); disc 84% (🟠, no escala <90%); web/migracions/git OK.

## No verificat
- Si el **frontend Estat (React)** usa `skip_concern` per a algun llindar visual (només he comprovat
  que el watchdog l'ignora i que estat.py l'exposa).
- Quin canal de `publicar_canal` queda últim escrivint el tag cada dia (el risc d'emmascarament és
  estructural, no l'he reproduït amb dades).
- L'origen dels logs a `/var/log/topquaranta/status/admin_mail/` (de 2026-04-17; probablement un
  període amb EMAIL_BACKEND de fitxer). No determinant per als patrons.
- No he comptat empíricament quants emails s'han reenviat (no hi ha un log d'enviaments SMTP
  accessible read-only); el mecanisme del Patró 2 està verificat per codi, no per volum d'inbox.

Cap fix ni proposta de fix (per indicació). Tot read-only; arbre net.
