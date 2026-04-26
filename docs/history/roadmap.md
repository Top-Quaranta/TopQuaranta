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

### 1. Sprint J — Privacitat i cookies (GDPR)

> Posar el lloc al dia amb el RGPD/LOPDGDD.

**Per què primer**: és el risc legal real del projecte. El SPA no
fa tracking de tercers (no Google Analytics, no píxels), però
seguim sense política de privacitat publicada ni banner de cookies
informatiu (la cookie de sessió és funcional, però convé documentar-ho).

- [ ] Pàgina `/privacitat` amb política completa (dades que es
      guarden, finalitat, base legal, drets de l'usuari, contacte).
- [ ] Pàgina `/cookies` amb la llista de cookies usades (sessionid,
      csrftoken, axes_*) i la seva finalitat. Al SPA, **no** s'usen
      cookies de tercers ni analytics.
- [ ] Banner discret la primera visita amb "Entès" + link a la
      política. No bloquejant.
- [ ] Endpoint `POST /api/v1/compte/exportar-dades/` (right to data
      portability) que envia un correu amb un fitxer JSON amb tot
      el que el sistema sap de l'usuari.
- [ ] L'auto-eliminació via correu ja existeix (Sprint G), enllaçar-la
      des de la política.
- [ ] Textos legals en català, revisió per algú amb formació jurídica
      abans de publicar.

### 2. Sprint I — Instagram automàtic

> Distribuir els tops setmanals automàticament al canal d'Instagram.

**Per què**: tracció gratuïta cada dissabte. Cost moderat. Requereix
un compte business i decidir API oficial vs solució no-oficial.

- [ ] Definir format visual del post setmanal (carrousel? imatge
      única amb top 10?). Generar via PIL/Cairo o html-to-image.
- [ ] Crear/configurar el compte Instagram business + Facebook page
      requerida per l'API oficial de Meta.
- [ ] Cron dissabte 09:30 UTC (post `calcular_top` setmanal) que
      publica el carrousel al feed.
- [ ] Decidir si afegim també `Stories` o només feed.

### 3. Backlog menor

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
