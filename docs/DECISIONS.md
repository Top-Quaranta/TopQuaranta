# Decisions (ADR digest)

This digest replaces reading the 17 full ADRs (~1.900 lines) for day-to-day
work: one entry per decision, what/why/status, plus the test or config that
guards it and any gap between the ADR text and what actually ships. It is a
summary, not a substitute — when a decision is being re-litigated, changed
or superseded, read the full record. Full ADRs live in
`docs/archive/decisions/` (one file per number, same slugs as below).

## ADR-0001 — Gunicorn `--reload` removed
- **Decision:** Drop `--reload` from `deploy/topquaranta-web.service`; code reaches prod only via `bin/tq-deploy` (`git reset --hard origin/main` → `migrate` → `systemctl reload`).
- **Why:** Three 5xx bursts on 2026-05-19/20 — workers hot-reloaded edited `models.py` before the migration ran. Operator discipline is the wrong layer for the fix.
- **Status/date:** Accepted 2026-05-20 (PR #55).
- **Guarded by:** `tq-sync-infra` reinstalls the unit file from the repo on every deploy; unit-file comment documents the removal; `tq-health` git-drift check.
- Full text: docs/archive/decisions/0001-gunicorn-no-reload.md

## ADR-0002 — GSC auth via OAuth user creds (admin@)
- **Decision:** `recollir_metrics_gsc` authenticates with OAuth user credentials minted under `admin@topquaranta.cat` (`.env::GSC_OAUTH_REFRESH_TOKEN`); the service account stays in `.secrets/` as inactive fallback.
- **Why:** Google bug on `sc-domain:` properties blocks adding a Service Account as user; a personal-account token broke on 2026-05-20 when permissions were tidied.
- **Status/date:** Accepted 2026-05-21.
- **Guarded by:** `_build_credentials()` falls back to SA when the three `GSC_OAUTH_*` vars are absent; re-mint procedure in `docs/ops/runbook.md`.
- **Live caveat:** Refresh token must be re-minted whenever the property's user list changes; no permission-layer synthetic monitor yet (backlog).
- Full text: docs/archive/decisions/0002-gsc-oauth-user-creds.md

## ADR-0003 — Pytest pins settings via `--ds=`
- **Decision:** `pytest.ini` uses `addopts = --ds=topquaranta.settings.test` instead of the `DJANGO_SETTINGS_MODULE` ini key.
- **Why:** pytest-django precedence is `--ds=` > env var > ini; an exported `web_server` settings module on the box silently ran the suite against prod settings and mailed admin@ with `DisallowedHost`.
- **Status/date:** Accepted 2026-05-20 (PR #56).
- **Guarded by:** `pytest.ini` (inline comment); ADR-0017 kept the pin.
- Full text: docs/archive/decisions/0003-pytest-ds-pin.md

## ADR-0004 — Workflow Sol·licituds de Revisió
- **Decision:** New `comptes.SolicitudRevisio` (gestor, artista, `pendents_ids`, `rebutjades_snapshot`, `estat` pendent/revisada/resolta) + `HistorialRevisio.reconsiderada`; ingest crons filter `decisio="rebutjada", reconsiderada=False`; staff workbench at `/staff/sollicituds-revisio/`.
- **Why:** The free-form DM to the `admin` pseudo-user collapsed under real moderation load — no selection, no state, no path to reapprove.
- **Status/date:** Accepted 2026-05-20 (PR #54).
- **Guarded by:** `ingesta/tests/test_previously_rejected_reconsiderada.py`, `web/tests/test_sollicituds_revisio_workbench.py`.
- Full text: docs/archive/decisions/0004-workflow-sollicituds-revisio.md

## ADR-0005 — Bluesky `upload_blob` timeout 180 s + retry 3×
- **Decision:** Blob upload timeout 60 → 180 s (`BLUESKY_UPLOAD_TIMEOUT_S`), up to 3 attempts with 5 s / 15 s back-off, retrying only `ReadTimeout`/`ConnectionError`; 4xx/5xx propagate.
- **Why:** ~2/3 of weekly Bluesky posts (five in 16–20 May 2026) dropped silently on 4×1 MB carousels; `status=error` reset the skip counter so `tq-health` never alerted.
- **Status/date:** Accepted 2026-05-21.
- **Guarded by:** `social/tests/test_bluesky_upload_retry.py`.
- **Live caveat:** Worst case ~12 min per publication if the PDS is fully down; per-channel consecutive-error aggregation in `tq-health` still backlog.
- Full text: docs/archive/decisions/0005-bluesky-timeout-retry.md

## ADR-0006 — Positions as Catalan ordinals, not `#N`
- **Decision:** `social.narrative.utils.ordinal_ca(n)` (`1r 2n 3r 4t 5è … 99è`, IEC forms) replaces every `#N` in the hero/top5 banks and detectors; detectors expose `posicio_ordinal` next to `posicio`.
- **Why:** Instagram/Telegram (and Bluesky/Mastodon) render `#3` as a clickable hashtag, sending traffic to a generic tag search and breaking the read.
- **Status/date:** Accepted 2026-05-21.
- **Guarded by:** `social/tests/test_ordinal_ca.py`; `test_short_phrases_fit_under_120_chars`; `test_no_positional_hashtag_in_any_channel`.
- Full text: docs/archive/decisions/0006-narrative-ordinals-catalan.md

## ADR-0007 — `@username` restored in the Instagram composer
- **Decision:** `social/narrative/composers/instagram_feed.py` rewrites `Scenario.data["artista"]` (+ `de_/per_a_/per_` variants) and top-5 entries to `@handle` when the artist has `instagram_url`; banks stay channel-agnostic; no other composer emits handles.
- **Why:** The Fase 4 narrative engine bypassed `captions.py::_artist_label`, so IG lost the `@handle` (no notification, no clickable link). Only IG autolinks handles; other networks have different mention syntax and we store no per-network handles.
- **Status/date:** Accepted 2026-05-21 (PR #59).
- **Guarded by:** `social/tests/test_captions.py::test_handle_only_on_instagram_feed`; mutation-verified 2026-08-16.
- Full text: docs/archive/decisions/0007-instagram-at-handles-restored.md

## ADR-0008 — Narrative detectors a9–a12 + tertiary slot on IG
- **Decision:** Four detectors (`a9_debut_anywhere`, `a10_artista_first_ever`, `a11_top5_drop_generic`, `a12_artista_emerging`), 180 new templates (4 × 3 tiers × 15), and a third scene (short tier) in the IG feed composer with truncation order tertiary → secondary → top-5 → hashtags. Other channels keep 2 scenes (budget).
- **Why:** With 8 detectors, ~30 % of week/territory combos fell to `fallback_no_event` across all 5 channels despite real mid-table movement.
- **Status/date:** Accepted 2026-05-21.
- **Guarded by:** `test_each_scenario_has_exactly_three_length_tiers_with_15_entries_each`, `test_no_emoji_repeats_more_than_twice_per_bank`, no-`#N` checks (`social/tests/test_narrative*.py`).
- **Live caveat:** Engine has since grown to 13 detectors (a13 + fallback; `test_narrative_alpha.py`).
- Full text: docs/archive/decisions/0008-narrative-detectors-expanded.md

## ADR-0009 — Spotify identity migrated to admin@ + Premium
- **Decision:** Transfer the Spotify Developer app to `admin@topquaranta.cat` (same client id/secret), subscribe that account to Premium Individual (11.99 EUR/mo), move redirect URI to `/staff/social/spotify/callback` (`SPOTIFY_REDIRECT_URI`).
- **Why:** Cron had failed daily since 2026-04-20: no `SpotifyAuth` row ever minted, and the Web API returns 403 unless the app owner has Premium; personal-account ownership is the anti-pattern `identities.md` Rule 1 forbids (GSC incident).
- **Status/date:** Accepted 2026-05-22.
- **Guarded by:** `analytics/health_report.py` Premium check (`me().product == "premium"`) on the tq-health report; token row in `docs/policies/identities.md`.
- **Live caveat:** Premium activation → API acceptance lag of "a few hours"; a trial expiry or downgrade silently re-breaks the cron.
- Full text: docs/archive/decisions/0009-spotify-identity-migration.md

## ADR-0010 — No second output to YouTube Music (yet)
- **Decision:** No YT Music playlist output; keep the "Escolta-ho a" search-URL pill only. Re-evaluate 2027-05.
- **Why:** No first-party YT Music API (`ytmusicapi` is reverse-engineered, breaks 2–3×/yr); no `isrc:` search filter; Data API quota (10 k units/day) is 2× short of one daily refresh; playlist ownership tied to a personal Google account.
- **Status/date:** Accepted 2026-05-22.
- **Live caveat:** Flip triggers: official API ships, `ytmusicapi` stable 12 months, or >25 % of `escolta_click` events prefer YT Music.
- Full text: docs/archive/decisions/0010-why-not-youtube-music.md

## ADR-0011 — Spotify sync cron schedule (daily 6 h + weekly Saturday)
- **Decision:** Split the single 07:15 line into `--freq daily` every 6 h and `--freq weekly` Saturday 10:00 UTC (30 min after `publicar_social`), same command.
- **Why:** Daily playlists source `TopProvisional` (rebuilt 07:00) and went stale for up to ~24 h; weekly ones source `TopSetmanal` and were rewritten daily for nothing.
- **Status/date:** Proposed 2026-05-22 — never flipped to Accepted in the file.
- **Guarded by:** `deploy/cron-meta.json` entries `actualitzar_playlists_spotify` (max_age 3 h) and `_weekly` (170 h).
- **Live caveat:** `deploy/cron.topquaranta` ships the daily run at `15 */2 * * *` (every 2 h, 12×/day, decided 2026-05-23 once Process A became cache-only per ADR-0013), not every 6 h; weekly line matches the ADR.
- Full text: docs/archive/decisions/0011-spotify-cron-schedule.md

## ADR-0012 — Spotify Web API capabilities for new apps (post-2026)
- **Decision:** Spotify is only (1) a canonical identifier source (`spotify:track/artist:<id>`) for playlists/embeds and (2) an artist-disambiguation oracle. Never a metadata source: no popularity, previews, genres, followers, audio-features, batch endpoints, or recommendation graph.
- **Why:** Empirical probe 2026-05-22: "Wave One" (Nov 2024) nulls those fields and 403s batch/audio endpoints for new apps; Feb 2026 migration replaced `/tracks` with `/items` (cause of the 2026-05-22 outage, PR #66).
- **Status/date:** Accepted 2026-05-22 (PR #66).
- **Guarded by:** `UserSpotifyClient.throttle_s` 0.2 s floor; single-fetch only in Process B; `GET /playlists/{id}/items?limit=1` for counts (legacy `tracks.total` stale).
- **Live caveat:** Re-run the probe when Spotify ships its next policy wave; no deprecation calendar exists.
- Full text: docs/archive/decisions/0012-spotify-api-capabilities-2026.md

## ADR-0013 — Split Spotify cron into Process A (sync) and Process B (enrichment)
- **Decision:** `actualitzar_playlists_spotify` becomes cache-only (reads `SpotifyMetadata.spotify_id`, pushes via `/items`, never `/search`); new `enriquir_spotify` resolves ISRC → id + track/artist metadata one-shot per Cançó with `--limit/--throttle/--retry-not-found/--target-playlists`; new `SpotifyMetadata` model + `Artista.spotify_artist_dispersio`.
- **Why:** Cold-cache bursts hit `/search` hundreds of times → `429 Retry-After 86076` (24 h ban) wedged the whole sync although the playlist-write bucket was fine.
- **Status/date:** Accepted 2026-05-22.
- **Guarded by:** `ingesta/tests/test_actualitzar_playlists_spotify.py` (cache-only), `test_enriquir_spotify*.py`, `test_user_spotify_client_throttle.py`; `RateLimitedError` → `CommandError` (non-zero exit for the watchdog).
- **Live caveat:** Cron: Process B daily 03:00 `--limit 250 --throttle 0.5` (ADR text says hourly `--limit 200`), plus `enriquir_spotify_rebuigs` at 05:00.
- Full text: docs/archive/decisions/0013-spotify-sync-enrichment-split.md

## ADR-0014 — Whisper as the language-ID signal (LID evaluation)
- **Decision:** faster-whisper large-v3 (CPU int8) `detect_language()` on the 30 s preview feeds `Canco.whisper_lang / whisper_p / whisper_processat_at` as a staff triage badge + RF feature. Signal, not gate; no separate instrumental filter (LID subsumes it).
- **Why:** 48-clip eval: precision(ca) 100 %, recall 81 %, all 27 non-ca clips below threshold. SpeechBrain VoxLingua107 rejected (36.8 % accuracy, 2 false positives on `ca`).
- **Status/date:** Accepted 2026-06-13; the raw harness (`scripts/model_comparison/`) was deleted the same day, last at commit `9c83908`.
- **Guarded by:** `WHISPER_MODEL` env-configurable; `analitzar_whisper` shares the `ram_heavy` SingletonLock with MusicBrainz.
- **Live caveat:** 48 clips is go/no-go, not a benchmark; the mixed-language featured-verse case is untested.
- Full text: docs/archive/decisions/0014-whisper-lid-eval.md

## ADR-0015 — Instagram collaborator invitations for feed posts
- **Decision:** Flag-gated layer: `InvitacioColaboracioIG` (unique per artist × media), slot policy in `social/collaboradors.py` (3 slots: 2 for proven acceptors, 1 fresh; cooldowns A 15 d / C 90 d; pending blocks re-invite), non-blocking publish guard (drop bad handle, substitute, publish without if pool empties), poller `pollar_colaboracions_ig` (expires pending → `caducada` at 14 d, writes acceptance-rate `MetricaPipeline`). Feed only — stories cannot take collaborators.
- **Why:** Collaborator invites put the post on the artist's own grid (reach beyond `user_tags` mentions); handle coverage of the working pool reached 51.4 % on 2026-07-03.
- **Status/date:** Accepted 2026-07-03; all tranches merged by 2026-07-13 (PRs #308, #309); flag ON in prod, first supervised batch 2026-07-06.
- **Guarded by:** `social/tests/test_collaboradors.py` (`test_slot_policy_empty_registry_returns_top3`, `test_collab_bad_handle_substitutes_next_candidate`), `test_publicar_social_collaboradors.py`; `GRAPH_MAX_COLLABORATORS = 3` clamp; hourly cron `pollar_colaboracions_ig`.
- **Live caveat:** Programmatic acceptance reads proved unviable (Instagram Login lacks the edge; FB user token returns empty; Page token inaccessible) — acceptances are marked manually via `POST /staff/social/invitacions/acceptar/`; 14-day window is a module constant, not a `ConfiguracioGlobal` field.
- Full text: docs/archive/decisions/0015-ig-collaborator-invitations.md

## ADR-0016 — Feed artwork covers + `moviment` tipus
- **Decision:** (1) Duotone artwork on the feed cover slide (`social/duotone.py`; #1 cover for tops, 2×2/2×3 novetats mosaic capped by `feed_artwork_mosaic_max`), gated by `feed_artwork_actiu`. (2) New Thursday `SocialPost.TIPUS_MOVIMENT` over the Global top (`payload.build_moviment`: direct top-10 entry, else strongest rise ≥ `moviment_pujada_minima`, else omitted), gated by `moviment_actiu`.
- **Why:** Typographic covers read flat on the profile grid and repeat when the #1 holds; Thursday was an empty publication day; the biggest mover rarely coincides with the #1.
- **Status/date:** Accepted 2026-07-15, shipped inert.
- **Guarded by:** `social/tests/test_feed_artwork_moviment.py` (flags off → covers byte-identical, Thursday slot creates no row).
- **Live caveat:** Both flags default `False` in `ranking/models.py::ConfiguracioGlobal` and nothing in the repo records them being flipped since July; the archived `social*.md` docs still describe both as INERT. Whether staff switched them on in prod is a DB question this digest cannot settle.
- Full text: docs/archive/decisions/0016-feed-artwork-i-moviment.md

## ADR-0017 — Pytest runs with `-n 4` fixed, not `-n auto`
- **Decision:** `pytest-xdist==3.8.0` in `requirements-dev.txt`; `-n 4` appended to `addopts` in `pytest.ini` next to the ADR-0003 `--ds=` pin.
- **Why:** Measured 2026-08-18 on a 4P+4E Mac: series 163 s, `-n 4` 78 s, `-n 8` (what `auto` picks) 119 s — efficiency-core workers drag the run; GitHub runners have 4 real cores.
- **Status/date:** Accepted 2026-08-18.
- **Guarded by:** `pytest.ini` inline comment; `-n 0` documented as the single-test opt-out.
- **Live caveat:** Cross-module state leaks now fail nondeterministically under xdist — by design.
- Full text: docs/archive/decisions/0017-pytest-xdist-n4.md
