# Investigació outreach/SEO — estat, evidència i fets (2026-06-14)

> **Fase 1 de 2. Document inert (només lectura + spec).** No conté
> recomanacions d'implementació: només estat actual amb evidència
> `file:line`, números reals de producció, superfície de canvi exacta
> per a la fase 2, veredictes de viabilitat amb prova, make-or-breaks
> i decisions pendents per a en Miquel.
>
> Protocol d'escèptic: cada claim de capacitat porta l'output cru de la
> comanda que el prova. Les consultes a prod s'han fet via SSH
> (`sudo -u topquaranta`, `DJANGO_SETTINGS_MODULE=topquaranta.settings.production`,
> `apps.get_model(...)`). Secció final de *unknowns* i *decisions*.

## Nota de layout (corregeix els sub-agents)

El codi viu a l'**arrel** del repo (`~/Claude/TopQuaranta/`). **No existeix
cap directori `app/`.** Prova:

```
$ ls -d app 2>&1
ls: app: No such file or directory
$ ls -d */
analytics/ bin/ comptes/ deploy/ docs/ ingesta/ music/ ranking/
redisseny-baseline/ scripts/ social/ territory_logos/ topquaranta/
vendor/ web-react/ web/
```

Totes les rutes d'aquest doc són relatives a l'arrel (p. ex.
`web/seo/jsonld.py`, no `app/web/seo/jsonld.py`).

---

## WS0 — Mesura honesta

### Estat actual (evidència)

**AnalyticsMiddleware.** Viu a `analytics/middleware.py`. En fase de
resposta, per a GET/HEAD públics 2xx/3xx escriu dos esdeveniments via
`register()`:

- `analytics/middleware.py:80-86` → `register("pageview", dim1=request.path[:80])`
- `analytics/middleware.py:88-94` → `register("utm_landing", dim1=utm_source, dim2=utm_campaign)`

**MAKE-OR-BREAK — el User-Agent NO es guarda.** El model
`MetricaEsdeveniment` té exactament 4 camps de dades i cap d'UA:

- `analytics/models.py:39` `data` (DateField)
- `analytics/models.py:40-44` `clau` (CharField 80)
- `analytics/models.py:45-54` `dimensio_1` (CharField 80)
- `analytics/models.py:55-60` `dimensio_2` (CharField 80)
- `analytics/models.py:61` `comptador` (PositiveIntegerField)

Exclusió deliberada documentada a `analytics/middleware.py:15-20`
("User-Agent string (could fingerprint)"). **Conseqüència de fet:
l'històric de pageviews NO es pot reclassificar bot/humà** perquè no hi
ha cap columna d'UA ni cap font derivada a la fila. La reclassificació
només és possible cap endavant (canviant la instrumentació) o creuant
amb els logs de Caddy (que sí tenen UA però roten per mida; veure sota).

**register().** `analytics/events.py:50-66`: data = `timezone.localdate()`
(zona local del servidor); upsert atòmic `get_or_create` + `F("comptador")+n`;
fail-open (`events.py:67-86`).

**Matcher `@bot` de Caddy.** `deploy/Caddyfile:143-146`, definició exacta:

```
@bot {
    header_regexp User-Agent (?i)(googlebot|google-inspectiontool|google-richresultstest|google-pagerenderer|googleother|adsbot-google|bingbot|bingpreview|duckduckbot|yandexbot|applebot|baiduspider|slurp|mastodon|pleroma|akkoma|misskey|bluesky|slackbot|telegrambot|whatsapp|facebookexternalhit|twitterbot|linkedinbot|discordbot|skypeuripreview|gptbot|claudebot|perplexitybot|bytespider|amazonbot|chatgpt-user|cohere-ai|anthropic-ai|aria/|ia_archiver|petalbot|seznambot|vkshare|w3c_validator|developers\.google\.com)
    path / /top /artistes /mapa /com-funciona /artista/* /album/* /canco/* /territori/* /comarca/* /decada/* /genere/* /top/*
}
```

Acció: `handle @bot { reverse_proxy 127.0.0.1:8083 }` (`deploy/Caddyfile:147-149`).

**KPIs del dashboard staff.** `web/api/staff/analytics.py`, endpoint
`analytics_summary()` (`:65-326`):
- pageviews: `:99-107` top-20 paths per `Sum("comptador")` amb `clau="pageview"`.
- events: `:87-96` totals diaris per `clau`.
- social: `:126-149` deriva de `SocialPost` (status=publicat, setmana≥), NO del comptador `social_publicat`.

**Instrumentació d'esdeveniments SPA.** Helpers a
`web-react/src/lib/analytics.js:79-93` (`trackPageview`, `trackEvent`).
Allowlist d'ingesta a `web/api/analytics_ingest.py:31-42`. Call sites:
- `escolta_click` → `web-react/src/components/ExternalListenLinks.jsx:129`
- `directori_filter` → `web-react/src/pages/ArtistesPage.jsx:127`
- `search_query` → `web-react/src/pages/ArtistesPage.jsx:137` (dim1 hardcoded `'artistes'`)
- `newsletter_signup` → `web-react/src/pages/ComptePerfilPage.jsx:78`
- **`mapa_zoom` → NO es dispara.** Prova (grep arrel, exclòs node_modules):
  ```
  $ grep -rn "mapa_zoom" . --include=*.py --include=*.jsx --include=*.js | grep -v node_modules
  web-react/src/lib/analytics.js:29: *   mapa_zoom          dim1 = level (...)   # comentari
  web/api/analytics_ingest.py:40:        "mapa_zoom",  # allowlist
  $ grep -rn "trackEvent" web-react/src/pages/MapaPage.jsx
  (cap resultat)
  ```
  → Només comentari + allowlist; cap call site. Els 90 events `mapa_zoom`
  vistos a prod (30d) són **residu d'un build anterior** que tenia el
  call site, ara eliminat.

### Números reals

**Pageviews 30d per tipus de path** (consulta ORM, prod):
```
Pageviews 30d=48885 sobre 7015 paths distints (7.0/path)
  /canco/*        30557  (62.5%)
  /album/*        10198  (20.9%)
  /artista/*       6074  (12.4%)
  (altres)           822  (1.7%)
  / (home)           434  (0.9%)
  sitemap*.xml       311  (0.6%)
  /top*              201  (0.4%)
  /artistes           75  (0.2%)
Long-tail (entitat+sitemap+rss+geo) = 47353 (96.9%)
Core (home+top+artistes+altres)     =  1532 (3.1%)
```

**Split bot/humà via regex `@bot` sobre logs Caddy** (output cru):
```
Finestra logs: 2026-06-09T19:49:08 -> 2026-06-14T19:22:49   (~5 dies)
TOTAL requests: 30923  | bot 12956 (41.9%) | no-bot 17967 (58.1%)
Pàgines públiques de contingut (GET): 12493
  bot:            11209 (89.7%)
  no-bot (humà):   1284 (10.3%)
Top bots: googlebot 7634, bingbot 1839, applebot 1345, gptbot 1225,
          amazonbot 279, yandexbot 239, googleother 102,
          facebookexternalhit 52, bytespider 50, claudebot 48
```

**GoAccess `--ignore-crawlers`** (panell `general` del report
`/var/cache/topquaranta/goaccess/report.html`, generat 2026-06-14 01:30,
output cru):
```
total_requests   3882
valid_requests   2758
failed_requests  2
unique_visitors  78
date_time        2026-06-14 01:30:02 +0200
```

**Comparació de les dues fonts (divergeixen — es reporta):** mesuren coses
diferents. El regex `@bot` és **més estret** que la base de crawlers de
GoAccess (que inclou heurístiques de versió de navegador + un catàleg
ampli), per això sobre el total de requests el regex deixa 17.967
"no-bot" mentre GoAccess només valida 2.758. Sobre pàgines de contingut,
el regex dona 1.284 no-bot, del mateix ordre que GoAccess. **Ambdues
fonts coincideixen en el fet de fons: el trànsit humà és una minoria
petita** (~78 visitants únics i ~10% de les peticions de contingut en
una finestra de ~5 dies; ~15 únics/dia). Coherent amb els events SPA
(escolta_click 53, search_query 14 en 30d).

**GSC 28d (fins 2026-06-11)** (output cru):
```
Posició   impr    clk
1-3         30      0
4-10      5442     30
11-20     1573      6
21+       1492      5
TOTAL     8537     41   (CTR 0.48%)
BRANDED (conté 'quaranta'): impr=0  clk=0
NO-BRANDED:                 impr=8537 clk=41
URLs distintes amb ≥1 impressió (28d): 1059
Cobertura ≈ 18.2% del catàleg (artistes 2235 + cançons_verif 3570) té impressions
```

### Superfície de canvi (fase 2)
- Instrumentació pageview: `analytics/middleware.py:80-86`,
  `analytics/events.py:34-86`, model `analytics/models.py:28-61`.
- Allowlist SPA: `web/api/analytics_ingest.py:31-42`; helpers
  `web-react/src/lib/analytics.js:79-93`.
- KPIs dashboard: `web/api/staff/analytics.py:65-326`.

### Make-or-breaks
- **UA no emmagatzemat** → cap reclassificació retroactiva possible (provat).
- **`mapa_zoom` mort al codi actual** → events de prod són residu.

### Unknowns WS0
- Finestra exacta de GoAccess: el cron diu "últims 30 dies" però els logs
  roten per mida i només n'hi ha ~5 dies a disc → la finestra efectiva de
  GoAccess és ambigua (≤ contingut del fitxer apuntat). No verificat quin
  conjunt de fitxers concret llegeix `generar_goaccess` en cada execució.
- No s'ha pogut calcular un split bot/humà a 30 dies des de logs (només
  ~5 dies disponibles).

---

## WS1 — Motor editorial SEO

### Estat actual (evidència)

Les cinc rutes **existeixen i estan implementades** (SSR + meta + template):

| Ruta | URL | View | Meta | JSON-LD | Template |
|---|---|---|---|---|---|
| `/top` | `topquaranta/urls.py:61` | `web/seo/views.py:138-194` | `web/seo/meta.py:125-144` `for_top()` | `web/seo/jsonld.py:274-301` `MusicPlaylist` | `web/templates/seo/top.html` |
| `/territori/<codi>` | `topquaranta/urls.py:78-80` | `web/seo/views.py:505-569` | inline `:532-548` | `breadcrumbs_jsonld()` `:549-556` | `web/templates/seo/territori.html` |
| `/genere/<slug>` | `topquaranta/urls.py:92-95` | `web/seo/views.py:720-785` (404 si <3 artistes) | inline `:751-765` | `breadcrumbs_jsonld()` `:766-773` | `web/templates/seo/genere.html` |
| `/decada/<decada>` | `topquaranta/urls.py:87-90` | `web/seo/views.py:655-715` (404 si <5 cançons) | inline `:681-698` | `breadcrumbs_jsonld()` `:699-702` | `web/templates/seo/decada.html` |
| `/mapa` | `topquaranta/urls.py:69` | `web/seo/views.py:814-842` | `web/seo/meta.py:309-321` `for_mapa()` | `breadcrumbs_jsonld()` `:837-838` | `web/templates/seo/mapa.html` |

Arquitectura comuna: `Meta` dataclass (`web/seo/meta.py:50-75`), `_trim(text,160)`
(`:98-104`); títol/descr injectats a `web/templates/seo/_base.html:7-8`;
blocs JSON-LD a `_base.html:35-38`.

### Números reals — rendiment GSC d'aquestes pàgines (28d, output cru)
```
tipus        impr    clk   #URLs
/canco       3896     17     365
/album       2441     14     194
/artista     2105     10     479
/genere        40      0      10
/artistes      24      0       2
/comarca       14      0       4
(home)         10      0       1
/top            4      0       1
/territori      2      0       2
/decada         1      0       1
```
**Fet:** les pàgines editorials (`/top`, `/territori`, `/genere`,
`/decada`, `/mapa`) existeixen però reben ~0 impressions; tota la
visibilitat SEO viu a les pàgines d'entitat (`/canco`, `/album`,
`/artista` → 8.442 de 8.537 impressions).

### Pipeline de prosa de la newsletter (per reutilitzar, NO reinventar)

Dos punts d'entrada:
- **Engine fallback (comanda):**
  `comptes/management/commands/generar_esborrany_newsletter.py:43-109`;
  compon via `comptes/newsletter.py:334-351` `build_draft_text(tipus,
  territori, setmana, publish_date, entries) -> (subject, narrative_html)`;
  persisteix `NewsletterDraft` `font=FONT_MOTOR`.
- **Rutina cloud (primària):** `web/api/newsletter_routine.py`
  - `GET /api/v1/newsletter-routine/brief/` (`:64-76`) — auth Bearer HMAC
    constant-time (`:34-46`); retorna `build_brief(setmana)`
    (`comptes/newsletter_brief.py:187-400`) que inclou `editorial_veu`
    (`:377`), `top10`, `top40`, `fets_grup`, `fet_lider`, `fets_destacats`,
    `actualitat` (RSS VilaWeb best-effort).
  - `POST /api/v1/newsletter-routine/esborrany/` (`:79-143`) — upsert del
    draft (`font=FONT_LLM`, `estat=pendent`); idempotent (refusa
    sobreescriure `ENVIAT`/`CANCELLAT` `:101-107` i edits staff
    `editat=True` `:110-113`); notifica admin (`:133`).

**Veu editorial.** `ranking/models.py:251-259`:
```python
editorial_veu = models.TextField(
    blank=True, default="",
    help_text="Prompt de veu editorial per a la rutina de newsletter. "
              "Servit dins el brief; editable des de Configuració. "
              "Buit = la rutina no genera res.")
```
Accés: `ConfiguracioGlobal.load().editorial_veu` (singleton
`ranking/models.py:308-311`).

### Superfície de canvi (fase 2)
- Pàgines editorials: `web/seo/views.py` (`top_seo`, `territori_seo`,
  `genere_seo`, `decada_seo`, `mapa_seo`) + `web/seo/meta.py` +
  `web/seo/jsonld.py` + templates `web/templates/seo/*.html`.
- Reutilitzar prosa: endpoints `web/api/newsletter_routine.py` +
  `comptes/newsletter_brief.py:187-400` + camp `editorial_veu`.

### Make-or-breaks / Unknowns WS1
- Make-or-break: les editorials no necessiten crear-se de zero (existeixen);
  el fet és que **no reben impressions**, no que faltin.
- Unknown: causa exacta de la invisibilitat (contingut prim vs novetat vs
  manca d'enllaços interns) — no determinable només des del codi/GSC.

---

## WS2 — Enllaçat intern

### Estat actual (evidència)
**Model `ArtistaLastfmSimilar`** `music/models.py:730-798`: FK `source`
(`related_name="similars_recomanats"`), FK `target`
(`related_name="recomanat_per"`, resolt via taula d'alias), `last_seen`,
`match` (0-1). `UniqueConstraint(source,target)` +
`Index(target)`. Cache denormalitzat `Artista.nb_similars_lastfm`
(`music/models.py:367`).

**Enllaços interns existents (JA presents).** Templates SSR:
- `web/templates/seo/artista.html`: àlbums `:25`, cançons `:39`, àlbum-en-cançó
  `:40`, **artistes similars `:50`** (`/artista/<slug>`).
- `web/templates/seo/album.html`: artista `:5`,`:9`; tracks `:27`.
- `web/templates/seo/canco.html`: artista `:5`,`:9`; àlbum `:10`; col·laboradors `:31`.

React: `web-react/src/pages/{ArtistaPage,AlbumPage,CancoPage}.jsx` amb `<Link>`.

### Números reals (output cru)
```
ArtistaLastfmSimilar files: 29961
Arestes source+target ambdós aprovats (enllaços interns útils): 15072
Artistes APROVATS amb ≥1 similar APROVAT: 1207 (54.0%)
```

### Make-or-break / Fet
- La cobertura de dades per a "artistes relacionats" és **alta** (54% dels
  aprovats tenen ≥1 similar aprovat; 15.072 arestes útils) i **els similars
  JA es mostren** a la pàgina SSR d'artista (`artista.html:50`). No és una
  capacitat per construir sinó existent.

### Unknowns WS2
- No verificat si la pàgina React d'artista (SPA, no SSR) mostra similars
  amb la mateixa cobertura que el template SSR.

---

## WS3 — GEO + structured data

### Estat actual (evidència)

**Builders JSON-LD** `web/seo/jsonld.py` — types produïts: `WebSite` +
`Organization` (`:73`,`:96`, amb `SearchAction`/`EntryPoint`),
`MusicGroup` (`:108-205`), `MusicAlbum` (`:208-238`), `MusicRecording`
(`:241-271`, + `AudioObject` si hi ha preview `:270`), `Place` (`:173`),
`MusicPlaylist` (`:274-301`), `BreadcrumbList`/`ListItem` (`:304-319`).

**`sameAs` JA EXISTEIX (contradiu el supòsit del brief).** Prova (grep cru):
```
$ grep -n "sameAs\|_social_links" web/seo/jsonld.py
46:def _social_links(a: Artista) -> list[str]:
102:                "sameAs": list(settings.SOCIAL_PROFILES),
178:    sameas = _social_links(a)
180:        data["sameAs"] = sameas
```
`_social_links()` (`:46-70`) recull spotify/viasona/web/bandcamp/youtube/
viquipedia/soundcloud/tiktok/facebook/instagram/twitter + MusicBrainz si
hi ha MBID. **Excepció:** en mode `minimal=True` (`:118-126`) NO s'inclou
`sameAs`.

**IDs externs a la BD — cobertura real** (sobre 2.235 artistes aprovats,
output cru):
```
spotify_id:      1990 (89.0%)
musicbrainz_id:   890 (39.8%)
instagram_url:    293 (13.1%)
≥1 deezer_id:    2235 (100.0%)
youtube_url:      134 (6.0%)
web_url:          318 (14.2%)
bandcamp_url:     148 (6.6%)
viquipedia_url:    32 (1.4%)
spotify_url:        4 (0.2%)
viasona_url:        1 (0.0%)
qualsevol àncora (spotify/mbid/deezer): 2235 (100.0%)
```
Camps: `Artista.spotify_id` `music/models.py:129`, `Artista.musicbrainz_id`
`:288-295`, URLs socials `:264-277`; Deezer via M2M `ArtistaDeezer`
`music/models.py:581-598` (`deezer_id`, `principal`); `Album.spotify_id`/`deezer_id`
`:870-871`; track-level `SpotifyMetadata` `:1567-1653`.

**Sitemap + lastmod.** `web/sitemaps.py`: `lastmod` emès a `ArtistesSitemap`
(`:67-89`, `obj.updated_at`), `AlbumsSitemap` (`:92-120`), `CanconsSitemap`
(`:123-140`), `TopHistoricSitemap` (`:158-187`, `setmana`). Les estàtiques
(`StaticSitemap`, `TerritorisSitemap`, `ComarquesSitemap`, `DecadesSitemap`,
`GeneresSitemap`, `TerritorisLandingSitemap`) NO emeten lastmod.

**robots.txt** `web/templates/web/robots.txt`:
```
User-agent: *
Disallow: /staff/
Disallow: /compte/
Disallow: /api/
Sitemap: https://www.topquaranta.cat/sitemap.xml
```

**IndexNow + servei de fitxers a l'arrel.** Clau actual
`8f4c2e5b3a9d7c1f6e0b8a5d4c2e9f7b`. Servida via Django TemplateView a
`topquaranta/urls.py:43-48`:
```python
path("8f4c2e5b3a9d7c1f6e0b8a5d4c2e9f7b.txt",
     TemplateView.as_view(template_name="seo/indexnow_key.txt",
                          content_type="text/plain")),
```
i enrutada per Caddy dins el matcher `@django` que llista el path explícit
(`deploy/Caddyfile:113-114`, dins `@django` `:108-126` → `reverse_proxy 127.0.0.1:8083`).
Lògica IndexNow a `web/seo/indexnow.py`.

**E-E-A-T.** Dates de publicació visibles (parcial): `album.html:10`,
`canco.html:11`, `artista.html:27`; en JSON-LD `datePublished`
(`jsonld.py:226,264`) i `dateModified` (`:286`). **Absents** (prova per
grep): autor/byline i citacions/referències — no hi ha camp d'autor a cap
model ni markup "escrit per". Enllaços externs marcats `rel="nofollow"`.

### Viabilitat servir `/BingSiteAuth.xml` (PROVAT)
El patró exacte ja funciona per a la clau IndexNow → **viable**. Superfície:
(1) afegir `path("BingSiteAuth.xml", TemplateView.as_view(template_name=...,
content_type="application/xml"))` a `topquaranta/urls.py`; (2) afegir
`path /BingSiteAuth.xml` dins el matcher `@django` de `deploy/Caddyfile`
(zona `:108-124`); (3) crear el template amb el contingut públic exacte:
```xml
<?xml version="1.0"?><users><user>A78E91EF0C51198850E147ED177F6129</user></users>
```
`tq-sync-infra` instal·la el Caddyfile en desplegar; valida amb `caddy
validate` abans.

### Make-or-breaks WS3
- **`sameAs` ja present** (no és feina nova; només mode minimal l'omet).
- Cobertura `instagram_url` baixa (13,1%) — limita sameAs/IG; spotify (89%)
  i deezer (100%) altes.

### Unknowns WS3
- No verificat si la SPA (Helmet) emet `sameAs` igual que l'SSR, o si el
  mode `minimal` s'usa en alguna ruta pública real.

---

## WS4 — Distribució + citació

### Estat actual (evidència)

**MAKE-OR-BREAK — no hi ha camp d'email a `Artista`.** Prova (grep cru):
```
$ grep -n "email" music/models.py
1373: ("usuari_reenviar_verificacio", "Usuari: reenviar email de verificació")
1376: "Usuari: enviar email de reset de contrasenya"
1444: who = self.actor.email if self.actor_id else "(deleted user)"
```
Cap dels 3 és un camp d'email d'artista (són choices d'audit-log + auth).
L'únic email assolible és indirecte: `Artista` → `UserArtista.usuari`
(`comptes/models.py:48`) → `Usuari.email` (AbstractUser).

**Senyal "artista entra al top".** `posicio_anterior` **NO és un camp
emmagatzemat** però **es computa** comparant amb la setmana prèvia:
- `web/api/top_views.py:57` `_serialize_entry(..., posicio_anterior=None)`;
  `:310` `_latest_week_positions(territori)`; `:354` `_prev_week_positions(...)`.
- `web/api/home_views.py:98,148,217-240`.
- `ranking/algorisme.py:353-360` calcula `posicio_anterior` i `canvi`.
`TopSetmanal` (top oficial) s'escriu a
`ranking/management/commands/calcular_top.py` (bulk dels `(canco,territori,
setmana,posicio)`). **Entrada nova = cançó al top d'aquesta setmana amb
`posicio_anterior is None`.** El hook natural per disparar un email és
post-càlcul a `calcular_top` reusant `_prev_week_positions`.

**Infra d'enviament newsletter.** `comptes/newsletter.py:403-457`
`send_top_newsletter(...)`; itera `Usuari.objects.filter(perfil__vol_newsletter=True)`;
salta `if not user.email`; SMTP per-usuari amb unsub signat. Consentiment
RGPD: `PerfilUsuari.vol_newsletter` + `consent_newsletter_at`
(`comptes/models.py:352-353`). Idempotència: `NewsletterDraft.estat`
(`ESTAT_ENVIAT`) + `UniqueConstraint(tipus,territori,setmana)`
(`comptes/models.py:683-686`); `enviar_newsletter.py:92-96` salta si ja
enviat (`--force` per re-enviar). **No hi ha tracking per-destinatari.**

**View staff "artistes sense instagram" (plantilla a replicar).**
`web/api/staff/artistes.py:89-245` `artistes_list()`. Filtre IG `:145-149`
(`?instagram=no` → `Q(instagram_url="")|Q(instagram_url__isnull=True)`).
Anotació `n_top` opcional `:195-222` (subqueries principal+collab amb
`Count("id", distinct=True)` sobre `TopSetmanal`), sort `-n_top` `:236-237`.

**`comptes/notifications.py`** (best-effort, swallow+log `:30`). Punts
d'entrada:
- admin: `notify_admins_nova_solicitud_gestio` `:95`,
  `notify_admins_nova_proposta` `:110`, `notify_admins_nou_feedback` `:125`,
  `notify_admins_nova_sollicitud_revisio` `:218`.
- usuari: `notify_user_solicitud_resolta(accio)` `:145`,
  `notify_user_proposta_resolta(accio)` `:190`,
  `notify_gestor_sollicitud_revisio_resolta` `:243`,
  `notify_user_feedback_resolt` `:261`.

**Mètriques agregades per a "Estat de la música en català 2026".**
`analytics/management/commands/snapshot_pipeline.py` escriu gauges a
`MetricaPipeline` (`analytics/models.py:86-126`): `cancons_verificades`,
`cancons_pendents`, `cancons_rebutjades_acumulades`, `artistes_aprovats`,
`artistes_pendents` (`:61-72`); `cobertura_whisper`, `cobertura_mb`
(`:75-95`); `usuaris_actius`, `newsletter_subscriptors`, `directori_visibles`
(`:98-109`); `cancons_per_territori` (dim1=codi) (`:112-123`).

### Números reals (output cru)
```
UserArtista totals: 3
UserArtista verificat+aprovat: 3
Artistes aprovats amb gestor verificat (email assolible): 3 (0.1%)
Emails de gestor distints assolibles: 3
```

### Make-or-break WS4 (FORT)
- **Cap camp d'email a `Artista` + només 3 artistes (0,1%) amb email
  assolible** (via gestor verificat). Qualsevol feature d'"email a
  l'artista quan entra al top" arriba avui a **3 artistes**. La font
  d'emails caldria decidir-la (vegeu decisions).

### Unknowns WS4
- No verificat si `calcular_top` ja calcula/desa internament les entrades
  noves (només s'ha confirmat que `_prev_week_positions` viu a la capa API,
  no dins `calcular_top`).
- No verificat si existeix cap font d'emails d'artista fora del model
  (full de càlcul, scraping d'instagram_url, etc.).

---

## WS5 — Comunicació (gating de publicació)

### Estat actual (evidència)
Comandes: `social/management/commands/publicar_social.py` (Instagram) i
`publicar_canal.py` (Mastodon/Bluesky/Telegram/Newsletter). Gating en 3
nivells:
- Mestre: `ConfiguracioGlobal.distribucio_activa` `ranking/models.py:174-179`.
- Per-canal: `*_actiu` `:182-213` (instagram=True, mastodon/bluesky/telegram/
  newsletter=False, rss=True per defecte).
- Per (canal×tipus): `MatriuPublicacio.actiu_per()` `:532-540` (fail-open:
  fila absent = True).
Mètodes: `pot_publicar(canal)` `:272`, `pot_publicar_tipus(canal,tipus)` `:285`.
Enforcement: `publicar_social.py:91-103` (mestre+canal) i `:178-181` (matriu
→ `_record_omes`). Assets de campanya encaixarien a la capa renderer/captions
(després de `payload.build_*`, abans de l'API). **Res a canviar en fase 1.**

### Unknowns WS5
- Cap addicional rellevant per a l'abast d'aquesta investigació.

---

## TRANSVERSAL — tests, CI, desplegament (on penjar guards a la fase 2)

### Estat actual (evidència)
- **pytest** `pytest.ini:1-17` (`--ds=topquaranta.settings.test`,
  `python_files = tests/test_*.py`). 119 fitxers de test; SQLite en memòria;
  HTTP extern mockejat.
- **Guards SEO** `web/tests/test_seo.py`: títols únics `:113`, JSON-LD
  MusicGroup `:123`, 404 no-verificat/no-aprovat `:132,:140`, thin
  200+noindex `:156`, sitemap exclou thin `:227`, breadcrumbs `:261`,
  canonical absolut `:271`, hreflang ca `:278`, no fuita de comentaris
  `:352`, IndexNow key file `:345`, sitemap-index llista seccions `:327`.
- **Guards captions** `social/tests/test_captions.py`:
  `test_no_positional_hashtag_in_any_channel` `:336`,
  `test_handle_only_on_instagram_feed` `:377`.
- **Guards renderer** `social/tests/test_renderer_*.py` (format JPEG, <500KB,
  presència de píxels; NO hi ha diff visual/pixel-snapshot).
- **CI** `.github/workflows/ci.yml`: jobs `tests` (pytest + `manage.py check`),
  `caddyfile` (validate), `lint` (black+isort), `frontend-tests` (vitest),
  `migrations` (`makemigrations --check`), `destructive-migrations` (warn).
- **CI docs** `.github/workflows/ci-docs.yml`: `markdownlint`, `link-checker`
  (offline), `spec-path`, **hard gates** `docs-coherence` `:83-141`,
  `docs-novelty` `:143-159`, `docs-size` `:161-175`.
- **docs-map** `docs/policies/docs-map.yml`: `web/seo` → `docs/architecture/seo.md`;
  `analytics/` → `docs/architecture/analytics.md`. `docs-size` scope =
  `docs/architecture/` + `docs/ops/` (llindar 400) — **`docs/seo/` NO hi és**,
  aquest doc no està sota el gate de mida.
- **Deploy** `.github/workflows/deploy.yml`: push a `main`, `paths-ignore`
  inclou `docs/**` i `*.md` → **un canvi només-doc/spec NO desplega**. Ordre
  segur a `bin/tq-deploy` (pull → `tq-sync-infra` → migrate → npm build →
  reload → smoke `/` i `/api/v1/top/?territori=PPCC`).

### Implicació fase 2
- Tocar `web/seo/` exigeix actualitzar `docs/architecture/seo.md` (o override
  `docs-reviewed:` al cos del PR); tocar `analytics/` exigeix
  `docs/architecture/analytics.md`. Tests/migracions queden exempts del gate.

---

## UNKNOWNS GLOBALS (tot el que no s'ha pogut confirmar)
1. Finestra temporal efectiva de GoAccess (logs roten per mida; només ~5
   dies a disc). No s'ha pogut fer cap mètrica humà/bot a 30 dies des de logs.
2. Causa de la invisibilitat GSC de les pàgines editorials (prim vs novetat
   vs enllaços) — no determinable des de codi/GSC sols.
3. Si la SPA (Helmet) replica `sameAs` i el comportament thin/noindex
   idènticament a l'SSR (només verificat a SSR + endpoint `/api/v1/seo/`).
4. Si `calcular_top` desa internament les entrades noves o només es deriven
   a la capa API.
5. Existència de qualsevol font d'emails d'artista fora del model de dades.
6. Cobertura de similars a la pàgina React d'artista (vs SSR, confirmada).
7. Origen real dels 90 events `mapa_zoom` de prod (hipòtesi: build anterior;
   no verificat a l'historial de git/desplegaments).

## DECISIONS PER A EN MIQUEL
1. **Font d'emails d'artista (WS4, bloquejant per a qualsevol email outreach
   a artistes).** Avui 0,1% assolible. Opcions de fet observades: (a) afegir
   camp d'email a `Artista`; (b) derivar de `UserArtista.usuari.email`
   (només 3); (c) una altra font externa. Cal decidir-ho abans de qualsevol
   feature d'email a artistes.
2. **`sameAs` ja existeix** (WS3): cal decidir si l'abast de la fase 2 sobre
   structured data canvia, ja que el supòsit inicial ("absència de sameAs")
   no es compleix.
3. **Mètrica de visites del dashboard** (WS0): decidir si es vol una mètrica
   humà-neta (no hi ha UA històric; només cap endavant o via logs de ~5d).
4. **Reclassificació històrica impossible** (WS0): assumir que qualsevol
   sèrie "humana" comença des de la data del canvi d'instrumentació, no
   retroactiva.
5. **Pàgines editorials existeixen però invisibles** (WS1): l'abast de la
   fase 2 és optimització/contingut, no creació.

---

*Investigació read-only. Cap canvi de codi, migració ni escriptura a prod.
Únics fitxers escrits: aquest doc + scratch de treball.*
