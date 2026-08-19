# ADR-0009 — Spotify identity migrated to `admin@topquaranta.cat` + Premium

- **Status:** Accepted
- **Date:** 2026-05-22
- **Authors:** Miquel

## Context

The `actualitzar_playlists_spotify` cron had been failing every day
since the feature shipped (commit `5adc898`, 2026-04-20). Two
independent root causes had compounded:

1. **No `SpotifyAuth` row in the production DB.** The one-time OAuth
   dance via `manage.py autoritzar_spotify` had never been completed
   on production. Every cron tick exited with
   `CommandError: No hi ha autorització Spotify.` and the
   `cron-meta.json::silenced=true` flag prevented `tq-health` from
   escalating the alert. The state file
   `/var/log/topquaranta/status/actualitzar_playlists_spotify.status`
   shows `exit_code=1` continuously since the oldest retained log
   (2026-04-21).

2. **Spotify Web API requires Premium on the app owner.** Spotify
   changed their developer policy in late 2024: any Web API request
   (catalog reads via Client Credentials, search, playlist mutations)
   returns `403 Forbidden` with the body
   `"Active premium subscription required for the owner of the app"`
   when the app's owner account is on a free tier. The previous
   owner of the Spotify Developer app (a personal account) had a
   free Spotify subscription, so even if step 1 had been completed
   the cron would have failed on every `GET /v1/search?q=isrc:...`
   call.

This pattern is the same one `docs/policies/identities.md` was
written to prevent (GSC incident, 2026-05-20). Tying a production
integration to a personal account creates a silent fragility:
permissions, subscriptions, or account states can change without
triggering an alert.

## Decision

Three changes, applied together:

1. **Migrate the Spotify Developer app owner to `admin@topquaranta.cat`.**
   The same Client ID / Client Secret are preserved, only ownership
   transferred. This avoids a destructive re-creation that would
   have orphaned the redirect URI registration history and any
   per-app rate-limit reputation.

2. **Subscribe `admin@topquaranta.cat` to Spotify Premium Individual.**
   Cost: 11.99 EUR/month recurring. This unlocks the Web API for the
   app owner; the playlist subscribers themselves are unaffected (they
   can listen on free accounts as before).

3. **Update the redirect URI from `/spotify/callback` to
   `/staff/social/spotify/callback`** at the Spotify Developer
   Dashboard, anticipating the FASE B refactor where the OAuth
   exchange becomes an HTTP endpoint backed by the staff SPA instead
   of the current paste-back-into-terminal flow.

The redirect URI change is registered at the Spotify Dashboard and
mirrored in `/home/topquaranta/app/.env` via a new
`SPOTIFY_REDIRECT_URI` line. The Django settings already read this
variable (with a default to the old URL) so production runs the
new path while local development still works.

## Alternatives considered

- **Keep the personal account as owner.** Rejected: this is exactly
  the anti-pattern that `identities.md::Rule 1` codifies. The GSC
  incident shows the cost when the human in the loop eventually
  cleans up permissions or rotates accounts.
- **Re-create the Spotify Developer app from scratch under `admin@`.**
  Rejected: would have required updating Client ID / Client Secret
  everywhere (env, .env.example, docs) and would have invalidated
  any in-flight rate-limit reputation. Owner transfer was simpler.
- **Drop Spotify entirely and pivot to Deezer for playlist output.**
  Rejected for this sprint: Deezer has a public API but its
  playlist-modify endpoints require user OAuth too, and the social
  proof of Spotify (followers on the existing 10 playlists) is not
  trivial to recreate. Deezer is on the backlog as a parallel
  output, not a replacement (ADR-XXXX TBD).
- **Skip Premium and use the playlist embeds only as static URLs.**
  Rejected: a stale playlist hurts both the user-facing product and
  the data quality of the analytics we get from Spotify itself.
  Premium is a small recurring cost vs. the value of a live sync.

## Consequences

- ✅ The cron will work once a refresh token is minted under the
  new owner. FASE C of the revival sprint does that via the new UI.
- ✅ The 10 existing playlists (5 daily territorials + 5 weekly
  territorials + novetats) keep their URLs, follower counts, and
  follower notification settings. Owner transfer is non-destructive.
- ⚠️ **Recurring cost** of 11.99 EUR/month. Needs explicit budget
  tracking and an automated check (FASE F) that fires if Premium
  ever lapses. A free-tier accidental downgrade would silently break
  the cron in the same way it did before.
- ⚠️ **Propagation delay** of "a few hours" between Premium
  activation and Spotify Web API recognising it. Observed empirically
  on 2026-05-22 — the cron's playlist accessibility check returns
  403 with the explicit body
  `"When the subscription status changes, it can take a few hours
  before requests are allowed again"` immediately after Premium
  activation. Plan for a same-day window between activation and
  first successful sync, not minutes.
- ⚠️ **Free trial accepted on activation.** If the admin account is
  using a Spotify Premium trial, the trial expiry date becomes a
  silent failure point. The FASE F monitoring check explicitly tests
  `me().product == "premium"` rather than just refresh-token
  validity for this reason.
- ⚠️ The redirect URI change means the legacy `autoritzar_spotify`
  management command (which used the old `/spotify/callback`) will
  not work as-is until the user updates the URI at the Spotify
  Dashboard or we expose both URIs as registered redirects. The
  legacy command is retained as a fallback but the primary OAuth
  path moves to the staff UI in FASE B.

## Related

- Post-mortem `docs/post-mortems/2026-05-20-gsc-permission-revoked.md`
  motivated the `identities.md` policy this ADR enforces for Spotify.
- ADR-0002 (GSC OAuth via admin@) is the equivalent decision for
  Search Console.
- Token inventory row added to `docs/policies/identities.md`.
- Revival sprint plan (multi-phase, A through G) covers the
  application of this decision end-to-end.
