# Panell staff · la superfície d'API

> Sub-àrea d'[`staff.md`](staff.md), separada el 2026-08-17 quan el
> document principal va passar el llindar de 400 línies
> (`docs-maintenance.md` regla 3). Ací viu la taula d'endpoints i el
> comportament de cada PATCH; el control d'accés, els invariants i
> la superfície de React es queden al document índex.

## 3. API surface (`web/api/staff_views.py`)

All endpoints are under `/api/v1/staff/` and return JSON. Shared helpers:
`_paginate(qs, request)` returns `(page, meta)` where `meta` is
`{page, num_pages, total, per_page, has_next, has_previous}`.

### Dashboard & estat
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/dashboard/` | Landing counters (artistes pendents, cançons no verificades, propostes, sol·licituds, feedback, usuaris). |
| GET | `/staff/estat/` | Full system health: BD inventory, Whisper coverage, ranking, cron status, ML model stats + feature importances, weekly flux + target. |

### Pendents (auto-discovered artists)
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/pendents/?q=&page=` | Pending artists with `nb_verif` annotation. |
| POST | `/staff/pendents/<pk>/aprovar/` | Body: `{deezer_id?, municipi_id? \| manual?}`. Approves, clears `pendent_review`. **Deezer gate (2026-06):** rejects with 400 unless the artist ends with ≥1 `ArtistaDeezer` (existing or supplied) — Deezer, not "Deezer or MBID" — mirroring the localitat check. A `deezer_id` already owned by another artist → 409 with `owner_pk`. |
| POST | `/staff/pendents/<pk>/descartar/` | **Tombstones** (never deletes): sets `aprovat=False, pendent_review=False`. The row leaves the queue but survives, so the Last.fm similar resolver matches it instead of re-creating the pendent (the resurrection loop, audit 2026-06-02 — see `docs/architecture/pipeline.md` §3.8). Applies to every source, not just `lastfm_similar`. |

### Artistes
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/artistes/` | Filters: `q`, `aprovat`, `deezer`, `territori`, `instagram`, `youtube`,
`al_top`. **`instagram=pendent` (2026-08)** és el tercer estat, bessó de
`youtube=pendent`: sense URL **i** sense revisar, **i amb ≥1 cançó viva**
(com a principal o col·laborador) — un artista sense res a etiquetar no és
feina pendent. El desempat del sort `-n_top` és tops → vives → **cançó més
nova** (l'artista que acaba de traure single va primer: la publicació de
«nous singles» és l'única oportunitat d'etiquetar-lo) → alfabètic. `instagram=no` conserva
el sentit antic (simplement no té URL) perquè els cridadors existents no
es moguen sota els peus. **`instagram=rebutjat`** llista els artistes el
compte dels quals Meta ha refusat en publicar. Aquests **també** tornen a
`pendent`: el camp es buida en refusar-lo (és públic) i el valor antic va
a `instagram_rebutjat_url`, que la cua mostra perquè l'operador sàpiga
que busca un compte NOU i no que l'artista no en tinga. Each row carries `te_homonims` (another artista shares the name modulo accents + punctuation). **`al_top=1` (Fase 2 D2):** restrict to artistes in the latest weekly PPCC top (social-tagging workflow); with it (or `include_gestor_email=1`) each row also carries `te_gestor_email` — whether the artist has a reachable verified-manager email (the D1 alert audience). **`include_n_top=1`** annotates two counts (both via distinct scalar subqueries, principal + collaborator paths, so they never Cartesian-inflate): `n_top` (distinct `TopSetmanal` rows) and `n_cancons_vives` (distinct live cançons — `verificada=True, activa=True` — where the artist is principal or collaborator; the two paths are disjoint per cançó by the D5 signal, so no overlap correction). **`sort=-n_top`** (the "artistes sense Instagram" queue) orders `n_top` desc → `n_cancons_vives` desc → alphabetical, so novetats artists (0 tops, live songs) surface at the top of their block. |
| POST | `/staff/avisos-top/enviar/` | Run the `enviar_avisos_top` command (Fase 2 D1/F2). Body `{send: bool, setmana?}`. **DRY-RUN by default**; `send=true` does the real send (all dedup/preference guards live in the command). Streams the command stdout back. |
| — | *(filtre `youtube`, 2026-08)* | `pendent` / `revisat`, sobre `Artista.youtube_canal_revisat`. **Tres estats, no dos:** un artista revisat i confirmat com a «no té canal propi» està FET, no pendent, i no ha de tornar a la cua per sempre (Malalts no en té). Alimenta `/staff/artistes/sense-youtube`. El PATCH de
`youtube_canal_oficial` accepta id, URL `/channel/` **o handle**
(`youtube.com/@nom`): YouTube va deixar d'ensenyar l'id `UC…` enlloc, i
exigir-lo feia la cua inservible. Es resol al servidor amb
`channels.list?forHandle=` (1 unitat) i es **refusa amb 400 si el canal
és l'automàtic** («- Topic» / «- Tema») **quan l'artista ja en té un**:
és un error fàcil, perquè la cerca el sol posar primer, i acceptar-lo
comptaria l'Art Track dues vegades i perdria el carril del videoclip.
Si l'artista **no** en té cap, en canvi, s'adopta al carril de l'Art
Track i s'aparellen les cançons a l'acte (2026-08-17): `search.list`
enterra els canals nous i menuts, i abans no hi havia cap manera de
donar-los des del panell — el cas DUPLICATS es va haver d'arreglar per
consola. L'aparellament ha de ser immediat perquè `_cua()` només visita
artistes amb `youtube_channel_id` buit. La resposta porta `avis` amb
l'explicació; el camp del videoclip es queda buit.
Cada fila porta `youtube_provat` per a distingir «encara no s'ha mirat»
de «no en té». |
| GET | `/staff/artistes/search/?q=` | Typeahead for pickers. Returns up to 10 results. |
| POST | `/staff/artistes/crear/` | Body: `nom`, `lastfm_nom?`, `deezer_id?`. |
| GET/PATCH | `/staff/artistes/<pk>/` | Detail + replace-semantics PATCH over `nom`, `lastfm_nom`, `genere`, `percentatge_femeni`, `aprovat`, social URLs, `localitats[]`, `deezer_ids[]`, `youtube_canal_oficial` + `youtube_canal_revisat`,
`instagram_suggerit` (provisional; posar `instagram_url` el neteja).
Descartar el suggeriment (PATCH amb valor buit) mou el handle a
`instagram_suggerits_descartats`, la llista de vetats que el sembrador
nocturn no torna a proposar; acceptar NO veta. **One transaction (2026-06):** the `aprovat=True` flip is deferred until after the localitat + Deezer writes, then gated (rejects 400 without ≥1 Deezer or localitat). A `deezer_ids[]` entry already owned by another artist now returns **409** with `owner_pk` (was a silent no-op); the rollback leaves nothing half-written. **Homonym marker (2026-06-11):** GET also returns `homonims[]` — other artistes with the same `nom_normalitzat` (name modulo accents + punctuation), each with `{pk, nom, slug, aprovat, localitats, deezer_ids, n_cancons_verificades}`. The edit page shows an amber warning so reviewers are careful before approving / assigning songs (the Crim case: same name, different bands). |

### Cançons
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/cancons/` | Filters: `q`, `verificada`, `ml_classe`, `whisper`, `deezer`, `sort`, `artista_pk`. The row's `artista` carries `te_homonims` (shown as a "⚠ homònim" badge in the workbench). |
| POST | `/staff/cancons/accio/` | Bulk `aprovar` / `rebutjar` with `motiu`. `artista_incorrecte` → cascades to `rebutjar_artista`; `album_incorrecte` → `rebutjar_album`. |
| GET/PATCH | `/staff/cancons/<pk>/` | Detail + PATCH incl. `artista_pk` reassignment + `artistes_col_pks` replace + `spotify_url` (manual Spotify track id, see below). |

**Manual Spotify id (`spotify_url`, 2026-06-02).** PATCH accepts a
Spotify track URL / `spotify:track:` URI / bare 22-char id. Store-and-trust:
format validated by `web/api/staff/_spotify_url.py::parse_track_id` (base62,
22 chars; album/artist/playlist refs → 400) with **no Spotify API call**. On
success the id is written to `SpotifyMetadata.spotify_id` with
`enrichment_status='manual'`, `enriched_at=NULL` (mirrored to legacy
`Canco.spotify_id`): Process A puts it in playlists at once and Process B
hydrates it from the id without `/search` (see `playlists.md` "Manual links +
hydration"). Accepted only when no id is set (fill-when-empty); an id already
on another canço → 400 (pre-check + an `IntegrityError` fallback for the
race); `spotify_url=""` clears back to `not_attempted`. `_canco_row` exposes
the link under `spotify` with `is_manual` and a `hydration` state
(`pending`/`ok`/`failed`).

### Albums
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/albums/` | List with `n_cancons` / `n_verificades` annotations, filter by `tipus`, `descartat`, `artista_pk`. |
| GET/PATCH | `/staff/albums/<pk>/` | Detail incl. track list with per-track collab map. PATCH accepts `artista_pk` + `cascade_cancons` to also re-point tracks. |

### Top (provisional)
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/top/?territori=CAT` | Top-40 provisional + territori list + motius. Each entry carries `escoltes_setmanals` (raw weekly plays) plus `escoltes_efectives` + `soft_cap_aplicat` — the post-soft-cap effective plays, derived read-only from the persisted score via the SAME `web/api/canco_views.py::_derive_plays_eff` the per-cançó `TopBreakdownPanel` uses (equals the raw value when the cap left the row uncompressed). |
| POST | `/staff/top/accio/` | Bulk `rebutjar_canco` / `rebutjar_artista` with `motiu`. |
| GET | `/cancons/<slug>/top-breakdown/` | Algorithm transparency for one Canço. **Public endpoint**, but the payload differentiates by viewer (anonymous → only territoris where the song currently sits in `TopProvisional`; staff or `UserArtista.verificat=True` over the song's main artist → also the eligible-territori list with theoretical scores for ones the song hasn't broken into yet). Returned shape per entry: `{territori, nom_territori, posicio, escoltes_setmanals, dies_des_del_llancament, age_factor, past_top_penalty_pct, monopoli_album_pct, monopoli_artista_pct, score_final, setmanes_al_top, is_at_top}`. Theoretical entries set `posicio: null` and `is_at_top: false` and exclude the monopoli post-process (would require re-running the per-artist pass). Sprint E, 2026-04-25. |

The legacy paths `/staff/ranking/` + `/staff/ranking/accio/` and the
sibling `/staff/cancons/<pk>/ranking/` stay alive as POST-safe aliases
(no redirect) per Sprint Naming Consolidation, 2026-04-25 — same view
at the new + old URLs.

### Propostes (user proposals) & Sol·licituds (management requests)
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/propostes/` | Filter by `estat`. |
| GET | `/staff/propostes/<pk>/` | Detail (justificació, localitzacions, Deezer IDs, social). |
| POST | `/staff/propostes/<pk>/aprovar/` | Creates the Artista in one transaction. |
| POST | `/staff/propostes/<pk>/rebutjar/` | Marks rejected. |
| GET | `/staff/solicituds/` | UserArtista list. |
| POST | `/staff/solicituds/<pk>/toggle/` | Toggle verificat. |
| POST | `/staff/solicituds/<pk>/rebutjar/` | Mark rejected. |

### Distribució multi-canal (`/staff/social`)

Six channels share the same `SocialPost` model. The staff surface is
split (distribution-views redistribution, 2026-06): the cockpit at
`/staff/social` (master switch + channel grid), per-channel views at
`/staff/social/<canal>`, and the **unified publications table** at
`/staff/social/publicacions` (house kit, filters + deep links). The
channel views embed that same table scoped to their channel.

| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/social/` | Publications list — paginated via `_paginate` (default 50, cap 200) with filters (`canal`, `estat`, `tipus`, `setmana`), free-text `q` (platform/tipus/territori), and `sort` (`data`\|`setmana`\|`canal`\|`estat`). Default order: `published_at` (nulls-last → `created_at`). Each row carries a best-effort clickable `url` (`_public_url`: Mastodon status URL, Bluesky AT-URI → `bsky.app/profile/<did>/post/<rkey>`, Telegram `metadata.url`; IG only if a permalink was stored — no Graph call; newsletter none). Also returns the channel + per-credential payloads the cockpit/channel views consume. |
| GET | `/staff/social/metrics-summary/` | Per-platform engagement totals (additive, 2026-06). Sums the LATEST `MetricaSocialPost` snapshot of each post grouped by `SocialPost.platform`: `{"per_platform": [{platform, n_posts, likes, replies, shares, reach, impressions, clicks}]}` sorted by platform. Read-only and decoupled from the row list (no `_serialize` change, no N+1); posts with no snapshot yet don't contribute. Feeds the `MetricsStrip` above the publications table. |
| POST | `/staff/social/preview/` | Render dry-run for a slot; returns the rendered PNG paths. |
| POST | `/staff/social/publicar-ara/` | Force-run `publicar_social` / `publicar_canal` for a `(data, tipus, platform)` triple. |
| POST | `/staff/social/eliminar-instagram/` | Legacy IG-only delete. Kept for back-compat. |
| POST | `/staff/social/eliminar-remot/` | **(2026-05-03)** Platform-aware delete. Dispatches by `post.platform` to `instagram_client` (DELETE Graph node), `mastodon_client.delete_status`, `bluesky_client.delete_post` (parses AT URI → deleteRecord), or `telegram_client.delete_messages` (uses `metadata.message_ids` captured at publish time). **Telegram té N missatges per publicació i cap esborrat de grup**, així que quan `message_ids` no hi és —posts anteriors al 2026-05-03, que només deixen la URL— només s'esborra el PRIMER missatge del carrusel i la resta es queden al canal. Des del 2026-08-15 això es diu explícitament al missatge de resposta en lloc de reportar-se com un èxit net: la fila es reinicia igualment i els altres ids es perden per sempre, així que l'operador ha d'anar a esborrar-los a mà. La fila NO es toca si l'esborrat remot falla (si no, quedaria publicada fora i pendent ací, i el cron següent la republicaria). |
| POST | `/staff/social/toggle/` | Distribution switch. `channel=global` writes the master `distribucio_activa`; `channel=instagram\|mastodon\|bluesky\|telegram\|newsletter\|rss` writes the per-channel switch. `channel` is REQUIRED (2026-06-07: removed the default-to-`instagram` footgun). See `social.md` for the gate. |
| GET | `/staff/social/matriu/` | **(2026-06)** Distribution matrix (third gate, `MatriuPublicacio`): `{canals, tipus, dies, cells:[{canal, tipus, actiu, dies_publicacio, seeded}]}`. `dies_publicacio` is a read-only list of weekday ints derived from the calendar/cron (`publish_weekdays_for`; newsletter=Sunday, `[]`=N/A). Non-seeded combos report `seeded=False`. See `social.md`. |
| POST | `/staff/social/matriu/toggle/` | **(2026-06)** Set one matrix cell. Body: `canal`, `tipus`, `actiu?` (defaults to flipping). Only seeded cells; `actiu=False` on (newsletter × top_ppcc) stops the Sunday send. The publish DAY is not editable here (calendar-derived indicator). |
| GET | `/staff/social/invitacions/` | **(2026-07-13, ADR-0015 §5.5)** The IG collaborator-invitation registry, newest first (no pagination — ≤3 rows per feed post). Each row: artista, `username`, `ig_media_id`, `tipus`, `data_invitacio`, `estat`, `data_resolucio`. |
| POST | `/staff/social/invitacions/acceptar/` | **(2026-07-13)** Mark one invitation accepted (`estat=acceptada` + `data_resolucio=now`; body `id`). The ONLY manual resolution — no manual reject exists (the 14-day `caducada` expiry covers silence and rejection alike). Idempotent on an already-accepted row; allowed from `caducada` (observed truth wins). Audit action `collab_invitacio_acceptada`. |
| GET | `/staff/social/estat-canals/` | **(2026-06-07)** Honest per-channel state: `efectiu` (actiu / pausat_global / pausat_canal) + raw `mestre_actiu`/`canal_actiu` + `ultim_enviament` = max `SocialPost.published_at` (status=publicat) with `StaffAuditLog *_publicat` as a reset-proof fallback (`font`=socialpost\|audit\|none). |
| GET | `/staff/social/spotify/estat/` | Spotify integration health (OAuth identity, playlists with per-playlist sync/`target_coverage`, cron silenced flag). **(2026-06)** also `enrichment_coverage` = catalog-wide `{total, enriched, ratio}`: of active Cançons with an ISRC (the `enriquir_spotify` target set), how many already hold a usable id (`SpotifyMetadata.enrichment_status` ∈ `LOCKED_STATUSES`). |
| GET/PATCH | `/staff/newsletter/esborrany/` | **(2026-06-07)** Newsletter review draft (opt-out flow, `web/api/staff/newsletter.py`). GET → draft + the live top it will ship with + Sunday `send_date`; PATCH edits `subject`/`narrative_html` (sets `editat`, only while `pendent`). `?setmana=` selects the week (default latest). See `comptes.md`. |
| POST | `/staff/newsletter/esborrany/cancellar/` | **(2026-06-07)** Cancel the week's draft (`estat=cancellat`) so it is NOT sent on Sunday. |
| POST | `/staff/newsletter/esborrany/preview/` | **(2026-06-07)** Render the FULL email HTML exactly as it would be sent (`comptes.newsletter.render_newsletter_preview` → same `_build_top_context` + template), honouring live `subject`/`narrative_html` overrides so unsaved edits show. Returns `{"html": …}`. Render-only: no `mark_used`, no send, no DB write; list + covers rebuilt from the consolidated top. |
| GET | `/staff/newsletter/setmanes/` | **(2026-06-08)** Weeks with a consolidated PPCC `TopSetmanal` (the on-demand selector), each with `has_draft`/`estat`, plus a `current` block (`build_brief().status`) so staff sees whether the automatic Saturday routine could generate the current week right now. |
| POST | `/staff/newsletter/esborrany/generar/` | **(2026-06-08)** Generate an ENGINE draft on demand for a chosen consolidated week (`?setmana=`, default latest). Uses the side-effect-free `build_draft_text` (no `mark_used`). Guards: week must be consolidated (409); never clobbers a terminal (`enviat`/`cancellat`) or staff-edited (`editat=True`) draft (409); a `pendent` draft is regenerated in place. `font=motor`. **NEVER sends** — the Sunday cron is the only sender. |
| POST | `/staff/newsletter/esborrany/publicar-comunitat/` | **(2026-06-10)** Newsletter→Comunitat bridge (additive, gated by `ConfiguracioGlobal.newsletter_publicacio_pont_actiu`). Mirrors the week's draft into a PUBLIC community `Publicacio` (admin pseudo-user as author); 409 while the gate is off; idempotent via `NewsletterDraft.publicacio`. Creates ONLY a `Publicacio` row — **no email, no distribution, no send**. See `comptes.md`. |

`publicar_canal` (Mastodon + Bluesky variants) publishes a 4-image
carousel since 2026-05-03 — portada + first three list slides via
`embed.images` / `media_ids[]` (both networks cap at 4). Per-slide
alt text indicates the rank range covered. The `extra_meta` returned
by each `_publish_*` is merged into `SocialPost.metadata`; for
Telegram that includes `message_ids` so a later delete can target
every message in the media-group (Telegram has no group-level delete).

### Feedback, senyal, historial, configuració, auditlog, usuaris
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/feedback/` | User correction reports with filter + search. |
| POST | `/staff/feedback/<pk>/resolve/` | Toggle resolved + attach staff notes. |
| GET | `/staff/senyal/` | Daily Last.fm signal inspector. |
| POST | `/staff/senyal/<canco_pk>/acceptar-correccio/` | R5: accept Last.fm's autocorrect for a track. |
| GET | `/staff/historial/` | Read-only HistorialRevisio. |
| GET/PATCH | `/staff/configuracio/` | ConfiguracioGlobal coeffs (auto-reflected). GET returns `{fields, sections}`: each field carries a `section` (Rànquing i fórmules · Soft cap · Editorial · Col·laboradors IG · Fiabilitat i certificats · Altres) so the SPA groups them; PATCH logs field-level diff to audit. **The `Distribució i canals` section is hidden here (2026-06-11)** — distribution switches/delays live in the cockpit/matrix (`/staff/social/*`); those fields stay on the model and `pot_publicar` is unchanged, but Config neither shows nor writes them. The legacy `/staff/social/story-cap/` endpoint + `story_max_cancons_ppcc` were removed 2026-06-11 (governed nothing). The **Editorial** section now also carries `novetats_stories_per_pagina` (default 4) — releases per paginated novetats story (see `docs/architecture/social.md`). The **Col·laboradors IG** section (ADR-0015, 2026-07-03) exposes the dormant collaborator-invite tunables (`ig_collaboradors_actiu` default off, slots, cooldowns). The **Fiabilitat i certificats** section (2026-07-27) carries the TLS expiry watch read by `tq-health`: `tls_endpoints_vigilats` (one `host:port` per line, **empty by default**) and `tls_avis_dies` (default 21). See `docs/ops/runbook.md`. |
| GET | `/staff/auditlog/` | Read-only StaffAuditLog (R9). |
| GET | `/staff/usuaris/` | User list with filters. |
| GET | `/staff/usuaris/<pk>/` | Detail with propostes + sol·licituds + audit. |
| POST | `/staff/usuaris/<pk>/toggle-actiu/` | Deactivate / reactivate (never self, never staff). |
| POST | `/staff/usuaris/<pk>/reset-2fa/` | Wipe TOTP **+ static** devices. Leaving the static ones would keep the backup codes working — the opposite of locking the account down. |
| POST | `/staff/usuaris/<pk>/esborrar/` | Hard delete. Refuses **self first**, then other staff. Eixe ordre importa: al revés, la branca d'auto-esborrat era inabastable (qui arriba a la vista és staff, així que un target que és un mateix també ho és) i responia «No pots esborrar un altre staff» a algú que s'esborrava a si mateix. Escriu `StaffAuditLog` amb l'email i el pk del compte que ja no existeix: la fila d'usuari desapareix, i el log és l'única evidència. |
