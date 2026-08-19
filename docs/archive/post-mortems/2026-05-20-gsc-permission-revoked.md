# GSC daily cron 403 — identity drift — 2026-05-20

- **Date of incident:** 2026-05-20 21:00 / 21:01 / 21:06 UTC (3
  retries, all failed)
- **Severity:** medium
- **Author:** Miquel

## Impact

`recollir_metrics_gsc` daily cron failed three times in a row with
HTTP 403 "User does not have sufficient permission for site
'sc-domain:topquaranta.cat'". One day of GSC search-analytics data
not ingested (183 rows for 2026-05-19 + the 2026-05-20 + partial
2026-05-21 slots that depend on the delayed GSC pipeline).

No user-visible impact: GSC metrics feed the staff analytics
dashboard only, not public surfaces. The gap was backfilled
2026-05-21 18:08 UTC after the fix.

## Timeline

- 2026-05-20 21:00 UTC — first daily run; HTTP 403 returned by
  `searchanalytics.query`. Retry 1 same minute.
- 2026-05-20 21:01 UTC — retry 2; same 403.
- 2026-05-20 21:06 UTC — retry 3; same 403. `tq-run` writes
  `status=FAIL, attempts=3/3`. `tq-health` email to `admin@`.
- 2026-05-21 morning — investigation begins.
- 2026-05-21 18:07 UTC — root cause confirmed: refresh token was
  bound to `miquelmatoses@gmail.com`, which had been removed from
  the GSC property's user list when ownership was moved to
  `admin@topquaranta.cat`.
- 2026-05-21 18:08 UTC — new refresh token minted via OAuth
  Playground using `admin@topquaranta.cat`, dropped into
  `.env::GSC_OAUTH_REFRESH_TOKEN`, gunicorn restarted.
- 2026-05-21 18:09 UTC — manual `manage.py recollir_metrics_gsc
  --date 2026-05-19/20/21` backfilled the gap (183 + 173 + 26
  rows).

## Root cause

Two layers:

1. **Direct cause:** the refresh token in `.env` was minted
   months earlier against the operator's personal Google account
   (`miquelmatoses@gmail.com`). When the GSC property's user list
   was tidied up (removing personal accounts in favour of
   `admin@topquaranta.cat`), the cron lost its permission silently.
   The token continued to refresh fine — only the downstream
   property check failed.
2. **Underlying cause:** Google has a confirmed bug
   ([support article](https://support.google.com/webmasters/community-guide/429538961))
   that prevents adding a Service Account email as a user on a
   `sc-domain:` DNS-verified property. That's why the cron was
   using OAuth user creds in the first place (workaround
   documented at commit `9391e3f`, 2026-05-06). OAuth user creds
   are inherently tied to a human identity — when the human
   loses access, the cron breaks.

## Fix applied

- **Immediate:** re-mint refresh token under
  `admin@topquaranta.cat`, replace value in `.env`, restart
  `topquaranta-web`, backfill the gap via per-day `--date`
  invocations.
- **Procedural:** added detailed re-mint procedure to
  `docs/ops/runbook.md` § "GSC — auth path" so the next operator
  (or the next session) doesn't have to reverse-engineer the OAuth
  Playground flow.
- **Decision:** `docs/decisions/0002-gsc-oauth-user-creds.md`
  records why OAuth user creds remain the right choice despite
  the identity coupling.

## Prevention

- `docs/policies/identities.md` § "Rule 1 — Service auth always
  belongs to `admin@topquaranta.cat`".
- `docs/policies/identities.md` § "Rule 3 — Tokens documented in
  the runbook" (the GSC row in the inventory).

## Lessons learned

- A refresh token that keeps minting tokens isn't the same as a
  working integration. The "HTTP 200 from `/token`" success
  isn't downstream of GSC permission; we only learn about the
  permission gap when we use the token. Monitoring at the
  permission level (a periodic synthetic `searchanalytics.query`
  for one row) would have caught this earlier.
- Cleaning up a service's user list is a deploy-shaped action even
  if it happens entirely in a web console. Future cleanups go
  through a checklist: remove → wait 24h → check every cron that
  used the removed identity.
