# ADR-0005 — Bluesky `upload_blob` timeout 180 s + retry 3×

- **Status:** Accepted
- **Date:** 2026-05-21
- **Authors:** Miquel

## Context

`social/bluesky_client.py::upload_blob` issued a single
`requests.post(timeout=60)` against `bsky.social`'s PDS for 4-PNG
carousels (~1 MB each). With variance on the connection, ~2/3 of
the weekly Bluesky publications dropped silently — five
publications missed in one week (16–20 May 2026). Full incident at
`docs/post-mortems/2026-05-21-bluesky-silent-failures.md`.

`SocialPost.status` flipped to `error` per failure and `tq-health`
recorded a `consecutive_skips=0` (because `status=error` resets the
counter), so the watchdog never fanned out an alert.

## Decision

Two changes inside `upload_blob`:

1. **Bump timeout from 60 s to 180 s** for the blob upload only
   (`BLUESKY_UPLOAD_TIMEOUT_S` constant). Other Bluesky calls
   (session, create-record) keep the 60 s default.
2. **Retry up to 3 times** with back-off (5 s, 15 s) between
   attempts. Retries trigger only for `requests.ReadTimeout` and
   `requests.ConnectionError`. HTTP 4xx and 5xx propagate
   immediately (those errors don't fix themselves).

Implementation: manual loop in the function body. No
`urllib3.util.retry.Retry` because the standard retry adapter
doesn't differentiate exception types cleanly and is harder to
reason about in tests.

## Alternatives considered

- **Bump timeout only (no retry).** Rejected: improves the
  per-attempt budget but doesn't handle transient PDS hiccups that
  resolve on the next try.
- **Retry only (keep 60 s).** Rejected: 60 s is marginal on its
  own for the 1 MB × 4 carousel; doubling cost via retries
  doesn't fix the underlying budget.
- **Use the official `atproto` SDK with its built-in retry.**
  Rejected: the SDK pulls in a heavy protobuf stack we don't
  otherwise need; the surface here is small.

## Consequences

- Positive: a single PDS hiccup no longer drops the publication.
  Three back-to-back hiccups during a single cron tick are
  vanishingly unlikely.
- Negative: a fully-failing day can spend up to ~3 minutes per
  upload (3 × 180 s + back-off) before propagating. With 4
  carousel images, worst case is ~12 min per publication. Doesn't
  hit any user-facing surface but lengthens the cron run.
- Sharp-edged: if `bsky.social`'s PDS is completely down, the
  cron run will be visibly slower (one carousel × ~12 min ×
  multiple territories). Acceptable; we'd rather wait than drop.

Follow-up backlog: aggregate "N consecutive errors per channel" in
`tq-health` (was not in scope for this fix). Vegeu el backlog del
post-mortem.

## Related

- Post-mortem: `docs/post-mortems/2026-05-21-bluesky-silent-failures.md`
- Files: `social/bluesky_client.py`, `social/constants.py`
- Tests: `social/tests/test_bluesky_upload_retry.py`
