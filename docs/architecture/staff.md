# CLAUDE_STAFF.md — Staff panel

> React SPA admin interface living at `/staff/*` in `web-react/src/pages/staff/`,
> backed by the `/api/v1/staff/*` DRF endpoints in `web/api/staff_views.py`.
> Replaced the Django-template staff panel in Sprint 4 (April 2026).

---

## 1. Architecture at a glance

```
Browser                   Caddy                    gunicorn :8083
  │                         │                           │
  │  GET /staff/pendents    │                           │
  │ ───────────────────────▶│                           │
  │                         │  (no path match in        │
  │                         │   Django allow-list)      │
  │                         │                           │
  │                         │  ▶ serve web-react/dist/  │
  │  React SPA              │                           │
  │                         │                           │
  │  fetch /api/v1/staff/…  │                           │
  │ ───────────────────────▶│ ────────────────────────▶ │
  │                         │                           │ IsStaff check
  │                         │                           │ → DRF JSON
  │                ◀──────────────────────────── JSON ──┤
  │  render table           │                           │
```

The SPA owns the visual layer + routing. The API owns the data + permission
gating. No Django templates are rendered for staff anymore.

## 2. Access control

- **Route gate (client)**: `components/AdminRoute.jsx` wraps every `/staff/*`
  route. It bounces non-staff users to `/compte/accedir` and staff users
  whose session hasn't been OTP-verified to `/compte/2fa/verificar/` (a full-
  page redirect — the Django 2FA form lives in the Caddy allow-list).

- **Permission gate (server)**: `IsStaff` DRF permission (`staff_views.py`)
  requires `user.is_authenticated AND user.is_staff AND user.is_verified()`.
  Every `/api/v1/staff/*` endpoint declares `@permission_classes([IsStaff])`.

- **Session**: same `sessionid` cookie as the public SPA. CSRF token comes
  from the `csrftoken` cookie and is echoed back as `X-CSRFToken` on writes
  by `web-react/src/lib/api.js`.

- **Self-elevation prevention**: toggling `is_staff` is intentionally not
  exposed from the UI. Admins must flip that via `manage.py` + SSH.

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
| GET | `/staff/artistes/` | Filters: `q`, `aprovat`, `deezer`, `territori`. |
| GET | `/staff/artistes/search/?q=` | Typeahead for pickers. Returns up to 10 results. |
| POST | `/staff/artistes/crear/` | Body: `nom`, `lastfm_nom?`, `deezer_id?`. |
| GET/PATCH | `/staff/artistes/<pk>/` | Detail + replace-semantics PATCH over `nom`, `lastfm_nom`, `genere`, `percentatge_femeni`, `aprovat`, social URLs, `localitats[]`, `deezer_ids[]`. **One transaction (2026-06):** the `aprovat=True` flip is deferred until after the localitat + Deezer writes, then gated (rejects 400 without ≥1 Deezer or localitat). A `deezer_ids[]` entry already owned by another artist now returns **409** with `owner_pk` (was a silent no-op); the rollback leaves nothing half-written. |

### Cançons
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/cancons/` | Filters: `q`, `verificada`, `ml_classe`, `whisper`, `deezer`, `sort`, `artista_pk`. |
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
| GET | `/staff/top/?territori=CAT` | Top-40 provisional + territori list + motius. |
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
| POST | `/staff/social/eliminar-remot/` | **(2026-05-03)** Platform-aware delete. Dispatches by `post.platform` to `instagram_client` (DELETE Graph node), `mastodon_client.delete_status`, `bluesky_client.delete_post` (parses AT URI → deleteRecord), or `telegram_client.delete_messages` (uses `metadata.message_ids` captured at publish time). |
| POST | `/staff/social/toggle/` | Distribution switch. `channel=global` writes the master `distribucio_activa`; `channel=instagram\|mastodon\|bluesky\|telegram\|newsletter\|rss` writes the per-channel switch. `channel` is REQUIRED (2026-06-07: removed the default-to-`instagram` footgun). See `social.md` for the gate. |
| GET | `/staff/social/matriu/` | **(2026-06)** Distribution matrix (third gate, `MatriuPublicacio`): `{canals, tipus, dies, cells:[{canal, tipus, actiu, dies_publicacio, seeded}]}`. `dies_publicacio` is a read-only list of weekday ints derived from the calendar/cron (`publish_weekdays_for`; newsletter=Sunday, `[]`=N/A). Non-seeded combos report `seeded=False`. See `social.md`. |
| POST | `/staff/social/matriu/toggle/` | **(2026-06)** Set one matrix cell. Body: `canal`, `tipus`, `actiu?` (defaults to flipping). Only seeded cells; `actiu=False` on (newsletter × top_ppcc) stops the Sunday send. The publish DAY is not editable here (calendar-derived indicator). |
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
| GET/PATCH | `/staff/configuracio/` | ConfiguracioGlobal coeffs (auto-reflected). GET returns `{fields, sections}`: each field carries a `section` (Rànquing i fórmules · Soft cap · Editorial · Altres) so the SPA groups them; PATCH logs field-level diff to audit. **The `Distribució i canals` section is hidden here (2026-06-11)** — distribution switches/delays live in the cockpit/matrix (`/staff/social/*`); those fields stay on the model and `pot_publicar` is unchanged, but Config neither shows nor writes them. The legacy `/staff/social/story-cap/` endpoint + `story_max_cancons_ppcc` were removed 2026-06-11 (governed nothing). |
| GET | `/staff/auditlog/` | Read-only StaffAuditLog (R9). |
| GET | `/staff/usuaris/` | User list with filters. |
| GET | `/staff/usuaris/<pk>/` | Detail with propostes + sol·licituds + audit. |
| POST | `/staff/usuaris/<pk>/toggle-actiu/` | Deactivate / reactivate (never self, never staff). |
| POST | `/staff/usuaris/<pk>/reset-2fa/` | Wipe TOTP + static devices. |

## 4. React surface (`web-react/src/pages/staff/`)

- **Layout** — `components/StaffLayout.jsx` renders a dark vertical sidebar
  nested inside the public yellow header. The nav lists: Panell · Estat ·
  Pendents · Artistes · Cançons · Albums · Ranking prov. · Propostes ·
  Sol·licituds · Feedback · Senyal · Historial · Configuració · Auditoria ·
  Usuaris · Social.
- **Shared chrome** — `components/staff/StaffTable.jsx` exports `TableCard`,
  `Table`, `THead/Th/Td/Tr`, `Btn`, `Pill`, `Input`, `Select`, `Pagination`,
  `PageHeader`, `EmptyState`. Keeps every page under ~150 LOC.
- **Typeahead pickers** — `staff/ArtistaPicker.jsx` (single) and
  `staff/ArtistesColPicker.jsx` (multi), both backed by
  `/staff/artistes/search/`. Used on edit pages for reassignment +
  collaborator editing.
- **Location cascade** — `staff/LocationCascade.jsx` pairs
  territori→comarca→municipi selects. Special case: when `territori=ALT`
  the comarca/municipi selects collapse into a single free-text input
  (saved to `ArtistaLocalitat.localitat_manual`).

### Pages (17 total)

`StaffDashboardPage` · `EstatPage` (visual health dashboard) · `PendentsPage` ·
`StaffArtistesPage` · `ArtistaCrearPage` · `ArtistaEditPage` ·
`StaffCanconsPage` · `CancoEditPage` · `StaffAlbumsPage` · `AlbumEditPage` ·
`StaffRankingPage` · `PropostesPage` · `PropostaDetailPage` ·
`SolicitudsPage` · `SenyalPage` · `HistorialPage` · `ConfiguracioPage` ·
`AuditlogPage` · `UsuarisPage` · `UsuariDetailPage` · `FeedbackPage`.

## 5. Accions post-rebuig — semantics

`music.constants.MOTIUS_VALIDS` = `{desvincular_canco,
desvincular_album, desvincular_artista}`. The motiu decides which
service function the bulk-action endpoint calls.

This doc is **the only place** that documents the cause and the
when-to-use prose. The choices list in `music.constants.MOTIUS_REBUIG`,
the model field choices in `HistorialRevisio.MOTIUS`, the
front-end button labels and badge labels are intentionally
**action-only** (e.g. just "Desvincular l'àlbum"). The old habit
of stuffing the cause into the label ("Àlbum incorrecte",
"desvincular l'àlbum (homònim)") brought back the same ambiguity
the rename was meant to kill, so the cause stays exclusively here.

### `desvincular_canco`

**Action.** `rebutjar_canco(canco)` sets `verificada=False,
activa=False`. The row remains in the DB for audit purposes but
disappears from pendents and rankings. No other state changes.

**When to use.** The cançó itself should not be in our catalogue:
not Catalan, podcast or audiobook, sample, interview, instrumental
filler, miscategorised content. The artista and album stay intact;
only this one track is dropped.

### `desvincular_album`

**Action.** `rebutjar_album(album)` physically deletes every
unverified cançó of the album and sets `Album.descartat=True`. The
artista's `ArtistaDeezer` rows are **not touched**.

**When to use.** Deezer has attached, under our artista's correct
Deezer profile, an entire album that in fact belongs to a
**different artist who happens to share the name with ours**. The
artist on this album is the homonym, not the album itself. The
Deezer profile stays linked because new releases of our artista
will still land under that profile correctly. The cleanest test is
Spotify: open the canonical Spotify profile of our artista; if the
album does not appear there but does appear under a different
Spotify artist with the same name, it is an `desvincular_album`
case. The blast radius is contained to this album.

### `desvincular_artista`

**Action.** `rebutjar_artista(artista)` physically deletes every
unverified cançó + clears every `ArtistaDeezer` row of the artista
+ sets `Album.descartat=True` on every album of the artista.
The `unapprove_on_last_deezer_removed` signal in
`music/signals.py` then runs; immediately afterwards
`rebutjar_artista` explicitly overrides the artista to
`aprovat=False, pendent_review=True` regardless of MBID. The
artista lands in the pendents queue so the operator can search for
the correct Deezer profile. MBID does not factor in: new releases
come from Deezer, and without a Deezer profile the artista has no
source for new material until the operator finds one.

**When to use.** The Deezer profile that ended up linked to our
artista is entirely wrong — no cançó on it belongs to our artista.
Typically a freshly-discovered artista that the auto-matcher mapped
to the wrong Deezer ID, and every track ingested so far has been a
homonym's. This action is destructive of every unverified track
the artista currently has under that profile. Verified cançons
(`verificada=True`) survive but stop receiving updates from the
Deezer pipeline; that is acceptable for the catalan-side `Crim`
case where the artista keeps living off MusicBrainz, but it should
be rare.

### Common contract

All three write `HistorialRevisio` with `artista_nom` set to the
canço's main artist. Collaborators in `Canco.artistes_col` are
**not** persisted to the decision log, so rejecting a track that
features Juan Magan as a collaborator does not contaminate Juan
Magan's own future classification.

### Data migrations

`music.0083_rename_motius_to_actions` rewrote historical
`HistorialRevisio.motiu` values from cause-based codes
(`no_catala`, `album_incorrecte`, `artista_incorrecte`,
`no_musica`) to the action-based codes documented above. The
`no_catala` (1 275) + `no_musica` (4) rows both collapsed into
`desvincular_canco` (1 279 unified); the language signal lives on
`Canco.whisper_*` features for the RF classifier and is not lost.

`music.0084_requeue_desvincular_artista_victims` brought back to
`pendent_review=True` the 63 historical Artistas that the previous
`desvincular_artista` flow had left in limbo (no Deezer, no MBID,
no pendent flag). Same shape as what the current code does
inline.

## 6. Invariants enforced by signals

- **`aprovat=True ⇒ Deezer ID OR MBID`** (2026-04-22, relaxed) —
  `music/signals.py` post_delete on `ArtistaDeezer`. When the last
  Deezer ID is removed the artist stays `aprovat` only if it has a
  non-empty `musicbrainz_id`; otherwise it flips to False (and
  `pendent_review=False`). Motivation: Crim-style collisions where two
  PPCC artists share one Deezer ID — one keeps Deezer, the other
  lives off MusicBrainz exclusively.
- **D5: main artist ≠ collaborator on same canço** — `m2m_changed` on
  `Canco.artistes_col`. Raises `ValidationError` on pre_add / pre_set.
- **`artista_no_aprovat_pendent_review`** — DB CheckConstraint (migration
  0042). `aprovat=True AND pendent_review=True` is impossible.

## 6b. MusicBrainz integration surface (2026-04-22)

MB sync is continuous: cron every 15 min, single-instance lock, exits
when the queue is empty (all artists synced within `--refresh-days=7`).
See `CLAUDE_PIPELINE.md §3.7` for the per-artist flow.

Where MB shows up on the staff UI:

- **ArtistaEditPage** (`/staff/artistes/<pk>`) — shared
  `MusicBrainzPanel` component renders type, gender, area, begin/end
  dates, disambiguation, aliases, tags, cached-ISRC count and last
  sync timestamp. Editable `musicbrainz_id` field + "Sincronitzar
  ara" button (disabled until the MBID is persisted). Posts to
  `/api/v1/staff/artistes/<pk>/sync-mb/`.
- **AlbumEditPage + CancoEditPage** — read-only MB panel variant
  with release-group / recording / work IDs, lyrics language (green
  when `cat`), `mbrainz_confirmed` status pill, link to MB.
- **StaffArtistesPage** (`/staff/artistes`) — new "MB" column with
  `MBID` / `Sense MBID` / `Dissolt YYYY` pills + new filter
  (`sense_mbid`, `amb_mbid`, `dissolt`, `no_sincronitzat`).
- **StaffCanconsPage** (`/staff/cancons`) — new "MB" column with
  ✓/✗/? + Work `cat` tag; artist cell warns `⚠ dissolt YYYY`
  inline; new filter (`confirmat`, `no_confirmat`, `desconegut`,
  `cat`, `artista_dissolt`).
- **EstatPage** (`/staff/estat`) — MusicBrainz section with coverage
  bar (`aprovats_amb_mbid` / `aprovats_total`), synced count,
  confirmed-album / confirmed-track totals, Catalan-lyrics Work
  counter, dissolved-artists counter, oldest pending sync. Plus a
  "Top artistes amb més backlog" list (approved artists with the
  most unverified tracks) that surfaces MBID pills + dissolved
  badges — the fastest way to spot Crim/Apa/Renata-style collisions.

The three MB-derived ML features (`mbrainz_confirmed`,
`mb_lyrics_cat`, `artista_te_mbid`) plug into the RF classifier and
are visible in the Estat → "Importància de features" chart after the
model retrains.

## 7. Adding a new staff page

1. Add the view in `web/api/staff_views.py` using `@api_view` +
   `@permission_classes([IsStaff])`. Use `_paginate()` for lists.
2. Register the route in `web/api/urls.py` under the `staff/` prefix.
3. Create the React page in `web-react/src/pages/staff/`. Use the
   `StaffTable.jsx` primitives. Seed filters from `useSearchParams` if the
   URL should be shareable.
4. Wire the route in `App.jsx` inside the `/staff/*` switch.
5. Add the sidebar link in `components/StaffLayout.jsx` if it's user-facing.
6. Drop a tile in `StaffDashboardPage.jsx` if it should surface on the
   landing grid.
7. If the action is destructive, call `log_staff_action(request, "<verb>",
   target=obj, **metadata)` from the backend. The `StaffAuditLog.ACTION_CHOICES`
   tuple accepts new values without a schema migration (only the UI filter
   needs to be updated).
