# Infra: ampliació de swap per a l'OOM de Whisper — 2026-06-06

> Acció d'**infraestructura** al servidor Hetzner (autoritzada explícitament). **NO** és codi, NO
> viu a git, NO passa per GHA, NO toca app/DB/git. Aquest fitxer és el registre de l'estat del
> servidor (no es committeja). Reversible.

## Motiu
El cron `analitzar_whisper` (04:00 UTC) va morir amb **OOM (exit 137)** als 3 intents el 2026-06-06
durant la càrrega del model `faster-whisper large-v3` (~2,8 GB RSS). El kernel/dmesg ho confirma:
3 OOM-kills, el primer invocat per `packagekitd` (pressió de memòria del sistema concurrent a les
04:00). Caixa CX22: RAM 3,7 GB, swap 2 GB ja ~1,7 GB ple en repòs → el model no hi cabia sota
pressió. (Vegeu `triatge-alertes-2026-06-06.md`.)

## Avaluació read-only prèvia (sense forçar)
- RAM: 3815 MB total, ~1112 MB lliure, ~2429 MB available.
- Swap: **2048 MB (2 GB)**, 1694 MB usat, 353 MB lliure (`/swapfile`, fstab `sw`).
- Disc `/`: 38 G, 27 G usat, **8,9 G lliure (76%)**.
- swappiness: 60. fstab: estàndard. → Cap STOP (disc ampli, config esperada).

## Acció
Afegit un **segon swapfile de 3 GB** (`/swapfile2`), sense tocar el swap actiu (més segur i
reversible que redimensionar `/swapfile` amb 1,7 GB en ús):
```
fallocate -l 3G /swapfile2   # (no sparse a ext4)
chmod 600 /swapfile2
mkswap /swapfile2            # UUID ac6b045b-...
swapon /swapfile2
# persistent:
cp /etc/fstab /etc/fstab.bak.20260606
echo '/swapfile2 none swap sw 0 0' >> /etc/fstab
swapon -a                   # valida que fstab parseja, sense errors
```

## Estat abans / després
| | Abans | Després |
|---|---|---|
| Swap total | 2 GB (`/swapfile`) | **5 GB** (`/swapfile` 2G + `/swapfile2` 3G) |
| Swap lliure (repòs) | 0,35 GB | **3,4 GB** |
| RAM + swap | 5,86 GB | **8,93 GB** |
| Disc lliure `/` | 8,9 G | **5,9 G** (84% usat, ≥ 3 G ✓) |
| Persistent (fstab) | sí | sí (línia afegida) |

Amb ~3 GB més de headroom de swap, la càrrega del model (~2,8 GB) sobreviu la finestra de
contenció de les 04:00 en lloc de provocar l'OOM-killer: les pàgines fredes d'altres processos
es poden evacuar a swap en comptes de matar el procés.

## Reversió (si calgués)
```
swapoff /swapfile2
sed -i '\#/swapfile2 none swap sw 0 0#d' /etc/fstab   # o restaurar /etc/fstab.bak.20260606
rm /swapfile2
```

## No verificat / límits
- No s'ha re-executat `analitzar_whisper` (consumiria ~2,8 GB de RAM real a prod); la mitigació és
  capacitat de memòria, l'efecte es confirmarà al pròxim tick de les 04:00 (o amb un `tq-run`
  manual si es vol forçar abans).
- swappiness deixat a 60 (no demanat). El `fail=10` constant de Whisper és un problema separat,
  no tocat.
- Arbre git de l'app intacte (`/home/topquaranta/app` net); els canvis són només `/swapfile2` +
  `/etc/fstab`, fora del repo.
