# CLAUDE_PIPELINE.md — Ingest → Signal → Ranking

> Daily + hourly automation. All commands run as user `topquaranta` from
> `/etc/cron.d/topquaranta`, with `DJANGO_SETTINGS_MODULE=topquaranta.settings.production`.

---

## 1. Overview

```
     Deezer (hourly, obtenir_novetats)     Last.fm (daily, obtenir_senyal)
           │                                        │
           ▼                                        ▼
   new Canco (verificada=False)              SenyalDiari (raw playcount)
           │                                        │
   staff review → verificada=True ──────────────────┤
                                                    ▼
                                     calcular_top (daily provisional,
                                                       Saturday official)
                                                    │
                               weekly_plays = playcount_today
                                              − playcount_7_days_ago
                                    × age_factor
                                    × past_top_factor
                                    × monopoly (album / artista)
                                                    │
                                                    ▼
                                     TopProvisional / TopSetmanal
```

> Related: the **self-hosted cover pipeline** (`ingesta/portades/` +
> `descarregar_portades`) downloads and transcodes Deezer covers to
> webp/avif variants on our own origin. It is documented separately at
> [`portades.md`](portades.md) (Fase 1 = ingestion only).

## 2. API clients (`ingesta/clients/`)

All clients import `DEEZER_RATE_LIMIT`, `LASTFM_RATE_LIMIT`, `MAX_API_RETRIES`
from `music/constants.py`. Never raise — return `None` on any failure.

### `deezer.py` — primary metadata source
- Public API, no auth. Base: `https://api.deezer.com`.
- Rate limit 1.0 s, retry 3× with exponential backoff.
- Detects error code 4 ("Quota limit exceeded"), sets a session-scoped flag
  that stops further calls until next day (`quota_exhausted()`).
- Functions: `search_artist`, `get_artist_info`, `get_artist_albums`,
  `get_album_tracks`. Returns dict or `None`.
- **Title handling (2026-07-21):** `Album.nom` / `Canco.nom` are stored
  with Deezer's casing **verbatim** — only `normalize_apostrophes` runs
  (orphan grave/acute accents + fancy quotes → ASCII `'`). The former
  `titlecase_catala` pass was dropped at ingestion because it mangled
  deliberate all-caps stylings (`QUE JO EM NEGUI` → `QUE JO EM Negui`:
  2–3-letter words survived as false acronyms while longer words were
  lowered). Applies going forward only; pre-existing rows were not
  backfilled. `titlecase_catala` + the `retitlecase` command remain for
  manual use but are no longer wired into the pipeline.

### `lastfm.py` — daily signal
- Endpoint: `track.getInfo?autocorrect=1`.
- Rate 0.2 s, retry 3×.
- On error 6 ("Track not found"), automatically retries once with the track
  name normalized: strips `(feat. X)`, `(Acoustic Version)`, `- Live`, `- Remix`,
  etc., and converts Unicode quotes to ASCII. Recovers ~10–15% of errors.

### `spotify.py` — playlist output (active since 2026-04)
- Two classes. `SpotifyClient` is the legacy Client-Credentials wrapper
  (ingest endpoints no longer available to us since Spotify gated Web API
  behind Premium in 2024).
- **`UserSpotifyClient`** is the live path: OAuth refresh-token flow for the
  admin account. Rotates access tokens on 401 mid-flight, honours 429
  `Retry-After`, persists a rotated refresh_token when Spotify issues one.
  Supports `search_isrc()` for resolution and chunked
  `replace_playlist_tracks()` for the daily sync (§3.9).
- Scopes used: `playlist-modify-private playlist-modify-public`.

## 3. Management commands

### Rules (all commands)
- `self.stdout.write()`, never `print()`.
- `raise CommandError(...)`, never `sys.exit()`.
- All DB writes inside `transaction.atomic()`.
- Idempotent where possible.
- Final line: counts of processed / success / errors.

### 3.1 `obtenir_senyal` — daily 06:00
```bash
python manage.py obtenir_senyal [--data YYYY-MM-DD] [--limit N] [--dry-run]
```
Selects `verificada=True AND activa=True AND
data_llancament ≥ today - DIES_CADUCITAT` tracks, calls Last.fm per
track, writes raw cumulative `lastfm_playcount` + `lastfm_listeners`
into `SenyalDiari`. Skips tracks already ingested for that date
(idempotent). No post-processing — the former `score_entrada`
normalisation was removed in algorithm v2.0 (2026-04-23); the
ranking consumes the raw counts directly.

**The gate is the cançó, not who signs it.** `artista.aprovat=True` sat
in that filter until 2026-08-10 and starved 23 verified, active, in-window
tracks of signal forever — 22 of them collaborations whose primary credit
is a pending artist but which reached the catalogue through an approved
one. They are eligible for the ranking (`_top_for_territoris` ORs
`artista`/`artistes_col` territoris and doesn't check approval either), so
excluding them here only guaranteed they could never chart. Verification
is the editorial gate; approval of the primary credit is not.

**Two fallbacks keep a failed lookup from becoming permanent silence**
(both added 2026-08-10; every failure lands in the same `error=True`
row reading "lookup failed", which staff correctly read as "nobody
scrobbles this" and nobody re-checked):

- **Drop the recording MBID.** Last.fm resolves `mbid` *instead of*
  artist+track: an MBID it hasn't indexed answers error 6 and the
  names sent alongside are never consulted. So a **successful**
  MusicBrainz match silently deleted a track's signal — the better
  the MB cron got, the more tracks went dark. `get_track_info` now
  retries once without the MBID and clears it for the rest of the
  ladder. 128 eligible tracks were affected; 25/25 sampled recovered.
- **Try the collaborators.** A collaboration is often filed on Last.fm
  under a credit that isn't our `Canco.artista` (Deezer names Poetas
  Puestos the main artist of "Tu Contra el Món"; we store it under
  Auxili), so we asked the wrong name every day. On failure
  `obtenir_senyal` retries under up to `MAX_COL_FALLBACK` (3)
  `artistes_col` names. Recovered 25 of the 150 failing tracks that
  have collaborators. **This changes only which name we ask** —
  attribution, territory and monopoly are untouched, since the
  ranking pool already ORs `artista__territoris` with
  `artistes_col__territoris`.

The name that answered is tracked as `asked_artist` and drives both
the alias summing (skipped on the collaborator path — aliases belong
to `canco.artista`) and `_detect_drift`. Comparing a collaborator's
legitimate response against the *primary* artist would flag drift, set
`corregit=True`, and `_top_for_territoris` filters those rows out —
the recovery would restore the row and lose it again.

### 3.1 bis YouTube — segona font de senyal *(2026-08)*

Last.fm només veu el que els seus usuaris escrobblen, i per a la música
valenciana i balear eixa mostra és quasi buida (116 de 400 cançons VAL
elegibles sense cap senyal). YouTube crea automàticament un canal
**«<artista> - Topic»** per a tot el que entrega un distribuïdor, amb
les «Art Tracks» (caràtula + àudio). Existeix encara que ningú no haja
escrobblat mai el grup: **30 de 30** artistes VAL/BAL mostrejats en
tenien.

La quota mana tot el disseny. 10.000 unitats/dia, gratis i sense tarifa
de pagament (ampliar-la exigeix una auditoria manual de Google):

| Endpoint | Cost | Ús |
|---|---|---|
| `search.list` | **100** | descobrir el canal — la meitat cara |
| `channels.list` | 1 | playlist d'uploads |
| `playlistItems.list` | 1 / 50 vídeos | enumerar Art Tracks |
| `videos.list` | 1 / 50 vídeos | estadístiques diàries |

Per tant `descobrir_youtube` (03:00) només pot resoldre ~90 artistes al
dia i **l'ordre importa més que la velocitat**: primer els artistes amb
cançons sense senyal de Last.fm, després la resta de VAL/BAL, i al final
CAT. `obtenir_senyal_youtube` (06:30) fotografia tot el catàleg per ~60
unitats i escriu `SenyalYouTube`, bessona de `SenyalDiari` — taula a
part a posta, perquè una visualització no és un scrobble i unir-les a
la capa d'emmagatzematge forçaria una decisió que volem mantindre
editorial.

YouTube **localitza** el sufix: un navegador en català ensenya
«Malifeta - Tema». Al servidor ens torna l'anglés, però això és el locale
per defecte de l'API, no un contracte — i exigir la paraula anglesa faria
que el descobriment no trobara res i en silenci. `topic_suffix_name()`
accepta les variants conegudes.

La comparació de noms va per `normalitza_nom_homonim` (NFKD, sense
diacrítics, sense puntuació): «Bèrnia» ha de trobar el canal que es diu
literalment `bernia - Topic`, i «Clàudia Xiva» fallava contra un canal
de nom idèntic perquè un costat era NFC i l'altre NFD. Afluixar això no
eixampla la superfície d'exploit — el candidat continua havent de portar
el sufix literal, que és el que deixa fora els canals de pàdel.

**El sufix `- Topic` no és opcional.** Cercar «Auxili - Topic» retorna
primer el canal humà de la banda («AUXILI»), ple de videoclips titulats
«AUXILI - TARRINETES AL SOL ft DJ Trapella», que no aparellen amb res.
Exigir el sufix literal va pujar l'encert de la mostra del 63% al 76%.

L'aparellament és conservador a posta: només títol normalitzat exacte
(`_normalize_track`, compartit amb Last.fm). Un aparellament erroni no
sembla erroni — sembla una cançó que ningú no escolta.

**Dos carrils (2026-08).** L'Art Track no sempre és on és el públic:
Maria del Mar Bonet té 97 visualitzacions a l'Art Track de «S'aigo No»
i 55.091 al seu canal propi; Malalts, en canvi, no té canal propi i tota
la seua audiència és a l'Art Track. Quin carril mana és propietat **de
l'artista**. Per això el senyal d'una cançó és la **suma** de:

1. l'**Art Track** — un vídeo, a `Canco.youtube_video_id`, automàtic;
2. el **canal oficial** — zero o molts vídeos, a `CancoYouTubeVideo`,
   i el canal el tria **una persona** a `/staff/artistes/sense-youtube`.

`sembrar_canals_youtube` (02:00) agafa gratis els enllaços curats de
MusicBrainz. Els `/channel/UC…` no costen res; els `/@handle` necessiten
una cerca (100 unitats), i per això `--resolve` va amb `--budget` i
`--nomes-finestra`: 655 handles serien set dies de quota, i el sostre fa
que la comanda pare en lloc de menjar-se el pressupost del senyal.
L'absència d'enllaç **no** marca l'artista com a revisat — «ningú no ho
ha mirat» i «revisat, no en té» només els distingeix una persona.

El canal oficial no s'endevina mai. Sondejar «Malalts» automàticament
retorna un canal de pàdel i una empresa d'esdeveniments; «Guerra» o
«Montenegro» són pitjors. `Artista.youtube_canal_revisat` dona el tercer
estat que fa que això funcione: «revisat, no en té» és una resposta
final i vàlida, distinta de «ningú no ho ha mirat».

**Invariant:** el senyal d'un artista s'ha de sumar sempre sobre el
**mateix conjunt de carrils**. Barrejar un artista mesurat amb un carril
i un altre amb dos fa que qualsevol conversió entre artistes no signifique
res. Un artista sense canal propi no està infravalorat; un amb la decisió
pendent, sí.

**L'enumeració del carril oficial va desacoblada del descobriment**
(2026-08-12): un canal confirmat des de la cua de staff (o per la sembra)
arriba DESPRÉS de la passada Topic de l'artista, i sense una segona fase
no s'escanejaria mai — el dia que es van aplicar les primeres 58
confirmacions hi havia exactament 1 vídeo aparellat. Cada execució
re-enumera els canals oficials dels artistes amb cançons en finestra
(idempotent per `get_or_create`; els menys coberts primer), cosa que de
propina captura els videoclips que les bandes pengen dies després del
llançament.

`suggerir_instagram` (02:30) tanca el cercle de l'estat estacionari: per
als artistes que entren a la cua de staff (aprovats, amb cançó viva, sense
URL ni suggeriment), busca un candidat al seu web propi i, si no, a
Viasona — que NO és font curada, per això només pot escriure
`instagram_suggerit` (mai `instagram_url`): un humà mira el perfil abans
d'acceptar. Els candidats descartats amb ✕ queden vetats a
`instagram_suggerits_descartats` i no es proposen mai més — buidar el camp
no bastava, perquè la font torna a publicar el mateix handle l'endemà
(caçat 2026-08-13). El vet és per handle, no per artista: una font
diferent pot proposar-ne un altre. Sense quota de YouTube.

Dins del canal oficial els títols són text lliure («AUXILI - TARRINETES
AL SOL ft DJ Trapella»), així que l'aparellament és per prefix +
decoració (`_conte_titol`): el títol de la cançó ha d'anar al principi i
darrere només hi pot haver un separador, una etiqueta coneguda o el nom
de l'artista. Contindre el títol **no** basta — «Llibertat» és una
paraula sencera dins de «Buscant la llibertat», i acceptar-ho és
exactament l'exploit que aquest projecte va decidir refusar.

Com entra al rànquing **encara no està decidit**: primer calen tres o
quatre setmanes de dades. Vegeu `docs/architecture/analytics.md` per a
l'informe diari de progrés.

### 3.2 `calcular_top`
```bash
python manage.py calcular_top [--setmana YYYY-MM-DD] [--territori CODE]
                                   [--dry-run] [--provisional]
```
- Without `--provisional`: writes `TopSetmanal`. Run Saturday 08:00.
  Territories processed: `TERRITORIS_FIXOS = {CAT, VAL, BAL}` + aggregates
  `{ALT, PPCC}`. Each territory is `delete + bulk_create` inside a transaction
  (prevents stale entries from previous runs).
- With `--provisional`: writes `TopProvisional`. Run daily 07:00. Includes
  all eligible territories (fixed + aggregates + optional if they cross the
  `min_cancons_ranking_propi` threshold).
- Aggregates (ALT, PPCC) must run last — they read the just-computed individual
  rankings in memory (`algorisme.calcular_ppcc_ranking` calls the per-territory
  function for each source territory).

### 3.3 `obtenir_novetats` — hourly (every :00)
```bash
python manage.py obtenir_novetats [--limit N] [--dry-run]
```
Incremental Deezer ingestion with a 3-tier priority queue:
- **P1** — tracks with `deezer_id` but no ISRC; fetches full track to backfill.
- **P2** — every non-discarded album with a `deezer_id` re-checked on a
  per-album cooldown (May-2026 redesign): <30 days since release → 24 h,
  30-365 days → 7 days, >365 days or unknown date → 30 days. Gate is
  `Album.last_album_check` (NULL = highest priority). Replaces the old
  `cancons_obtingudes=False` flag, which masked ~3.7k phantom albums
  marked OK with zero tracks because Deezer flake or quota_exhausted at
  the wrong moment looked like "no tracks". `descartat=True` is the
  only permanent exclusion. Idempotence is preserved by `_create_track`'s
  `deezer_id` + ISRC dedup so a re-scan never duplicates rows.
- **P3** — approved artists, oldest `last_checked_deezer` first; fetches albums
  released within `DIES_CADUCITAT` days.

Uses an `fcntl.flock` on `/tmp/obtenir_novetats.lock` — if a run is still
going, the next hour's run exits with code 75 (EX_TEMPFAIL) so `tq-run`
records `status=SKIPPED_BY_LOCK` without refreshing `last_run`. All
created Canco records start with `verificada=False`;
`classificar_i_guardar(canco)` applies the ML class.

When `_create_track` finds a track whose ISRC already exists under a
different `deezer_id` (single re-released inside an LP, or a featuring
listed under both contributors) the second row is skipped silently and
the existing main artist gets the contributor added as `artistes_col`
when appropriate. The contributor-vs-self check compares against
**every** Deezer ID of the existing artista, not just the principal —
this guards against signal D5 self-collab errors when an artist has
multiple Deezer profiles (autoedit + label, etc.; cron crashed for
~12 h on 2026-05-02 with this exact case before the fix).

**Album-alien guard (2026-06).** Deezer's `/artist/{id}/albums` lists every
album an artist *participates* in, so a single guest feature on someone
else's album used to drag the whole foreign album in under our artista (the
"Baya Baye / Pangea" case — see `ingest-album-alie-recon.md`). `_create_track`
now creates a Canco under `album.artista` only when **`own_album OR
our_on_track`**: `own_album` is True when the album's Deezer titular
(`album.artist.id`, resolved once per album via `deezer.get_album_titular_id`
and reused for every track) is one of the artista's Deezer IDs; `our_on_track`
is True when any of those IDs appears among the track's **live** contributors
(`track.contributors`, never the persisted `contributors_raw`, whose role
labels are unreliable). Otherwise the track is skipped. Own albums (incl.
guest-led interludes) still enter whole; a track where the main contributor
resolves to a *different* known artista is created under that artista
(guard stands down). If the titular call fails the guard is conservative
(`own_album=True`, nothing dropped) so a transient API error never silences
real tracks.

### 3.4 `obtenir_metadata` — on demand
```bash
python manage.py obtenir_metadata [--artista-id N] [--force] [--dry-run] [--limit N]
```
For approved artists without an `ArtistaDeezer` link, resolves the
Deezer ID (name search + ISRC cross-validation) and pulls albums +
tracks. Previously the filter was `deezer_no_trobat=False`, but that
flag is a stale cache — the signal-cleared M2M relation is the source
of truth, so the command now targets `deezer_ids__isnull=True`
artists. The flag is still written on the failure path for
backwards-compat readers.

When the artista has more than one `ArtistaDeezer` row (Deezer
sometimes keeps separate profiles for the same person, e.g. an
early autoedit + a later label profile), the command iterates **all**
of them, principal first. The same multi-Deezer-ID guard described in
§3.3 applies to the contributor check. ISRC collisions during track
creation no longer abort the artista's transaction — they're caught,
logged with the canonical owner, and the loop continues so the rest
of the album processes cleanly.

Not in the cron by default — run on demand when staff approves a
batch of new artists without Deezer ids, or before a marketing push
that needs fresh fan counts.

### 3.5 `analitzar_whisper` — nightly 04:00 UTC
```bash
python manage.py analitzar_whisper [--limit N] [--refresh-older-than DAYS]
                                    [--canco-id PK] [--dry-run]
```
Runs `faster-whisper large-v3 .detect_language()` on each Canco's
30-second Deezer preview. Populates `Canco.whisper_lang`,
`whisper_p`, `whisper_all_probs` (99-lang JSON), `whisper_processat_at`.
Processes tracks never analysed first, optionally re-analyses rows
older than N days. Cron window is 04:00 with `--limit 200` (~27 s/track
on CPU; daily intake is <50 tracks/night, so it finishes well before
the 06:00 signal step). Slot moved 05:00→04:00 UTC (2026-05-05) to
clear the 04:30 MusicBrainz tick. Backfill of the historical ~6.7k
catalogue completed 2026-04-25.

See ADR-0014 (`docs/decisions/0014-whisper-lid-eval.md`) for the eval
numbers that justified this integration.

**Whisper-LID auto-approval gate (2026-07).** Right after each track's
Whisper fields are saved, `music.services.auto_aprovar_per_whisper`
runs: a still-pending track with an approved artist anchor and
`p_ca > WHISPER_AUTO_APPROVE_P_CA` (0.90) is auto-approved on the spot
(`motiu="auto_whisper"`), skipping the staff queue. The command reports
`auto_aprovades=N` in its summary. Justification: on 18 755 staff
decisions, `p_ca > 0.90` had 100 % precision once staff false-rejects
later re-approved are counted correctly; the first genuine non-Catalan
false positive only appears at p_ca ≈ 0.879. This is the only signal
that clears `ML_AUTO_APPROVE_THRESHOLD`. Unlike `auto_ml`, Whisper is an
independent oracle, so `auto_whisper` rows DO feed RF training (they
propagate the "this spotify/deezer id is ours" label). See
`music/constants.py::WHISPER_AUTO_APPROVE_P_CA` and models.md
(`HistorialRevisio.motiu`).

### 3.6 `obtenir_metadata_musicbrainz` — hourly at minute 30
```bash
python manage.py obtenir_metadata_musicbrainz [--refresh-days N]
                                              [--limit N] [--artista-id PK]
```
Pulls MusicBrainz metadata into our Artista / Album / Canço rows.
Single-instance `fcntl.flock` on `/tmp/mb_sync.lock`; MB's 1 req/s
rate limit is globally enforced by the client.

Per artist the flow is:
  0. **Validate the existing MBID** (added 2026-04-29). If the
     artista has both an MBID and PPCC `localitats`, fetch the MB
     artist's `area` and check it's PPCC-compatible. If MB explicitly
     says non-PPCC (e.g. "United States"), the MBID is auto-unassigned
     + added to `mb_blocked_mbids` + audit-logged
     (`artista_mbid_auto_unassign`) + the artist's Cançons/Albums
     have their MB fingerprints reset. This catches accumulated drift
     from the pre-2026-04-29 score-based auto-resolver. After
     unassign, step 1 re-attempts a clean match.
  1. If no `musicbrainz_id`: `resolve_mbid(artista)` →
     `search_artist(nom)` then disambiguate ourselves on **name +
     location**, ignoring MB's Lucene score as a quality signal.
     Rules (post 2026-04-29):
       * Exact-name match (case-insensitive), score ≥ 50 (loose
         floor — see `MB_AUTO_MATCH_SCORE`).
       * If our `Artista` has **localitats** in PPCC: keep candidates
         whose MB `area` matches PPCC. One match → accept. Zero or
         multiple → refuse (staff picks).
       * If our `Artista` has **no localitats**: refuse — we can't
         disambiguate honestly without a location anchor.
     History: pre-2026-04-29 the score floor was 95 and the location
     check only ran on multi-candidate ties; the "Casual" homonym bug
     (US rapper at 100 vs CAT band at 91) prompted the rewrite.
     Ambiguous names (Crim, Apa, …) still get skipped; staff sets
     the MBID by hand.
  2. Otherwise: `get_artist` + `get_artist_release_groups` +
     `get_release_group_with_recordings` → fills type/gender/area/
     begin_date/end_date/disambiguation/sort_name/aliases/tags/rating,
     plus URL relationships (bandcamp/spotify/youtube/youtube music/
     soundcloud/wikipedia/viasona/facebook/myspace — never overwriting
     values staff already set).
  3. **Reset** stale MB-reconciliation fields on this artist's
     existing Albums + Cançons (`mb_release_group_id`,
     `mb_recording_id`, `mb_work_id`, `mb_lyrics_language`,
     `mbrainz_confirmed`) so a corrected MBID purges its predecessor's
     fingerprints. The same `sync_from_mbid()` is also auto-invoked by
     `artista_detail` PATCH whenever staff changes the MBID — caught
     2026-04-29 ("Casual" case).
  4. Reconciles Albums by normalised title (fuzzy 0.9+) →
     `mb_release_group_id`, `mb_type_secondary`, `mb_status`,
     `mbrainz_confirmed=True`.
  5. Reconciles Cançons by ISRC first, then normalised title →
     `mb_recording_id`, `mb_work_id`, `mb_lyrics_language`,
     `mbrainz_confirmed=True`. A `Work.language=='cat'` is logged
     and feeds the `mb_lyrics_cat` ML feature.
  6. Caches `{isrcs, titles}` on `Artista.mb_discography_cache` for
     quick future matches.
  7. Stamps `mb_last_sync` regardless of outcome, so idle retries
     don't thrash.

There is also a one-shot audit command `auditar_mb_orphans` (added
2026-04-29) that sweeps existing rows looking for `mb_recording_id` /
`mb_release_group_id` values that no longer belong to the artist's
current MB discography (i.e. residue from a previous wrong MBID
auto-resolve). `--dry-run` lists; `--apply` resets.

Queue priority: aprovat > pendent > descartat; within each, oldest
`mb_last_sync` first. Refresh every 7 days by default. The cron
exits when nobody needs attention — idle invocations are cheap.

### 3.7 `netejar_caducades` — daily 04:00
```bash
python manage.py netejar_caducades
```
Deletes unverified tracks with `data_llancament < today - DIES_CADUCITAT`.
The cutoff comes from the shared `ingesta/caducitat.py::caducitat_cutoff()`
(`__lt`, so NULL-dated rows are KEPT — never purged).

**Survivor-mirror invariant (2026-06-03).** `enriquir_spotify`'s pending
candidate pool must be EXACTLY the survivors of this purge. The enrich
cron runs 03:00, the purge 04:00; before the guard, the equity floor
spent its reserved pending slots on high-`ml_confianca` old-catalog
tracks (past `DIES_CADUCITAT`) that the 04:00 purge then deleted an hour
later, cascade-dropping the fresh `SpotifyMetadata` — so pending coverage
of the `no_verificades` playlists stayed flat. `_select_candidates` now
wraps its pending pool in `ingesta/caducitat.py::exclude_caducats()` (the
queryset mirror of `is_caducat`: same `caducitat_cutoff()`, same `__lt`
NULL-keeping). Public pendents are NOT guarded — the purge only sweeps
`verificada=False`. See `playlists.md` "Spotify enrichment (Process B)".

### 3.8 `obtenir_metadata_lastfm` — daily 05:00 UTC
```bash
python manage.py obtenir_metadata_lastfm [--limit N] [--refresh-days N]
                                         [--artista-id PK] [--dry-run]
```
Pulls Last.fm artist-level metadata into `Artista.lastfm_*` and walks
the `artist.getSimilar` network to surface candidate pendents. Single-
instance `fcntl.flock` on `/tmp/lastfm_artist_sync.lock`. Defaults to
500 artists per invocation; refresh window 7 days.

Per artist (queue order = aprovat → pendent → discartat, then oldest
`lastfm_last_sync`):
  1. `artist.getInfo` → fill bio summary/content, listeners,
     playcount, ontour, tags, four image sizes, url.
  2. `artist.getSimilar` (limit 100, `match >= 0.3`) → for every
     candidate name, find an existing Artista by `lastfm_nom` or
     case-insensitive `nom`. If found, increment
     `nb_similars_lastfm`. Otherwise create a placeholder
     (`pendent_review=True`, `auto_descobert=True`,
     `font_descoberta="lastfm_similar"`, `nb_similars_lastfm=1`).
  3. Stamp `lastfm_last_sync = now()`.

Idempotency is gated by the source artist's recency: re-running on
the same artist within `--refresh-days` is a no-op (the queue skips
it). Within a single sync each similar's counter is incremented
exactly once.

The `nb_similars_lastfm` count surfaces in the staff Artistes /
Pendents lists and in the `LastfmPanel` of `ArtistaEditPage`. Pendents
gains a sort `?sort=similars_lastfm` (high-affinity first) and a
filter `?font_descoberta=lastfm_similar` to triage just this batch.

**Rejection memory — the resurrection loop fix (audit 2026-06-02).**
`_resolve_similar_target` has no separate rejection record (the resolver
only checks for an existing `Artista` row; `HistorialRevisio` is
per-cançó, so a song-less placeholder leaves no trail). When
`pendent_descartar` *hard-deleted* discarded placeholders, the next sync
of any approved artist that still recommended the name re-created the
pendent — Tremenda Jauría / The Fades were each discarded 4×. The fix:
discard now **tombstones** (`aprovat=False, pendent_review=False`) instead
of deleting (`web/api/staff/pendents.py`), so step 3 of the resolver
matches the surviving row and `_process` never re-queues it
(`pendent_review` stays False). The loop converges: every previously
deleted name resurrects at most once more, then the tombstone is
permanent. One-shot `backfill_lastfm_tombstones` (`--dry-run`)
re-tombstones the pendents that had already resurrected (live
`font_descoberta="lastfm_similar"` rows whose name carries a prior
`pendent_descartar`/deleted `StaffAuditLog` trace).

**Backlog drain preserves recommended candidates (2026-06-02).** The
weekly `netejar_pendents_no_ppcc` cron (Mon 02:15, cap 2000/run) that
drains the ~35 k `lastfm_similar` backlog now requires
`nb_similars_lastfm = 0` in its candidate filter — so it only sweeps the
dead weight (no approved recommender) and **preserves** every pendent
with ≥1 approved recommender for staff triage. `nb_similars_lastfm` is
the exact model field the prioritiser (`pendents_list`) sorts by, so the
preserved set equals the "sort by Last.fm affinity" view. Drain target
drops to the ~27 k dead-weight subset (~14 weeks); the ~8 k recommended
candidates stay.

### 3.9 Utility / ad-hoc commands (not cron-scheduled)
- `recalcular_ml` — force retrain the RF model and reclassify all unverified
  tracks. Normally runs automatically via `recalcular_ml_si_cal()` when 5+ new
  decisions have accumulated.
- `arxivar_senyal_vell` — quarterly archive of SenyalDiari rows older than 2 years
  (Φ6 retention).

**One-shot migrations already executed** live under
`scripts/archived_commands/` (out of `manage.py` reach):
`fix_album_dates`, `fix_artista_principal`, `deduplicar_isrc`,
`backfill_deezer_artistes`, `backfill_preview_url`,
`seed_spotify_playlists`. Preserved for history only.

### 3.10 Spotify playlist sync — daily 07:15 UTC
```bash
python manage.py actualitzar_playlists_spotify [--dry-run] [--only <codi>]
```
Reads every `SpotifyPlaylist` row with a configured `spotify_playlist_id`
and rewrites its tracklist in place. Runs 15 minutes after the provisional
ranking settles.

Per kind:
- `top` → `TopProvisional.filter(territori=X).order_by('posicio')[:40]`
- `novetats` → `Canco.filter(data_llancament=yesterday, activa=True)[:100]`

Resolves each Canço to a Spotify URI via `UserSpotifyClient.search_isrc()`
and caches the result on `Canco.spotify_id` so subsequent runs skip the
search. Mismatches (ISRC not found on Spotify) are silently dropped; the
`SpotifyPlaylist.last_n_tracks` vs `last_n_matched` fields expose the
mismatch rate per run.

One-time setup (once per Spotify account):
```bash
# Prints the OAuth URL, takes the `code` from the callback, persists
# refresh_token to SpotifyAuth (singleton).
python manage.py autoritzar_spotify

# Attach the existing Spotify playlist IDs to the 5 seeded rows.
python manage.py configurar_spotify_playlists \
    --top-cat <id> --top-val <id> --top-bal <id> --top-alt <id> \
    --novetats <id>
```

## 4. Track verification (ML classifier)

`music/ml.py` — Random Forest (100 estimators, `class_weight="balanced"`)
trained on **7,912** decisions from `HistorialRevisio`. After the
2026-04-25 TF-IDF retall: **49 features** (12 structured + 4 Whisper LID
+ 3 MusicBrainz + 30 TF-IDF char n-grams of the track title). Path
to today: 223 → 76 (slim) → 79 (+ MB) → 49 (TF-IDF cap 60 → 30 after
A/B 5-fold CV proved the smaller cap matched ROC-AUC and improved F1
+ accuracy slightly).

5-fold CV metrics (2026-04-25, 7 730 training rows, max_features=30):
- ROC-AUC **0.9998** · F1 **0.9908** · Accuracy **0.9953**.
- Top 7 features (4 of which are Whisper LID) carry **70%** of the
  signal; estructurals dominate at 95.6 %, TF-IDF only 4.4 %.

Top 5 features by importance (2026-04-25 retrain, max_features=30):
1. `ratio_rebuig_par_artist` (20.0%) — Bayesian-smoothed (k=5,
   prior=0.5). Renamed 2026-05-25 from `ratio_rebuig_artista` (by
   name only). The new key is the most-specific available among
   `(artista_deezer_id, artista_spotify_id)`,
   `artista_deezer_id` alone, then `artista_nom` as legacy
   fallback. Disambiguates Deezer-collapsed homonyms (canonical
   `Aion` and `Jim` cases) so the wrong-Aion's rejections stop
   penalising the real-Aion's catalogue. Position at index 8 of
   `FEATURE_NAMES` preserved across the rename: length stays 50,
   so the RF on disk keeps loading; quality degrades silently
   at that index until the next `entrenar_model()` learns the
   new splits.
2. `whisper_p_ca` (17.8%) — Whisper LID confidence the track is català
3. `ratio_rebuig_registrant` (10.7%)
4. `whisper_p_en` (9.8%)
5. `whisper_margin_ca` (9.0%)

Bayesian smoothing on the three `ratio_rebuig_*` features: returns
`(rej + k*p) / (total + k)` with `k=5, p=0.5`, so an artist with few
decisions can't collapse to 0 or 1 from one or two calls. Prevents
feedback loops where an early false rebuig biases the model
permanently.

Per-pair coverage of historical decisions: `HistorialRevisio`
stores `artista_spotify_id` as a snapshot from migration 0085
onwards. New decisions fill it from the canço's `SpotifyMetadata`
at decision time. Legacy rejection rows (essentially 0 % enriched
as of 2026-05-25) are filled in by the dedicated drain command
`enriquir_spotify_rebuigs` (see section 5 below) on a separate
daily budget. Until coverage fills out, the per-pair ratio falls
back to per-deezer or per-name automatically — same FEATURE_NAMES
slot, no MISALIGNED flag.

### Backfill rate controller (AIMD)

`ingesta/clients/spotify_backfill_controller.py` implements an
additive-increase / multiplicative-decrease controller that
chooses the daily limit `enriquir_spotify_rebuigs` runs at. The
shape matches TCP congestion control: ramp up slowly, drop hard
on the first sign of trouble.

State persists at `/var/log/topquaranta/status/
enriquir_spotify_rebuigs.controller.json`. Each daily run:

  1. Looks at the two cooldown files
     (`enriquir_spotify.cooldown` for maintenance and
     `enriquir_spotify_rebuigs.cooldown` for the backfill itself)
     plus the persisted `last_ban_at` (**48 h** memory) to decide
     whether a ban has been observed.

  > **Ordering invariant (2026-05-30):** `handle()` runs
  > `adjust_for_run()` **before** `clear_expired()`, so the
  > controller checks for recent bans BEFORE expired cooldown
  > sentinels are pruned. A Spotify Retry-After runs 18–24 h —
  > longer than the gap to the next daily tick — so by the time the
  > cron fires again the sentinel has usually just expired. The old
  > order pruned it first, `detect_recent_ban` found nothing,
  > `last_ban_at` stayed null, no multiplicative-decrease fired, and
  > the limit bumped back up the day after a ban (the 24/05 and
  > 29/05 bans were both lost). Detection keys on the sentinel's
  > **mtime** — read as **UTC-naive** (`fromtimestamp(..., tz=utc)`) to
  > match `_utcnow()` / `last_run_at` / `last_ban_at`; plain
  > `fromtimestamp()` returns server-local (CEST) time and stored a ban
  > 2 h in the future (fixed 2026-05-30) — not its `resume_at`, so an
  > expired-but-present file still counts; the 48 h `last_ban_at`
  > memory covers the case
  > where the maintenance command pruned the sentinel before the
  > backfill tick. The decrease is `save_state`d before the
  > cooldown-active early return, so it persists even when the run
  > then aborts.
  2. If a ban is fresh: drop to `last_safe_limit` if any (the
     most recent limit that survived `DAYS_BEFORE_BUMP = 3` days
     unbanned); otherwise halve, with `MIN_LIMIT = 50` as the
     floor. Reset the day counter.
  3. If no ban: increment the day counter. After 3 ban-free
     days, promote the current limit to `last_safe_limit` and
     bump it by `BUMP = 200`, capped at `MAX_DAILY_LIMIT = 800`.

Volume reasoning for the constants: each backfill cançó costs
up to 3 Spotify API calls (search + track + artist). Hard
ceiling 800 cançons/day → 2 400 backfill calls + ~150
maintenance ≈ 2 550 calls/day, well under the ~3 600/day that
triggered the 2026-05-24 ban. Initial limit 200 → 600 + 150 =
750 calls/day, comfortably safe.

Manual overrides via `--limit <N>` bypass the controller for one
run and leave the persisted state untouched. Use them for
sanity-test runs or one-off pushes, never as a daily setting.

### Cascade (alive -> orfes -> rest -> pendents)

`enriquir_spotify_rebuigs` walks four tiers in priority order
within a single run; each tier only fills what the previous left
in the AIMD budget:

1. **Live shortlist alive** — Cançons that still exist in the DB
   whose `artista_deezer_id` carries at least one
   `desvincular_album` HR row. Three calls per cançó (search +
   track + artist) and the full `SpotifyMetadata` is persisted,
   so the playlist sync can use the resulting `spotify_id`.
   The HR scan pre-filters `canco_deezer_id` against the set of
   surviving Cançons whose `SpotifyMetadata` is not in
   `LOCKED_STATUSES` (`found` or `manual` — staff-pasted manual links,
   2026-06-02, are excluded here too so their id is never re-resolved;
   see `playlists.md`) *before* the budget cap is applied,
   and tiebreaks the `created_at` ordering with `pk`. The
   pre-filter is required because ~95 % of shortlist HR rows point
   to cançons already deleted by `rebutjar_album`/`rebutjar_artista`;
   without it the cap was spent entirely on dead deezer_ids and the
   tier starved to 0 even when live candidates existed (2026-05-28
   `live_alive=0` incident). The `pk` tiebreak makes the capped
   selection deterministic across runs given large same-`created_at`
   batches.
2. **Orphan flow shortlist** — HR rows whose `canco_deezer_id`
   no longer has a matching Canco (deleted by `rebutjar_album` /
   `rebutjar_artista`) but still carries an ISRC. One `/v1/search`
   per distinct ISRC; the principal `spotify_artist_id` from the
   response is written back to every HR row carrying that ISRC.
   No `Canco` or `SpotifyMetadata` rows are created. Every HR row
   gets `spotify_lookup_at` stamped (found or not), and the
   candidate query excludes rows looked up within the last 30
   days so a not-found ISRC is not re-searched on every nightly
   run. Behind `--include-orfes`.
3. **Rest of rebuigs** — when `--shortlist-only` is OFF, tiers 1
   and 2 widen beyond the `desvincular_album` shortlist to any
   rebuig HR row with an ISRC.
4. **Pendents** — Cançons with `verificada=False, activa=True`
   and an ISRC that have not been classified yet. Most-recent
   `created_at` first so the freshest queue items reach the
   playlists first. Behind `--include-pendents`.

The AIMD budget caps total items processed in a run, not API
calls. Tier 1 and tier 4 cost ~3 calls/item; tier 2 costs ~1.
A run that shifts toward orphans is automatically more
conservative on the metadata quota.

`--include-orfes` and `--include-pendents` are off by default and
the production cron does not pass them. They are validated
manually via `tq-run enriquir_spotify_rebuigs ...` before any
schedule change.

### Shared metadata cooldown (`spotify_metadata_cooldown`)

The maintenance enrichment and the rebuig backfill both call the
same Spotify endpoints (`/v1/search`, `/v1/tracks`, `/v1/artists`)
and share a single Spotify quota bucket. Until 2026-05-25 each
command kept its own cooldown file, so a ban seen by maintenance
left the backfill free to keep probing — which the Spotify docs
warn extends the ban window. The shared module
`ingesta/clients/spotify_metadata_cooldown.py` consolidates the
state:

- **Single canonical file** at
  `/var/log/topquaranta/status/spotify_metadata.cooldown`. Both
  commands write to it on `RateLimitedError` and check it before
  the first API call.
- **Legacy fallback reads** of
  `enriquir_spotify.cooldown` and `enriquir_spotify_rebuigs
  .cooldown` keep an old-binary ban honoured during the
  transition. New writes never touch the legacy paths, so they
  drain naturally as their `resume_at` passes.
- **`active_resume_at`** returns the latest unexpired `resume_at`
  across every file. The longest pending back-off wins
  (conservative against silently shrinking the window).
- **`clear_expired`** prunes files whose `resume_at` is in the
  past on every successful run, so the AIMD controller's mtime-
  based ban detection does not re-look fresh after every
  filesystem touch.
- **Playlist sync is OUT.** `actualitzar_playlists_spotify` hits
  `/v1/playlists/<id>/items`, a separate bucket. Empirically the
  playlist sync ran successfully during the 2026-05-24 metadata
  ban without extending it; routing playlist writes through the
  shared cooldown would cause spurious skips of work Spotify
  allows. The test
  `test_playlist_sync_does_not_reference_metadata_cooldown`
  pins that boundary.

Classes: `A ≥ 0.7`, `B 0.4–0.7`, `C < 0.4`. Stored on `Canco.ml_classe` +
`ml_confianca`. Model files: `music/ml_model.joblib` + `ml_tfidf.joblib`.
Both cached in-memory with mtime-based invalidation.

Retraining triggers automatically via `recalcular_ml_si_cal()` when
≥ `MIN_NEW_DECISIONS=5` records have arrived since last run (marker:
`/tmp/tq_last_ml_recalc`). Runs in a daemon thread. If
< `MIN_TRAINING_SAMPLES=20` decisions exist, `pre_classificar` falls
back to a hand-tuned heuristic.

Live feature importances + training size + class distribution + mean
confidence are surfaced on `/staff/estat` via `/api/v1/staff/estat/`.

## 5. Cron schedule

File: `/etc/cron.d/topquaranta`. Commands go through
`/home/topquaranta/bin/tq-run` which captures each run's exit code and last
output into `/var/log/topquaranta/status/<tag>.status` — consumed by the
health check (§7).

```cron
# Hourly: ingest + metadata refresh
0 * * * *    topquaranta  tq-run obtenir_novetats                 # every hour
30 * * * *   topquaranta  tq-run obtenir_metadata_musicbrainz     # 30 min after novetats

# Nightly pipeline (each step feeds the next)
0 3 * * *    postgres     tq-backup                               # 03:00 DB backup
0 4 * * *    topquaranta  tq-run netejar_caducades                # 04:00 purge expired
0 4 * * *    topquaranta  tq-run analitzar_whisper --limit 200    # 04:00 Whisper LID
0 5 * * *    topquaranta  tq-run obtenir_metadata_lastfm --limit 500  # 05:00 Last.fm artist meta
0 6 * * *    topquaranta  tq-run obtenir_senyal                   # 06:00 Last.fm signal
45 6 * * *   topquaranta  tq-run detectar_anomalies_senyal        # 06:45 clean signal before ranking
0 7 * * *    topquaranta  tq-run calcular_top --provisional       # 07:00 daily provisional
15 */2 * * * topquaranta  tq-run actualitzar_playlists_spotify --freq daily  # every 2h Spotify Process A

# Weekly
0 8 * * 6    topquaranta  tq-run calcular_top                     # Sat 08:00 official
0 10 * * 6   topquaranta  tq-run actualitzar_playlists_spotify --freq weekly # Sat 10:00 weekly playlists

# Retention + ops
0 5 1 1,4,7,10 * topquaranta tq-run arxivar_senyal_vell           # quarterly
30 4 1 * *   postgres       tq-restore-test                       # monthly
*/30 * * * * topquaranta    tq-recover                            # recovery sweep
```

Curated subset — the **source of truth is `deploy/cron.topquaranta`**
(synced by `bin/tq-sync-infra`). Not shown above: Spotify Process B
enrichment (`enriquir_spotify` 03:00, `enriquir_spotify_rebuigs`
05:00), self-hosted covers (`descarregar_portades` 02:00), SEO
inference + metrics snapshots (02:00, 21:00–23:30), social distribution
(`publicar_social` / `publicar_canal`, Sat/Wed/Mon/Fri/Tue) and the
`tq-health` watchdog (hourly at :15).

Two pacing changes since the original schedule (2026-04-25 sweep):
- `obtenir_metadata_musicbrainz` was `*/15` during the MB backfill;
  now hourly at minute 30 — the queue is empty most of the time and
  the 15-min cadence was just polling for nothing.
- `analitzar_whisper` was 01:30 with `--limit 700` (5 h backfill
  window). Backlog drained 2026-04-25; now 04:00 with `--limit 200`
  (slot moved 05:00→04:00 on 2026-05-05 to clear the 04:30 MB tick),
  so it slots cleanly into the daily pipeline before signal ingestion.

## 6. Backups

`/home/topquaranta/bin/tq-backup` runs daily at 03:00 as `postgres`.
Tiered retention in `/home/topquaranta/backups/`:
- `daily/` — last 7 days
- `weekly/` — Sundays, last 4 weeks
- `monthly/` — 1st of month, last 12 months

DB is ~45 MB uncompressed; gzipped ≈ 3 MB per backup. Total retention
worst case ≈ 60 MB.

## 7. Monitoring / health check

No external services. Everything is file-based on the server.

- **`errors.log`** (`/var/log/topquaranta/errors.log`): every `logger.error(...)`
  / `logger.exception(...)` call across the project ends up here (configured
  in `settings/base.py::LOGGING`). Tests are isolated via a `NullHandler` in
  `settings/test.py` so this file only ever captures real production errors.
- **Per-command status files** (`/var/log/topquaranta/status/<tag>.status`):
  written by `tq-run`. Contain `status=OK|FAIL`, `exit_code`, `last_run`
  (ISO-8601), and the last 20 lines of output.
- **`/home/topquaranta/bin/tq-health`**: gathers the facts (status files +
  `cron-meta.json`, disk, web smoke, Spotify sub-checks, pending migrations,
  today's Django errors) in shell, then delegates the PRESENTATION to
  `analytics/health_report.py` (pure stdlib, runs without Django). Exits
  non-zero if any command is FAIL/STALE/STUCK past its cadence (a gated
  feature reporting `status=DISABLED` — e.g. `tq-backup-offsite` before
  activation — renders gray and never escalates), disk ≥90%,
  a web check fails, a Spotify sub-check is WARN/CRIT, a migration is
  pending, or there are Django ERRORs today. The rendered report has:
  a one-line **executive summary** (🟢 Tot OK / 🔴 N anomalies), an
  **Anomalies** block (only genuinely-escalating items; `[silenced]`
  known-issues stay in their group and don't turn the header red), **crons
  grouped** by logical area, **Sistema** + **Spotify** sections, and a
  **legend**. Timestamps render in **CEST** (UTC stays in logs/files).
  `--email-on-fail` mails the report to admin only when something escalates,
  with signature dedup so a persistent failure doesn't spam hourly.

## 6. Artist discovery

1. **Deezer contributor detection** — `obtenir_novetats` P3 reads an album's
   tracks; unknown contributors get created as
   `Artista(aprovat=False, auto_descobert=True, pendent_review=True,
   font_descoberta="collaborador")` — `pendent_review=True` enqueues
   it for staff review; `auto_descobert` is immutable provenance.
2. **User proposal** — `PropostaArtista` submitted via `/compte/artista/proposta/`;
   staff approves via `/staff/propostes/<pk>/` which creates the Artista
   together with its Deezer IDs + locations in one transaction.
3. **Manual** — staff can create an approved artist directly.

All auto-discovered artists sit in the pending queue (`/staff/artistes/pendents/`)
until a human approves them with a municipality assignment (which auto-sets
the territory via the `ArtistaLocalitat` → `Municipi` → `Territori` chain).

## 7. HomePage feed endpoints (Sprint I bis, 2026-04-26)

The redesigned `/` is composed from a small set of read-only public
endpoints, all anonymous-friendly and cached via `cache_for_anon`.
Live in `web/api/home_views.py`:

| Endpoint | Cache | Returns |
|---|---|---|
| `GET /api/v1/stats/` | 60 s | `{cancons_verificades, artistes_aprovats, territoris_actius, setmana}` — the latter is the latest `TopSetmanal.setmana` against which `territoris_actius` is computed (number of distinct `territori` values). |
| `GET /api/v1/top/nova-setmana/` | 1 h | First entry (lowest `posicio`) of the latest PPCC `TopSetmanal` whose `canco_id` was absent from the previous PPCC week. `null` when first run / no movement. |
| `GET /api/v1/artistes/destacat/` | 1 h | The artist with `UserArtista.verificat=True` whose biggest per-cançó positive PPCC delta is the largest. Tie-breaker: count of `Canco(verificada=True)`. Includes `lastfm_image_large`, `bio` (or `lastfm_bio_summary` truncated to 120 chars), territoris codes. |
| `GET /api/v1/artistes/descoberta/?limit=N` | 1 h | Artists `aprovat=True`, `created_at >= today − 30 d`, with `≥1` verified cançó, never present in `TopSetmanal`. Ordered by `-created_at`. `limit` capped at 12. |

Plus extensions to existing endpoints:

- **`GET /api/v1/albums/`** (new list view; the per-slug detail
  endpoint is unchanged). Filters: `ordering=±data_llancament`,
  `amb_verificades=true|false`, `limit≤24`. Annotates each album
  with `n_verificades` (count of `Canco(verificada=True, activa=True)`
  rows under it).
- **`GET /api/v1/top/?oficial=true&limit=N`**. The default behaviour
  falls back to `TopProvisional` when no weekly row exists; with
  `oficial=true`, the response is `entries=[]` instead — the
  HomePage hero can then hide the section cleanly. `limit` is also
  honoured (capped at `MAX_POSICIONS_TOP`) so the home strip can
  request only the 10 first rows.

## 8. Social distribution (Sprint I)

App `social/` + package `ingesta/social/` ship the weekly Instagram
publication.

**Model**: `SocialPost(platform, tipus, territori, setmana, status,
instagram_media_id, metadata, error_msg, scheduled_at, published_at)`.
Unique together `(platform, tipus, territori, setmana)` makes the
publication command naturally idempotent — re-running `publicar_social`
is safe; only `--force` re-publishes a `publicat` row.

**Commands**:
- `autoritzar_instagram` — interactive token-exchange flow. Run once
  per long-lived (60-day) token. Prompts for the OAuth `code`,
  exchanges it for a long-lived token, prints the values to add to
  `.env`.
- `publicar_social [--data D] [--tipus T] [--platform P] [--dry-run]
  [--force]` — the cron entrypoint. Walks `ingesta.social.calendari`
  for the target weekday, gates each slot on the distribution matrix
  (`MatriuPublicacio.pot_distribuir_avui` — actiu + optional
  `dia_setmana`), builds payload, renders PNGs to
  `<SOCIAL_CACHE_DIR>/renders/`, uploads them via
  `ingesta.social.instagram_client` and publishes.
- `renovar_token_instagram` — monthly cron. Refreshes the long-lived
  token via the Graph API; prints the new value (you write it to
  `.env`).

**DRY_RUN**: `instagram_client.is_dry_run()` returns `True` when
`INSTAGRAM_ACCESS_TOKEN` is empty or `"test"`. Every API method
returns a synthetic ID and logs what would happen; PNGs are still
rendered. This is the default during local development.

**Cron schedule** (`deploy/cron.topquaranta`):

| Day | Slot |
|---|---|
| Saturday 09:30 UTC | feed + stories PPCC |
| Wednesday 09:30 | feed + stories territorial rotatori |
| Monday 09:30 | feed + stories second territorial |
| Friday 10:00 | feed nous singles |
| Tuesday 10:00 | feed nous àlbums |
| 1st of month 03:00 | `renovar_token_instagram` |

The cron rows are present unconditionally; per-slot gating happens
inside `publicar_social` via the distribution matrix, marking the
SocialPost as `omes` when the `(canal × tipus)` cell is off or its
`dia_setmana` doesn't match today. (The legacy `min_fase` rollout
phase was removed 2026-06.)

**Staff cockpit**: `/staff/social` exposes the SocialPost list along
with the kill switch, the distribution matrix (canal × tipus ×
dia_setmana) and the `story_max_cancons_ppcc` slider; preview button
renders dry-run PNGs and prints the captured stdout; "Publicar ara"
forces a re-publication. Token expiry days shown via
`instagram_client.days_until_expiry()`.

**Caddy serving**: Caddy needs a `handle_path /static/social/*` rule
pointing at `/var/cache/topquaranta/social/renders/` so Meta can
fetch the rendered PNGs by URL. Update `deploy/Caddyfile` before
the first non-dry-run publication.
