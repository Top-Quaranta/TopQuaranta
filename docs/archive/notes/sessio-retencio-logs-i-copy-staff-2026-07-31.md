# Sessió 2026-07-31 — retenció de logs de Caddy, còpia del panell staff, recon de /root

Notes locals. No committades. Detall complet; al xat només va el resum curt.

Context previ de la mateixa jornada: PR #350 (endurir el check `Web SPA shell`
de `tq-health`) i PR #351 (fer que `generar_goaccess` llija els segments
rotats). Aquesta sessió tanca els dos caps solts que van quedar.

---

## FEINA 1 — retenció de logs de Caddy · PR #352 · `1bc89b3`

### Canvi

`deploy/Caddyfile`, **només** el bloc `log` del vhost de TopQuaranta:

```
roll_size 10MiB
roll_keep 30        (era 5)
roll_keep_for 90d   (nou)
```

El vhost de cercol i tota la resta de blocs, intactes. El diff són 10 línies
afegides i 1 llevada, totes dins d'aquest bloc.

`--days` del cron: **NO tocat**, es queda a 30, com em vas demanar.

### Per què

Un sweep de ClaudeBot el 2026-07-30 (21:58 → 00:09) va cremar un segment
sencer de 10 MiB en 2 h 11. Amb `roll_keep 5` això va deixar
`generar_goaccess` amb 1 h 32 min d'història per a informar, sobre una
etiqueta de «últims 30 dies».

### Les dues xifres que no s'han de barrejar

Aquest és el punt que em vas demanar que quedara explícit als docs. Caddy
gzipa un segment rotat i el factor és gros:

| Fitxer | gzipat | descomprimit | ratio |
|---|---|---|---|
| `…2026-07-28T14-32-51.275.log.gz` | 695 KiB | 10,00 MiB | 14,7× |
| `…2026-07-29T03-46-02.809.log.gz` | 682 KiB | 10,00 MiB | 15,0× |
| `…2026-07-29T16-42-15.969.log.gz` | 637 KiB | 10,00 MiB | 16,1× |
| `…2026-07-30T21-58-19.500.log.gz` | 715 KiB | 10,00 MiB | 14,3× |
| `…2026-07-31T00-09-14.267.log.gz` | 468 KiB | 10,00 MiB | 21,9× |
| **mitjana** | **639 KiB** | 10 MiB | **~15×** |

Per tant, amb `roll_keep 30`:

- **Al disc (gzipat):** ~19 MiB + fins a 10 MiB del fitxer viu = **<30 MiB**.
  Contra 5,3 GB lliures, irrellevant.
- **Llegit (descomprimit):** ~300 MiB. Aquesta és la que fixa fins on pot
  veure l'informe, i **no** és la factura del disc.

El primer esborrany d'`analytics-goaccess.md` (que vaig escriure jo ahir)
deia «~60 MiB al disc». Estava malament en un ordre de magnitud: havia
multiplicat els 10 MiB descomprimits per 5 i ho havia cridat disc. Corregit
als dos docs, amb la taula que separa les dues columnes.

### Cobertura resultant

Com que la rotació és per mida, els dies depenen del tràfic:

- ~34 dies al ritme base mesurat (0,37 MiB/h).
- ~2,7 dies sota un sweep de crawler sostingut (4,59 MiB/h).
- `roll_keep_for 90d` tapa l'altre extrem perquè una temporada tranquil·la
  no acumule segments indefinidament.

### Docs tocats

- `docs/architecture/analytics-goaccess.md` — el paràgraf de retenció
  reescrit amb la taula disc/cobertura, i la nota que el `--days` del cron
  és deliberadament independent (la finestra que **demanem** vs la que el
  disc pot **subministrar**).
- `docs/ops/infra.md` — secció nova «Access log retention». Cal perquè
  `deploy/` mapeja a aquest doc al gate dur `docs-coherence`.

### Verificació a prod

`caddy validate` a CI: `Valid configuration`. Després del deploy, al box:

```
=== retenció instal·lada a /etc/caddy/Caddyfile ===
235:		output file /var/log/caddy/topquaranta_access.log {
236-			roll_size 10MiB
237-			roll_keep 30
238-			roll_keep_for 90d

=== coincideix amb el repo? ===
IDÈNTICS

=== Caddy ===
NRestarts=0
ActiveState=active
SubState=running
ActiveEnterTimestamp=Thu 2026-07-02 13:56:13 UTC

=== la config VIVA (admin API :2019, no el fitxer) ===
  log log0 -> /var/log/caddy/topquaranta_access.log
    roll_size_mb=10 roll_keep=30 roll_keep_days=90

=== errors recents ===
-- No entries --
```

Punt important: vaig comprovar la config **viva** per l'API d'admin, no
només el fitxer al disc. `ActiveEnterTimestamp` sense moure's del 2 de
juliol confirma que va ser un reload en calent, no un restart, i
`NRestarts` continua a 0.

---

## FEINA 2 — còpia del panell staff · PR #353

`web-react/src/pages/staff/StaffAnalyticsPage.jsx:785`, només aquest
paràgraf. Res més del fitxer.

**Abans:** «GoAccess processa `/var/log/caddy/topquaranta_access.log` i
mostra el que Django no veu…»

**Després:** «GoAccess processa el registre d'accés viu de Caddy
`topquaranta_access.log` i tots els seus segments rotats `.log.gz`, i mostra
el que Django no veu (assets estàtics, errors 404, distribució geogràfica,
bots…). L'informe indica a dalt l'interval realment cobert, que pot ser més
curt que els 30 dies demanats si la rotació ha menjat la cua. El fitxer es
serveix només a través d'aquest endpoint amb sessió staff + 2FA — no és
accessible públicament.»

Còpia i prou: cap canvi de comportament, dades ni endpoint.

`docs/architecture/frontend.md` rep la línia mínima que demana el gate.

Mergejat com a `75ae63c`. El PR va quedar bloquejat un moment perquè la
protecció de `main` té `strict: true` i la branca havia quedat darrere del
merge de la feina 1; resolt amb `gh pr update-branch` i una segona passada
de CI, també 12/12.

### Sobre la captura

`goaccess-card-2026-07-31.png`, al costat d'aquest fitxer.

**És un render local del component, no una captura del panell viu.** Ho
etiquete a la pròpia imatge. El motiu: `/staff/analitiques` està darrere
d'`AdminRoute` amb sessió staff + 2FA, i jo no puc iniciar sessió. El que
sí que és real: el marcatge i les classes són els del component tal com
queda al fitxer, i el CSS és el `index-Cmw8JJjD.css` que ix del build de
producció, no un full inventat. O siga que tipografia, espaiat i colors
són els de veres; el que no hi ha és la resta de la pàgina al voltant.

Si vols la captura del panell autèntic, obri
`/staff/analitiques` amb la teua sessió i la faig jo o la fas tu.

### Trampa del gate que val la pena recordar

`scripts/check_docs_coherence.py` llig la llista de fitxers canviats de
**stdin**, no d'un `--base`. Durant tota la jornada l'havia estat invocant
com `python scripts/check_docs_coherence.py --base main`, i sempre deia «No
subsystem/doc coupling triggers detected» — perquè stdin estava buit, no
perquè no hi haguera res. Un fals verd silenciós.

La manera correcta, la mateixa que fa CI:

```bash
git diff --name-only main | .venv/bin/python scripts/check_docs_coherence.py
```

Amb això confirmat, la feina 2 **sí** que demanava `frontend.md`. Els PRs
anteriors (#350, #351, #352) van passar el gate a CI de veres perquè
tocaven els docs mapejats igualment; el meu check local era el que no valia
res. Cap conseqüència, però convé no repetir-ho.

---

## FEINA 3 — recon de disc, només lectura

Res esborrat, res mogut. Només inventari.

```
=== df -h ===
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        38G   31G  5.3G  86% /
```

```
=== /root, primer nivell, ordenat ===
4.5G	/root/.vscode-server
844M	/root/.claude
416M	/root/TopQuaranta_dev
390M	/root/venv_topq_backup
258M	/root/.nvm
179M	/root/.npm
169M	/root/outreach
114M	/root/.cache
107M	/root/topquaranta_db_backup_20260409.sql
40M	/root/.duckdb
26M	/root/llotja-backups
12M	/root/logs_topq_backup
2.4M	/root/.launchpadlib
788K	/root/ultima_documentacio.md
272K	/root/.dotnet
164K	/root/backups
88K	/root/.bash_history
64K	/root/snap
52K	/root/CLAUDE.md
52K	/root/.claude.json
28K	/root/.config
20K	/root/.local
20K	/root/Claude
16K	/root/.ssh
12K	/root/tq-deploy.bak-20260727T111821Z

=== total ===
7.0G	/root
```

`/root` és 7,0 G dels 31 G ocupats: **el 23 % del disc usat viu al home de
root**, no a l'aplicació.

Domina `.vscode-server` amb 4,5 G. Segon i tercer nivell:

```
=== /root/.vscode-server ===
3.6G	/root/.vscode-server/cli
516M	/root/.vscode-server/extensions
207M	/root/.vscode-server/data
32M	/root/.vscode-server/code-7e7950df89d055b5a378379db9ee14290772148a
32M	/root/.vscode-server/code-4fe60c8b1cdac1c4c174f2fb180d0d758272d713
31M	/root/.vscode-server/code-8761a5560cfd65fdd19ce7e2bd18dab5c0a4d84e
31M	/root/.vscode-server/code-6928394f91b684055b873eecb8bc281365131f1c
31M	/root/.vscode-server/code-1b50d58d73426c9171299ec4037d01365d995b78

=== tercer nivell ===
3.6G	/root/.vscode-server/cli/servers
259M	/root/.vscode-server/extensions/anthropic.claude-code-2.1.210-linux-x64
257M	/root/.vscode-server/extensions/anthropic.claude-code-2.1.207-linux-x64
183M	/root/.vscode-server/data/CachedExtensionVSIXs
23M	/root/.vscode-server/data/User
1.3M	/root/.vscode-server/extensions/batisteo.vscode-django-1.15.0
```

### Lectura, sense tocar res

El que hi ha, descrit i prou. La decisió és teua:

- **`/root/.vscode-server/cli/servers` — 3,6 G.** Un servidor VS Code Remote
  per commit-hash al qual t'has connectat mai. Cinc directoris `code-<sha>`
  més al primer nivell, ~31 M cadascun, són la mateixa acumulació.
- **`extensions` — 516 M**, dels quals 516 M són **dues còpies de
  l'extensió de Claude Code** (2.1.210 i 2.1.207, 259 M + 257 M). La versió
  vella hi és des de l'actualització.
- **`data/CachedExtensionVSIXs` — 183 M.** Caché d'instal·ladors.
- **`/root/venv_topq_backup` — 390 M** i **`/root/TopQuaranta_dev` — 416 M**:
  còpies velles d'abans que el desplegament anara per GHA.
- **`/root/topquaranta_db_backup_20260409.sql` — 107 M**, un dump solt
  d'abril, fora del sistema de `tq-backup`.
- **`/root/.claude` — 844 M**: històric de sessions.

Ordre de magnitud si algun dia decideixes netejar: `.vscode-server` sol
alliberaria ~4 G, o siga passar del 86 % al ~75 %. No he tocat res.

---

## Estat final

- `main == prod`, arbre net.
- `tq-health`: tot verd.
- Disc: 5,3 G lliures, molt per damunt del límit de 3 G que vas posar.
- Caddy: reload en calent, `NRestarts=0`, retenció nova activa a la config viva.
