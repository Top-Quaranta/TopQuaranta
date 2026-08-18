# Recon — alerta tq-health 2026-08-12 17:15 CEST (disc 90% + sembrar_canals_youtube MISSING)

> Nota local (untracked), 2026-08-12. Només investigació (agent
> read-only sobre el Hetzner); cap canvi fet al servidor.

## 1. `sembrar_canals_youtube` MISSING — es resol sol demà

**Causa: mai no li ha arribat l'hora.** No és cap fallada:

- PR #366 (11/08 08:05 UTC) va afegir command + cron **setmanal**
  (dilluns 02:00 UTC) + entrada a `cron-meta.json` (llindar 176 h).
  El dilluns 10 ja havia passat → primer tret hauria sigut el 17.
- PR #371 (12/08 08:30 UTC) el passa a **diari** (02:00 UTC) i abaixa
  el llindar a 26 h — però el slot d'avui ja havia passat 6,5 h abans
  del deploy.
- El watchdog veu l'entrada amb llindar 26 h i cap status file
  (`tq-run` sempre n'escriu, fins i tot en FAIL → confirma que no ha
  corregut mai).

La línia de cron ESTÀ desplegada (`/etc/cron.d/topquaranta:112`) i el
command existeix. **Primer tret: 2026-08-13 02:00 UTC (04:00 CEST)**;
l'alerta hauria de desaparéixer al tick de les 03:15 UTC. Si demà
persisteix, aleshores sí: mirar `youtube.log` i el `.status`.

Nota lateral: `descobrir_youtube` d'avui va quasi exhaurir la quota
de Google (8.981/9.000 unitats, warnings «Quota exceeded»). No afecta
la sembra (forHandle = 1 unitat), però és un símptoma a vigilar.

## 2. Disc al 90% (38G totals, 32G usats, 3.9G lliures)

### Majors consumidors

| Consumidor | Mida | Notes |
|---|---|---|
| Swap (`/swapfile` + `/swapfile2`) | 5.0G | Probablement intencionat (CX22 4GB RAM) |
| `/root/.vscode-server` | 4.9G | 6 builds del server (598-699M c/u); només cal l'últim → **~3.3G recuperables** |
| `~topquaranta/.cache/huggingface` | 3.0G | faster-whisper-large-v3 — necessari, no tocar |
| `/var/lib/snapd` | 2.9G | Revisions disabled duplicades + 1.2G cache → **~1.5-2G recuperables** (`snap set system refresh.retain=2`) |
| `/home/topquaranta/app` | 2.2G | .venv 1.8G (necessari) |
| `/home/llotja` | 2.1G | Altre tenant; no és cosa nostra |
| `/var/topquaranta/portades` | **1.7G, 60.402 fitxers** | ⚠️ El creixedor: +6.342 fitxers / +166 MB en 7 dies, **sense retenció** |
| Caches Claude Code | 1.7G | root 844M + topquaranta 890M |
| Restes dev a `/root` | 0.8G | `TopQuaranta_dev` (416M) + `venv_topq_backup` (390M) — semblen morts, confirmar |
| `/var/log` | 603M | topquaranta només 17M — **logrotate funciona** |

### Recomanacions (cap executada), ~6-8G potencials

1. Podar builds vells de `/root/.vscode-server/cli/servers/` (~3.3G) —
   el guany més gran i més segur.
2. Snapd: retain=2 + purgar revisions disabled + cache (~1.5-2G).
3. Confirmar mort i esborrar `TopQuaranta_dev` + `venv_topq_backup`
   (~0.8G).
4. `pip cache purge` + `npm cache clean` + `apt-get clean` (~0.6G).
5. **Estructural**: retenció per a `/var/topquaranta/portades`
   (~700 MB/mes de creixement — tornarà a disparar l'alerta encara
   que es netege la resta). Valorar també si calen 5G de swap.

### Matís del logrotate de renders socials

La poda >60d de renders deixa 21 fitxers vells (juny) a
`/var/cache/topquaranta/social/renders/`: la regla poda `*.png` però
els renders són **`.jpg`**. Impacte mínim (dir sencer 86M), però el
glob no cobreix l'extensió — fix d'una línia a
`deploy/logrotate.topquaranta` quan es toque.
