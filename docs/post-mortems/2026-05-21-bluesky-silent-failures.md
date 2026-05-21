# Bluesky publication channel silent for 5 days — 2026-05-21

- **Date of incident:** 2026-05-16 (last OK) to 2026-05-21
  (detected)
- **Severity:** high (silent degradation, not visible without
  cross-channel comparison)
- **Author:** Miquel

## Impact

Five days with no Bluesky publication where the calendar said
there should have been:

| Slot | Result |
|---|---|
| 2026-05-16 09:50 UTC — `top_ppcc` PPCC | publicat (last OK) |
| 2026-05-18 09:50 UTC — `top_territorial` VAL | error |
| 2026-05-19 10:20 UTC — `nous_albums` | omes (skipped by content gate) |
| 2026-05-20 09:50 UTC — `top_territorial` CAT | error |
| 2026-05-15 10:20 UTC — `nous_singles` | omes |

The `top_territorial` slots are what should have published. Two
slots (`VAL` and `CAT`) dropped into `status=error` and the cron
moved on — no retry, no human alert.

## Timeline

- 2026-05-18 11:51 UTC — first failure logged in
  `/var/log/topquaranta/errors.log` with
  `ReadTimeoutError: read timeout=60`.
- 2026-05-20 11:51 UTC — second failure, identical shape.
- 2026-05-21 — detected during the broader social investigation
  (`PUNT 4` of the read-only sweep).

`tq-health` did not fan out an alert because each failure was a
single-shot per slot; the watchdog flags `consecutive_skips` but
`status=error` resets that counter.

## Root cause

`social/bluesky_client.py::upload_blob` issues
`requests.post(timeout=TIMEOUT_S)` with `TIMEOUT_S = 60` (from
`social/constants.py:15`). For a carousel of 4 PNGs ~1 MB each
against `bsky.social`'s PDS, 60 s is marginal — enough variance in
the network to trip occasional reads.

No retry, no exponential back-off. The exception propagates to
`publicar_canal._publish_bluesky`, the outer `try/except` marks
the `SocialPost` row as `error`, and the cron exits 0 (because
"one channel failed" isn't a cron failure).

## Fix applied

Not yet applied at the time of this post-mortem — captured here
because the broader social refactor (mentioned in
`docs/post-mortems/2026-05-20-narrative-engine-collapsed.md`) is
the natural place to add:

- `TIMEOUT_S` bumped to 120-180 s for `upload_blob` (heavy
  payload); keep 60 s for the auth + create-record calls.
- Retry with exponential back-off (1s, 4s, 16s) on `ReadTimeout`
  and `ConnectionError` only — not on HTTP 4xx.
- Aggregate "N consecutive failures on channel X" alert in
  `tq-health` (open backlog item).

## Prevention

- Backlog item (high): add a `consecutive_failures` counter per
  channel in `tq-health`, separate from `consecutive_skips`. The
  rule "alert when consecutive_failures ≥ 3" catches this shape
  in 2-3 days instead of 5.
- Backlog item (medium): retry policy in `bluesky_client` and
  the other publishers.

## Lessons learned

- Single-shot failures hide silent degradation. The
  `tq-health` watchdog was designed around "is the cron stuck?",
  not "is the cron silently dropping output?". A real downstream
  check (compare expected vs actual `SocialPost.status=publicat`
  per day) would have caught this in one cycle.
- The renderer + payload pipeline runs fine; the failure is
  entirely in the publisher network call. Splitting renderer
  errors from publisher errors in the status taxonomy would help
  routing.
