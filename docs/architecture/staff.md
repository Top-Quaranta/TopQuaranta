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

## 3. API surface

Vegeu [`staff-api.md`](staff-api.md): la taula completa d'endpoints, els filtres de la cua d'artistes i la semàntica de cada PATCH.

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
