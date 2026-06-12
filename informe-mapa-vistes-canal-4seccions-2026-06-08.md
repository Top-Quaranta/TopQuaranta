# Mapa per a les vistes de canal de 4 seccions (read-only)

> 2026-06-08 · informe local, NO committejat · prod només lectura.
> Objectiu: dissenyar les 4 seccions analítiques/de-control de la vista
> de canal (llesques 3-4 de la redistribució de distribució), sabent per
> a cada secció QUÈ existeix, QUÈ falta, i un esquema de descriptor que
> ho lligue. Cap canvi de codi ni dades.

Les 4 seccions (numeració del brief):
1. **Newsletter** — selector de setmana + generar esborrany sota demanda + indicador en viu.
2. **KPIs per canal** — enviaments, subscriptors/membres, abast, seguidors.
3. **Control de què publica** — matriu canal × tipus de contingut.
4. **Analítica de posts** — engagement per publicació.

La vista de canal de la llesca 1 ja té: capçalera (estat + toggle),
credencials, publicacions recents (taula unificada, llesca 2),
diagnòstics (buit). Aquestes 4 seccions s'hi afegeixen, condicionades per
canal via el descriptor.

---

## Secció 1 — Newsletter

### Què existeix
- **Setmanes consolidades** = files a `TopSetmanal(territori='PPCC', setmana=X)`. **No hi ha cap flag «consolidat»**: l'existència de files ÉS la consolidació (mateix predicat a `generar_esborrany_newsletter.py:56`, `newsletter_brief.py:136`, `enviar_newsletter.py:65`).
  - Llistar totes les setmanes per al selector:
    ```python
    TopSetmanal.objects.filter(territori="PPCC") \
        .values_list("setmana", flat=True).distinct().order_by("-setmana")
    ```
    Índex compost `(territori, setmana, posicio)` a `ranking/models.py:350` ho cobreix barat.
- **Generador reutilitzable sense efectes**: `comptes/newsletter.py::build_draft_text(tipus, territori, setmana, publish_date, entries)` → `(subject, narrative_html)` (`:237`). No escriu DB, no fa `mark_used`. És el que usa el command.
- **`NewsletterDraft`** (`comptes/models.py:608`): camps `tipus, territori, setmana, subject, narrative_html, estat, font, editat, enviat_at`; unique `(tipus, territori, setmana)`. Estats: `pendent` (per defecte; «s'enviarà»), `enviat`, `cancellat`. Font: `motor` | `llm`. **Opt-out**: no hi ha estat «aprovat».
- **Endpoints staff** (`web/api/staff/newsletter.py`), tots accepten `?setmana=`:
  - GET/PATCH `/staff/newsletter/esborrany/` (llegir/editar; PATCH només si `pendent`),
  - POST `…/cancellar/`, POST `…/preview/` (HTML complet, render-only).
  - El GET ja retorna `newsletter_actiu = cfg.pot_publicar("newsletter")`.
- **Indicador en viu «es pot generar ara?»**: `comptes/newsletter_brief.py::build_brief(setmana)` retorna `status='ready'|'not_ready'` segons existència de `TopSetmanal(PPCC, setmana)`. Accepta `setmana` explícita.
- **Cadència cron** (`deploy/cron.topquaranta`): dissabte 08:00 `calcular_top` consolida; dissabte rutina LLM deixa draft (`font=llm`); dissabte 16:00 `generar_esborrany_newsletter` (fallback motor, idempotent); diumenge 10:00 `enviar_newsletter`.

### Què falta
- **No hi ha endpoint staff per GENERAR un esborrany sota demanda.** Tots els existents llegeixen/editen/cancel·len/previsualitzen un draft que JA existeix (GET fa 404 si no n'hi ha — `newsletter.py:90`). La creació només passa pel cron (motor, només-aquesta-setmana) o la rutina al núvol (token, només-aquesta-setmana via `current_monday()`).
- **El command `generar_esborrany_newsletter` està blocat a la setmana actual**: només accepta `--dry-run`, calcula `setmana = avui - weekday` (`:54`). No accepta `--setmana`.

### Seam per generar sota demanda per a una setmana triada
Replicar els 3 passos del command amb `setmana` arbitrària, dins un nou endpoint `IsStaff` (p. ex. `POST /staff/newsletter/esborrany/generar/?setmana=`):
1. Guard: `TopSetmanal.objects.filter(territori="PPCC", setmana=chosen).exists()`.
2. Entrades: `from social import payload; payload.build_top("PPCC", chosen)["entries"]`.
3. Text: `build_draft_text("top_ppcc", "PPCC", chosen, chosen + timedelta(days=5), entries)`.
4. Persistir amb `update_or_create` + guards de no-clobber (no sobreescriure `editat=True` ni estats terminals `enviat`/`cancellat`) — reusar la lògica de `web/api/newsletter_routine.py:94-121`.

> Aquest endpoint NOU és l'únic codi backend que la secció Newsletter
> requereix; tota la resta (selector, preview, edició, indicador) reusa
> el que ja hi ha.

---

## Secció 2 — KPIs per canal

### Inventari real (EXISTEIX / PARCIAL / FALTA)

| Canal | Enviaments | Membres/Subscriptors | Abast (reach) | Seguidors (sèrie) |
|---|---|---|---|---|
| **Instagram** | EXISTEIX | n/a | EXISTEIX (per-post) | EXISTEIX |
| **Mastodon** | EXISTEIX | n/a | **FALTA** | EXISTEIX |
| **Bluesky** | EXISTEIX | n/a | **FALTA** | EXISTEIX |
| **Telegram** | EXISTEIX | EXISTEIX (`members`) | **FALTA** | EXISTEIX (`members` sèrie) |
| **Newsletter** | EXISTEIX | EXISTEIX (subscriptors) | PARCIAL (camp `clicks` sense cablejar) | n/a (escalar, sense sèrie) |
| **RSS** | **FALTA** | **FALTA** | **FALTA** | **FALTA** |
| **GSC** (pseudo-canal) | n/a | n/a | EXISTEIX (impressions) + clicks | n/a |

### D'on surt cada família
- **Enviaments**: `SocialPost(status=publicat)` agrupat per `platform` (`web/api/staff/analytics.py:137`) + `social_estat_canals` ja dona `ultim_enviament` per canal (`web/api/staff/social/posts.py:152`, mapa `_CHANNEL_ESTAT`).
- **Subscriptors/membres**:
  - Newsletter: `PerfilUsuari.objects.filter(vol_newsletter=True, usuari__is_active=True).count()` → ja exposat com `newsletter_audience` (`analytics.py:176`). **Correcció de doc**: el flag és a **`PerfilUsuari`** (`comptes/models.py:352`), NO a `Usuari` com diu CLAUDE.md. Escalar, sense sèrie temporal.
  - Telegram: `members` via `getChatMemberCount` → `MetricaSocialPlatform(platform='telegram', metric='members')`, sèrie diària.
- **Abast**: `MetricaSocialPost.reach`/`impressions`, però **només Instagram** el retorna de veritat. Mastodon/Bluesky/Telegram → 0 silenciós (els clients no demanen reach / l'API no l'exposa).
- **Seguidors**: `MetricaSocialPlatform(metric='followers')` sèrie diària per IG/Mastodon/Bluesky (+ Telegram com `members`). Ja exposat com `social_metrics.followers_series` (`analytics.py:217`) i graficat a `StaffAnalyticsPage.jsx` SocialTab.
- **GSC** (cerca orgànica com a pseudo-canal): `MetricaSEOQuery` (impressions/clicks/ctr/position), endpoint separat `analytics_seo`. Site-wide.

### Què falta / advertències
- **RSS: zero KPIs de cap mena** (pull-based, sense `SocialPost`). Qualsevol KPI RSS seria aspiracional.
- **Reach només real a Instagram.** Un strip «abast per canal» mostraria 0 a la resta.
- **Newsletter sense sèrie de seguidors** ni mètriques d'obertura/clic (Brevo stats no cablejat). El camp `MetricaSocialPost.clicks` existeix però mai s'escriu.
- **Telegram engagement per-post sempre 0** (Bot API).

---

## Secció 3 — Control de què publica cada canal

### Veredicte: **implícit al codi, NO configurable**
No hi ha cap matriu canal×tipus: ni camp de model, ni setting a `ConfiguracioGlobal`, ni dict constant. La decisió es calcula en runtime des de:
1. **`social/calendari.py::CALENDARI`** (`:57-119`) — taula `(weekday → platform → tipus → territori → min_fase)`, **només Instagram**. Cada slot és `instagram_feed` o `instagram_story`. Cap fila menciona Mastodon/Bluesky/Telegram/Newsletter/RSS.
2. **`publicar_canal.py:95-99`** (Mastodon/Bluesky/Telegram) — únic filtre per-canal del codi, i NO és per-canal: `slots = [... if s.platform == instagram_feed]`. Conseqüència: els tres publiquen **tots** els tipus «feed» del calendari (`top_ppcc`, `top_territorial`, `nous_singles`, `nous_albums`). No es pot dir «Telegram: només tops».
3. **`enviar_newsletter.py:36-37`** — newsletter hard-codeja `TIPUS="top_ppcc"`, `TERRITORI="PPCC"`. Ignora el calendari.
4. **`web/feeds.py`** — RSS: dos `Feed` fixos (top PPCC 12 setmanes; novetats 30 dies).

`fase_distribucio` (1-5) **només gateja Instagram** (`publicar_social._handle_slot:172`); `publicar_canal` no la llig (asimetria: a fase 1, Telegram encara publicaria tots els tipus si està actiu).

Controls staff actuals (només on/off): `distribucio_activa` (mestre), `*_actiu` per canal, `fase_distribucio` (IG), `delay_*_min`, `story_max_cancons_ppcc`. `pot_publicar(canal) = distribucio_activa AND <canal>_actiu`.

### Què falta / seam per fer-ho un control
Cal una matriu `{canal, tipus} → bool` (nou model `SocialChannelTipus` o JSON a `ConfiguracioGlobal`), llegida un cop per run i intersectada amb `slots_for`:
- **`publicar_canal.py:95-99`** — seam principal (Mastodon/Bluesky/Telegram): substituir el filtre `instagram_feed` per `… and matrix_allows(channel, s.tipus)`. Ja itera `(channel, slot)`.
- **`publicar_social.py:119-178`** — seam Instagram (al costat del gate `fase_distribucio`; cal dimensió story).
- **`enviar_newsletter.py:36`** — newsletter és cas especial (no calendari; només `top_ppcc`).
- **`web/feeds.py`** — RSS: muntar/desmuntar feeds (com el kill-switch `rss_actiu`).
- Etiquetes canòniques dels eixos: `SocialPost.{PLATFORM,TIPUS}_CHOICES` + `CHANNEL_SWITCH_FIELDS` (`ranking/models.py:209`).

> El calendari segueix sent la font de SCHEDULING; la matriu seria la font
> de ROUTING per sobre. Decisió de pes (nou model/migració + cablar 4
> publishers): **proposta only**, fora d'aquesta sessió read-only.

---

## Secció 4 — Analítica de posts

### Models (`analytics/models.py`)
- **`MetricaSocialPost`** (`:128`) — sèrie per `(socialpost, data)`. FK real a `SocialPost` (`related_name="metriques"`). Camps: `likes, replies, shares, reach, impressions, clicks, raw (JSON), fetched_at`. Propietat `total_engagement = likes+replies+shares`.
- **`MetricaSocialPlatform`** (`:189`) — gauge per `(data, platform, metric)`, EAV. `metric` ∈ {`followers`, `following`, `posts_total`, `members`}. **No** lligat a `SocialPost`.

### Cobertura per plataforma (què retorna `get_post_metrics`)
| Plataforma | likes | replies | shares | reach | impressions |
|---|---|---|---|---|---|
| Instagram feed | ✅ | ✅ | ✅ | ✅ | ✅ (deprecat per Meta en alguns tipus → 0) |
| Instagram story | ❌ | ✅ | ❌ | ✅ | ✅ (~24h) |
| Mastodon | ✅ | ✅ | ✅ (reblogs) | ❌ | ❌ |
| Bluesky | ✅ | ✅ | ✅ (repost+quote) | ❌ | ❌ |
| Telegram | ❌ | ❌ | ❌ | ❌ | ❌ (Bot API, sempre 0) |
| Newsletter | — sense handler — | | | | |

### Enllaç amb `SocialPost`
- FK directa (`MetricaSocialPost.socialpost`); el cron resol l'id extern per plataforma des de `SocialPost`: IG `instagram_media_id`; Mastodon/Bluesky `metadata.external_id`; Telegram `metadata.message_ids[0]`.

### Cobertura/freqüència
- Cron `recollir_metrics_social` **22:30 UTC diari**, `SingletonLock("analytics_metrics_social")`. Idempotent (`update_or_create`), **fail-open** (WARNING, no trip a `tq-health`).
- **Finestra 30 dies** (`LOOKBACK_DAYS=30`): només refresca posts amb `published_at >= avui-30d`. Sense backfill. Account-stats sempre (gauge diari).

### GSC / PSI (no per-canal)
- `recollir_metrics_gsc` → `MetricaSEOQuery` (impressions/clicks/ctr/position per query+page). Site-wide SEO.
- `recollir_metrics_psi` → `MetricaCWV` (Core Web Vitals per url×{mobile,desktop}). Site-wide rendiment.
- Cap dels dos lliga amb `SocialPost` ni té dimensió de canal. Contextual, no per-canal (excepte tractar GSC com a pseudo-canal de cerca orgànica).

### Què ja s'exposa (per no duplicar)
`web/api/staff/analytics.py::analytics_summary` ja dona: `social[]` (enviaments per platform/tipus), `social_omes[]`, `newsletter_audience`, `social_metrics.{followers_series, latest_platform, top_posts}`. SocialTab de `StaffAnalyticsPage.jsx` ho grafica **global** (no per-canal). El `raw` JSON de tots dos models es desa però **no es llegeix** enlloc — escapatòria per a extres específics de plataforma sense migració.

### Què falta
- `impressions`/`clicks` per-post i `following`/`posts_total` es recullen però no s'exposen.
- No hi ha **cap vista per-canal** d'analítica avui (només KPIs globals + taula plana de top-posts). Una vista de canal hauria de filtrar `metriques` per `socialpost__platform`.
- Newsletter i Telegram són els forats estructurals (newsletter sense files de mètrica; Telegram només `members`).

---

## Proposta d'esquema de descriptor de 4 seccions

Estén el `channelDescriptors.jsx` de la llesca 1 (que ja té
`key/nom/switchField/payloadKey/platforms/auth`). Cada canal declara quines
de les 4 seccions mostra i amb quina font; la `ChannelView` pinta cada
secció des del descriptor (afegir canal/secció = ampliar descriptor, no
nova pàgina). Forma proposada (per-canal, valors `null` = secció oculta):

```js
{
  key: 'mastodon',
  // … (auth de la llesca 1) …

  // Secció 2 — KPIs (strip de capçalera). Cada KPI declara la seva font;
  // 'missing' es renderitza com a "—" honest, no com a 0 fals.
  kpis: {
    enviaments:  { source: 'social_estat_canals' },     // tots els canals (excepte RSS)
    seguidors:   { source: 'followers_series', metric: 'followers' },
    abast:       { source: 'metrica_post.reach', status: 'missing' }, // IG: 'exists'
    membres:     null,                                   // Telegram: {metric:'members'}; Newsletter: {source:'newsletter_audience'}
  },

  // Secció 3 — Control canal×tipus. De moment READ-ONLY (reflecteix la
  // realitat implícita); editable quan existeixi la matriu (seam §3).
  control: {
    editable: false,                                     // true quan hi hagi SocialChannelTipus
    tipus: ['top_ppcc','top_territorial','nous_singles','nous_albums'], // el que publica avui
    nota: 'feed-only; tots els tipus del calendari',
  },

  // Secció 4 — Analítica de posts. Quines mètriques té sentit mostrar.
  analytics: {
    available: ['likes','replies','shares'],             // IG afegeix reach/impressions; Telegram: []
    source: 'metrica_post', filter: 'socialpost__platform__in',
    window_days: 30,
  },

  // Secció 1 — Newsletter (només canal newsletter).
  newsletter: null,
}
```

Per al canal **newsletter** la secció 1 substitueix bona part de la resta:
```js
newsletter: {
  weekList: 'TopSetmanal PPCC distinct setmana desc',
  generateSeam: 'POST /staff/newsletter/esborrany/generar/?setmana=  (endpoint NOU)',
  canGenerate: 'build_brief(setmana).status === "ready"  (o .exists() barat)',
  draftEndpoints: ['GET/PATCH /staff/newsletter/esborrany/', '…/cancellar/', '…/preview/'],
  channelGate: 'cfg.pot_publicar("newsletter")',
}
```

### Aplicabilitat per canal (quines seccions té sentit pintar)

| Canal | 1 Newsletter | 2 KPIs | 3 Control | 4 Analítica |
|---|---|---|---|---|
| Instagram | — | enviaments·seguidors·abast | tipus (feed+story) | likes·replies·shares·reach·impressions |
| Mastodon | — | enviaments·seguidors | tipus (feed) | likes·replies·shares |
| Bluesky | — | enviaments·seguidors | tipus (feed) | likes·replies·shares |
| Telegram | — | enviaments·membres·seguidors | tipus (feed) | **buit** (Bot API) |
| Newsletter | **completa** | enviaments·subscriptors | només `top_ppcc` | **buit** (sense mètriques) |
| RSS | — | **buit** | feeds fixos | **buit** |

### Resum del que cal de codi (per a les llesques 3-4)
- **Secció 1 (Newsletter)**: 1 endpoint NOU `POST /staff/newsletter/esborrany/generar/?setmana=` (reusa `build_draft_text` + guards de `newsletter_routine`). Tota la resta reusa l'existent.
- **Secció 2 (KPIs)**: cap backend nou — reusa `social_estat_canals` + `analytics_summary`. Frontend: strip per-canal que degrada «—» on `status:'missing'`.
- **Secció 3 (Control)**: READ-ONLY ara (reflecteix la realitat). Editable = decisió de pes (nou model/migració + cablar 4 publishers) → proposta, no en aquestes llesques sense l'OK explícit.
- **Secció 4 (Analítica)**: backend nou petit — un endpoint o param que filtri `MetricaSocialPost` per `socialpost__platform`; el model i el cron ja existeixen.

### Banderes vermelles a no amagar
- **Abast**: real només a IG → marcar «—» a la resta, mai 0.
- **RSS**: sense dades; la vista de canal hauria de dir-ho explícitament.
- **Telegram/Newsletter analítica**: buides per disseny d'API; secció 4 oculta, no buida-amb-zeros.
- **Doc-drift**: `vol_newsletter` és a `PerfilUsuari`, no a `Usuari` (CLAUDE.md desactualitzat).
- **Control canal×tipus editable** = nou model + migració + 4 publishers → STOP/decisió abans d'implementar.
