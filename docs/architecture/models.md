# CLAUDE_MODELS.md — Django Data Models

> Post-Sprint-4 snapshot (2026-04-21). All models are Django-managed. No
> unmanaged / legacy models remain. DB: 48 tables total (18 domain + Django
> internals: auth_*, django_session, axes_*, otp_totp_*, otp_static_*,
> django_migrations, django_content_type).

---

## music/

### `Territori` — `music_territori`
Reference data. 10 rows, managed via data migration.
- `codi` CharField(4, pk) — `CAT, VAL, BAL, PPCC, ALT, CNO, AND, FRA, ALG, CAR`
- `nom` CharField(50)

### `Municipi` — `music_municipi`
1,825 municipalities, populated from legacy in migration `0025`.
- `nom` CharField(255)
- `comarca` CharField(255)
- `territori` FK → Territori (PROTECT, related_name="municipis")
- `unique_together = [("nom", "comarca")]`

### `Artista` — `music_artista`
Core model. Territories are auto-synced from `ArtistaLocalitat` via signals;
**do not edit the `territoris` M2M directly**.

Identity: `spotify_id` (legacy), `deezer_id` (nullable BigInteger), `slug`.
`lastfm_nom` holds the exact Last.fm name for track.getInfo calls.

| Group | Fields |
|---|---|
| Core | `nom`, `nom_normalitzat` (homonym key: `normalitza_nom_homonim(nom)` — lowercase, no diacritics, no punctuation/spaces; maintained in `save()`, indexed; backs the staff homonym marker), `slug`, `lastfm_nom` |
| Approval state | `aprovat` ✦, `pendent_review` ✦ |
| Discovery provenance (immutable) | `auto_descobert`, `font_descoberta` |
| Discovery cache | `last_checked_deezer` |
| Deezer meta | `deezer_nb_fan`, `deezer_nb_album`, `deezer_nom`, `deezer_nom_similitud` |
| Last.fm | `lastfm_te_scrobbles` ✦ |
| Territories | `territoris` M2M (auto-synced) |
| Social links | 12 URLFields, listed in `SOCIAL_LINK_FIELDS` (added `instagram_url` + `twitter_url` 2026-04-25, migration `music 0049`) |
| Genre | `genere` (free text), `percentatge_femeni` (choices) |
| MusicBrainz (2026-04-22) | `musicbrainz_id` (UUID unique, `null=True`; `Artista.save()` normalises `""→None` to avoid UNIQUE collisions), `mb_type`, `mb_gender`, `mb_area`, `mb_area_hierarchy` (JSON), `mb_begin_date`, `mb_end_date`, `mb_disambiguation`, `mb_sort_name`, `mb_aliases` (JSON), `mb_tags` (JSON), `mb_rating`, `mb_discography_cache` (JSON {isrcs, titles}), `mb_last_sync` ✦ |
| MB staff lockouts (2026-04-25, migration `music 0048`) | `mb_blocked_mbids` (JSON list of MBIDs `resolve_mbid` must skip) + `mb_auto_match_disabled` (bool — kills auto-match for this artist entirely; cleared automatically when staff types in a fresh MBID by hand) |
| Last.fm artist metadata (2026-04-25, migration `music 0050`) | `lastfm_url`, `lastfm_bio_summary`, `lastfm_bio_content` (HTML), `lastfm_bio_published`, `lastfm_listeners`, `lastfm_playcount_total` (cumulative — distinct from per-track `SenyalDiari.lastfm_playcount`), `lastfm_ontour`, `lastfm_tags` (JSON list of `{name,url,count}`), `lastfm_image_{small,medium,large,extralarge}`, `lastfm_last_sync` ✦. Populated by `obtenir_metadata_lastfm` cron (05:00 UTC, 7-day refresh window). |
| Last.fm similar-affinity (2026-04-25, migration `music 0050`) | `nb_similars_lastfm` (PositiveIntegerField). Counts the times this artist has been surfaced as a `similar` by `artist.getSimilar` of another aprovat artist. Used as a triage score on the pendents page (`?sort=similars_lastfm`). |
| `created_at` | auto_now_add |

✦ = `db_index=True`.

**`instagram_revisat` (2026-08).** Tercer estat de la cua de staff,
bessó de `youtube_canal_revisat`: «revisat, no en té» és una resposta
final. Sense ell, un artista que genuïnament no té Instagram tornava a la
cua cada passada. Omplir la URL el marca sol.

**`instagram_suggerit` (2026-08, PROVISIONAL).** Candidat trobat pels
escombratges (Viasona, web propi). No és evidència — els handles d'IG no
es poden validar per API — així que la cua el mostra amb enllaç perquè un
humà mire el perfil abans d'acceptar. Es neteja en posar `instagram_url`.
El camp s'esborra quan la cua estiga buidada.

**`instagram_rebutjat_at` (2026-08).** Es marca quan Meta refusa aquest
compte en publicar (code 110). No podem validar handles per endavant, així
que un rebuig en publicar és l'única evidència que un compte ha canviat.
En marcar-lo, `instagram_url` es **buida** (és públic: fitxa + JSON-LD
`sameAs`) i el valor va a `instagram_rebutjat_url`, amb
`instagram_revisat=False` perquè l'artista torne a la cua. Editar la URL
neteja les dues marques. Vegeu `social-etiquetatge.md`.

**Canal oficial (2026-08).** `youtube_canal_oficial` és el canal PROPI
de l'artista (videoclips), segon carril de senyal i sovint el més gran.
El tria **una persona** a `/staff/artistes/sense-youtube`; no s'endevina
mai, perquè sondejar «Malalts» retorna un canal de pàdel.
`youtube_canal_revisat` aporta el tercer estat: «revisat, no en té» és
final i vàlid, distint de «ningú no ho ha mirat».

**YouTube (2026-08).** `youtube_channel_id` + `youtube_uploads_playlist`
apunten al canal auto-generat «`<nom>` - Topic», no al canal humà de la
banda que ja guarda `youtube_url` — són coses distintes i confondre-les
trenca l'aparellament. `youtube_checked_at` es marca també quan NO se'n
troba cap, perquè reintentar-ho costa 100 unitats de quota.

### Approval state machine (since migration 0042)

`aprovat` and `pendent_review` are orthogonal and ENFORCED by
`CheckConstraint("artista_no_aprovat_pendent_review")`:

| `aprovat` | `pendent_review` | Meaning |
|---|---|---|
| ✅ True  | ❌ False | **Live.** Tracks can enter the ranking. |
| ❌ False | ✅ True  | **In the pendents queue** (`/staff/artistes/pendents/`). |
| ❌ False | ❌ False | **Descartat.** Row kept for FK integrity; not in any queue. |
| ✅ True  | ✅ True  | **FORBIDDEN** by the DB constraint. |

`auto_descobert` is a separate immutable record of *how* the artist
got into the system (True for feat.-resolution / Viasona / auto
sources, False for manual creation and legacy imports). It is NEVER
flipped by the approval flow — historical code used it as a
queue-membership flag, a conflation the 0042 migration resolved.

**Relations (related_name):**
- `localitats` — reverse of `ArtistaLocalitat.artista`
- `cancons` — reverse of `Canco.artista` (main artist)
- `participacions` — reverse of `Canco.artistes_col` (collaborator M2M)
- `albums` — reverse of `Album.artista`
- `deezer_ids` — reverse of `ArtistaDeezer.artista`

**Methods:**
- `get_territoris()` → list of codes
- `sync_territoris_from_localitats()` — recomputes M2M from ArtistaLocalitat → Municipi
- `deezer_id_principal` (property) — primary Deezer ID from ArtistaDeezer
- `all_deezer_ids` (property) — list of all Deezer IDs
- `homonims()` — other Artista rows with the same `nom_normalitzat` (same name modulo accents + punctuation); backs the staff homonym heads-up marker
- `clean()` — requires a location when `aprovat=True`

### `ArtistaDeezer` — `music_artistadeezer`
1:N — one artist may have multiple Deezer IDs (name collisions across releases).
- `artista` FK → Artista (CASCADE, related_name="deezer_ids")
- `deezer_id` BigInteger(unique)
- `principal` BooleanField — the canonical one, used by `deezer_id_principal`

### `ArtistaLastfmAlias` — `music_artistalastfmalias` (2026-05-01)
1:N — one artist may scrobble to multiple Last.fm pages (variant
spellings). Confirmed aliases sum playcounts into the canonical at
`obtenir_senyal`. Caught from the «Delên» case + audit
(35 of 1958 approved artists affected, worst losing 87-99 % of plays).
- `artista` FK → Artista (CASCADE, related_name="lastfm_aliases")
- `nom` CharField — the literal Last.fm name (case-sensitive)
- `confirmat` Bool / `rebutjat` Bool — staff workflow state
- `confirmat_at` / `confirmat_per` — audit
- `playcount_canonical` / `playcount_variant` / `top_tracks_overlap`
  — detection-time evidence kept for staff review
- UNIQUE(artista, nom) — re-running `detectar_lastfm_aliases` is
  idempotent

Lifecycle: `manage.py detectar_lastfm_aliases` proposes candidates
(artist.search → top-tracks ≥50 % overlap); staff confirms or
rejects from the LastfmAliasesCard at `/staff/artistes/<pk>`.
Confirming auto-absorbs any pendent at the same name created by
the cron pre-alias-era (see
`web.api.staff.artistes._absorb_lastfm_duplicate_pendents`).

### `ArtistaLastfmSimilar` — `music_artistalastfmsimilar` (2026-05-01)
Row-per-recommendation table — one row = one source artist
recommending one target. Replaces the previous integer
`Artista.nb_similars_lastfm` counter (now a recomputed cache
= COUNT(*) WHERE target=…).
- `source` FK → Artista (CASCADE, related_name="similars_recomanats")
- `target` FK → Artista (CASCADE, related_name="recomanat_per")
- `last_seen` DateTime / `match` Float
- UNIQUE(source, target)

Why a table not a counter: when Last.fm lists the same artist
under multiple spellings within a single source's getSimilar
response, the integer went up by 2 when the actual signal is 1
unique recommender. With the table the cron resolves variant
names through `ArtistaLastfmAlias` and dedups before insert.
Re-running for the same source REPLACES the row set, so the
cache stays honest across re-pulls.

### `ArtistaLocalitat` — `music_artistalocalitat`
N:M between Artista and Municipi, with optional free-text override.
- `artista` FK → Artista (CASCADE, related_name="localitats")
- `municipi` FK → Municipi (PROTECT, nullable) — NULL for non-PPCC locations
- `localitat_manual` CharField — used when `municipi` is NULL
- `descripcio` CharField — e.g. "nascut a"

Signals (`music/signals.py`): post_save + post_delete call
`artista.sync_territoris_from_localitats()` to keep the Artista.territoris M2M
current. This is what makes `algorisme.py`'s raw SQL territory join work.

### `Album` — `music_album`
- `spotify_id`, `deezer_id`, `slug`
- `artista` FK → Artista (CASCADE, related_name="albums")
- `nom`, `data_llancament`, `tipus` ("album" / "single" / "ep")
- `imatge_url`
- `cancons_obtingudes` ✦ — **DEPRECATED (2026-05-03)**. Used to gate
  `obtenir_novetats` P2; replaced by `last_album_check` + age-based
  cooldown after the cron was found marking ~3.7k albums OK with zero
  tracks. Field kept for backward compat; nothing filters on it.
- `last_album_check` (DateTimeField, nullable, indexed) ✦ — Last time
  `obtenir_novetats` P2 fetched this album's tracks. Cooldown gate:
  recent (<30d since release) → 24 h, mid-aged (30-365d) → 7 days,
  old (>365d) or unknown date → 30 days. NULL = never checked → highest
  priority.
- `descartat` ✦ — True if all tracks were rejected; the only permanent
  exclusion from `obtenir_novetats`
- `mb_release_group_id` ✦ — MusicBrainz release-group UUID when matched
- `mb_type_secondary` — Live/Remix/Compilation/Soundtrack (from MB)
- `mb_status` — Official/Bootleg/Promotion (from MB)
- `mbrainz_confirmed` — nullable Bool; True when MB's discography confirms ownership
- `created_at`

### `Canco` — `music_canco`
A single track. Each track exists once (not duplicated per territory).
Territory derived via `artista.territoris ∪ artistes_col.territoris`.

| Group | Fields |
|---|---|
| Identity | `spotify_id`, `deezer_id`, `isrc`, `slug`? (no — only album) |
| Relations | `album` FK, `artista` FK, `artistes_col` M2M |
| Names | `nom`, `lastfm_nom` |
| Flags | `verificada` ✦, `activa` ✦, `lastfm_confirmed` |
| Dates | `data_llancament` ✦, `created_at` |
| Metadata | `durada_ms`, `preview_url` |
| ML | `ml_classe` ✦ (A/B/C), `ml_confianca` (float) |
| Whisper LID | `whisper_lang` ✦, `whisper_p`, `whisper_all_probs` (JSON), `whisper_processat_at` ✦ |
| MusicBrainz (2026-04-22) | `mb_recording_id` ✦, `mb_work_id`, `mb_lyrics_language` (3-char ISO, `cat` = Catalan), `mbrainz_confirmed` |

- `lastfm_lookup_nom` (property) — falls back to `nom` if `lastfm_nom` is empty
- `get_territoris()` — returns union of main + collaborator territories

**Whisper fields** (populated nightly by `analitzar_whisper` at 04:00
UTC). `whisper_all_probs` is the full 99-language distribution —
richer than the top-1 shortcut (`whisper_lang` + `whisper_p`) and fed
into the RF classifier as 4 features (`whisper_p_ca`, `whisper_p_es`,
`whisper_p_en`, `whisper_margin_ca`). Eval on a 48-clip ground-truth
set (ADR-0014, `docs/decisions/0014-whisper-lid-eval.md`): precision(ca) = 100 %,
recall(ca) = 81 %, specificity = 100 %.

**YouTube (2026-08).** `youtube_video_id` és l'Art Track del canal Topic;
`youtube_match` diu COM s'hi ha arribat (`exacte` / `durada` / `manual`) i
`youtube_matched_at` quan. Vegeu `pipeline.md` §3.1 bis.

### External-anchor invariant (2026-04-22, relaxed)
Signal `unapprove_on_last_deezer_removed` (post_delete on ArtistaDeezer)
enforces: `aprovat=True ⇒ ≥ 1 external anchor` (Deezer ID OR non-empty
`musicbrainz_id`). When the last Deezer ID of an approved artist is
removed, the signal checks for an MBID; if present the artist keeps
`aprovat=True` (MusicBrainz pipeline is enough to stay live). Only
when BOTH anchors are gone do we flip `aprovat=False,
pendent_review=False`. Motivation: Crim-style collisions where one
Catalan artist keeps the shared Deezer ID and the other lives off
MusicBrainz alone.

### Reviewable-canço invariant (2026-06-07, informe 2a)
A pendent canço (`verificada=False, activa=True`) is only reviewable if
it has **≥ 1 approved artist** — the main `artista` or any `artistes_col`
collaborator. The canonical predicate is
`music.services.has_approved_artist(canco)`; the bulk form is
`music.services.orphan_pendents_qs()` (pendent + active + no approved
artist + `contributors_raw` empty). Orphans are deactivated, not deleted:
- **De-approval hook**: `rebutjar_artista` deactivates (`activa=False`)
  any pendent canço left with no approved artist after the rejection
  (the Irokz case — a song surviving on a pendent collaborator).
- **Backfill**: migration `music 0090` deactivated the historical
  orphans (149 at audit time).
- **Recurring net**: the weekly `netejar_cancons_orfes` command
  (Monday 02:30) re-applies `orphan_pendents_qs()` with a grace window
  (`--grace-days`, default 7) so the invariant is self-healing whatever
  the drift source — it never races an in-progress approval on a
  freshly-ingested song.
- **Spared**: cançons with non-empty `contributors_raw` (deferred
  collaborators that may yet resolve to an approved artist on approval)
  are never deactivated by this rule.

Not enforced at ingest (P1/P2 of `obtenir_novetats`): gating song
creation there is entangled with the deferred-collaborator model and was
left as an open decision (see the audit report).

### `StaffAuditLog` — `music_staffauditlog`
R9. Append-only log of every destructive staff action. Written via
`music/audit.py::log_staff_action(request, action, target=obj,
**metadata)`. `target_type`, `target_id` and `target_label` are snapshots
so rows stay meaningful after the target is deleted. `metadata` is a
JSONField for action-specific context (motiu, diff, counts).

### `SpotifyAuth` — `music_spotifyauth` (singleton, 2026-04)
Holds the admin's Spotify OAuth refresh token after the one-time
`autoritzar_spotify` dance. Fields: `id=1` forced in save(),
`refresh_token`, `scope`, `spotify_user_id`, `updated_at`.

### `SpotifyPlaylist` — `music_spotifyplaylist`
One row per managed Spotify playlist. Fields: `codi` (slug, unique),
`kind` (`top` | `novetats` | `no_verificades` | `novetats_per_verificar`),
`territori` (when kind=top), `chunk_index` (no_verificades only), plus
last-sync metadata: `spotify_playlist_id`, `last_sync_at`, `last_sync_ok`,
`last_sync_msg`, `last_n_tracks`, `last_n_matched`. Populated by
`seed_spotify_playlists` (archived) + `configurar_spotify_playlists`
once per deployment.

### `HistorialRevisio` — `music_historialrevisio`
Immutable audit trail of every approval / rejection. Read-only by convention;
written by `music/services.py` via `verificacio.crear_historial()`.

Records a snapshot of the track and artist at decision time plus the ML class
and confidence — this allows the ML model to be retrained from its own history
(`music/ml.py::entrenar_model`).

- **Identifiers:** `canco_deezer_id`, `canco_spotify_id`, `canco_isrc`
- **Track snapshot:** `canco_nom`, `album_nom`, `data_llancament`, `isrc_prefix`
- **Artist snapshot:** `artista_nom`, `artista_territori`, `artista_deezer_id`,
  `artista_deezer_nb_fan`, `artista_deezer_nb_album`, `artista_nom_deezer`,
  `artista_nom_similitud`, `artista_spotify_id` (added 2026-05-25,
  migration 0085 — principal Spotify artist id at decision time,
  read from the canço's `SpotifyMetadata.spotify_artist_id`. Keyed
  by the per-pair rejection-ratio feature in
  `music/ml.py`; backfilled for legacy rows by the dedicated
  drain command `enriquir_spotify_rebuigs` once Process B
  enriches them.), `spotify_lookup_at` (added 2026-05-26,
  migration 0086 — stamp of the last orphan-flow ISRC lookup so
  not-found ISRCs are not re-searched for 30 days)
- **ML snapshot:** `ml_classe_decisio`, `ml_confianca_decisio`
- **Decision:** `decisio` (aprovada/rebutjada), `motiu` — action code
  from `music.constants.MOTIUS_REBUIG` (for rebuigs:
  `desvincular_canco`, `desvincular_album`, `desvincular_artista`)
  or `ok` / `auto_ml` / `auto_whisper` for approvals (`auto_whisper` =
  the Whisper-LID p_ca>0.90 gate, see pipeline.md §3.5). Each value
  names the exact action the rebuig triggered; full semantics at
  `docs/architecture/staff.md §5`. Renamed 2026-05-25 from
  cause-based codes (`no_catala`, `album_incorrecte`,
  `artista_incorrecte`, `no_musica`) via migration
  `music.0083_rename_motius_to_actions`.
- `created_at`

---

## ranking/

### `ConfiguracioGlobal` — `ranking_configuracioglobal`
Singleton. `save()` forces `pk=1`, `load()` classmethod uses get_or_create.
Holds the editable coefficients consumed by algorithm v2.0 plus
`min_cancons_ranking_propi` (threshold for optional territoris to get
their own ranking). See `docs/architecture/algorithm.md`.

Fields after the 2026-04-23 simplification:

| Field | Default | Meaning |
|---|---|---|
| `dia_setmana_ranking` | 6 | Day of the week the official ranking runs (0=Mon, 6=Sun). |
| `exponent_penalitzacio_antiguitat` | 2.5 | `age_factor = 1 - min(1, (dies/365)^exponent)`. |
| `coeficient_penalitzacio_top` | 0.04 | Per-past-position penalty base. Position N costs `coef / 2^(N-1)`. |
| `penalitzacio_album_per_canco` | 0.25 | Monopoli àlbum: `×(1 - value)` per earlier same-album track. |
| `penalitzacio_artista_per_canco` | 0.2 | Monopoli artista: `×(1 - value)` per earlier same-artist track. |
| `min_cancons_ranking_propi` | 20 | Threshold for an optional territori to get its own top. |
| `ppcc_penalitzacio_per_posicio` | 0.04 | PPCC aggregator weight per source-territori position. Each entry from a territorial top scales by `(1 - (posició - 1) × valor)`. Promoted from a `ranking/algorisme.py` constant on 2026-04-25 (Sprint A). |

Dropped 2026-04-23 (algorithm v1 legacy): `penalitzacio_descens`,
`penalitzacio_setmana_0..2`, `suavitat`, `max_factor_a/b/c/final`.

### `SenyalDiari` — `ranking_senyaldiari`
Daily Last.fm signal per track. One row per `(canco, data)`.
- `canco` FK, `data` DateField
- `lastfm_playcount` BigInt (cumulative total plays), `lastfm_listeners` Int
- `error` Bool, `error_msg` Text
- R5 drift fields: `lastfm_returned_track`, `lastfm_returned_artista`, `corregit`
- Indexes: `(canco, data)` unique, `(data, error)`, `(data, corregit)`
- **No normalisation** since 2026-04-23. Algorithm v2.0 reads
  `lastfm_playcount` directly and computes weekly deltas at ranking time.

### `CancoYouTubeVideo` — `music_cancoyoutubevideo` (2026-08)

Vídeos del **canal oficial** aparellats a una cançó. Taula filla perquè
una banda pot penjar videoclip, directe i lyric del mateix tema i sota
una lectura de «ressò» compten els tres. L'Art Track, que és un per
cançó, es queda a `Canco.youtube_video_id`.

### `SenyalYouTube` — `ranking_senyalyoutube` (2026-08)

Bessona de `SenyalDiari` per a la segona font: `views` (acumulatiu) +
`likes` + `video_id`, únic per `(canco, data)`. Taula separada a posta —
una visualització no és un scrobble, i unir-les ací forçaria una decisió
que ha de ser editorial. Vegeu `pipeline.md` §3.1 bis.

### `TopSetmanal` — `ranking_topsetmanal`
Weekly official ranking. `setmana` = Monday of the ranking ISO week.
- `canco` FK, `territori` CharField(4), `setmana` DateField
- `posicio` PositiveSmallInt, `score_setmanal` Float
- Unique: `(canco, territori, setmana)`. Index: `(setmana, territori)`

### `TopProvisional` — `ranking_topprovisional`
Rolling daily ranking. Truncated and rebuilt on each run.
- `canco` FK (SET_NULL), `territori` CharField(4)
- `posicio`, `score_setmanal` (the v2.0 final score = base × monopoli)
- `escoltes_setmanals` — rolling 7-day plays delta (the algorithm's
  `weekly_plays`). Renamed from the legacy `lastfm_playcount` on
  2026-04-25 (migration `ranking 0012`, Sprint A) so the column name
  matches the actual semantics. The companion `dies_en_top` column was
  dropped in the same migration (had been NULL since v2.0).
- Algorithm breakdown (migration `ranking 0011`, 2026-04-24):
  `age_factor`, `past_top_factor`, `monopoli_factor` (all FloatField,
  nullable). Surfaced as percentages in the staff ranking page and
  in `RankingBreakdownPanel` on `CancoEditPage`.
- `data_calcul` DateField(auto_now)
- Unique: `(canco, territori)`. Index: `(territori, posicio)`

---

## comptes/

### `Usuari` — `auth_user`
Custom user model extending `AbstractUser`. Reuses the `auth_user` table name
because `AUTH_USER_MODEL = "comptes.Usuari"` is the only user in the project.

### `UserArtista` — `comptes_userartista`
Request from a user to manage an **existing** artist.
- `usuari` FK (CASCADE)
- `artista` FK (CASCADE) — **non-nullable**
- `sollicitud_text` TextField (≥20 chars on form)
- `verificat` BooleanField (legacy flag, maps to `estat=="aprovat"`)
- `estat` CharField: `pendent` / `aprovat` / `rebutjat`
- `created_at`
- Unique: `(usuari, artista)` — one request per user per artist

### `PropostaArtista` — `comptes_propostaartista`
Proposal for a **new** artist not yet in the system.
- `usuari` FK
- `nom`, `justificacio`
- Social links (9 URLFields)
- `deezer_ids` CharField — comma-separated list
- `localitzacions_json` TextField — JSON array of `{"municipi_id": n}` or `{"manual": "..."}`
- `estat` (same values as UserArtista)
- `artista_creat` FK → Artista (SET_NULL) — set on approval
- `created_at`

**On approval** (`/api/v1/staff/propostes/<pk>/aprovar/` in React): creates
`Artista`, `ArtistaDeezer` per Deezer ID, `ArtistaLocalitat` per location,
copies social link fields — all inside one `transaction.atomic()`. Links the
new Artista back via `artista_creat`.

### `PerfilUsuari` — `comptes_perfilusuari` (Grup C, 2026-04)
1:1 extension of `Usuari`. Created automatically on user creation via
`comptes/signals.py::create_perfil_usuari` (post_save on AUTH_USER_MODEL),
so every account row always has a paired profile — downstream code can
assume `usuari.perfil` exists.

- `usuari` OneToOne → Usuari (CASCADE, related_name="perfil")
- `nom_public` CharField(120)
- `localitat` FK → Municipi (SET_NULL, nullable)
- `imatge_url`, `bio` (≤2000)
- Social URLs (10 fields, listed in `SOCIAL_FIELDS` — same shape as
  `Artista.SOCIAL_LINK_FIELDS` plus `instagram_url`)
- `rol_musical` CharField(choices=escoltador/music/productor/altre)
- `instruments` CharField(255, free text)
- `visible_directori` Bool (db_index=True) — gates `/comunitat/directori`
  listing; default False (opt-in)
- `obert_colaboracions` Bool
- `onboarding_complet` Bool — set after the user either fills the
  onboarding form or explicitly skips it. Surfaced on `/auth/me/` so
  the SPA can auto-route first-time users to `/onboarding`.

### `Publicacio` — `comptes_publicacio` (Grup C)
User-authored content at `/comunitat`. Staff bypasses the pending queue
(posts auto-land in `publicat` regardless of visibilitat). Non-staff
with `visibilitat=interna` posts directly; with `visibilitat=publica`
the post goes `pendent` until staff approves.

- `autor` FK → Usuari (CASCADE, related_name="publicacions")
- `titol` (≤200), `cos` (≤20 000 chars, markdown)
- `visibilitat` choices: `interna` (registered users only) / `publica` (public)
- `estat` choices: `esborrany` / `pendent` / `publicat` / `rebutjat`
- `notes_staff` TextField — reject reason shown to author
- `publicat_at` — set on transition into `publicat`
- `created_at` / `updated_at`
- Indexes: `(estat, -created_at)`, `(visibilitat, estat, -publicat_at)`

### `Feedback` — `comptes_feedback` (2026-04)
User-submitted correction reports filed from public artist/album/canço
pages via the "Corregir" button.

- `usuari` FK → Usuari (CASCADE). Non-null: anonymous visitors are
  bounced to `/compte/accedir` before they can file.
- `url` CharField — the page the reporter was on.
- `target_type` CharField (artista/album/canco/altres), `target_pk`
  (nullable), `target_slug`, `target_label` — snapshot so the row
  stays meaningful after rename/delete.
- `missatge` TextField.
- `resolt` Bool, `notes_staff` TextField, `resolt_at`, `resolt_per`
  FK → Usuari (SET_NULL).
- Indexes: `(resolt, -created_at)`, `(target_type, target_pk)`.

### `Missatge` — `comptes_missatge` (Grup C, 2026-04-21)
Direct message 1-to-1. No threads, no attachments.

- `remitent` FK → Usuari (SET_NULL, related_name="missatges_enviats").
- `destinatari` FK → Usuari (CASCADE, related_name="missatges_rebuts").
- `assumpte` (≤200), `cos` (≤10 000).
- `llegit_at` ✦ — set when the recipient opens the thread.
- `created_at` ✦.
- Indexes: `(destinatari, -created_at)`, `(remitent, -created_at)`.
- Email notification to recipient on creation (opt-out via
  `PerfilUsuari.notificar_missatges_email`). Unread count surfaces
  as a red badge on the top-bar account icon.

### `Comentari` — `comptes_comentari` (Grup C, 2026-04-21)
Flat comment attached to a `Publicacio`. No nested threads.

- `publicacio` FK → Publicacio (CASCADE, related_name="comentaris").
- `autor` FK → Usuari (SET_NULL, related_name="comentaris").
- `cos` (≤2 000).
- `created_at` ✦, `Meta.ordering = ["created_at"]`.
- Delete: author, post owner, or staff.
- Email notification to the post author on new comment (opt-out via
  `PerfilUsuari.notificar_comentaris_email`).

---

## Migrations

- `music/` 0001–0059. Latest: `0059_artistalastfmsimilar`
  (row-per-recommendation table replacing the integer counter,
  2026-05-01). `0058_alter_staffauditlog_action` (alias workflow
  actions). `0057_artistalastfmalias` (variant Last.fm names that
  sum into the canonical signal). `0056_alter_staffauditlog_action`
  (added `artista_mbid_auto_restore` for the area-validation false-
  positive cleanup). `0055_alter_staffauditlog_action`
  (added `artista_mbid_auto_unassign` action, 2026-04-29 — defence-in-
  depth audit on every MB cron iteration). `0050_lastfm_artist_metadata`
  (Last.fm block + `nb_similars_lastfm`, 2026-04-25).
- `ranking/` 0001–0017. Latest: `0017_configuracioglobal_telegram_actiu`
  (Telegram kill switch, Sprint I bis, 2026-04-27). `0016_…_bluesky_actiu_and_more`
  (Mastodon/Bluesky/Newsletter/RSS toggles, 2026-04-27). `0012_sprint_a_cleanup`
  (Sprint A renames + ppcc_penalitzacio_per_posicio, 2026-04-25).
- `social/` 0001–0004. Latest: `0004_alter_socialpost_platform_telegramauth`
  (TelegramAuth singleton + PLATFORM_TELEGRAM choice, 2026-04-27).
  `0003_…_blueskyauth_mastodonauth` (the other relay singletons,
  2026-04-27). `0002_…_instagramauth` (initial IG infra, Sprint I).
- `comptes/` 0001–0013. Latest: `0013_legal_consent_fields` (Sprint J:
  `vol_newsletter`, `consent_newsletter_at`, etc., 2026-04-26).
  `0012_perfilusuari_twitter_url_and_more` (2026-04-25).
