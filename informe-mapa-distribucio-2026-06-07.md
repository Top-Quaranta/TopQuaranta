# Mapa read-only de la capa de distribució

Data: 2026-06-07. Read-only (codi + BD prod). Cap canvi de codi ni dades.

---

## 1. Controls de pausa

### 1.1 El botó de pausa "principal" — abast REAL: només Instagram

- **Frontend**: `web-react/src/pages/staff/StaffSocialPage.jsx` — la card gran "Kill switch" crida `toggle()` (línies 72-78), que fa `POST /staff/social/toggle/` amb `{ actiu: !config.instagram_actiu }` i **sense `channel`**. La seva etiqueta llegeix `config.instagram_actiu`.
- **Endpoint**: `web/api/staff/social/controls.py::social_toggle` — `channel = request.data.get("channel") or "instagram"` (per defecte `instagram` quan no s'envia channel, que és el cas del botó principal) → escriu el camp `instagram_actiu`.
- **On viu el flag**: `ranking/models.py::ConfiguracioGlobal.instagram_actiu` (BooleanField, default True). El help-text del model l'anomena "Kill switch **global**", però **no ho és**: l'únic consumidor és `publicar_social.py` (Instagram). No existeix cap camp `pausa_global` a `ConfiguracioGlobal`.

**Veredicte: CONFIRMAT** — el botó "principal" només escriu `instagram_actiu` i només gateja Instagram. El nom/etiqueta ("Kill switch global") és enganyós; el camp real (`instagram_actiu`) és honest.

### 1.2 Toggles de pausa per canal

Mateix endpoint `social_toggle`, però amb `channel` explícit (`toggleChannel(channel)` a StaffSocialPage.jsx). `field_map` a controls.py:

| Channel (arg) | Camp ConfiguracioGlobal | Default |
|---|---|---|
| instagram | `instagram_actiu` | True |
| mastodon | `mastodon_actiu` | False |
| bluesky | `bluesky_actiu` | False |
| telegram | `telegram_actiu` | False |
| newsletter | `newsletter_actiu` | False |
| rss | `rss_actiu` | True |

### 1.3 Taula canal → flag(s) que el gategen → estat efectiu (valors EN VIU a prod 2026-06-07)

| Canal | Flag(s) consultats abans d'enviar | On (file:line) | Valor prod | Estat efectiu |
|---|---|---|---|---|
| Instagram feed/story | `instagram_actiu` (early return) + per-slot `fase_distribucio ≥ min_fase` | `publicar_social.py:96,166` | `instagram_actiu=**f**`, `fase=5` | **PAUSAT** |
| Mastodon | `mastodon_actiu` | `publicar_canal.py:65,70` | `t` | Actiu |
| Bluesky | `bluesky_actiu` | `publicar_canal.py:66,70` | `t` | Actiu |
| Telegram | `telegram_actiu` | `publicar_canal.py:67,70` | `t` | Actiu |
| Newsletter | `newsletter_actiu` (i prou; `send_top_newsletter` no llegeix cap flag) | `publicar_canal.py:68,70`; `comptes/newsletter.py:237-281` | `t` | **Actiu** |
| RSS | `rss_actiu` | `ranking/models.py:154` | `t` | Actiu |

Notes:
- `publicar_canal.py` (mastodon/bluesky/telegram/newsletter) consulta **NOMÉS** el seu `*_actiu` per canal (dict a línies 64-72). No consulta mai `instagram_actiu` ni cap pausa global.
- `fase_distribucio` / `min_fase` **NO és una pausa**: és el desplegament per fases NOMÉS d'Instagram (marca slots com `omès` a `publicar_social.py:166-171`). `publicar_canal` no aplica fases.
- `send_top_newsletter` (newsletter.py:237-281) un cop invocat envia incondicionalment a `Usuari.objects.filter(perfil__vol_newsletter=True)` — cap flag de ConfiguracioGlobal a dins.

### 1.4 Diagnòstic del misteri de la pausa (resolt amb dades en viu)

Estat de `ConfiguracioGlobal` a prod: `instagram_actiu=f`, `mastodon_actiu=t`, `bluesky_actiu=t`, `telegram_actiu=t`, `newsletter_actiu=t`, `rss_actiu=t`.

Evidència de `SocialPost` (`max(published_at)` per plataforma):
- `instagram_feed` → **2026-06-03**, `instagram_story` → **2026-06-03** (parats des d'aleshores).
- `mastodon` → 2026-06-06 09:40, `bluesky` → 09:50, `telegram` → 09:55, **`newsletter` → 2026-06-06 10:00**.

**Causa:** algú va prémer el botó "principal", que va posar `instagram_actiu=False`. Això **només** gateja Instagram (per això no hi ha posts IG després del 06-03). El dissabte 06-06 la newsletter (i mastodon/bluesky/telegram) van sortir igualment perquè el seu camí (`publicar_canal --channel newsletter`) consulta **`newsletter_actiu` (=True)** i mai `instagram_actiu`. El botó "principal" i la newsletter estan cablejats a dos camps booleans diferents. Per parar la newsletter cal prémer el toggle **per canal** de Newsletter (escriu `newsletter_actiu=False`); el botó etiquetat "Kill switch" no pot fer-ho.

---

## 2. Traçabilitat d'enviaments

### 2.1 Inventari

| Senyal | Què registra | Granularitat | Fiabilitat per a "últim enviament per canal" |
|---|---|---|---|
| **`SocialPost.published_at`** (max per `platform`, `status=publicat`) | Timestamp de publicació real d'un slot | per (platform, tipus, territori, setmana); UNIQUE | **El més fiable.** Cobreix les 6 plataformes (incl. newsletter). Caveats: (a) IG = 2 plataformes (`instagram_feed` + `instagram_story`); (b) `republicar`/`reset` posa `published_at=NULL` (`posts.py:344,409,477`) → esborra l'últim-enviament d'aquell slot |
| **`StaffAuditLog`** `*_publicat` | Esdeveniment append-only de publicació | per esdeveniment, per canal | Fiable i append-only (sobreviu al reset). Actor sempre None (cron). Els **deletes NO** es registren → sobrecompta vs estat viu. Bo per "quan va publicar per últim cop el canal X" |
| Cron status `publicar_canal_<canal>.status` / `publicar_social.status` (post-#156) | Últim **RUN** (exit code/hora) | per variant de comanda (per canal des de #156) | **Fràgil per a "últim enviament":** OK també per a `omès`/ja-publicat/no-op. Diu que el cron viu, no que va sortir contingut |
| `MetricaEsdeveniment(social_publicat)` | +1 per publicació | per (dia, canal, tipus) | Comptador diari sense timestamp d'esdeveniment; ara **vestigial** (l'`analytics_summary` deriva de SocialPost) |
| `analytics_summary.social[]` | Compte d'slots publicats en finestra | per (platform, tipus), **només compte** | **No exposa cap timestamp** (`Count` group-by). No pot respondre "últim enviament" |

### 2.2 Què hi ha i què falta

- **Una fila SocialPost per (canal, slot)** via `get_or_create` UNIQUE(platform, tipus, territori, setmana). `status=publicat` + `published_at=now()` els escriuen `publicar_social.py` (IG) i `publicar_canal.py:206-217` (mastodon/bluesky/telegram **i newsletter** — la newsletter SÍ crea fila SocialPost). RSS NO té fila SocialPost.
- **Publicacions auditades** a StaffAuditLog (`social_publicat`, `{mastodon,bluesky,telegram,newsletter}_publicat`); deletes/republicar/reset **no** auditats (`posts.py` no importa `log_staff_action`).
- **Forat:** no hi ha cap camp/endpoint que mostri "últim enviament per canal". `analytics_summary.social[]` és només compte; `social_list` torna files, no un max per canal. Font autoritzada recomanada: `max(SocialPost.published_at) GROUP BY platform WHERE status='publicat'`, amb `StaffAuditLog *_publicat` (max `created_at`) com a fallback a prova de reset. **NO** usar el cron `last_run` (és hora de run, no de publicació).

---

## 3. Camí de contingut de la newsletter (per al pilot de rutines)

### 3.1 Cadena motor → composer → text → context → enviament

1. **Motor** `social/narrative/`: `detect_all(territori, setmana)` (`scenarios.py:759-775`) → llista de `Scenario` (13 detectors a1-a13 + fallback), ordenats per severitat. Bancs de frases a `banks/`, anti-repetició via `social.NarrativePhraseUsage` (`registry.py`).
2. **Composer de newsletter** `social/narrative/composers/newsletter.py::compose(scenarios, entries, *, territori, setmana)` (línies 62-155) → dict amb `narrative_part`, `text`, `hashtags`, `cta`, `phrase_ids`.
3. **`comptes/newsletter.py::_build_top_context`** (137-234), recipient-independent, **compost UN cop per run**:
   - imports (164-165): `from social.narrative import detect_all` + `composers import newsletter as nl_composer`.
   - (167-183): `scenarios = detect_all(...)`; `engine_out = nl_composer.compose(...)`; construeix `narrative_html` a partir de `engine_out["narrative_part"]`.
   - subject (187-191): `derive_subject(hero, week)` (`comptes/newsletter_meta.py:136-158`, banc de frases per code) o fallback `"Setmana N · Top Global"`.
   - tot dins `try/except` (159,184-185): si el motor peta, `narrative_html=""` + subject genèric i la newsletter surt igualment.
   - retorna `(context, subject)`; `narrative_html` i `subject` van dins `context`.
4. **`send_top_newsletter`** (237-281): `base_context, subject = _build_top_context(...)` (248-250); després loop per destinatari (255-279) que renderitza `comptes/templates/comptes/email_newsletter_top.html` + `unsub_url` i envia.

`mark_used` (anti-repetició) NO es crida en compondre; es crida després d'una publicació reixida des de `publicar_canal.py:229-237`. Per tant `_build_top_context` és **sense efectes secundaris** sobre el registre → segur per a generar esborranys.

### 3.2 El SEAM d'inserció per a la rutina (esborrany + gate de revisió humà)

**El punt net és la frontera entre `_build_top_context` i el loop de destinataris, dins `send_top_newsletter` — `comptes/newsletter.py:248-255`.**

A 248-250 el text editorial ja és **dues cadenes discretes i independents del destinatari** en un sol punt:
- `subject`
- `base_context["narrative_html"]`

Tot el que hi ha sota 255 és fan-out per destinatari (render + send). Una rutina faria:
- **(a) generar sense enviar:** cridar `_build_top_context(...)` i parar (sense efectes secundaris; `mark_used` no s'hi crida).
- **(b) persistir per revisió:** desar `subject` + `narrative_html` (o tot `base_context`) en un model d'esborrany nou, keyed per (tipus, territori, setmana). Punt de captura: just després de 250.
- **(c) gate de l'enviament:** condicionar el loop 252-279 a un `approved` sobre l'esborrany; si un humà edita el text, alimentar el `narrative_html`/`subject` editat al loop en lloc de re-compondre.

Subtilesa: `engine_out["phrase_ids"]` (els pids realment enviats) els descarta `_build_top_context` (no els retorna). Si el gate envia text pre-capturat directament (sense passar per `publicar_canal`), caldria cridar `mark_used` per a aquests pids manualment → requeriria exposar `phrase_ids` (canvi petit). Si l'aprovació re-dispara el camí normal `publicar_canal`, el registre ja funciona sol.

### 3.3 Inventari de canals (confirmat)

| Canal | Constant `SocialPost.PLATFORM_CHOICES` | Publisher |
|---|---|---|
| Instagram Feed | `instagram_feed` | `publicar_social.py::_publish_feed` |
| Instagram Stories | `instagram_story` | `publicar_social.py::_publish_story` |
| Mastodon | `mastodon` | `publicar_canal.py::_publish_mastodon` |
| Bluesky | `bluesky` | `publicar_canal.py::_publish_bluesky` |
| Telegram | `telegram` | `publicar_canal.py::_publish_telegram` |
| **Newsletter (pública)** | `newsletter` | `publicar_canal.py::_publish_newsletter` → `comptes/newsletter.py::send_top_newsletter` |
| RSS | (sense fila SocialPost) | feeds `/rss/{top,novetats}.xml` |

**La newsletter pública de veritat** és `newsletter` / `send_top_newsletter` (HTML a tots els `Usuari` amb `perfil__vol_newsletter=True`). **`enviar_digest_setmanal` NO és la newsletter de subscriptors**: és el digest de KPIs en **text pla** a `admin@topquaranta.cat` via `mail_admins()` (cap motor narratiu, cap plantilla HTML, cap fan-out per subscriptor).

---

## Resum executiu

- **Botó "principal" = `instagram_actiu`, només Instagram.** El nom "Kill switch global" enganya; no hi ha pausa global.
- **Misteri resolt (amb dades en viu):** IG parat des del 06-03 (`instagram_actiu=f`) però newsletter + mastodon/bluesky/telegram van sortir el 06-06 perquè cada canal consulta el seu propi `*_actiu` (tots True) i mai `instagram_actiu`.
- **Traçabilitat:** font fiable = `max(SocialPost.published_at) per platform (status=publicat)` + `StaffAuditLog *_publicat` com a fallback; **falta** un endpoint/UI que ho mostri; el cron `last_run` no serveix.
- **Seam per a la rutina:** `comptes/newsletter.py:248-250` (després de `_build_top_context`, abans del loop d'enviament) — `subject` + `narrative_html` ja són cadenes discretes capturables; generar via `_build_top_context` és sense efectes secundaris.

Cap acció presa (read-only).
