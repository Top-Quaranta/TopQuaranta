# Backup offsite (capa 2) — disseny i activació

> Estat: **DECIDIT I IMPLEMENTAT (GATED)** — 2026-07-05. El codi és a
> main però inert: fins que el Miquel no complete l'activació (§9), el
> cron reporta `DISABLED` i no toca res. Decisions preses pel Miquel el
> 2026-07-05: destí **Backblaze B2** amb key append-only; **retenció
> dividida per PII** (90 dies el dump complet / 12 mesos el sanejat);
> xifratge restic en origen. Mesures que fonamenten el disseny:
> `docs/audits/2026-07-05-recon-backup-offsite.md`. Política de
> retenció completa: `docs/ops/retention.md` §Backups.

## 1. Per què una capa 2

La capa 1 (imatges Hetzner Cloud diàries ×7 + dumps locals de
`tq-backup` + `tq-restore-test` mensual) comparteix un únic domini de
fallada: el compte Hetzner. El token de l'API viu al `.env` del mateix
servidor, així que un compromís del box permet esborrar també les
imatges Cloud. I la BD conté PII de comunitat (perfils, DMs) — la
condició que el runbook fixava per revisar el risc acceptat del
2026-05-07.

Objectiu: una còpia **fora del compte Hetzner**, **xifrada en origen**,
que **el servidor no puga destruir** ni tan sols amb root.

## 2. Peces (totes a main, totes gated)

| Peça | Fitxer | Estat |
|---|---|---|
| Script diari 03:30 | `bin/tq-backup-offsite` | Implementat; `DISABLED` fins a l'activació |
| Cron | `deploy/cron.topquaranta` (03:30) + `deploy/cron-meta.json` | Desplegat |
| Estat a tq-health / panell | `analytics/health_report.py` + `EstatPage.jsx` — estat `DISABLED` gris, legítim, sense alerta; si el wrapper deixa de córrer, cau a `STALE` vermell | Implementat |
| Dump sanejat mensual | `bin/tq-backup` → `monthly-safe/tq-month-safe-*` | Actiu des del primer dia 1 post-deploy |
| Retenció PII 90 d | `bin/tq-backup` → `monthly/tq-month-pii-*` | Activa (només fitxers nous; els legacy conserven 365 d) |
| Guards CI | `topquaranta/tests/test_backup_offsite.py` | Actius |

## 3. Payload i tags

Dos snapshots restic per nit, etiquetats per política de retenció:

- **`--tag pii`** (retenció ≤90 dies, aplicada des del Mac): últim dump
  diari complet + `.env` + `data/`.
- **`--tag safe`** (12 mesos): `monthly-safe/` (dumps sanejats — schema
  complet, DATA de les taules amb dades personals exclosa; llista
  exacta i guard CI a `retention.md` §Backups) + portades (868 MB,
  append-mostly; cobreix els àlbums Deezer delistats).

El dump diari viatja en `gzip -9` tal qual (churn ~30 MB/dia — l'opció
(a) del recon; a aquesta escala el cost és negligible i evita tocar el
`tq-backup` existent més del necessari).

## 4. Append-only: què protegeix i què no

La key B2 del servidor té **només** `listFiles`/`readFiles`/`writeFiles`
— sense `deleteFiles`. `restic forget`/`prune` des del servidor falla
amb permission denied; el script no els invoca mai (guard al test: cap
verb destructiu a les crides restic).

**Protegeix contra**: compromís total del box (root inclòs) — l'atacant
pot llegir el repo (res que no tinga ja del disc viu) i pujar
escombraria (detectable, §7), però **no pot destruir l'històric**;
esborrat accidental; ransomware; pèrdua del compte Hetzner sencer.

**NO protegeix contra**: compromís del compte B2 mestre (per això el
compte és independent, amb 2FA, i la key privilegiada només viu al
Mac); pèrdua de la contrasenya restic (repo il·legible — còpia al
gestor personal I en paper); bugs de restic (mitigat per la capa 1,
tecnologia diferent); un atacant pacient que espera que expire l'últim
backup net.

## 5. RGPD i transferència fora de la UE

restic xifra i autentica **en origen** (AES-256 + Poly1305): Backblaze
només emmagatzema blobs opacs i **mai veu dades en clar**. Això cobreix
el matís de transferència internacional — el processador extern no té
accés a dades personals, només a xifrat del qual no posseeix la clau.
Tot i això, es recomana bucket a la regió UE de B2 (Amsterdam, mateix
preu). El límit temporal de PII als backups (90 dies) està declarat a
`retention.md` §Backups.

## 6. Cost

Dipòsit estimat ~2-4 GB el primer any (payload inicial ~0,9 GB + churn
30 MB/dia amb la retenció de §3): **< 0,10 $/mes** a les tarifes B2
(6 $/TB/mes), mínims de facturació a banda. Irrellevant al pressupost.

## 7. Verificació

1. **Diari** (dins del mateix run): el status file inclou el tail del
   `restic backup` de cada tag; `tq-health` marca `STALE` si el status
   envelleix (>26 h) i `FAIL` si restic retorna error.
2. **Trimestral, manual, des del Mac** (§9.7): `restic check
   --read-data-subset=10%` + restore real del dump més recent + el
   `forget`+`prune` amb la key privilegiada. És alhora la prova que la
   capa 2 és recuperable sense el box.
3. **Post-activació (seguiment, no implementat encara)**: cron setmanal
   de `restic check` lleuger i variant mensual de `tq-restore-test`
   que restaure des del destí — es faran quan el sistema estiga actiu
   i hi haja snapshots reals contra els quals provar; mentre el flag
   està apagat serien files DISABLED permanents sense valor.

## 8. Decisions preses (2026-07-05, Miquel)

1. **Destí**: Backblaze B2, compte propi del Miquel (2FA, email de
   recuperació propi); cap credencial mestra toca el servidor.
2. **Retenció**: dividida per PII — complet 90 dies / sanejat 12 mesos,
   local i offsite (detall a `retention.md` §Backups). Els monthly
   locals legacy conserven la finestra original de 365 dies;
   esborrar-los abans demana OK explícit seu.
3. **Contrasenya restic**: generada pel Miquel, al seu gestor personal +
   còpia en paper; al servidor només via `.env` (necessària per
   escriure). Un atacant amb el `.env` pot *llegir* el repo offsite
   (res de nou per a ell) però no esborrar-lo.
4. **Pla B autoritzat però NO exercit**: la divisió del dump ha resultat
   viable (una llista `--exclude-table-data` + guard CI), així que la
   sèrie de 12 mesos es conserva.

## 9. Procediment d'activació (el que fa el Miquel)

Cap d'aquests passos el fa el codi; el sistema queda actiu quan tots
estan fets. Ordre pensat perquè cada pas siga verificable abans del
següent.

1. **Compte B2** (backblaze.com): compte nou amb 2FA, bucket privat
   (regió UE — `eu-central-003`), sense lifecycle rules (la retenció la
   gestiona restic des del Mac).
2. **Dues application keys**:
   - *Key servidor* (anirà al `.env`): capabilities `listFiles`,
     `readFiles`, `writeFiles` — **sense** `deleteFiles`. Restringida al
     bucket.
   - *Key admin* (només al Mac, per a §9.6-9.7): totes les capabilities
     del bucket.
3. **Contrasenya restic**: genera-la (gestor de contrasenyes) i fes-ne
   la còpia en paper ABANS de continuar.
4. **Inicialitza el repo des del Mac** (així la primera operació ja
   prova les credencials fora del box):

   ```bash
   export AWS_ACCESS_KEY_ID=<keyID admin>
   export AWS_SECRET_ACCESS_KEY=<applicationKey admin>
   restic -r s3:s3.eu-central-003.backblazeb2.com/<bucket> init
   ```

5. **Servidor** — instal·la restic i posa les variables:

   ```bash
   sudo apt-get update && sudo apt-get install -y restic
   ```

   Al `.env` de `/home/topquaranta/app/` (noms exactes que llig
   `bin/tq-backup-offsite`):

   ```dotenv
   OFFSITE_BACKUP_ACTIU=1
   RESTIC_REPOSITORY=s3:s3.eu-central-003.backblazeb2.com/<bucket>
   RESTIC_PASSWORD=<contrasenya restic>
   AWS_ACCESS_KEY_ID=<keyID SERVIDOR>
   AWS_SECRET_ACCESS_KEY=<applicationKey SERVIDOR>
   ```

6. **Primer run manual + verificació**:

   ```bash
   sudo -u topquaranta /home/topquaranta/bin/tq-backup-offsite
   cat /var/log/topquaranta/status/tq-backup-offsite.status   # status=OK
   sudo -u topquaranta tq-health | grep -i offsite            # 🟢
   ```

   I des del Mac (key admin): `restic snapshots` ha de mostrar els dos
   tags. Prova també que la key del SERVIDOR no pot esborrar:
   `restic forget --id <snap>` amb les credencials del servidor ha de
   fallar amb permission denied.
7. **Prova de recuperació en fred (obligatòria la primera vegada)**: al
   Mac, teclejant la contrasenya des de la CÒPIA EN PAPER (ni gestor ni
   copy-paste — és el simulacre de "he perdut el Mac i el servidor"):
   `restic restore latest --tag pii --target /tmp/tq-drill`, obre el
   dump i verifica que conté dades. Després `rm -rf /tmp/tq-drill`.
   Repetir el drill (ja amb el gestor) cada trimestre, juntament amb:

   ```bash
   restic check --read-data-subset=10%
   restic forget --tag pii  --keep-within 90d --prune
   restic forget --tag safe --keep-monthly 12 --prune
   ```

8. Quan tot això estiga verd: cap acció més — el cron de les 03:30 ja
   corre cada nit i tq-health el vigila com qualsevol altre.
