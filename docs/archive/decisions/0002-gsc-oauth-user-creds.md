# ADR-0002 — GSC auth via OAuth user creds (admin@topquaranta.cat)

- **Status:** Accepted
- **Date:** 2026-05-21
- **Authors:** Miquel

## Context

Google Search Console properties of type `sc-domain:` (DNS-TXT
verified) have a confirmed Google bug
([support article](https://support.google.com/webmasters/community-guide/429538961))
that prevents adding a Service Account email as a property user:
the UI returns "Failed to add user: email address not found".
The bug has been open since April 2026 and is not addressed.

The daily `recollir_metrics_gsc` cron needs to call
`searchanalytics.query` against `sc-domain:topquaranta.cat`. With
SA blocked, the alternative is OAuth user credentials. The trap:
OAuth user creds inherit the identity of the user who minted them.
If that user later loses access to the GSC property, the cron
breaks silently — exactly the failure mode of
`docs/post-mortems/2026-05-20-gsc-permission-revoked.md`.

## Decision

The cron uses OAuth user credentials minted under
`admin@topquaranta.cat`. The refresh token lives in
`.env::GSC_OAUTH_REFRESH_TOKEN`. The service account
`seo-ingest@topquaranta-seo.iam.gserviceaccount.com` remains in
`.secrets/` as an inactive fallback — when Google fixes the
`sc-domain:` UI bug, the SA path can be reactivated by deleting
the three `GSC_OAUTH_*` env vars (the existing fallback in
`recollir_metrics_gsc._build_credentials()` then picks up the SA).

## Alternatives considered

- **Service Account via DNS verification on the property.**
  Rejected: the bug specifically affects `sc-domain:` properties
  regardless of how the SA is added; the verification path is the
  same trap.
- **Use a personal account (e.g. `miquelmatoses@gmail.com`).**
  Rejected: ties production auth to a human identity that
  rotates, breaks when ownership is tidied up. Exactly what
  caused the 2026-05-20 incident.
- **Switch to the Search Console URL-prefix property type** (where
  SA works). Rejected: requires re-verifying via `<meta>` tag or
  HTML file upload, loses the domain-level coverage we currently
  have for HTTP+HTTPS+www+apex, and is itself a regression in
  signal quality.

## Consequences

- Positive: the SA bug doesn't block the daily ingestion.
  Operator owns the identity; rotation procedure documented.
- Negative: the refresh token must be regenerated every time the
  GSC property's user list changes (Owner reassignment, account
  cleanup, manual revoke at `account.google.com/permissions`).
- Sharp-edged: OAuth user tokens can be revoked by Google for
  reasons outside our control (suspicious activity, password
  change cascading, etc.). Mitigation: documented re-mint
  procedure at `docs/ops/runbook.md` § "GSC — auth path".
- Follow-up: synthetic monitor that runs a 1-row
  `searchanalytics.query` daily and alerts at the permission
  layer, not just the token-refresh layer (open backlog).

## Related

- Post-mortem: `docs/post-mortems/2026-05-20-gsc-permission-revoked.md`
- Policy: `docs/policies/identities.md` § Rule 1 + token inventory.
- Runbook: `docs/ops/runbook.md` § "GSC — auth path".
- Original SA→OAuth fallback commit: `9391e3f` (2026-05-06).
