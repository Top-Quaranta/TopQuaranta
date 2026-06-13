# Disc prod al 90% — desglossament + proposta de neteja (2026-06-12)

> **NOMÉS-LECTURA. No s'ha esborrat RES.** La decisió és de Miquel.
> Disc: `/dev/sda1` 38G, **32G usats, 3.9G lliures (90%)**.

## On va l'espai (els grans)

| Mida | Camí | Què és | Reclamable? |
|---|---|---|---|
| **3.8G** | `/var/log/journal` | journal de systemd (**sense límit de mida**) | ✅ molt (vacuum) |
| 1.8G | `/home/topquaranta/app/.venv` | virtualenv Python | ⚠️ recreable (deploy) |
| 479M | `/home/topquaranta/backups` | backups daily/weekly/monthly | ⚠️ política de retenció |
| 382M | `/var/lib/postgresql` | la BD | ❌ (és la BD) |
| **267M** | `/var/cache/topquaranta/social/renders` | PNG/JPEG socials (512 fitxers) | ✅ es regeneren sols |
| **245M** | `/home/topquaranta/app/temp/geodata` | GeoJSON font del mapa | ✅ ja preprocessat a `web-react/public/geodata/` |
| 217M | `app/web-react/node_modules` | deps del build SPA | ✅ recreable (`npm ci`) |
| **74M** | `app/scripts/model_comparison` | artefactes de comparació ML | ✅ probable (anàlisi puntual) |
| ~12M | `/var/log/*.gz` (syslog/auth rotats) | logs rotats antics | ✅ |
| 22M | `/var/log/topquaranta` | logs propis (ja amb logrotate) | — (ja gestionat) |

La resta de `app/` (social 21M, music 7M, web 6M…) és codi — no toquem.

## Proposta de neteja (mides estimades, ORDENADA per benefici/risc)

### A. `/var/log/journal` — **~3.6G** · risc BAIX, el gros del problema
El journal creix sense límit. Capar-lo i fer vacuum:
```
sudo journalctl --vacuum-size=200M      # allibera ~3.6G ara
# permanent: a /etc/systemd/journald.conf → SystemMaxUse=200M ; systemctl restart systemd-journald
```
**Sol açò ja trau el disc del vermell** (de 90% a ~80%).

### B. `app/temp/geodata` — **~245M** · risc BAIX
És la font GeoJSON; el mapa serveix els preprocessats de `web-react/public/geodata/`. `app/temp/` és scratch (no al repo). Verificar que el preprocessat existeix i moure'l fora de prod / esborrar.

### C. `/var/cache/topquaranta/social/renders` — **~250M** · risc BAIX
512 fitxers de renders socials; es regeneren al pròxim cron. El logrotate ja poda PNG >60d, però els JPEG i l'acumulació recent queden. Es pot buidar el que tinga >14-30 dies sense perdre res reproduïble. *(Nota: aquest PR del TOP family en generarà de nous; bon moment per netejar els antics del disseny vell.)*

### D. `app/scripts/model_comparison` — **~74M** · risc BAIX-MITJÀ
Artefactes d'una comparació de models ML puntual. Si l'anàlisi ja està feta, arxivar fora de prod.

### E. `node_modules` (217M) i `.venv` (1.8G) — risc MITJÀ
Recreables (`npm ci` / recrear venv al deploy), però **NO** els tocaria en calent: el `tq-deploy` els necessita i recrear-los a mà pot trencar el servei. Només si cal espai d'emergència i amb el servei aturat.

### F. Backups (479M) — decisió de retenció
No els toque jo; revisar la política a `docs/ops/retention.md` si vols reduir.

## Recomanació
Fes **A** ja (treu ~3.6G, baixa a ~80%, risc baix) i de passada **B+C+D** (~570M més). Amb A sol n'hi ha prou per a eixir de l'alerta. **Cap esborrat fet — espere la teua decisió.**

---

# EXECUTAT (2026-06-12) — neteja autoritzada acció per acció

**Disc: 90% → 79%** · lliures **3.8G → 7.7G** (~3.9G reclamats). Smoke verd
(/, /api/v1/top, /api/v1/stats, /mapa = 200). Tree de prod net, HEAD == origin/main.
Cap BD, backup ni config tocats fora del cap del journal.

| # | Acció | Abans | Després | Reclamat | Notes |
|---|---|---|---|---|---|
| 1 | `journalctl --vacuum-size=200M` | 3.9G | ~313M | **~3.5G** | sudo NOPASSWD OK |
| 2 | Cap permanent `SystemMaxUse=200M` | (sense límit) | drop-in actiu | — | `/etc/systemd/journald.conf.d/00-maxuse.conf` + `systemctl restart systemd-journald` |
| 3 | `app/temp/geodata` | 245M | esborrat | **245M** | gitignored (`temp/`), només el llig el build `scripts/simplify_geodata.py`; el servit (`web-react/public/geodata/`, 17 fitxers) intacte |
| 4 | Renders socials >28d | 269M | 143M | **~126M** | esborrats 215 fitxers >4 setmanes; **304 conservats** (últimes 4 setmanes). `SocialPost` no té camp de path local (només `instagram_media_id`); es regeneren al publicar |
| 5 | `scripts/model_comparison` | 74M | 88K (font) | **~74M** | ⚠️ el dir és **git-tracked**: esborrar-lo sencer dirtia el tree (alerta de drift) i el deploy el restauraria. He **restaurat** la font tracked (14 fitxers, ownership tornada a `topquaranta`); el que s'ha alliberat són els **artefactes untracked** (~74M de clips d'àudio, gitignorats → no tornen al deploy). |

## Verificació post-neteja
- `df -h /`: **38G, 29G usats, 7.7G lliures, 79%**.
- Tree de prod **net**, `HEAD == origin/main` (`de411af`) — cap drift.
- Smoke només-lectura: web `/` 200, `/api/v1/top` 200, `/api/v1/stats` 200, `/mapa` 200.
- **Cron de demà (dissabte) no depèn de res esborrat:** el top es renderitza de nou cada cop (paths deterministes, sense dependència de renders antics); el `/mapa` serveix `web-react/public/geodata/` (intacte); el journal queda capat a 200M.

## Pendent (NO fet — decisió de Miquel)
- Si vols treure també la **font tracked** de `scripts/model_comparison` del repo (els 14 fitxers, 88K), és un **PR amb `git rm`**, no un esborrat al servidor (perquè és tracked). Avisa'm i el munto.
