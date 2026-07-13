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
