# CLAUDE_EXCELLENCE.md — Auditoria integral cap a l'obra eterna

> **Document històric (2026-04-26)**. La fase d'Excellence (Phase 9)
> està tancada — totes les troballes Tier 1 i Tier 2, i la majoria de
> Tier 3 i 4, van baixar als sprints A–J ter del `ROADMAP.md`. Es
> manté aquest document com a referència del marc d'avaluació
> original (severitats, tiers, taxonomia S*/R*/P*) que va guiar la
> fase. Per a l'estat de cada troballa concreta, vegeu el ROADMAP o
> el `git log`.
>
> Audit sense pietat cap a l'excel·lència. Data original: 2026-04-16.
>
> El sistema actual *funciona correctament*. Aquest document no tracta d'això.
> Tracta de la distància entre "correcte" i "indistingible de la perfecció".
> És un inventari honest de tot el que encara no ho és.
>
> Aquest fitxer és la guia estratègica de la **Fase 9 — Excellence** del
> ROADMAP. Cada troballa té una identificació estable (S1, R1, P1, …)
> perquè es pugui referenciar en commits i issues.

## Progrés de la Phase 9

**Sessió 1 — Tier 1 Foundations, security hardening (2026-04-16)** ✅

| ID | Estat | Commit |
|---|---|---|
| **S1** Rotar contrasenya PostgreSQL | ✅ | `48a617f` |
| **S2** PAT GitHub → SSH deploy key | ✅ | (ops; `.git/config` net, PAT revocat) |
| **S3** Rotar `DJANGO_SECRET_KEY` | ✅ | `48a617f` |
| **S4** `django-axes` (brute-force protection) | ✅ | `96ec17b` |
| **S5** Anti-enumeració al registre | ✅ | `dcb41b0` |
| **S6** CSP estricta + X-Frame-Options + nosniff | ✅ | `f8693c0` |
| **S7** `json_script` a `/mapa/` (XSS-safe) | ✅ | `57a225c` |
| **S8** URL scheme allowlist (`http`/`https`) a `PropostaArtista` | ✅ | `d85e226` |
| **S10** Argon2 password hashing | ✅ | `96ec17b` |
| **S13** Templates 404 / 500 / 403 amb branding | ✅ | `47fc449` |
| **R8** Min/Max validators a `ConfiguracioGlobal` | ✅ | `b33197a` (+ `e0cf68b` Decimal-str fix) |

**Sessió 2 — Tier 2 Reliability + rate limiting (2026-04-16)** ✅

| ID | Estat | Commit |
|---|---|---|
| **S9** Rate limit `/api/v1/*` (60/min anon, 300/min user, DB-cache) | ✅ | `5247bad` |
| **R1** `algorithm_version` + `config_snapshot` a `RankingSetmanal` | ✅ | `12a8a41` |
| **R2** `CASCADE` → `SET_NULL` + name snapshots per preservar història | ✅ | `12a8a41` |

**Sessió 3 — Staff audit log (2026-04-16)** ✅

| ID | Estat | Commit |
|---|---|---|
| **R9** `StaffAuditLog` model + helper + integració cross-views + `/staff/auditlog/` | ✅ | 3 commits (model, integració, UI) |

**Sessió 4 — Staff 2FA (2026-04-16)** ✅

| ID | Estat | Commit |
|---|---|---|
| **S11** TOTP 2FA (django-otp) + backup codes + enrollment/challenge/mgmt UI + `reset_2fa` admin command | ✅ | 3 commits (deps, views, enforcement) |

Tancament associat: `root` staff user (sense 2FA enrollat) desactivat amb
`is_staff=False`. Queda només el compte `admin` amb 2FA confirmat + 10
backup codes. La IP allowlist queda fora d'aquesta sessió — additiva, a
fer quan es decideixi.

**Sessió 5 — Gestió d'usuaris al staff (2026-04-16)** ✅ (no-ID, follow-up UX)

Nova secció `/staff/usuaris/` amb llista + detall + 2 mutacions segures
(toggle is_active sobre no-staff no-self; reset 2FA). `is_staff` queda
intencionadament fora del panell — requereix SSH. Totes les mutacions
van a `StaffAuditLog` via `log_staff_action`. Afegides 3 noves choices
(`usuari_desactivar`, `usuari_reactivar`, `usuari_reset_2fa`).

**Sessió 6 — Last.fm autocorrect drift (2026-04-16)** ✅

| ID | Estat | Commit |
|---|---|---|
| **R5** Drift detection: client retorna noms Last.fm, SenyalDiari captura i compara fuzzy (artist 0.90, track 0.80 amb normalització de variants), filtre + "acceptar correcció" a `/staff/senyal/` | ✅ | 4 commits |

**Sessió 7 — Transparència algorítmica pública (2026-04-16)** ✅

| ID | Estat | Commit |
|---|---|---|
| **Φ4** `/com-funciona/` editorial + live coefficients + reproducibility note | ✅ | `26e55e2` |
| **Φ4** `/com-funciona/historial/` anonimitzat (de StaffAuditLog) | ✅ | `21076ad` |
| **Φ4** Footer + ranking CTA links | ✅ | `fa2474d` |
| **Φ4b** Portal artista exposa `score_setmanal` + `dies_en_top` + link a com-funciona; fix latent `canco.titol` → `canco.nom` | ✅ | `0c8501e` |

Les línies R1 (reproduïbilitat) i R9 (audit log) finalment es fan visibles
al públic: qualsevol usuari ara pot veure com es calcula el top i cada canvi
dels coeficients queda exposat (anonimitzat) en ordre cronològic invers.

**Sessió 8 — Doble font de veritat eliminada + cron retry (2026-04-16)** ✅

| ID | Estat | Commit |
|---|---|---|
| **R10** Drop `Artista.deezer_id` — `ArtistaDeezer` és la única font | ✅ | `fdc649a` |
| **R11** Drop `Artista.localitat`/`comarca`/`provincia` — `ArtistaLocalitat` és la única font | ✅ | `759bb87` |
| **R10b** Regressió: 3 commands ingest oblidaven `deezer_id=` als `Artista.objects.create()` | ✅ | `f1bf5f5` |
| **R7** Retry intern a `tq-run` (3 intents, backoff 60s/300s) + `tq-recover` cron horari | ✅ | `835d6ac` |

Pre-flight audit per a R10: 3.794 artistes amb camp directe, 3.795 files a
`ArtistaDeezer`, 0 orfes. Pre-flight per a R11: 2.288 artistes aprovats,
tots tenien ja almenys una `ArtistaLocalitat`. Les dades ja eren
consistents — només calia eliminar la possibilitat física de divergència.

R10b: tres commands d'ingest (`obtenir_novetats`, `obtenir_metadata`,
`fix_artista_principal`) creaven Artistes amb `deezer_id=...` directe;
detectat quan tq-run va capturar el primer FAIL real (`TypeError:
Artista() got unexpected keyword arguments: 'deezer_id'`). Substituït per
crear l'`Artista` sol i un `ArtistaDeezer.get_or_create(...)` darrere.

R7 implementat com a defensa-en-profunditat de dos nivells:
1. `tq-run` retry per intent. Per defecte 3 intents amb sleep 60s i 300s.
   Excepció: `obtenir_novetats` (hourly, 1 intent — el següent tick ja és
   el retry natural). Status file ara inclou `attempts=` i `max_attempts=`.
2. `tq-recover` (nou): cron */30 minuts. Per a cada cron diari, si el
   status file és absent / FAIL / amb last_run anterior al cutoff d'avui,
   torna a executar via tq-run. Cap a `MAX_RECOVER_PER_DAY=5` per evitar
   tempestes en outages persistents. Comptador per dia a `<tag>.recover`.

**Sessió 9 — Closing-out fiabilitat + CI (2026-04-16)** ✅

| ID | Estat | Commit |
|---|---|---|
| **R13** Defensa templates `canco.album.X` + neteja regressions latents R10/R11 a 5 templates | ✅ | `080349b` |
| **R12** Signal `sync_territoris_from_localitats` mou-se a `transaction.on_commit()` | ✅ | `33ba957` |
| **D1** `Canco.isrc` partial unique constraint (només quan no buit) | ✅ | `b54623d` |
| **R14** `tq-restore-test` mensual: restaura el backup més recent a una DB efímera, valida row counts | ✅ | `b641343` |
| **O9** logrotate weekly per a `/var/log/topquaranta/*.log` | ✅ | `fee0472` |
| **style** Baseline `black` + `isort` (100 fitxers) + `pyproject.toml` | ✅ | `f810c42` |
| **O3** GitHub Actions CI: pytest + lint + missing-migration check | ✅ | `e0175df` |

Audit pre-flight per a D1: 10.353 Cancons amb ISRC no buit, **0 duplicats**.
Constraint aplicat sense backfill. Auditoria de templates per a R13 va
trobar 5 regressions latents R10/R11 (links Deezer que no renderitzaven
silenciosament perquè `{% if artista.deezer_id %}` retornava falsy
després que el camp fos esborrat); fixades en el mateix commit.

R14 verificat amb el dump de fa unes hores: artistes=4231/4239,
cancons=19937/19961 — drift dins de la tolerància del 5%.

O3 (CI): tres jobs paral·lels (tests, lint, missing-migrations check).
Tests usen settings.test (SQLite in-memory) — no calen credencials ni
servei Postgres a CI. El primer push amb el workflow ha de passar net
gràcies al baseline d'estil del commit anterior.

Phase 9 ja té **27 troballes resoltes** en 9 sessions. Tier 1 (security)
i Tier 2 (reliability) completes; Ops avançat (R14, O3, O9 fets, queden
O1/O2/O4-O7/O8). Tier 3 (Architecture), Tier 4 (Culture), Tier 5
(Exquisitesa) per a sessions futures.

**Sessió 10 — Pack performance sense canviar res (2026-04-17)** ✅

| ID | Estat | Commit |
|---|---|---|
| **P6** `CONN_MAX_AGE=600` + `CONN_HEALTH_CHECKS=True` a production.py | ✅ | `36d7579` |
| **P3** Composite indexes `(artista_nom, decisio)` + `(isrc_prefix, decisio)` a `HistorialRevisio` | ✅ | `e7925a7` |
| **P4** `obtenir_senyal` canvia `update_or_create` per `bulk_create(ignore_conflicts=True)` en batches de 200 | ✅ | `26f75a7` |
| **P8** `@last_modified` + `@etag` a `homepage` i `ranking_page` — 304 per a clients revalidant | ✅ | `0d2e200` |

Efecte combinat: rendiment millor sense tocar lògica ni UI.
- P6: elimina ~5 ms/request de DB handshake.
- P3: queries de ML passen a 2.2 ms per full table scan sobre 1.5k
  rows — a 100k decisions el benefici serà ordres de magnitud.
- P4: ~2400 roundtrips per run de `obtenir_senyal` passen a ~6 bulk
  inserts.
- P8: revalidacions client (setmanal / diari) retornen 304 Not
  Modified sense re-renderitzar templates ni re-fetchar rows.
  Verificat amb curl end-to-end.

**Sessió 11 — Pack "ho fem tot" (2026-04-17)** ✅

| ID | Estat | Commit |
|---|---|---|
| **P2** Cache del classificador RF + TF-IDF amb invalidació per mtime | ✅ | `761d51e` |
| **D5** Prevenir self-collab: migració de neteja (7 files) + `m2m_changed` guard | ✅ | `613572c` |
| **D2** Esborrar camps dead `lastfm_mbid` i `lastfm_verificat` | ✅ | `9446f89` |
| **F3+F5** SEO: meta description, OG, Twitter Cards, sitemap.xml, robots.txt + og-default.png; timestamp "Actualitzat el ..." a les pàgines de ranking | ✅ | `f14a3e8` |
| **A10** Vendor mm-design a `vendor/mm-design/` (ja no depenem de npm per a la UI) | ✅ | `d37fcd2` |
| **A8** Política de versionat d'API (`VERSIONING.md`) + middleware `X-API-Version` | ✅ | `4c8295a` |
| **O5** Verificació + documentació de la política de claus SSH | ✅ | `76adfa9` |
| **O8** `RUNBOOK.md` — playbook per a 8 incidents operacionals | ✅ | `521f19a` |
| **C1** `.pre-commit-config.yaml` — mirror de la CI local | ✅ | `99bc2dc` |

Deu troballes en una sola sessió. Sense regressions (59 tests passen
després de cada commit). Smoke tests reals:
- P2 benchmark: 22 ms per classificació (era 22 + 30 ms de joblib.load).
- D5 audit: 7 self-collabs existents netejats; guard rebutja nous amb
  ValidationError.
- F3: `/robots.txt` servit, `/sitemap.xml` amb ~4k entries i protocol
  https, 15 meta tags al head del homepage (OG + Twitter + canonical).
- A10: `/static/mm-design/tokens/colors.css` 200 via Caddy des de
  `vendor/mm-design/`.
- A8: GET `/api/v1/localitzacio/territoris/` retorna `X-API-Version: 1`.
- O5: `grep -E 'ghp_|://.+:.+@github' ~/.git/config ~/app/.git/config
  ~/.netrc` → "OK: no PAT in git/netrc".

**Sessió 12 — "ho fem tot" v2: process + data + perf + filosofia (2026-04-17)** ✅

| ID | Estat | Commit |
|---|---|---|
| **C2** `.github/dependabot.yml` — updates setmanals de pip + github-actions, groupats per família | ✅ | `f201d38` |
| **C3 + C5** `CHANGELOG.md` baseline (0.9.0) + `README.md` refrescat per a contributors | ✅ | `278c3de` |
| **D3 + D4** `PropostaArtista.deezer_ids` i `localitzacions` passen a `JSONField` | ✅ | `84e530f` |
| **P1** `pagecache` LocMem + `cache_page_for_anon` — homepage / ranking serveixen a ~13 ms en cache hit sense trencar el 304 de P8 | ✅ | `449be4c` |
| **Φ5 + Φ1 + Φ7** `LICENSE-DATA.md` (CC BY 4.0), `docs/DEFINITION.md` (què compta com a música en català), `MANIFEST.md` (què farà / no farà el projecte) | ✅ | `b7564fa` |

Nou troballes en una sola sessió. Notes:
- P1 va introduir un bug subtil (cache hit no comprovava `If-None-Match`),
  detectat amb curl i arreglat al mateix commit abans de push.
- Audit pre-flight D3/D4: `PropostaArtista` té 0 files a producció —
  migració trivial.
- Els tres docs filosòfics (Φ) converteixen valors implícits en àncores
  explícites que decisions futures poden consultar. El que abans era
  coneixement del mantenidor ara és visible i auditable.

Benchmark P1: homepage cold ~386 ms, warm cache hit ~13 ms. `If-None-
Match` conditional encara retorna 304 contra la resposta cached.

**Sessió 13 — Quickwins defensius + revisió del manifest (2026-04-17)** ✅

| ID | Estat | Commit |
|---|---|---|
| **Φ7 revisió** | `MANIFEST.md` — secció "No monetization" reescrita: distingir *revenue alineada amb la missió* (anuncis culturals en català, suport institucional amb placement no position) de *revenue que corrompria la mesura* (vendre dades, vendre la llista d'usuaris, qualsevol cosa lligada a resultats del ranking) | ✅ | `694303a` |
| **D6** Índexs compostos: `RankingSetmanal(territori, setmana, posicio)` i `Canco(verificada, artista)`. Els altres dos proposats (SenyalDiari) ja tenien cobertura existent. | ✅ | `cf52345` |
| **C4** `docs/DEPRECATION.md` — com retirar camps / commands / API / features sense sorpreses. Motivada per la regressió R10b (Sessió 8). | ✅ | `b8e2de5` |
| **Φ6** `docs/RETENTION.md` + nou management command `arxivar_senyal_vell` (cron trimestral). `SenyalDiari` > 2 anys s'exporta a `senyal-YYYY.csv.gz` i s'esborra. Ranking + audit logs per sempre. | ✅ | `977beef` |

Notes:
- Manifest: el compromís de "no monetització" era meu, no del mantenidor.
  La nova versió obre la porta a publicitat alineada amb la missió
  (àlbums en català, esdeveniments culturals, patrocini institucional
  sense influència sobre el ranking) mantenint la línia dura contra
  vendre dades o comprar posició al ranking.
- D6: EXPLAIN sobre la taula actual (40 files) encara fa Seq Scan —
  PostgreSQL escull scan lineal per a taules molt petites. L'índex
  entra en acció quan la taula creix, exactament el cas d'ús futur.
- Φ6: `arxivar_senyal_vell --dry-run --retention-days 3` detectà
  correctament 6515 files per arxivar i agrupar per any. El command
  real (730 dies) no troba cap fila hui perquè la instal·lació és
  recent.

**Sessió 14 — Petites follow-ups: titlecase, regressions, signal smart (2026-04-18)** ✅

| ID | Estat | Commit |
|---|---|---|
| **titlecase v2** Normalitzar accents orfes (` ´ ' ' ʼ → '), single-letter "I"/"A"/"O" mai acrònims, majúscula després de `([{«"¿¡` | ✅ | `ee4652b`, `43a000b` |
| **titlecase a Albums** També aplicat a `Album.nom` a `_create_album` + re-run en bloc del comand `retitlecase` | ✅ | `43a000b` |
| **R10c** `try/finally` a `classificar_i_guardar` als tres sites d'ingest — garanteix ml_classe mai NULL post-persistence | ✅ | `f41d40a` |
| **Φ1 fold** DEFINITION.md: instrumentals no són regla separada — són `no_catala` per manca de delivery | ✅ | `a7b04fe` |
| **Last.fm signal smart** `"|"` stripping al retry + `artist.getTopTracks` fallback + `Artista.lastfm_te_scrobbles` flag | ✅ | `116505a` |

Efecte operacional mesurable:
- Retitlecase: 2038 Cancons + 2881 Albums actualitzats.
- `lastfm_te_scrobbles`: 424 artistes aprovats amb scrobbles confirmades
  (18.5%), 1864 silent artists.
- Errors recurrents Last.fm passen de 222 tracks sense distinció a
  131 reals (artista actiu, track no indexat) + 91 silents (artista
  sense cap scrobble, expected).
- "+ Arcade" de Adrien Broadway recuperat automàticament via fallback
  a "+ ARCADE" (pc=33, funciona real).

---

## Taula de severitat

| Nivell | Nombre trobats | Definició |
|---|---|---|
| 🔴 **CRÍTIC** | 7 | Exposició real ara mateix o pèrdua de dades garantida sota condicions normals |
| 🟠 **ALT** | 15 | Risc concret sota condicions versemblants o defecte que erosiona la confiança |
| 🟡 **MITJÀ** | 22 | Defensa-en-profunditat; deute estructural; mediocritats que s'acumulen |
| 🟢 **BAIX / FILOSÒFIC** | 18 | Polish, transparència, fidelitat al propòsit cultural |

---

# PART I · SEGURETAT (13 troballes)

## 🔴 CRÍTIC

### S1. La contrasenya de PostgreSQL és literalment `topquaranta` (el nom d'usuari)
```
DATABASE_URL=postgres://topquaranta:topquaranta@localhost:5432/topquaranta
```
Només està salvat perquè el port 5432 no és exposat externament i PostgreSQL usa peer auth des de localhost. **Però si qualsevol servei al servidor es comprometés i tingués connectivitat a localhost:5432, la DB completa està oberta.** Rotar a una contrasenya de 40 caràcters aleatoris és treball de 5 minuts. No s'ha fet.

### S2. Personal Access Token de GitHub en text pla dins del `.git/config` del servidor
```
https://miquelmatoses:ghp_***@github.com/...
```
Qualsevol que pugui executar una comanda com a `topquaranta` o `root` fa `git remote -v` i obté un PAT amb probablement scope complet `repo`. **Si aquest PAT té també scope `workflow` o `admin:org`, la cadena de compromís va més enllà del repo.** Pitjor encara: el token apareixeria a cada backup del `.git/` inclòs en snapshots del volum. Hauria de ser SSH deploy key.

### S3. Backups en text pla sense xifrar, llegibles per tothom del sistema
```
-rw-rw-r-- 1 postgres postgres 2.8M ... tq-20260416-190810.sql.gz
```
Permisos `664` (grup i others poden llegir). Sense xifratge. Sense còpia off-site. **Un robatori físic del servidor = robatori de totes les credencials hashejades, emails d'usuaris, i tota la història del ranking.** El xifratge amb `gpg --symmetric` o `age` són canvis d'1 línia.

## 🟠 ALT

### S4. Sense protecció de força bruta al login
`comptes/views.py` no usa `django-axes`, `django-ratelimit` ni cap equivalent. Un atacant pot fer 100 intents per segon a `/compte/login/` sense cap resposta defensiva. Amb 10 comptes staff coneguts, **un diccionari de 10⁶ paraules es processa en hores**.

### S5. Enumeració de comptes al registre
`comptes/forms.py:29-30` retorna missatge específic si l'email existeix:
```python
raise forms.ValidationError("Ja existeix un compte amb aquest correu.")
```
Permet mapar tot l'univers d'usuaris registrats simplement provant emails. Hauria de retornar el mateix missatge per a ambdós casos ("t'hem enviat un correu si ets nou").

### S6. Content Security Policy és gairebé inexistent
El Caddyfile només posa `Content-Security-Policy: upgrade-insecure-requests`. **No hi ha `default-src`, `script-src`, `style-src`.** Cap límit d'orígens. El mapa carrega D3 des de `cdnjs.cloudflare.com` amb SRI (bé), però la resta del JS pot venir d'on vulgui en un escenari d'injecció. Una XSS reflectida (qualsevol) seria executable sense restriccions.

### S7. XSS latent al mapa via `|safe` aplicat a `artistes_json`
`web/templates/web/mapa.html:28-29`:
```html
var comData = {{ comarques_json|safe }};
var munData = {{ municipis_json|safe }};
```
El JSON conté noms d'artistes que venen de `PropostaArtista.nom` (camp lliure d'usuaris). Si un usuari proposa un artista amb nom `<img src=x onerror=alert(document.cookie)>` i un staff el aprova, **tothom que visita el mapa executa aquell JS**. Django no escapa automàticament el contingut de `|safe`. S'hauria de validar `nom` a `PropostaArtista.clean()` i/o usar `json_script` de Django enlloc de `|safe`.

### S8. Enllaços socials a `PropostaArtista` sense validar ni escapar correctament
Els camps `spotify_url`, `bandcamp_url`, etc. són `URLField`, cosa que dona validació de format però **no valida l'esquema**. Un atacant pot proposar una URL `javascript:alert(1)` si l'`URLField` accepta esquemes arbitraris. A Django 5.2 l'`URLField` per defecte accepta `http`, `https`, `ftp`, `ftps` — però *no* `javascript:`, així que probablement segur. Però no s'ha verificat explícitament a `SOCIAL_LINK_FIELDS`.

### S9. Cap límit de rate a cap API endpoint
`/api/v1/mapa/artistes/` retorna ~4.000 artistes + ~1.800 municipis en cada crida. Un atacant pot fer 100 crides/segon i saturar la DB. **No hi ha `@api_view` amb throttle a cap lloc.** DRF té `DEFAULT_THROTTLE_CLASSES` i no s'ha configurat.

### S10. Hashing de contrasenyes és PBKDF2 per defecte, no Argon2
Django 5.2 suporta Argon2 si s'instal·la `argon2-cffi` i s'afegeix a `PASSWORD_HASHERS`. PBKDF2 (~260k iterations) resisteix brute-force però és 10x més feble que Argon2id contra GPUs. Quan la DB es filtri, això compta.

### S11. Sense 2FA ni IP allowlist per al panel staff
`@staff_required` només comprova `is_staff=True`. **Un password staff filtrat = accés complet al panel**: aprovar artistes fake, modificar coeficients de ranking, editar cançons individuals. No hi ha `django-otp` ni verificació per email per a sessions noves ni whitelist d'IP. Un sol usuari = un sol punt de compromís.

## 🟡 MITJÀ

### S12. `auth_user_user_permissions` i `auth_group_permissions` actius però no usats
Django té el framework de permisos complet, però `staff_required` no mira permisos — només el flag `is_staff`. Hi ha una superfície semàntica sense cap ús real. Desaprofita el potencial de Django.

### S13. Error pages poden filtrar informació
`DEBUG=False` a producció ✅. Però no s'ha definit un `handler500`, `handler404`, `handler403` personalitzats — Django usa les pàgines per defecte que poden filtrar el valor d'`ALLOWED_HOSTS` o altres informacions si es malconfiguren. Caldria templates 404/500 propis.

---

# PART II · FIABILITAT I INTEGRITAT DE DADES (14 troballes)

## 🔴 CRÍTIC

### R1. `ranking_diari` es regenera cada setmana *amb la configuració actual*, no la d'aleshores
`RankingSetmanal` no té `algorithm_version` ni `config_snapshot`. Si un staff canvia `penalitzacio_descens` de 0.025 a 0.075 avui, **demà pots executar `calcular_ranking --setmana 2026-03-01` i obtindràs un resultat diferent del que es va publicar el 2026-03-01**. Els rànquings històrics són no-reproduïbles: no hi ha una veritat única. Aquest és un pecat mortal per un sistema que pretén ser arxiu cultural.

### R2. CASCADE delete d'un `Artista` esborra tot el seu historial de rànquing
`RankingSetmanal.canco` → `Canco.album` → `Album.artista` — totes amb `on_delete=CASCADE`. Si un staff esborra un `Artista` duplicat: **tots els seus rànquings setmanals històrics desapareixen**. L'URL pública a un rànquing antic retorna posició inexistent. **Això reescriu la història.** Hauria de ser `SET_NULL` o soft-delete (`actiu=False`).

## 🟠 ALT

### R3. Recalc ML en un thread sense aïllament transaccional
`music/ml.py:471` fa `threading.Thread(target=recalcular_ml, daemon=True).start()` des de `recalcular_ml_si_cal()` cridat dins de vistes. **El thread comparteix la connexió DB del procés gunicorn, però Django's thread-local state no està pensat per a això.** Si la vista que crida encara té una transacció oberta, el thread pot llegir estat no comitit o produir `DatabaseError: in transaction, commands are ignored`. Hauria de ser una cua de feines (Celery / RQ) o, mínim, `transaction.on_commit()`.

### R4. `obtenir_senyal` → `normalize_score_entrada` no és tot dins una transacció
Si `obtenir_senyal` crashea entre els inserts de `SenyalDiari` i el càlcul de `score_entrada`, tens files amb `score_entrada=NULL`. `actualitzar_score_entrada` ho cobreix, però només si després es torna a executar. Si no, queden files que no entren al rànquing. **No hi ha monitor per detectar aquest estat.**

### R5. Errors de Last.fm amb `autocorrect=1` produeixen deriva silenciosa
Last.fm canvia el nom de track / artista silenciosament. Nosaltres guardem el `playcount` retornat independentment de si el track correspon a la nostra cançó. **Per tracks amb noms comuns, estem acumulant playcounts de cançons diferents durant setmanes sense saber-ho.** No hi ha verificació de `data['track']['name'] == our_name`. Caldria almenys marcar els casos on Last.fm ha corregit i que un humà ho revisi.

### R6. PPCC es calcula per 5× el treball
`calcular_ppcc_ranking` crida `calcular_ranking_territori(t)` per a cada territori font (CAT, VAL, BAL, ALT, + opcionals). **Cada crida executa les 14 CTEs completes.** A 1000ms per CTE run, PPCC triga 5 segons. La solució correcta és calcular un cop per territori i agregar en memòria o en una CTE final addicional.

### R7. Sense retry a nivell de cron ✅ resolt (Sessió 8)
Si `obtenir_senyal` de dimarts falla (Last.fm caigut 10 min), **no s'executa de nou avui**. `actualitzar_score_entrada` pot omplir el buit només si hi ha `SenyalDiari` rows a backfillejar, però si no s'han inserit mai, quedem amb un dia sense ranking signal. El `score_entrada` per al dia és `NULL`, i el rànquing provisional de l'endemà inclou dades incompletes. **Caldria un mecanisme de detecció de "missing days" amb re-run automàtic.**
> **Resolució:** dos nivells. (1) `tq-run` retry intern: 3 intents amb backoff 60s/300s per a comandes diàries; 1 intent per a `obtenir_novetats` (que ja és horari). (2) Nou `tq-recover` (cron */30 min) que detecta status absent / FAIL / last_run anterior al cutoff diari i rellança via tq-run. Cap a 5 recoveries per dia per comanda per evitar tempestes en outages persistents.

### R8. `ConfiguracioGlobal` és editable en viu sense validació de rangs
A `/staff/configuracio/` un staff pot escriure `-999.99` a `penalitzacio_descens`. **No hi ha `MinValueValidator`, `MaxValueValidator`, ni tipus de dades que impedeixin valors absurds.** Un error tipogràfic (`0.25` → `25`) pot destruir el rànquing d'una setmana.

### R9. Sense log d'auditoria al panel staff
Qui va aprovar quina proposta d'artista? Qui va canviar quin coeficient? Qui va esborrar quina cançó? **Cap registre.** Per errors humans o mala-fe, no hi ha manera de traçar-ho. Hauria d'haver un `StaffAuditLog` model amb cada acció destructiva.

## 🟡 MITJÀ

### R10. Doble font de veritat per als Deezer IDs ✅ resolt (Sessió 8, `fdc649a`)
`Artista.deezer_id` (BigInteger directe, unique) vs `ArtistaDeezer` (M2M). El codi té fallback (`deezer_id_principal` property). **Poden divergir silenciosament.** Si algú actualitza només `Artista.deezer_id` però no l'`ArtistaDeezer` corresponent, la pipeline usa un mentre la UI mostra l'altre.
> **Resolució:** la columna `Artista.deezer_id` s'ha esborrat (migració 0030). `ArtistaDeezer` és l'única font ara. La propietat `deezer_id_principal` ja no té fallback.

### R11. Camps de localització legacy conviuen amb ArtistaLocalitat ✅ resolt (Sessió 8, `759bb87`)
`Artista.localitat`, `comarca`, `provincia` (CharField) i `ArtistaLocalitat` (FK a `Municipi`). La vista edit manté els dos. **Què passa si divergeixen?** No hi ha una regla clara. Aquest és deute de migració incomplet.
> **Resolució:** les tres columnes legacy s'han esborrat (migració 0031). `ArtistaLocalitat` és l'única font. Nova propietat `localitat_principal` per a la cadena de display.

### R12. Signal fires in-transaction amb `self.territoris.set()` en mig ✅ resolt (Sessió 9, `33ba957`)
Quan `proposta_aprovar` crea `Artista` + N `ArtistaLocalitat` dins d'una `atomic()` block, **el post_save signal dispara `sync_territoris_from_localitats()` després de cada ArtistaLocalitat**. Cada invocació fa `self.localitats.all()` + `self.territoris.set()`. Al final de la transacció estem en el mateix estat final, però intermèdiament el M2M `territoris` ha estat reescrit N vegades. Si un thread concurrent llegeix entre-mig, veu estats intermedis. La solució correcta és `transaction.on_commit()`.
> **Resolució:** signals embolicats en `transaction.on_commit(lambda: _resync(artista_id))`. Es resync una sola vegada després del commit. Defensa addicional: re-fetch de l'artista per id, no-op si fou cascade-deleted entre-mig.

### R13. Cançons amb `album=NULL` fan crashear la vista ✅ resolt (Sessió 9, `080349b`)
`Canco.album` és FK CASCADE, així que idealment no queda mai NULL. Però si alguna cosa trenca la integritat (suport migratori, ALTER manual), els templates `{{ canco.album.nom }}` crashen amb `NoneType`. No es fa servir `|default:"..."` a enlloc.
> **Resolució:** templates staff defensats amb `{% if canco.album %}`. Auditoria va trobar a sobre 5 regressions latents R10/R11 (links Deezer i fallback de localitat) — totes fixades en el mateix commit.

### R14. Backups no es testen en restore ✅ resolt (Sessió 9, `b641343`)
Tenim backups. Mai s'han restaurat. **Un backup no testat no és un backup.** Un error de `pg_dump` podria estar generant fitxers gzip corruptes i només ho descobriríem en el moment pitjor.
> **Resolució:** nou `tq-restore-test` (cron mensual el dia 1). Restaura el dump més recent a una DB efímera, valida row counts dins del 5% del live, drop. Status escrit a `tq-restore-test.status`, surfaced per `tq-health` (max-age 35 dies). Primer run real: artistes=4231/4239, cancons=19937/19961 — passat.

---

# PART III · RENDIMENT I ESCALABILITAT (8 troballes)

## 🟠 ALT

### P1. **Zero caching layer** ✅ resolt (Sessió 12, `449be4c`)
No hi ha `CACHES` configurats a `settings/*.py`. **Cada visita a la homepage executa el mateix query complet.** Les pàgines de rànquing, el selector de territoris, el mapa — tots es regeneren on-demand. A tràfic 10x, el gunicorn de 2 workers saturarà. Una cache LocMem (zero dependencies) + `@cache_page(3600)` a les vistes públiques donaria 10-100x d'amplada de banda.
> **Resolució:** `pagecache` alias (LocMem, TTL 600s, separat del DatabaseCache que usa axes / DRF throttles). Decorador `cache_page_for_anon` a `homepage` i `ranking_page` — usuaris autenticats passen directe, anònims llegeixen de memòria. Cache hit preserva el 304 de P8 comprovant `If-None-Match` contra l'ETag de la resposta cached. Cold 386 ms → warm 13 ms.

### P2. ML model recarregat del disc a cada thread de gunicorn ✅ resolt (Sessió 11, `761d51e`)
`music/ml.py:67-72` carrega el model RF (1.3 MB) lazily. Cada worker gunicorn = 2 càrregues. Però pitjor: `pre_classificar()` és eager en invocacions múltiples, però no hi ha garantia que el model estigui en memòria si Python GC l'allibera. A més, amb scikit-learn recents `joblib.load` pot trigar ~30ms. Hauria de ser module-level amb `@functools.lru_cache`.
> **Resolució:** `_model_cache` module-level dict amb claus `clf_mtime` + `tfidf_mtime`. Invalidació automàtica quan `recalcular_ml` escriu un model nou (mtime canvia → reload transparent). Benchmark post-canvi: 22 ms per classificació (vs 52 ms abans).

### P3. Taula `HistorialRevisio` sense índexs ✅ resolt (Sessió 10, `e7925a7`)
`HistorialRevisio.objects.filter(artista_nom=X).count()` s'executa 2 vegades per track durant `recalcular_ml` (una per ratio, una per count). A 9.000 tracks × 2 = 18.000 queries. Cadascun és un full table scan sobre 1.448 files. És ràpid ara (uns 50 ms) però **a 100k decisions acumulades serà dolor pur**. Els camps `artista_nom`, `isrc_prefix`, `decisio` haurien de tenir `db_index=True`.
> **Resolució:** composite indexes `(artista_nom, decisio)` i `(isrc_prefix, decisio)`. PostgreSQL serveix també les queries single-column quan el camp és líder. Benchmark post-migració: 2.2 ms per query.

### P4. `obtenir_senyal` fa `update_or_create` en loop ✅ resolt (Sessió 10, `26f75a7`)
A `ingesta/management/commands/obtenir_senyal.py:113` un `update_or_create` per cada track. ~1.200 queries. Amb `bulk_create(ignore_conflicts=True)` es reduiria a 1-2 queries. Al ritme actual són 30 segons que podrien ser 1.
> **Resolució:** buffer d'instàncies + `bulk_create(ignore_conflicts=True)` en batches de 200. El unique_together `(canco, data)` fa que `ignore_conflicts` substitueixi el skip-set previ. Elimina la transaction.atomic per fila (ara les bulk fan de commit natural).

### P5. Gunicorn amb WSGI blocking i 2 workers
Django 5.2 suporta vistes asíncrones (`async def`). Les pipelines I/O-bound (Deezer, Last.fm) no són cridades per vistes web, però les vistes staff sí tenen blocking queries. Amb 2 workers, **capacitat concurrent teòrica és 2 requests simultanis**. A tràfic moderat ja es nota.

### P6. Sense connection pooling ✅ resolt (Sessió 10, `36d7579`)
Django usa `CONN_MAX_AGE=0` per defecte (nova connexió a cada request). Amb `django-db-geventpool` o `CONN_MAX_AGE=600` i `CONN_HEALTH_CHECKS=True`, estalviaries ~5ms per request.
> **Resolució:** `conn_max_age=600` + `conn_health_checks=True` a production.py via `dj_database_url.config(...)`. Només a producció; local.py/test.py sense canvi.

## 🟡 MITJÀ

### P7. CSS monolític de 1.989 línies
`web/static/web/css/style.css` és un únic fitxer que bloqueja el render. Hauria de fragmentar-se per pàgina i carregar-se amb `<link media="print" onload="this.media='all'">` o bé fer critical CSS inline.

### P8. Sense ETag ni Last-Modified a pàgines públiques ✅ resolt (Sessió 10, `0d2e200`)
El rànquing setmanal canvia un cop per setmana. Servir-lo amb `Cache-Control: public, max-age=86400` + `ETag` reduiria les crides al gunicorn per usuaris recurrents en un 90%. Django té `django.views.decorators.http.etag` i `last_modified` decoradors que no s'usen.
> **Resolució:** `@last_modified` + `@etag` a `homepage` i `ranking_page`. Last-Modified = més recent entre `RankingSetmanal.created_at` i `RankingProvisional.data_calcul` per a (territori, setmana). ETag inclou `is_authenticated` per distingir headers logged-in vs anon. Sense `Cache-Control: public` (header varia per auth). Verificat: 304 tant amb `If-Modified-Since` com amb `If-None-Match`.

---

# PART IV · ARQUITECTURA (11 troballes)

## 🟠 ALT

### A1. Algoritme de ranking en SQL raw acobla la lògica al vendor
`ranking/algorisme.py` és 14 CTEs en PostgreSQL-específic amb `percent_rank`, `window functions`, `DISTINCT ON` i arrays. **La lògica de producte més important del projecte no és testejable en Python.** Cap test unitari pot validar que un canvi a la fórmula produeix el resultat esperat sense una DB real. Una cita de Robert C. Martin: *"El codi que no es pot testejar és un dèbit tècnic que s'acumula amb interès compost."*

Reformular en ORM Django o almenys en SQLAlchemy Core (que permet testejar amb SQLite in-memory) seria feinada, però **és la diferència entre un sistema fràgil i un sistema industrial**.

### A2. No hi ha una capa d'aplicació / servei
Les vistes importen directament models, criden directament serveis, emeten directament signals, manipulen directament QuerySets. **No hi ha una capa `Application Service` que encapsuli transaccions, políticament.** Resultat: lògica de negoci esparsa en views, templates, signals, i properties del model. Canviar la regla "un artista ha de tenir localitat per ser aprovat" requereix tocar `Artista.clean()`, `Artista.save()`, vistes staff, i les rutes d'aprovació de propostes.

### A3. Acoblament template ↔ ORM
Templates fan `{{ canco.artista.territoris.all }}` que dispara queries. El template té la responsabilitat de saber que cal prefetch. **Aquesta barreja de concerns és un clàssic Django anti-pattern.** Hauria d'haver DTOs (dataclasses) passades al template, preparades per vista.

### A4. `music/` és un monolit intern
En un sol paquet: models ORM, signals, ML, serveis, verificació, titlecase, constants. Si el projecte creix, seria natural separar:
- `music.domain` — Artista, Canco, Album + regles pures de domini
- `music.infrastructure` — Django ORM models
- `music.application` — serveis (`aprovar_canco`, `fusionar_artistes`)
- `music.ml` — classificador (separat, potser app pròpia)

### A5. Sense event bus ni domain events
"Artista aprovat" → "recalcular ML" és un acoblament directe via `recalcular_ml_si_cal()`. "Nova cançó verificada" → "potser retrain" — mateix. **Si mai volem afegir una acció més (ex: notificar un webhook extern, refrescar una cache), cal tocar cada call site.** Un `EventBus` lleuger (Django signals fins i tot, però diferents del `post_save`) permetria desacoblar.

### A6. L'API DRF té un sol endpoint semànticament ric
`/api/v1/mapa/artistes/` retorna comarques + municipis + artistes — tot barrejat. **No segueix REST pur**: recursos distints en un sol recurs. Hauria de ser `/api/v1/territoris/`, `/api/v1/comarques/?territori=CAT`, `/api/v1/municipis/?comarca=...`, `/api/v1/artistes/?posicio_top=1`.

## 🟡 MITJÀ

### A7. `music/ml.py` barreja classificador + heurística + retraining
~500 línies barregen: feature extraction, RF training, heuristic fallback, background thread management, joblib I/O. **Unit testing és impracticable** sense refactor en classes. Una classe `Classifier` amb mètodes clars permet tests de mutació.

### A8. Sense versionament d'API ✅ resolt (Sessió 11, `4c8295a`)
`/api/v1/` existeix com a prefix, però no hi ha política: què passa si es canvia el schema de resposta? Cap consumidor extern pot confiar-hi. Si un dia volem fer app mòbil, **no hi ha una API estable documentada.**
> **Resolució:** `web/api/VERSIONING.md` documenta quan bumpar, què es considera canvi additiu vs breaking, i el procediment per introduir v2 amb finestra de 6 mesos de solapament. Middleware `ApiVersionHeaderMiddleware` afegeix `X-API-Version: N` a qualsevol resposta sota `/api/vN/*`.

### A9. Sense feature flags
Un canvi d'algoritme és all-or-nothing. Amb un `FeatureFlag` a `ConfiguracioGlobal` (ex: `enable_ppcc_v2`) es podria llançar una versió nova en paral·lel i comparar. Ara qualsevol experiment requereix deploy complet.

### A10. mm-design com a npm git dependency és fràgil ✅ resolt (Sessió 11, `d37fcd2`)
`package.json` apunta a `github:miquelmatoses/mm-design`. Si l'autor (tu mateix) esborres el repo, TopQuaranta **falla al `npm install`** fins que es rehabiliti. **Una copia al repo o vendoring a `static/vendor/mm-design/` és la defensa.**
> **Resolució:** còpia de mm-design vendrada a `vendor/mm-design/` (committed). `STATICFILES_DIRS` apunta ara allà. Els 34 `{% static 'mm-design/...' %}` dels templates continuen funcionant sense canviar-los. node_modules/ deixa de ser requisit per a deployar.

### A11. `Usuari(AbstractUser)` reusa `auth_user` table — un anti-pattern
`AUTH_USER_MODEL = "comptes.Usuari"` però usa la mateixa taula que el default de Django (`auth_user`). Funciona, però és confús: lector nou pensa "això és el User de Django" i es despistarà. Hauria de ser `comptes_usuari`.

---

# PART V · MODEL DE DADES (6 troballes)

## 🟠 ALT

### D1. `Canco.isrc` NO és unique ✅ resolt (Sessió 9, `b54623d`)
Diverses cançons poden tenir el mateix ISRC (p. ex. reedicions). **La nostra pipeline tracta l'ISRC com a clau universal** (matching_isrc_deezer ho va fer). Però si algú crea dues `Canco` amb el mateix ISRC, què? No hi ha constraint. `deduplicar_isrc.py` suggereix que s'ha hagut de fer manualment. Hauria de ser unique o almenys amb `unique_together` amb `album`.
> **Resolució:** partial UniqueConstraint `condition=~Q(isrc='')`. Els ~9k Cancons amb ISRC buit (legacy Last.fm-only) queden fora de l'index. Audit pre-flight: 10.353 Cancons amb ISRC, zero duplicats — constraint aplicat sense backfill.

## 🟡 MITJÀ

### D2. `Canco.lastfm_mbid`, `Canco.lastfm_verificat`, `Artista.lastfm_mbid` gairebé dead fields ✅ resolt (Sessió 11, `9446f89`)
Són fields editables al staff però no consumits pel pipeline. **Són metadata orphanada**. O afegir un consumidor (usar `mbid` per fer lookups més precisos a Last.fm), o eliminar-los.
> **Resolució:** eliminats els tres camps (migració 0035). Audit previ: 0 consumidors de lectura; `Artista.lastfm_mbid` estava populat (4253 files) però mai llegit. Si algun dia cal, es pot regenerar amb una sola crida Last.fm `artist.getInfo`.

### D3. `PropostaArtista.deezer_ids` és CharField comma-separated ✅ resolt (Sessió 12, `84e530f`)
Hauria de ser un model relacional `PropostaArtistaDeezer` o almenys `JSONField`. **Parsing manual és font de bugs.** Què passa si algú posa una coma dins d'un ID? Què passa si hi ha espais extra?
> **Resolució:** `JSONField(default=list)`. El ORM ja parsa per nosaltres. La shim `get_deezer_id_list()` continua existint per coaccionar strings que arribin del formulari a int. Audit previ: 0 files a PropostaArtista → migració trivial.

### D4. `PropostaArtista.localitzacions_json` és TextField amb JSON serialitzat ✅ resolt (Sessió 12, `84e530f`)
PostgreSQL té `JSONField` natiu des de Django 3.1. Validació automàtica, queries indexables, tot millor. **Aquest és llegacy-by-design.**
> **Resolució:** renombrat a `localitzacions`, ara `JSONField(default=list)`. Els 3 call sites (submission a comptes/views.py, detall + approve a web/views/staff/eines.py) simplificats: sense `json.loads()`, iteració directa sobre la llista de dicts.

### D5. Sense constraint "un artista no pot col·laborar amb si mateix" ✅ resolt (Sessió 11, `613572c`)
`Canco.artistes_col` (M2M a Artista) **permet que `artista == artista_col`**. No tenim cap constraint que ho eviti. Dada bruta amb aquesta inconsistència es pot ficar i contaminar els càlculs de territori (doble comptabilitat).
> **Resolució:** migració 0034 neteja les 7 files existents (portable entre SQLite+PostgreSQL via `DELETE … WHERE EXISTS`). Receiver `m2m_changed` (pre_add/pre_set, tots dos costats de la relació) rebutja amb `ValidationError`.

### D6. Índexs compostos que podrien millorar la pipeline ✅ resolt (Sessió 13, `cf52345`)
- `RankingSetmanal (territori, setmana, posicio)` — per a les pàgines de rànquing
- `SenyalDiari (data, canco_id, error)` — per al normalize
- `Canco (verificada, artista_id)` — per a les queries del pipeline
> **Resolució:** afegits els índexs de `RankingSetmanal(territori, setmana, posicio)` i `Canco(verificada, artista)`. L'índex proposat per a `SenyalDiari` descartat després d'auditar: els existents `(canco, data)`, `(data, error)` i `(data, corregit)` ja cobreixen totes les query shapes del normalize — afegir-ne un de nou només costaria write throughput.

---

# PART VI · OPERACIONS (9 troballes)

## 🔴 CRÍTIC

### O1. Single point of failure
Un sol servidor, un sol disc, un sol proveïdor (Hetzner), un sol DC. **Un incident a Nuremberg = tot el sistema caigut fins que es faci recovery manual.** Sense full-disk backup offsite, un fallo de RAID és pèrdua total. 24€/mes a Hetzner Storage Box + `restic` resoldria una part important d'això.

## 🟠 ALT

### O2. Deploy = `git pull && systemctl restart` = downtime
Sense blue-green, sense canary, sense rollback automàtic. **Un bug a un deploy = pàgina trencada en producció fins que es faci rollback manual.** Fa uns mesos això era acceptable. Amb usuaris reals ja no.

### O3. Sense CI/CD ✅ resolt (Sessió 9, `e0175df`)
No hi ha `.github/workflows/`. Cap test es corre automàticament en push. Cap validació de lint, type checking, format. **És qüestió de temps que algú (jo inclòs) committegi un fail que trenca producció.**
> **Resolució:** `.github/workflows/ci.yml` amb 3 jobs paral·lels — pytest + `manage.py check` (SQLite in-memory), `black --check` + `isort --check-only`, i `makemigrations --check --dry-run`. Precedent: el commit `f810c42` estableix el baseline d'estil perquè el job de lint passi des del primer push.

### O4. Sense ambient de staging
Els canvis van directe a producció. **Primera vegada que es veu el codi amb dades reals és en producció.** Errors que només apareixen amb volum real (performance, race conditions) es descobreixen amb l'usuari final.

### O5. Token GitHub al git config exposable ✅ resolt (Sessió 11, `76adfa9`)
Ja esmentat al S2. Però des del costat d'ops: **quan aquest servidor es decomissioni i el disc no es destrueixi físicament, aquest token viatja al nou server o al reciclador**.
> **Resolució:** verificació actual confirmada (no hi ha cap PAT a `.git/config`, `~/.netrc`, ni env vars — S2 al seu moment ja va passar a SSH deploy key). `deploy/SSH_KEY_POLICY.md` documenta regles + procediment de rotació + one-liner de verificació perquè no retrocedim.

### O6. Monitoring és pull-based — ningú mira `tq-health` regularment
Vàrem crear `tq-health`, però exigeix algú que el executi. **Un failure de pipeline pot durar hores o dies abans que algú s'adoni.** Un `tq-health` executant-se cada hora + enviant webhook a healthchecks.io o Uptime Kuma (gratuït, self-hosted) resoldria això.

### O7. Backups locals només
Si el servidor s'incendia, els backups s'incendien amb ell. Una política 3-2-1 (3 còpies, 2 media diferents, 1 offsite) és el standard. **Ara tenim 1-1-0.**

## 🟡 MITJÀ

### O8. Sense runbook ni playbook ✅ resolt (Sessió 11, `521f19a`)
Què fas si el pipeline falla a les 6 AM un dissabte? Hi ha algun document que digui "mira A, si fail mira B"? No. **Tot el coneixement operacional és implícit al cap del manteniment.**
> **Resolució:** `RUNBOOK.md` amb 8 seccions (lloc caigut, cron fallat, ranking erroni, DB trencada, disc ple, rollback, lockout staff, re-run de migracions). Cada secció té comandes concrets per diagnosticar i remeiar.

### O9. Logrotate no configurat per `novetats.log` ✅ resolt (Sessió 9, `fee0472`)
El novetats.log de cada hora acumula. Ara fa 25 MB. En 6 mesos farà 180 MB. Sense rotació, pot acabar omplint disk. Caldria `/etc/logrotate.d/topquaranta`.
> **Resolució:** `/etc/logrotate.d/topquaranta` (config a repo `deploy/logrotate.topquaranta`). Setmanal, 8 rotacions, gzip, copytruncate (perquè els crons amb `>>` no perdin el FD).

---

# PART VII · FRONTEND / UX (6 troballes)

## 🟠 ALT

### F1. Accessibilitat: cap `aria-label` sistemàtic ni testejat
Els SVG icons tenen `aria-hidden="true"`, bé. Però el mapa D3 **és inaccessible a screen readers** — és una representació visual pura. No hi ha alternativa textual al rànquing geogràfic. La paleta de colors per territori depèn de colors per distingir (CAT groc, VAL vermell...). **Un daltònic no pot distingir territoris al selector.** WCAG AA no compleix.

### F2. Cap internacionalització
Tot Catalan-only. No hi ha `{% trans %}` ni `gettext` en ús. **Si un curiós de fora vol entendre què és TopQuaranta, no hi ha botó EN.** Paradoxalment: això va en contra de la missió cultural — difondre música en català a nous públics que no parlen català.

### F3. Cap estratègia SEO mínima ✅ resolt (Sessió 11, `f14a3e8`)
Ni `<meta name="description">` sistemàtic, ni Open Graph tags, ni Twitter Cards, ni sitemap.xml, ni robots.txt estructurat. **Quan algú comparteix un enllaç de rànquing a WhatsApp, apareix sense preview.**
> **Resolució:** blocks `meta_description` / `og_*` / `twitter_*` / `canonical_url` a `base.html` amb defaults raonables; `ranking.html` els sobreescriu per territori. `sitemap.xml` (~4k URLs, protocol https) i `robots.txt` servits a l'arrel. Imatge `og-default.png` 1200×630 generada amb Pillow.

## 🟡 MITJÀ

### F4. Sense dark mode
mm-design podria suportar-ho amb `@media (prefers-color-scheme: dark)`. Actualment només light.

### F5. Pàgines públiques no mostren timestamp de darrera actualització ✅ resolt (Sessió 11, `f14a3e8`)
"El rànquing del 2026-04-13" — però *quan* es va calcular? Quan serà el pròxim? Això dona context que manca.
> **Resolució:** homepage i ranking_page exposen `darrera_actualitzacio` al context (reusant `_ranking_last_modified_dt` de P8). Templates mostren "Actualitzat el DD MMMM YYYY a les HH:MM" sota la data del rànquing.

### F6. Cap indicador de progrés en accions staff llargues
Un bulk approve de 100 cançons executa el POST i no mostra res fins al final. Sense feedback, l'usuari no sap si cal esperar o ha fallat.

---

# PART VIII · PROCÉS I CULTURA (8 troballes)

## 🟡 MITJÀ

### C1. Sense pre-commit hooks ✅ resolt (Sessió 11, `99bc2dc`)
Black, isort, ruff, mypy — tot declarat a `requirements-dev.txt` però no executat automàticament. **Cada commit confia que l'autor hagi corregut ell mateix.**
> **Resolució:** `.pre-commit-config.yaml` amb hooks estàndard (trailing whitespace, EOF, YAML/JSON/TOML valid, detecció de merge markers, privat keys, fitxers >512KB) + black 25.1.0 + isort 6.0.1 (mateixes versions que CI) + hook local `makemigrations --check --dry-run`. `pre-commit==4.0.1` afegit a requirements-dev.txt.

### C2. Sense política de dependencies updates ✅ resolt (Sessió 12, `f201d38`)
Res com Dependabot o Renovate. **scikit-learn, Django, requests — es van actualitzant nosaltres o quan algun CVE crític força l'acció.**
> **Resolució:** `.github/dependabot.yml` setmanal (dl 06:00 Europe/Madrid) per a `pip` + `github-actions`. Updates groupats per família (django-and-auth, dev-tooling) per minimitzar soroll. CI (O3) valida cada PR automàtica.

### C3. Sense versionament semàntic ✅ resolt (Sessió 12, `278c3de`)
Cap tag git, cap CHANGELOG.md. **Dir "la versió que funcionava el 3 d'abril" depèn de reconstruir mentalment quin commit era.**
> **Resolució:** `CHANGELOG.md` baseline amb entry 0.9.0 que inventaria totes les troballes de Phase 9. Keep a Changelog + SemVer. Futurs releases tagueig git.

### C4. Sense política de deprecation ✅ resolt (Sessió 13, `b8e2de5`)
Quan el sistema evolucioni i una API o camp passi a obsolet, no hi ha procés per a anunciar-ho, quant temps mantenir compatibilitat, etc.
> **Resolució:** `docs/DEPRECATION.md` — procés de 4 passos (CHANGELOG/Deprecated → avís al codi → espera 90d/180d → elimina). Cobreix model fields, management commands, API endpoints, staff features, ops scripts. Inclou template per a la propera deprecation. Motivada per la regressió R10b de la Sessió 8.

## 🟢 BAIX

### C5. Documentació dispersa ✅ resolt (Sessió 12, `278c3de`)
CLAUDE.md i CLAUDE_* són útils però no hi ha un `README.md` per a un nou contribuidor. **Onboarding d'algú nou al projecte és "mira aquesta carpeta i fes-te'n la teva idea".**
> **Resolució:** `README.md` refrescat: drop de referències stale a Wagtail i `distribucio/`/`legacy/`, secció "Desenvolupament local" amb clone + install + test + pre-commit install, enllaços explícits a CLAUDE.md / RUNBOOK.md / VERSIONING.md / SSH_KEY_POLICY.md. El CI badge ara apunta al workflow real.

### C6. Sense codi d'ètica, sense govern
Decisions com "què és Catalan music" es fan per defecte (ML trained on past decisions). **Però no hi ha document que expliqui els criteris.** Si algú discrepa, no sap a qui apel·lar-se.

### C7. Sense analítica del projecte
No sabem: quants usuaris úniques visiten? Quin rànquing es mira més? Quantes propostes entren per setmana? **Sense dades, les decisions de producte són intuïció.**

### C8. Sense roadmap públic ni feedback channel
Els usuaris no saben què es planeja. No hi ha un lloc per proposar features. **TopQuaranta és un producte unilateral.**

---

# PART IX · FILOSÒFIC / CULTURAL (7 troballes)

Aquesta és la secció que un audit "normal" no fa. I és la que més importa per fer l'obra eterna.

### Φ1. La definició de "música catalana" és implícita ✅ resolt (Sessió 12, `b7564fa`)
El sistema classifica via ISRC prefix + noms + heurístiques ML. **El resultat és un model estadístic, no una declaració cultural.** Què considera el projecte "català"?
- Artista nascut al PPCC?
- Cantat en català (majoritàriament)?
- Vinculació cultural (residencia, identitat declarada)?

No hi ha una resposta documentada. La fórmula 14-CTE té decisions arbitràries incrustades (pesos dels coeficients). **Un projecte aspirant a excel·lència cultural necessita un manifest.**
> **Resolució:** `docs/DEFINITION.md` fixa la regla (primary vocal delivery en català), els criteris operacionals (release < 12 mesos, artista aprovat), els edge cases (bilingüe, multiple versions, col·laboracions, covers, escopi territorial) i la governança (staff decideix, ML prioritza, apel·lacions via PropostaArtista). El ML no decideix — només ordena la cua de revisió humana.

### Φ2. Opacidad cap als usuaris finals
El públic veu una posició (#1, #2...) però no sap:
- Quin és el `score_setmanal` d'una cançó
- Per què és #3 i no #4
- Quan es va actualitzar el rànquing
- Com impugnar una classificació

**La manca de transparència és un greuge de la missió cultural.** Un projecte cultural que es vol "obra d'art" ha d'explicar com funciona.

### Φ3. Cap agencia dels artistes
Un artista verificat pot veure les seves estadístiques, **però no corregir dades sobre ell**. No pot dir "aquesta cançó és col·laboració al 50%, no al 20%". No pot proposar canvis al seu perfil. **És paternalisme estructural.**

### Φ4. Cap transparència algorítmica
Els coeficients de `ConfiguracioGlobal` no són públics. **Un artista que cau del #5 al #20 en una setmana no sap si ha estat per la seva reproducció o per una decisió del sistema.** Publicar els coeficients + documentació del que fan els 14 CTEs seria un acte de respecte.

### Φ5. Sense llicència de dades ✅ resolt (Sessió 12, `b7564fa`)
RankingSetmanal és dades valuoses. **Si algú vol publicar "Evolució del rànquing 2025-2026", té permís?** No hi ha CC-BY-SA ni CC0 declarat. La dada queda com a bé privat per defecte. **Això va contra l'esperit de difusió cultural.**
> **Resolució:** `LICENSE-DATA.md` — CC BY 4.0 explícit per a rankings, signal, coeficients, historial. Scope definit (què cobreix, què no — upstream Last.fm/Deezer queda sota les seues llicències). Attribution l'única contrapartida.

### Φ6. Sense retenció explícita ✅ resolt (Sessió 13, `977beef`)
`SenyalDiari` creix per sempre. **Què passa l'any 2030 quan siguin 3M+ files?** Hauria d'haver una política: "Les dades de signal Last.fm es poden arxivar després de 2 anys; el ranking setmanal es conserva indefinidament com a document cultural."
> **Resolució:** `docs/RETENTION.md` + management command `arxivar_senyal_vell` (cron trimestral). `SenyalDiari` > 2 anys s'exporta a `senyal-YYYY.csv.gz` dins de `/home/topquaranta/archive/` i s'esborra de la DB. Write atomic (fsync + rename before DB delete). Ranking setmanal + HistorialRevisio + StaffAuditLog: per sempre.

### Φ7. Sense manifest del projecte ✅ resolt (Sessió 12, `b7564fa`)
CLAUDE.md parla de l'arquitectura tècnica. ROADMAP.md de feines pendents. **No hi ha un CULTURAL.md que digui "això és TopQuaranta i per què existeix".** Si un dia el desenvolupador original es retira, el projecte perd la seva brúixola.
> **Resolució:** `MANIFEST.md` — què és el projecte (provar setmanalment que la música en català és viva), què NO serà mai (no monetitzar, no platform capture, no surveillance, no gatekeeping, no canvis quiet d'algoritme). Àncora per a decisions futures.

---

# PART X · EL CAMÍ A L'OBRA ETERNA

## Els 10 passos que separen "correcte" de "excepcional"

### Nivell 1 — Fonaments (setmanes)
1. **Rotació immediata de secrets**: password DB, PAT GitHub, SECRET_KEY.
2. **Backups xifrats + offsite** (Hetzner Storage Box, restic, GPG).
3. **`django-axes` + Argon2 + 2FA staff** (via `django-otp`).
4. **CSP real** (script-src 'self' + CDN whitelisted).
5. **Content validation** a tots els camps d'usuari (PropostaArtista.nom, social URLs).

### Nivell 2 — Reliability (setmanes)
6. **`algorithm_version` i `config_snapshot`** a RankingSetmanal — fes els rànquings reproduïbles per sempre.
7. **Staff audit log** immutable — cada acció destructiva deixa traça.
8. **`@cache_page` + `ETag`** a pàgines públiques.
9. **CI/CD** amb pytest + ruff + mypy a cada push.
10. **Restore test mensual** dels backups.

### Nivell 3 — Arquitectura (mesos)
11. **Extreure domain layer** de `music.models` — models ORM separats de la lògica de domini.
12. **Cua de feines** (Celery / RQ) per al retraining ML i les notificacions.
13. **API REST pura amb versionament** (`/api/v1/rankings/`, `/api/v1/artistes/`, `/api/v1/territoris/`).
14. **Event bus** per desacoblar "artista aprovat" de "recalcular ML".
15. **Portar el 14-CTE a Python** (al menys una versió testejable amb SQLite).

### Nivell 4 — Cultura (mesos)
16. **Manifest cultural** (`CULTURAL.md`): què és la música catalana segons TopQuaranta, per què els coeficients valen el que valen.
17. **Transparència algorítmica**: a cada cançó del rànquing, un botó "Per què és aquí?" que mostri els pesos.
18. **Agencia artística**: artistes verificats poden proposar correccions a les seves dades (amb revisió staff).
19. **CC-BY-SA de les dades**: permetre que terceres parts publiquin anàlisi del rànquing.
20. **Multilíngüe**: almenys CAT + EN. La missió és difondre, no tancar-se.

### Nivell 5 — Exquisitesa (anys)
21. **App mòbil** nativa (Flutter / Kotlin Multiplatform), consumint l'API v1.
22. **Recomanacions personalitzades**: els usuaris registrats tenen "per tu", entrenat amb la seva activitat.
23. **Federació**: TopQuaranta pot compartir dades amb altres projectes culturals catalans.
24. **Open governance**: junta editorial que revisa els coeficients anualment.
25. **Arxiu físic**: una publicació setmanal en paper / digital en format revista.

---

# Conclusió honesta

El sistema actual **és un projecte correcte i funcional**. La infraestructura és estable, el pipeline corre sense crashar, els rànquings es publiquen.

Però entre "no falla" i "és una obra que perdurarà" hi ha un abís.

Els **7 problemes crítics** (contrasenya DB feble, PAT exposat, backups en clar, rànquings no reproduïbles, CASCADE que esborra història, single point of failure, opacitat cap als usuaris) **no són deute tècnic — són vulnerabilitats**.

Els **15 problemes alts** són mediocritat acumulada que erosiona la confiança dia a dia, i que cada setmana fa el projecte una mica menys respectable.

Els **22 problemes mitjans** són deute estructural que vindrà a cobrar quan es vulgui escalar o canviar.

Els **18 problemes baixos i filosòfics** són la diferència entre software bo i **software que mereix existir**.

**La música catalana mereix una plataforma que sigui ella mateixa una obra d'art de la programació.** Ara no ho és. Però podria ser-ho, amb voluntat i temps.
