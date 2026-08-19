# Informe 2d — Disc: trajectòria i amenaça

Data: 2026-06-07. Read-only (prod). Sense canvis.

## Estat

`/dev/sda1 38G total, 30G usat, 5.9G lliure, 84%` (🟠 al panell; 🔴 a ≥90%).

## Consumidors (du, top)

| Camí | Mida | Naturalesa |
|---|---|---|
| `/var/log/journal` | **3.8G** | systemd journal, **SENSE CAP** (`SystemMaxUse` i `MaxRetentionSec` comentats a journald.conf) → **creix sense límit** |
| `/home/topquaranta/.cache/huggingface` | 3.0G | models Whisper, descàrrega única, **estàtic** |
| `/var/lib/snapd` | 1.8G | snaps, ~estàtic |
| `/home/topquaranta/app/.venv` | 1.8G | virtualenv, ~estàtic |
| `/home/topquaranta/.claude` | 890M | (eines locals) |
| `/home/topquaranta/.cache/puppeteer` | 627M | estàtic, netejable |
| `/home/topquaranta/backups` | 492M | retenció escalonada, **acotat** |
| `/var/cache/topquaranta/social/renders` | 264M | PNGs socials; logrotate hauria de podar >60d |
| `/var/topquaranta/portades` | 232M (8.004 fitxers) | creix amb el catàleg, **lent** |
| `/var/log/topquaranta` | 20M | logs app, logrotate funciona (8 setmanes) |
| BD postgres (`/var/lib/postgresql`) | 363M | petita |

## Trajectòria i veredicte

- La **base estàtica domina** (huggingface 3.0G + snapd 1.8G + .venv 1.8G + caches ≈ 10G no creixen).
- L'**únic creixement no acotat rellevant és el journal de systemd (3.8G, sense cap)**. La resta o està acotat (backups, logs app via logrotate) o creix lentament (portades amb el catàleg).
- **NO és amenaça propera**: 5.9G lliures i cap vector de creixement ràpid. El risc real només arribaria si el journal segueix inflant-se durant mesos o si un procés escup temporals.

## Recomanacions (ops, decisió de l'usuari — fora de l'abast de FASE 3)

1. **Capar el journal** (`SystemMaxUse=500M` a journald.conf + `journalctl --vacuum-size=500M`) → allibera ~3.3G immediatament. És un canvi de config del servidor (out-of-band), per tant **no el faig**; o caldria gestionar-lo via `deploy/` si es vol versionar.
2. Verificar que la poda de `social/renders` >60d s'executa (264M sembla alt).
3. Netejables puntuals si calgués marge: `.cache/puppeteer` (627M), `.cache/pip` (270M).

Cap acció presa (read-only). Cap d'aquests és un fix de codi de FASE 3.
