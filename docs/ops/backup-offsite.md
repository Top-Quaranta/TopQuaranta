# Backup offsite (capa 2) — document de disseny

> Estat: **PROPOSTA** (2026-07-05). Cap peça implementada. Les decisions
> de la §8 corresponen al Miquel. Mesures que fonamenten aquest disseny:
> `docs/audits/2026-07-05-recon-backup-offsite.md`.
> Capa 1 existent: Hetzner Cloud Backups (imatge diària, 7 de retenció,
> 20% del preu de la instància) + `tq-backup` (dumps locals) +
> `tq-restore-test` (mensual). Vegeu runbook §4.

## 1. Per què una capa 2

La capa 1 sencera comparteix un únic domini de fallada: el compte
Hetzner. El token de l'API viu al `.env` del mateix servidor, així que
un compromís del box permet esborrar també les imatges Cloud. I la BD
conté ara PII de comunitat (perfils, DMs) — la condició que el runbook
fixava per revisar el risc acceptat del 2026-05-07.

Objectiu: una còpia **fora del compte Hetzner**, **xifrada en origen**,
que **el servidor no puga destruir** ni tan sols amb root.

## 2. Eina: restic

- Xifratge autenticat en origen (AES-256 + Poly1305); el destí només veu
  blobs opacs.
- Dedup per contingut: les portades (868 MB, append-mostly) costen una
  vegada; els dumps diaris només pugen el delta real.
- Suporta SFTP (Storage Box) i S3 (Backblaze B2) sense dependències.
- Binari estàtic únic — s'instal·la copiant un fitxer (quan s'aprove;
  res s'instal·la durant el recon).
- `restic check --read-data-subset` permet verificació d'integritat
  incremental barata.

## 3. Què es copia (payload)

| Inclòs | Mida | Nota |
|---|---|---|
| Dump BD del dia | ~30 MB | Vegeu nota de format ↓ |
| `/home/topquaranta/app/.env` | 2 KB | Secrets — xifrats per restic |
| `/home/topquaranta/app/data/` | 2 MB | CSVs d'operacions |
| `/var/topquaranta/portades/` | 868 MB | Cobreix àlbums Deezer delistats |

Exclòs (regenerable): `.venv`, `staticfiles/`, renders socials, models
ML, goaccess, logs. El conjunt està definit al recon §3.

**Nota de format del dump**: el `gzip -9` actual trenca la dedup de
restic (qualsevol canvi re-xifra tot el fitxer). Opcions, de menys a més
canvi: (a) apuntar restic al `.sql.gz` tal qual i acceptar ~30 MB/dia de
churn — simple, i a aquesta escala el cost és negligible; (b) afegir un
`pg_dump -Fc` (custom, comprimit intern per taula, dedup raonable) només
per a la capa 2. **Proposta: (a) per començar** — 30 MB/dia × retenció
365 dies ≈ 11 GB/any de pitjor cas, que segueix costant cèntims. Es pot
migrar a (b) si el dipòsit molesta.

## 4. Freqüència i encaix amb el cron

- **Diari, 03:30** (30 min després de `tq-backup`, que acaba en segons).
- Embolcallat amb el contracte existent: `tq-run tq-backup-offsite` →
  status file → visible a `tq-health` i al panell `/staff/estat`, amb
  entrada a `deploy/cron-meta.json` (threshold de preocupació: 26 h).
- `SingletonLock` no cal (una execució diària, curta); sí un timeout
  generós per a la primera pujada (~1 GB inicial).

## 5. Model append-only: què protegeix i què no

El requisit central: **les credencials que viuen al servidor no poden
esborrar ni sobreescriure res del dipòsit.**

- **Backblaze B2**: application key **sense** `deleteFiles` ni
  `listBuckets` (només `listFiles`, `readFiles`, `writeFiles`). restic
  no pot fer `prune`/`forget` des del servidor — falla amb permission
  denied. El prune es fa des d'una màquina de confiança (el Mac) amb una
  key separada que mai toca el servidor. Opcional: Object Lock al bucket
  per a immutabilitat amb finestra temporal.
- **Hetzner Storage Box**: SFTP no té permisos append-only de veritat (el
  mateix login que escriu pot esborrar). La mitigació són els
  **snapshots automàtics del Storage Box** (fins a 10, programables
  diaris/setmanals): es gestionen des del panell Robot del compte destí,
  el client SFTP no els pot tocar. Protecció equivalent en la pràctica
  (finestra de snapshots), però no és un deny real a nivell de
  credencial.

**Protegeix contra**: compromís total del servidor (root inclòs) — l'
atacant pot llegir el repo (i ja té les dades vives, res de nou), pot
pujar snapshots-escombraria (cost, detectable per la verificació §7),
però **no pot destruir l'històric**; esborrat accidental (`rm` humà o
script); ransomware al box; pèrdua del compte Hetzner sencer.

**NO protegeix contra**: compromís del compte destí (credencials mestres
B2/Robot — per això el compte destí ha de ser independent, amb 2FA i
sense cap credencial seua al servidor); pèrdua de la contrasenya restic
(el repo esdevé il·legible: cal guardar-la a un gestor de contrasenyes
personal I en paper, mai al servidor... però sí al `.env` per poder
escriure — vegeu matís §8.4); bugs de restic mateix (mitigat per la
capa 1, que és d'una tecnologia diferent); i un atacant pacient que
espera que la retenció expire l'últim backup net.

## 6. Destins considerats i cost mensual estimat

Dipòsit estimat (payload ~0,9 GB + churn 30 MB/dia amb retenció §8.3):
**~2-4 GB el primer any**, ~12 GB de pitjor cas si mai es fa prune.

| | Hetzner Storage Box (compte separat) | Backblaze B2 |
|---|---|---|
| Preu | BX11 1 TB ≈ **3,8 €/mes** (preu fix) | 6 $/TB/mes → **&lt;0,10 $/mes** a 4 GB (mínims a banda) |
| Append-only | Aproximat (snapshots del box, §5) | **Real** (capacitats de la key) |
| Independència | Compte Hetzner separat: proveïdor igual, jurisdicció igual | Proveïdor i jurisdicció diferents (EUA) |
| Protocol | SFTP (restic natiu) | S3 (restic natiu) |
| RGPD | UE (Alemanya/Finlàndia) | EUA (o cluster UE de B2 a Amsterdam, mateix preu) |
| Fricció | Panell Robot conegut; factura previsible | Compte nou; facturació per ús |

Lectura honesta: a la nostra mida, el cost és irrellevant en tots dos
casos; la decisió real és **append-only fort + proveïdor divers (B2,
regió UE)** contra **jurisdicció UE amb marca coneguda i preu fix
(Storage Box)**. El disseny funciona igual amb qualsevol; només canvia
l'URL del repo i el mecanisme de la §5.

## 7. Pla de verificació (integrat amb tq-health)

1. **Diari** (dins del mateix `tq-backup-offsite`): `restic snapshots
   --latest 1` post-pujada; el status file inclou id, mida i durada.
   `tq-health` marca STUCK si el status envelleix (>26 h), com qualsevol
   cron.
2. **Setmanal** (diumenge, slot tranquil): `restic check
   --read-data-subset=10%` — verifica integritat real d'un 10% rotatori
   dels blobs descarregant-los i re-hashant-los. Status file propi.
3. **Mensual, restore-test real de la capa 2**: variant de
   `tq-restore-test` que en lloc del dump local fa `restic restore` del
   dump més recent **des del destí** a un directori temporal, el
   restaura a `topquaranta_restore_test` i passa les mateixes sanity
   queries de forma i row counts. Si el disc ho fa patir (dump ~30 MB,
   cap problema previst), `restic dump` en streaming directe a psql.
4. **Trimestral, manual, des del Mac** (documentat al runbook, no
   automatitzable des del servidor per definició): restore amb les
   credencials de només-lectura des d'una màquina que no és el box —
   prova que la capa 2 és recuperable encara que el box haja
   desaparegut. També és el moment del `restic forget + prune` amb la
   key privilegiada (B2) o de revisar els snapshots del box (Storage
   Box).

La detecció d'un atacant que puja escombraria (§5) cau del punt 2-3: un
repo corromput o inflat falla el check o dispara la mida reportada.

## 8. Decisions que corresponen al Miquel

1. **Proveïdor i compte destí**: B2 (append-only real, jurisdicció
   mixta) vs Storage Box en compte separat (UE, preu fix). El compte, en
   tots dos casos, l'obri i el controla ell (2FA, email de recuperació
   propi); cap credencial mestra toca mai el servidor.
2. **Pressupost**: tots dos càpiguen en &lt;4 €/mes; confirmar que el marge
   existeix i si es prefereix cost fix (Storage Box) o per ús (B2).
3. **Retenció de la capa 2 amb PII**: proposta inicial 7 diaris / 4
   setmanals / 12 mensuals (mirall de `tq-backup`). Però cal una decisió
   RGPD explícita: un compte esborrat persisteix als backups fins que
   l'últim dump que el conté expira (12 mesos amb la proposta). Cal (a)
   fixar aquest màxim com a política documentada a `retention.md`
   (l'enfocament estàndard: backups exempts de l'esborrat immediat amb
   retenció màxima declarada), o (b) escurçar la retenció mensual de la
   capa 2 (p. ex. 6 mesos) si 12 es considera excessiu. La mateixa
   decisió aplica retroactivament als monthly locals de `tq-backup`
   (365 dies), que avui no estan documentats a `retention.md`.
4. **On viu la contrasenya del repo restic**: proposta — generada pel
   Miquel, guardada al seu gestor personal + còpia en paper; al servidor
   només via `.env` (la necessita per escriure). Matís important: això
   vol dir que un atacant amb el `.env` pot *llegir* el repo offsite
   (res que no tinga ja del disc viu) però continua sense poder-lo
   esborrar. Si es vol que ni tan sols puga llegir-lo, cal un esquema de
   claus asimètric fora de restic (age/rclone crypt) — complexitat que
   NO es proposa per a la v1.

## 9. Fora d'abast d'aquesta proposta

Implementació (binari restic, systemd/cron, entrada a `cron-meta.json`,
extensió de `tq-health`, docs runbook §4) — vindrà com a PR separat
quan les decisions de la §8 estiguen preses. Cap canvi a la capa 1.
