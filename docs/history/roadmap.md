# ROADMAP.md — TopQuaranta

> Estat actual i propers passos. El detall fi viu al `git log` i als
> commits per sprint; la història de Phase 9 (auditoria d'excel·lència)
> al fitxer `docs/history/roadmap.md` (sprints A–J ter).
> Last updated: 2026-04-26.

---

## Estat actual

- **Públic**: `https://www.topquaranta.cat/` — React SPA a l'arrel.
  Pàgines redissenyades amb llenguatge editorial (bandes alternants
  ink/blanc + Playfair) als sprints H/I bis/J bis: `/`, `/top`,
  `/artistes`, `/mapa`, `/comunitat`, `/com-funciona`. Tot WCAG AA
  (axe-core 0 violacions a 10 URLs auditades).
- **Staff**: `/staff/*` — 17 pàgines React + DRF. Taules amb scroll
  horitzontal a mòbil (Sprint J ter). Filter-panel pattern reutilitzat
  per la pàgina pública d'artistes.
- **Auth**: sessions Django + CSRF + TOTP 2FA per staff.
- **Pipeline**: nightly chain documentada a `docs/architecture/pipeline.md`.
- **DB**: PostgreSQL 14, 37 taules. Volums actuals (2026-04-26):
  ~1.9k artistes aprovats, ~2.4k cançons verificades, 5 territoris
  amb top oficial actiu.
- **ML**: 79 features, ROC-AUC 0.9994 (post Whisper + MB).
- **Infra**: Caddy + gunicorn :8083 amb `ExecReload=HUP`.

Si vols més detall del que es va lliurar a cada sprint, vés a la
secció [Sprints — completats](#sprints--completats) més avall.

---

## Phase status

Cada **fase** és una era del projecte (estructural). Cada **sprint**
dins una fase és un lliurament concret. Les fases ja són totes ✅;
l'activitat des d'abril 2026 viu en sprints.

| Fase | Resum | Estat |
|---|---|---|
| 0 | Esquelet del projecte, settings split | ✅ |
| 1 | Importació legacy (taules buidades a Phase 8) | ✅ |
| 2 | Ingesta Last.fm | ✅ |
| 3 | Normalització Formula B (Phase 4 la va deprecar) | ✅ |
| 4 | Algorisme de top portat a Python (v1) | ✅ |
| 5 | Top provisional + revisió staff | ✅ |
| 6 | Pipeline metadata Deezer + lloc públic | ✅ |
| 7 | Panell `/staff/` propi | ✅ |
| 8 | Neteja legacy (taules, codi, serveis) | ✅ 2026-04-16 |
| Audit | Consolidació + reescriptura docs | ✅ 2026-04-16 |
| Ops | `tq-health` + backups diaris + settings | ✅ 2026-04-16 |
| 9 | **Excellence** — security + reliability + arch + culture | ✅ (history a `docs/history/roadmap.md` (sprints A–J ter)) |
| 10 | Migració React SPA + neteja Django UI | ✅ 2026-04-21 |
| 11 | Plataforma comunitat (Grup C) | ✅ 2026-04-21 |
| 12 | Sprints temàtics A–J ter (vegeu sota) | ✅ |

---

## Sprints — pendents

Per ordre de prioritat (no alfabètic). Quan se'n fa un, es mou a la
secció _completats_ amb la data i el detall.

### 1. Sprint K — Analytics ètica (interna)

> Mètriques agregades sense vulnerar el manifest. GoAccess sobre
> logs Caddy + comptadors interns + UTM convention.

- [ ] GoAccess cron diari → `/var/www/analytics/index.html` (privat).
- [ ] Model `MetricaEsdeveniment(data, clau, comptador)` + middleware
      que incrementa pageviews per pàgina pública.
- [ ] `register_event(clau)` cridat des dels endpoints clau
      (registre completat, proposta enviada, feedback enviat).
- [ ] Pàgina staff `/staff/analytics` amb gràfics setmanals.
- [ ] Convenció UTM documentada (`?utm_source=instagram&utm_campaign=top-YYYY-wWW`).
- [ ] Documentació al `docs/product/definition.md` i `/legal/privacitat`
      sobre què mesurem internament.

### 2. Backlog menor

Items petits per fer en sessions curtes:

- [ ] Demucs → Whisper pipeline com a recall booster per les ~3-4
      false negatives on Whisper sent `es` a tracks catalans
      (Jonatan Penalba × 2, Adrien Broadway). Cost ~3× més lent;
      només val la pena si surt un cluster significatiu després
      del backfill.
- [ ] Auditar les 39 prediccions `ja` (japonès) de Whisper —
      sospitós, probablement vocalitzes/instrumentals/scat.
- [ ] Snapshot baseline pre-Whisper RF abans del proper retrain
      per A/B sobre el set de 48 clips.
- [ ] Decidir què fem amb `/root/TopQuaranta/` (1.4 GB Wagtail
      legacy): tar.gz a backup off-site o `rm -rf`.
- [ ] Test coverage 52% → 70%. Gaps: `music/services.py`,
      `music/verificacio.py`, `ranking/senyal.py`. Sprint C ja en
      va cobrir part.
- [ ] Valorar correu @topquaranta.cat: avui Sprint G va concloure
      "stay on cdmon"; revisitar si el volum d'enviaments puja.
- [ ] **Stalwart polish** (post Sprint I bis):
  - [ ] Habilitar port 587 STARTTLS submission (ara només 465 SMTPS).
        Útil per a clients mòbils que no accepten SMTPS implicit.
  - [ ] Crear bústia o alias `postmaster@topquaranta.cat` per a rebre
        els reports DMARC (`rua=mailto:postmaster@…`). Ara queden en
        cua sense destinació real.
  - [ ] Integrar parsejat de DMARC reports al panell staff (gràfic de
        què passa SPF/DKIM en nom nostre + alertes de potencial
        spoofing). Alternativa: subscriure'ns a [dmarcian.com](https://dmarcian.com)
        free tier i delegar el parseig.
- [ ] Verificar `cercol.team` a Resend (panell Resend → Domains) per
      a que el smarthost route per Cercol funcioni de veritat. Mentre
      no estigui, els correus de `hello@cercol.team` reben 550.
- [ ] **Gmail avatar** per `info@`/`admin@` quan se reseti el límit
      del telèfon (ara només `miquel@` té Google Account associat).
- [ ] (Quan Hetzner ens desbloca port 25 outbound) considerar treure
      els relays Brevo/Resend i fer entrega directa des de Stalwart.
      Implica warm-up d'IP de 4-8 setmanes + maintenance més pesat.

> **Sprint K — Capa editorial pública**: descartat. La intenció
> original (donar entrada clara a un visitant nou) la va cobrir
> Sprint H + `/com-funciona` + el redisseny editorial dels Sprints
> I bis i J bis.

---

## Sprints — completats

Resum d'una pantalla per sprint. Per ordre alfabètic per facilitar
la cerca; les dates al títol indiquen la cronologia real. Per al
detall fi: `git log` per fitxer o pel rang de dates.

### Sprint A — Tancar deute acumulat ✅ (2026-04-25)

Drop columnes mortes + renames + constants a config. Migracions
`ranking 0012` (drop `dies_en_top`, rename `lastfm_playcount` →
`escoltes_setmanals`); `PPCC_PENALITZACIO_PER_POSICIO` mogut a
`ConfiguracioGlobal`; magic numbers ML → `music/constants.py`.

### Sprint B — Whisper milestone + reentrenament ML ✅ (2026-04-25)

Backfill Whisper LID complet sobre la cua. Reentrenament RF amb
4 features Whisper noves (top-7 d'importància). 5-fold CV ROC-AUC
0.9994. A/B TF-IDF 60→30 max_features adoptat.

### Sprint C — Robustesa `staff_views` + tests ✅ (2026-04-25)

Split del `staff_views.py` monolític (3.330 línies) en 16 mòduls per
àrea sota `web/api/staff/`. Backward-compat shim a `staff_views.py`.
Nous tests (`web/tests/test_staff_endpoints.py`).

### Sprint D — Performance pública ✅ (2026-04-25)

`cache_for_anon` + ETag + Last-Modified als endpoints públics
(`/top`, `/artistes`, `/mapa/artistes-top`). LocMem `pagecache` per
worker. ~30× speedup en hits anònims; 304 ràpids per re-fetches.

### Sprint E — Transparència algorítmica pública ✅ (2026-04-25)

Nou `TopBreakdownPanel` exposant `age_factor`, `past_top_factor`,
`monopoli_factor` per cançó al `/canco/<slug>` i a la `CancoEditPage`.
Migració `ranking 0011`.

### Sprint F — Accessibilitat i mobile ✅ (2026-04-26)

Skip-to-content + `:focus-visible` global + landmarks correctes.
Auditoria axe-core sobre 6 pàgines: 4 violacions detectades, totes
corregides. Re-auditoria 0 violacions a 6 URLs.

### Sprint G — Gestors d'artista i correu ✅ (2026-04-26)

Bloc 1: nou camp `Artista.bio` + endpoint `PATCH /api/v1/compte/
artista/<pk>/editar/` per a `UserArtista.verificat=True`. Audit row
només quan canvia algun camp. Migracions `music 0052` + `0053`.
Bloc 2: anàlisi Hetzner Hosted Mail vs cdmon — recomanació "stay on
cdmon" (només +25 €/any d'estalvi vs cost del cutover).

### Sprint H — Comunicació del producte + onboarding ✅ (2026-04-26)

Hero + 3 blocs + CTA a HomePage; intros discrets a `/top`, `/mapa`,
`/comunitat`, `/comunitat/directori`; targeta amb 3 punts a
`/onboarding`; nova pàgina `/com-funciona` (6 seccions divulgatives);
ComptePage reestructurada amb guiatges contextuals.

### Sprint I bis — Redisseny editorial de la HomePage ✅ (2026-04-26)

Reescriptura completa: 10 seccions verticals amb bandes alternants
ink/blanc, Playfair, kicker tone-aware. Endpoints nous: `/api/v1/
stats/`, `/top/canco-destacada/`, `/artistes/destacat/`,
`/artistes/descoberta/`, `/albums/`. Rotació territori en focus,
compte enrere amb segons + "X cançons noves", notícies en 2 cols
pública/interna amb extracció d'imatge des del markdown.

### Sprint J bis — Redisseny editorial `/top` `/artistes` `/mapa` `/comunitat` ✅ (2026-04-26)

Aplicat el llenguatge editorial a totes les pàgines públiques.
Extreta primitiva compartida `web-react/src/components/editorial.jsx`
(`Section` / `SectionHeader` / `TerritoriBadge` / `TrendCue` +
`TERR_COLORS` + `TERRITORI_NOM` amb PPCC → "Global"). `/top` amb
navegador setmanal (prev/next), nous camps `prev_setmana`/
`next_setmana` a `/api/v1/top/`. Llenguatge intern eliminat de la
UI pública (verificada/aprovat/revisió humana).

### Sprint I — Distribució automàtica a Instagram ✅ (2026-04-26)

App nova `social/` (model `SocialPost` idempotent per
`(platform, tipus, territori, setmana)`); package `ingesta/social/`
amb `colors`, `fonts`, `cover_cache`, `calendari`, `captions`,
`renderer` (PIL, formats 1080×1350 feed + 1080×1920 stories),
`instagram_client` (Graph API v19; mode DRY_RUN automàtic quan
`INSTAGRAM_ACCESS_TOKEN` és buit/`"test"`). Commands
`autoritzar_instagram` (interactiu, code → long-lived 60 dies),
`publicar_social --data --tipus --platform --dry-run --force`,
`renovar_token_instagram`. Calendari amb 5 fases via
`ConfiguracioGlobal.fase_distribucio`: Fase 1 (default) només
dissabte; Fases 2-5 desbloquegen dimecres/dilluns/divendres/dimarts.
Kill switch a `instagram_actiu`. Story cap configurable
`story_max_cancons_ppcc` (1-40). Pàgina staff `/staff/social` amb
preview en viu, force-publicar, controls de fase + kill + token TTL.
Crons al `cron.topquaranta` per als 5 dies + token mensual. Fonts
Playfair + Roboto vendoritzades. Audit action `social_publicat`
afegida (migració `music 0054`). 12 tests nous (153 total).

> **Recordatori operatiu**: Fase 1 al començament. Pujar de fase
> requereix avaluar Insights Instagram durant 4 setmanes —
> llindars documentats al fitxer del sprint o al panell staff.

### Sprint I bis (post) — Redisseny renderer + multi-canal + email ✅ (2026-04-27)

Tres blocs grossos en una sessió:

**1. Redisseny editorial del renderer Instagram.** El primer disseny
era massa fosc + monocrom + esquemàtic. Reescrits els 4 tipus de
slide (top global, top territorial, nous singles, nous àlbums) +
stories (intro, cançó individual, CTA): logo SVG real (substitueix
"Top" + "Quaranta" sintetitzat), icones territorials (`vendor/mm-design/
icons/territories/`) recolorejades dinàmicament, paleta brand
mirrorejada a Python (`TERR_COLORS`), bin-packing dinàmic per a
singles (≤10 → 1 slide, 11–20 → 2 slides equilibrats), pill-system
amb format mm-design (`--mm-radius-lg`), cover full-bleed
(`ImageOps.fit`), eliminació de tot referència a "Països Catalans"
(sensibilitat política). Auto-tag d'artistes a feed posts via
`user_tags` Graph API. Captions en project-week numbering (`Setmana
N`) amb anchor a Sat 2026-04-25 = setmana 34, helper canònic a
`music/dates.py`. Finestra de novetats anclada a la última
publicació del mateix tipus (no "darrers 7 dies fix") per evitar
duplicats entre setmanes consecutives. Staff page amb Preview/
Veure slides/Reset/Esborrar IG buttons + project-week column +
filtre "últims 7 dies" a /staff/cancons.

**2. Distribució multi-canal.** Un sol comandament `publicar_canal
--channel <name>` per als 4 nous canals + el setup d'Instagram
existent. Models singletons per a cada credencial (`MastodonAuth`,
`BlueskyAuth`, `TelegramAuth`); kill switches independents a
`ConfiguracioGlobal.{mastodon,bluesky,telegram,newsletter,rss}_actiu`.
Endpoints staff per gestionar credencials (`/staff/social/{mastodon,
bluesky,telegram}/{,test/,clear/}`). Frontend amb panell unificat de
canals + toggles. RSS Atom 1.0 a `/rss/{top,novetats}.xml` (kill-
switched). Newsletter HTML setmanal via Brevo (utilitza la infra de
consentiment del Sprint J). Crons escalonats: Sat IG 09:30 → Mastodon
09:40 → Bluesky 09:50 → Telegram 09:55 → Newsletter 10:00. 8 tests
nous (160 passing).

**3. Email infrastructure** (necessari per verificar Mastodon/Bluesky/
Telegram, però va créixer molt). Stalwart Mail Server v0.16.1
configurat com a backend IMAP + receptor SMTP per `topquaranta.cat` i
`cercol.team`. TLS Let's Encrypt sincronitzat des de Caddy via
systemd path-watch. **Smarthost routing condicional** (Stalwart →
Brevo per `@topquaranta.cat`, Stalwart → Resend per `@cercol.team`)
configurat al panell amb 2 routes Relay + expressió `sender_domain ==
'cercol.team' ? 'resend-relay' : 'brevo-relay'`. Hetzner Cloud
Firewall configurat via API per obrir 25/465/587/993. CDMON DNS API
integrat (`dns-backup/cdmon_clean.py`): netejada massiva de 18
registres legacy (CDMON Micropla — imap/pop3/smtp/sogo/roundcube/
autodiscover/etc.). Apex A actualitzat de CDMON IP a `188.245.60.20`.
Brevo configurat com a relay outbound (DKIM via 2 CNAMEs `brevo*._
domainkey`, SPF inclou `spf.brevo.com`). Resend pendent de
verificació de domini cercol.team al panell Resend. BIMI publicat
sense VMC (avatar a Yahoo/Fastmail; per Gmail cal Google Account per
adreça). Autoconfig Mozilla Thunderbird a `https://mail.topquaranta.cat/
.well-known/autoconfig/mail/config-v1.1.xml`. Documentació exhaustiva
a `docs/EMAIL.md`.

> **Operativament**: Mastodon i Telegram credencials posades + cron
> actiu. Bluesky pendent de credencials. Newsletter pendent
> d'activació quan hi hagi subscriptors. RSS live ja.

### Sprint J — Privacitat, cookies i corpus legal complet ✅ (2026-04-26)

Paquet legal sencer (no només GDPR): 7 pàgines a `/legal/{avis-legal,
privacitat,cookies,termes,codi-conducta,llicencies,accessibilitat}` +
índex `/legal`. Banner de cookies informatiu (no bloquejant) amb
persistència a localStorage. Registre amb 3 checkboxes (termes
obligatori, edat ≥14 obligatori, newsletter opt-in opcional). Camps
nous a `PerfilUsuari` (`consent_termes_at`/`_versio`,
`vol_newsletter`, `consent_newsletter_at`) — migració `comptes 0013`.
Endpoints `POST /api/v1/compte/exportar-dades/` (RGPD art. 20, envia
JSON per email) i `GET /api/v1/compte/baixa-newsletter/?token=…`
(unsubscribe via signed token, sense login). Botó "Exporta les meves
dades" a `PerfilUsuariPage`. Identitat del titular: CVR 46414683
(Dinamarca), info@topquaranta.cat. Datatilsynet com a lead authority.
0 violacions axe-core a 9 URLs noves. **Esborranys legals; pendent
revisió jurídica humana abans de comunicació externa**.

### Sprint J ter — FilterPanel a `/artistes` + scroll mòbil a taules staff ✅ (2026-04-26)

`StaffTable.Table` ara embolcalla la `<table>` en `overflow-x-auto`
amb `min-w-[640px]` — scroll horitzontal a totes les taules staff
en mòbil. `ArtistesPage` migrada al `FilterPanel` staff (popover
amb badge de comptador).

### Sprint L — Metadata d'artista des de Last.fm ✅ (2026-04-25)

Nou cron `obtenir_metadata_lastfm` (diari 05:00 UTC). Camps nous a
`Artista`: `lastfm_url`, `lastfm_bio_*`, `lastfm_listeners`,
`lastfm_playcount_total`, `lastfm_image_*`, `lastfm_tags` (JSON),
`nb_similars_lastfm`. Migració `music 0050`.

### Sprint M — Naming consolidation: "ranking" → "top" ✅ (2026-04-25)

Renaming massiu UI/codi/migracions/scripts. Models `Ranking*` →
`Top*` amb àlies Python per backward-compat. URLs `/staff/ranking`
mantingudes com Navigate-alias a `/staff/top`. URLs públiques
intactes. Migració `ranking 0013`.

- Image generation (PIL) for ranking posters.
- Telegram / Instagram distribution.

Original assets (TTF fonts, SVG territory logos) were on a local machine
that is no longer accessible. The public website is the distribution
channel instead.

---

## Ground rules for future work

- Never commit without explicit request.
- Update this file at the end of each session.
- Follow the conventions in `CLAUDE.md` §9.
- No new parallel design systems — tokens come from mm-design.
- No raw SQL outside `ranking/algorisme.py` and migrations.
- When in doubt about a decision, check §5 of `CLAUDE.md`.
- Re-run axe-core (`/tmp/axe/run.js`) after touching any public page.
- After deploys: `sudo systemctl reload topquaranta-web` (graceful HUP).
