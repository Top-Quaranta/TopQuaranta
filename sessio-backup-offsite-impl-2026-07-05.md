# Sessió implementació backup offsite (capa 2) — 2026-07-05

> Nota local de referència (untracked). Fonts canòniques:
> PR #313 (implementació) · docs/ops/backup-offsite.md (disseny +
> activació §9) · docs/ops/retention.md §Backups (política).
> El PR #311 (recon + disseny) es va mergejar a l'inici d'aquesta
> sessió en declarar-se el disseny aprovat.

## Què ha quedat fet (tot inert/gated fins que actives)

- `bin/tq-backup-offsite` — cron diari 03:30. Sense flag+vars+restic →
  `DISABLED` (gris a tq-health, sense alerta), exit 0, no toca res.
  Amb tot present: 2 snapshots restic per nit — `--tag pii` (dump
  complet + .env + data/) i `--tag safe` (dumps sanejats + portades).
  Mai `forget`/`prune` (la key del servidor no pot esborrar).
- `bin/tq-backup` — split PII: `monthly/tq-month-pii-*` (90 dies) +
  `monthly-safe/tq-month-safe-*` (12 mesos, sense dades personals).
  **Els 3 monthly legacy (maig/juny/juliol) NO s'esborren**: conserven
  la finestra de 365 dies fins al teu OK explícit.
- tq-health + `/staff/estat`: nou estat `DISABLED` gris i legítim.
- Guard CI: si algú afig un model amb FK a usuari i no l'exclou del
  dump sanejat, CI trenca. (Ja va caçar `auth_user` — db_table legacy —,
  `social_*auth` i `music_artistalastfmalias` a la primera passada.)

## La teua part — procediment d'activació (detall complet a backup-offsite.md §9)

1. Compte B2 nou (2FA), bucket privat regió UE (`eu-central-003`),
   sense lifecycle rules.
2. Dues application keys: **servidor** (list/read/write, SENSE
   deleteFiles, restringida al bucket) i **admin** (només al Mac).
3. Contrasenya restic → gestor personal + CÒPIA EN PAPER abans de res.
4. Des del Mac (key admin):
   `restic -r s3:s3.eu-central-003.backblazeb2.com/<bucket> init`
5. Al servidor: `sudo apt-get install -y restic` i al `.env`:
   ```
   OFFSITE_BACKUP_ACTIU=1
   RESTIC_REPOSITORY=s3:s3.eu-central-003.backblazeb2.com/<bucket>
   RESTIC_PASSWORD=<contrasenya>
   AWS_ACCESS_KEY_ID=<keyID SERVIDOR>
   AWS_SECRET_ACCESS_KEY=<applicationKey SERVIDOR>
   ```
6. Primer run manual:
   `sudo -u topquaranta /home/topquaranta/bin/tq-backup-offsite`
   → status OK + tq-health verd; des del Mac `restic snapshots` mostra
   els 2 tags; i comprova que la key del servidor NO pot fer
   `restic forget` (permission denied).
7. **Prova de recuperació en fred** (primera vegada, obligatòria):
   restore al Mac teclejant la contrasenya DES DEL PAPER.
8. Trimestral (Mac, key admin):
   `restic check --read-data-subset=10%` +
   `restic forget --tag pii --keep-within 90d --prune` +
   `restic forget --tag safe --keep-monthly 12 --prune`.

## Decisions que queden obertes

- OK (o no) per esborrar abans de hora els 3 monthly legacy amb PII.
- Post-activació: cron setmanal de `restic check` + variant mensual de
  tq-restore-test que restaure des de B2 (seguiment documentat a
  backup-offsite.md §7.3).
