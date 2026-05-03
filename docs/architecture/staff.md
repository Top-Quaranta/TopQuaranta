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
| POST | `/staff/pendents/<pk>/aprovar/` | Body: `{deezer_id?, municipi_id? \| manual?}`. Approves, clears `pendent_review`. |
| POST | `/staff/pendents/<pk>/descartar/` | Deletes if no verified tracks; else only clears `pendent_review`. |

### Artistes
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/artistes/` | Filters: `q`, `aprovat`, `deezer`, `territori`. |
| GET | `/staff/artistes/search/?q=` | Typeahead for pickers. Returns up to 10 results. |
| POST | `/staff/artistes/crear/` | Body: `nom`, `lastfm_nom?`, `deezer_id?`. |
| GET/PATCH | `/staff/artistes/<pk>/` | Detail + replace-semantics PATCH over `nom`, `lastfm_nom`, `genere`, `percentatge_femeni`, `aprovat`, social URLs, `localitats[]`, `deezer_ids[]`. |

### Cançons
| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/cancons/` | Filters: `q`, `verificada`, `ml_classe`, `whisper`, `deezer`, `sort`, `artista_pk`. |
| POST | `/staff/cancons/accio/` | Bulk `aprovar` / `rebutjar` with `motiu`. `artista_incorrecte` → cascades to `rebutjar_artista`; `album_incorrecte` → `rebutjar_album`. |
| GET/PATCH | `/staff/cancons/<pk>/` | Detail + PATCH incl. `artista_pk` reassignment + `artistes_col_pks` replace. |

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

Six channels share the same `SocialPost` model and the same staff
surface. Channel column tints in the UI: IG pink, Mastodon indigo,
Bluesky sky, Telegram cyan, newsletter amber, RSS orange.

| Method | Path | Purpose |
|---|---|---|
| GET | `/staff/social/` | Posts list ordered by `published_at` (nulls-last → `created_at`), Data column first, Setmana N second. Channel + per-credential payloads. |
| POST | `/staff/social/preview/` | Render dry-run for a slot; returns the rendered PNG paths. |
| POST | `/staff/social/publicar-ara/` | Force-run `publicar_social` / `publicar_canal` for a `(data, tipus, platform)` triple. |
| POST | `/staff/social/eliminar-instagram/` | Legacy IG-only delete. Kept for back-compat. |
| POST | `/staff/social/eliminar-remot/` | **(2026-05-03)** Platform-aware delete. Dispatches by `post.platform` to `instagram_client` (DELETE Graph node), `mastodon_client.delete_status`, `bluesky_client.delete_post` (parses AT URI → deleteRecord), or `telegram_client.delete_messages` (uses `metadata.message_ids` captured at publish time). |
| POST | `/staff/social/toggle/` | Per-channel kill switch (`channel=instagram\|mastodon\|bluesky\|telegram\|newsletter\|rss`). |

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
| GET/PATCH | `/staff/configuracio/` | ConfiguracioGlobal coeffs; PATCH logs field-level diff to audit. |
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

## 5. Motius de rebuig — semantics

`music.constants.MOTIUS_VALIDS` = `{no_catala, artista_incorrecte,
album_incorrecte, no_musica}`. The motiu decides which service function
gets called by the bulk-action endpoint:

| Motiu | Escalation | Side effects | Safe for |
|---|---|---|---|
| `no_catala` | per-Canço `rebutjar_canco` | deletes + writes HistorialRevisio with this motiu | track-level corrections |
| `no_musica` | per-Canço `rebutjar_canco` | same as above | interviews, samplers, empty tracks |
| `album_incorrecte` | per-Album `rebutjar_album` | deletes all unverified tracks of the album + marks `album.descartat=True` | **Deezer-blurred homonym albums (e.g. wrong-Aion's album)** — blast radius contained |
| `artista_incorrecte` | per-Artista `rebutjar_artista` | deletes all unverified tracks + clears all Deezer IDs + marks all albums descartat | an artist whose Deezer profile is entirely wrong; **destructive of real artists with the same name** |

All four write `HistorialRevisio` with `artista_nom` = canço's main artist.
Collaborators (`artistes_col`) are NOT persisted in the decision log, so
rejecting a track with Juan Magan as collab does not taint Juan Magan's
future classification.

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
