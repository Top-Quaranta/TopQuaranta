# ADR-0011 — Spotify sync cron schedule (daily every 6h + weekly Saturday)

- **Status:** Proposed
- **Date:** 2026-05-22
- **Authors:** Miquel

## Context

The legacy `actualitzar_playlists_spotify` cron line in
`deploy/cron.topquaranta` was a single daily entry at 07:15 UTC:

```cron
15 7 * * *  topquaranta  /home/topquaranta/bin/tq-run actualitzar_playlists_spotify >> /var/log/topquaranta/playlists.log 2>&1
```

That schedule mixed two refresh cadences that the FASE D model
separates:

- **`freq=daily` playlists** (5 rows: top-{cat,val,bal,alt}-daily +
  novetats-daily) source from `TopProvisional`, which itself
  rebuilds every day at 07:00 UTC. The 07:15 window catches the
  freshly recalculated provisional ranking but only updates once
  per day; an artist who climbs at lunchtime won't show on Spotify
  until tomorrow morning.

- **`freq=weekly` playlists** (5 rows: top-{ppcc,cat,val,bal,alt}-weekly)
  source from `TopSetmanal`, which is computed every Saturday at
  08:00 UTC alongside the social distribution cycle (09:30 UTC).
  Updating weekly playlists every day is pure waste: the underlying
  rows don't change between Saturdays.

This ADR proposes the FASE D schedule split.

## Decision

Two separate cron lines, both pointing at the same management
command via the `--freq` flag (FASE D adds the flag):

```cron
# Daily playlists every 6h. Spotify Web API quotas are generous
# (180k requests/day per app), and the cost is dominated by the
# initial ISRC search per Cançó — that result is cached on
# Canco.spotify_id, so steady-state cost is one PUT/POST per
# playlist per tick.
0 */6 * * *  topquaranta  /home/topquaranta/bin/tq-run \
    actualitzar_playlists_spotify --freq daily \
    >> /var/log/topquaranta/playlists.log 2>&1

# Weekly playlists once a week, Saturday 10:00 UTC. That's
# 30 min after the publicar_social cron (09:30 UTC) which gives
# us a margin for any TopSetmanal recomputation that might still
# be in flight.
0 10 * * 6  topquaranta  /home/topquaranta/bin/tq-run \
    actualitzar_playlists_spotify --freq weekly \
    >> /var/log/topquaranta/playlists.log 2>&1
```

Rationale for each parameter:

- **Daily every 6h** (00:00, 06:00, 12:00, 18:00 UTC). Empirical:
  the most recent ranking change a user might notice is a song
  climbing into the top 10 after a streaming spike. With 6h
  granularity, the worst-case delay between TopProvisional update
  and Spotify playlist update is ~6h. Could be every 3h, but the
  marginal user value drops sharply (most listeners check daily,
  not hourly) and the operational cost (more log volume, more
  chances to catch a transient 5xx) grows linearly.

- **Weekly Saturday 10:00 UTC**. Aligned with the social cycle
  (`publicar_social` at 09:30 UTC). The 30-min offset is the same
  pattern we use for `actualitzar_playlists_spotify` running 15 min
  after `calcular_top_provisional` (legacy). It guards against the
  Saturday Top being still being recomputed when the playlist sync
  fires.

- **Same command for both**. The `--freq` flag filters at SELECT
  time in `_select_cancons`; the rest of the command (matching,
  PUT/POST) is identical. Two cron lines, one code path. Less
  surface to maintain than two separate commands.

## Alternatives considered

- **Hourly daily refresh.** Rejected: TopProvisional only changes
  once a day (07:00 UTC); refreshing 24 times overwrites the same
  data 23 times. Quota waste with no user-visible benefit.
- **Daily refresh once at 07:15 (status quo)**. Rejected for the
  daily playlists: a user who hits Spotify at 18:00 UTC sees an
  11-hour-old version of "top diari". For a weekly playlist it'd
  be acceptable but we still want the safety margin after
  TopSetmanal.
- **Trigger from the application** (call the command after
  `calcular_top_provisional` finishes). Cleaner coupling but
  fragile to the post-deploy environment (the management command
  is run from cron context, not Django request context, and the
  triggering would have to live inside `calcular_top` which is
  not its concern). Cron is the simplest source of truth.
- **Tie weekly to dissabte 10:00 UTC vs dissabte 11:00 UTC**.
  10:00 is safer: it's 30 min after social. 11:00 would be safer
  still but the playlist visibility on Spotify weekend matters,
  and pushing it later cuts into Saturday afternoon listening.

## Consequences

- ✅ Daily playlists stay fresh within a 6h window.
- ✅ Weekly playlists refresh once per cycle, no waste.
- ✅ Cron lines are explicit about the frequency in their args, so
  log lines and `tq-health` rows are easy to disambiguate (the
  status file paths split on the command + args hash).
- ⚠️ **Two status files** instead of one. `tq-health` reads each
  command's status file separately; the FASE F monitoring will
  need to know about both. Updating
  `/var/log/topquaranta/status/actualitzar_playlists_spotify*.status`
  glob to capture both is straightforward.
- ⚠️ **Pre-FASE-D**, the `--freq` flag does not exist on the
  command. The new cron lines need to land in the same deploy as
  the FASE D commit, otherwise the cron silently fails with
  `unrecognized arguments: --freq`. The FASE D PR includes both.

## Related

- ADR-0009 — Identity migration (the reason this cron is
  resurrected at all).
- FASE D of the revival sprint plan — model + command change that
  introduces `--freq`.
- `deploy/cron.topquaranta` — file that will gain these two lines
  (replacing the single legacy 07:15 line).
- `deploy/cron-meta.json` — the `actualitzar_playlists_spotify`
  entry that goes from `silenced=true` to `silenced=false`, with
  `max_age_hours` tuned per the new cadence (≤7h for daily,
  ≤170h for weekly).
