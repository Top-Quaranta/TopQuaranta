> Còpia local de referència (untracked). Font canònica: PR #311
> (branch worktree-backup-offsite-recon) — docs/ops/backup-offsite.md
> + docs/audits/2026-07-05-recon-backup-offsite.md. No editar ací.

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


---

# Recon backup offsite (capa 2) — mesures en prod, 2026-07-05

> Sessió estrictament només-lectura contra prod. Cap instal·lació, cap
> credencial, cap escriptura. Tot l'output d'aquest informe és cru, de
> les comandes indicades. Document de disseny associat:
> `docs/ops/backup-offsite.md`.

## 1. Mida de la BD (real, no estimada)

`sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('topquaranta'));"`

```
 db_total
----------
 288 MB
```

Top taules (`pg_total_relation_size`, top 15):

```
 music_artista                 | 88 MB
 ranking_senyaldiari           | 57 MB
 music_canco                   | 31 MB
 analytics_metricaesdeveniment | 23 MB
 music_artistalastfmsimilar    | 12 MB
 music_artistalastfmalias      | 12 MB
 music_historialrevisio        | 9992 kB
 music_album                   | 9528 kB
 music_staffauditlog           | 9336 kB
 analytics_metricasocialpost   | 5960 kB
 music_spotifymetadata         | 4280 kB
 analytics_metricaseoquery     | 2792 kB
 ranking_topsetmanal           | 1456 kB
 music_canco_artistes_col      | 1208 kB
 music_artista_territoris      | 792 kB
```

**Dump comprimit real** (no ha calgut generar-ne cap: `tq-backup` en
deixa un cada nit): **29 MB** (`gzip -9` de `pg_dump`).

## 2. Creixement

Mides reals dels dumps retinguts (`ls -lh /home/topquaranta/backups/`):

```
monthly:
  17M  tq-month-20260501-030001.sql.gz   (1 maig)
  25M  tq-month-20260601-030001.sql.gz   (1 juny)
  28M  tq-month-20260701-030001.sql.gz   (1 juliol)
weekly:
  26M (7 jun) · 26M (14 jun) · 27M (21 jun) · 28M (28 jun) · 29M (5 jul)
daily (28 jun – 5 jul):
  28M · 28M · 28M · 28M · 29M · 29M · 29M · 29M
```

Ritme: **+3 a +5 MB/mes comprimit** en règim actual (maig→juny va ser
+8 MB per l'arribada de features noves — whisper/aliases/similars).
Extrapolació prudent a 12 mesos vista: dump de ~70-90 MB. Els motors
del creixement són `music_artista` (features ML denses per artista) i
`ranking_senyaldiari` (acotat per l'arxivat a 2 anys, `retention.md`).

## 3. Inventari: regenerable vs irrecuperable

Mides reals (`du -sh`, 2026-07-05):

| Ruta | Mida | Classificació |
|---|---|---|
| BD (dump gzip) | 29 MB | **IRRECUPERABLE** — tota la curació manual (aprovacions, MBIDs pinnats, aliases, audit log), la comunitat (PII: perfils, DMs, publicacions) i l'històric de rànquings. És el projecte. |
| `/home/topquaranta/app/.env` | 2.172 B | **IRRECUPERABLE** amb matís — secrets regenerables un a un (rotar API keys), però la reconstitució és lenta i alguns (refresh token Spotify) requereixen re-OAuth manual. |
| `/home/topquaranta/app/data/` | 1,9 MB | **IRRECUPERABLE** (CSV d'operacions ad-hoc, p. ex. `cleanup_cascada_2026-05-12.csv`). |
| `/var/topquaranta/portades/` | 868 MB | **PARCIALMENT regenerable** — es re-baixa de Deezer, EXCEPTE àlbums delistats (Deezer serveix 200 estàtics però la CDN pot morir; casos reals coneguts). No hi ha manera barata de saber quins són irrecuperables per endavant. |
| `/var/cache/topquaranta/social/renders/` | 174 MB | Regenerable (re-render des de BD+portades); a més logrotate poda >60 d. Valor històric menor. |
| `/var/cache/topquaranta/social/covers/` | 51 MB | Regenerable (subconjunt de portades). |
| `music/ml_*.joblib` | ~3,7 MB | Regenerable (retrain des de la BD, minuts). |
| `staticfiles/` | 11 MB | Regenerable (`collectstatic`). |
| `.venv/` | 1,8 GB | Regenerable (`pip install`). |
| `/var/log/topquaranta/` | 14 MB | Prescindible (nice-to-have forense). |
| `/var/cache/topquaranta/goaccess/` | 448 KB | Regenerable des de logs Caddy. |

**Conjunt mínim irrecuperable: ~31 MB/dia.** Conjunt recomanat
(mínim + portades, per cobrir els delistats): **~0,9 GB inicials +
deltes petites** (les portades són append-mostly; restic dedueix).

## 4. Què cobreix el sistema actual (capa 1) i on són els forats

**a) Hetzner Cloud Backups** (verificat amb `hcloud image list -t backup`):

```
402886765   Mon Jun 29 10:13   14.04 GB   topquaranta-server
403251607   Tue Jun 30 10:13   14.26 GB   topquaranta-server
403616677   Wed Jul  1 10:13   14.32 GB   topquaranta-server
403982451   Thu Jul  2 10:13   14.38 GB   topquaranta-server
404347183   Fri Jul  3 10:13   14.59 GB   topquaranta-server
404711619   Sat Jul  4 10:13   14.95 GB   topquaranta-server
405076072   Sun Jul  5 10:13   15.21 GB   topquaranta-server
```

Imatge de disc sencer, diària (~10:13 UTC), **7 de retenció**. Cobreix
tot el disc (BD, portades, .env, tot).

**b) `tq-backup`** (cron 03:00, usuari postgres): `pg_dump | gzip -9` a
`/home/topquaranta/backups/`, retenció daily 7 / weekly 30 d / monthly
365 d, status file per a `tq-health`. **Només la BD** — ni portades, ni
`.env`, ni `data/`. (Nota menor: el comentari de capçalera del script
diu "~45 MB DB, gzipped ~5-10 MB" — desactualitzat; real 288 MB / 29 MB.)

**c) `tq-restore-test`** (mensual, dia 1 04:30): restaura el dump més
recent a una BD temporal i valida forma + row counts. Verifica **el
dump local**, no la imatge Hetzner ni cap còpia externa.

**Forats de la capa actual:**

1. **Mateix compte, mateixa infraestructura.** Els backups Hetzner i els
   dumps locals cauen amb el mateix esdeveniment: compromís del compte
   Hetzner (API token al `.env` del mateix servidor! — `hcloud` funciona
   des del box), impagament, ban, o desastre del datacenter. Un atacant
   amb root al servidor pot esborrar els dumps locals **i** (via el
   token) les imatges de backup del Cloud.
2. **Retenció curta de la capa 1**: 7 dies d'imatges. Una corrupció
   silenciosa (o un esborrat RGPD erroni) descoberta al dia 8 només és
   recuperable des dels dumps locals — que viuen al mateix disc.
3. **PII sense xifrar**: dumps al disc i dins d'imatges Hetzner, en clar.
4. La retenció monthly de 365 dies dels dumps **no està coordinada amb
   `retention.md`** pel que fa a PII (un usuari esborrat persisteix fins
   a 12 mesos als dumps — no documentat com a decisió RGPD).

## 5. Disc

```
/dev/sda1   38G   29G   7.0G   81%   /
```

**7,0 GB lliures.** Condiciona poc: no cal staging per a la capa 2
(restic llegeix els dumps ja existents i les portades in-place; no
duplica res al disc). Sí que desaconsella estratègies tipus "tar
temporal complet" (~1 GB extra evitable). El creixement de la imatge
Hetzner (14,0→15,2 GB en 7 dies) és soroll de renders/logs, no tendència
de la BD.

## 6. Conclusió de mesures

- Payload capa 2 mínim: **~31 MB/dia** (dump + .env + data/).
- Payload recomanat: **+868 MB de portades** (una vegada; deltes petites).
- Amb dedup de restic i retenció d'un any: dipòsit total estimat
  **2-4 GB** el primer any (dumps canvien ~3-5 MB/mes de contingut nou;
  restic no dedueix bé gzip -9, per això el disseny proposa dumpar en
  format custom o sense comprimir — vegeu doc de disseny §3).
- Qualsevol dels dos destins considerats costa cèntims o pocs euros al
  mes a aquesta escala (detall al doc de disseny §6).
