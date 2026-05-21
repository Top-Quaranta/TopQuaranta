# Identities — humans vs services

How TopQuaranta separates personal Google / Github / instance
identities from the identity used by automated integrations.

## Why this policy exists

On 2026-05-20 the GSC daily cron started failing with HTTP 403.
The refresh token had been minted against a personal Gmail account
months earlier; when ownership of the GSC property was tidied up
to `admin@topquaranta.cat`, the cron stopped working without
warning. See `docs/post-mortems/2026-05-20-gsc-permission-revoked.md`.
The pattern generalises: any automation tied to a person breaks when
that person rotates, leaves, or cleans up permissions.

## Rules

### Rule 1 — Service auth always belongs to `admin@topquaranta.cat`

Every OAuth token, API key, or external service authorisation used
by production runs (cron, web, signals) is held under the
`admin@topquaranta.cat` identity. Personal accounts
(e.g. `miquelmatoses@gmail.com`) are never used for production
integrations.

If a third-party service does not let `admin@` be added as
collaborator (rare), this is the trigger to file the limitation in
an ADR rather than work around it with a personal account.

### Rule 2 — E2E smokes use a dedicated QA account, never real artists

When testing a production-shaped flow end-to-end, use a fixture
account: `qa_smoke` user paired with a fixture artist (slug
`qa-smoke`). Real artists (Rosalía, La Fúmiga, Manel, anyone the
DB has) are off-limits for E2E mutations.

See `docs/post-mortems/2026-05-20-smoke-side-effects.md` for the
incident this rule prevents. Until the `qa_smoke` fixture exists
(open backlog item), the operator manually documents every smoke
mutation and reverts it post-test.

### Rule 3 — Tokens documented in the runbook

Each refresh token / API key has a row in `docs/ops/runbook.md`:
- which integration uses it
- which identity owns it
- last rotation date
- procedure to rotate it

A token without a runbook row is an outage waiting to happen.

## Token inventory (snapshot 2026-05-21)

| Integration | Identity | Storage | Rotation procedure |
|---|---|---|---|
| GSC Search Analytics API | `admin@topquaranta.cat` (OAuth user creds) | `.env::GSC_OAUTH_REFRESH_TOKEN` | `docs/ops/runbook.md` § "GSC — auth path" |
| Instagram Graph API | TopQuaranta IG business account | `.env::INSTAGRAM_ACCESS_TOKEN` | `bin/renovar_token_instagram` (long-lived 60 d cycle) |
| Mastodon API | TopQuaranta instance app | `social.MastodonAuth` row | `social/management/commands/autoritzar_instagram.py` equivalent (TODO: document) |
| Bluesky | `topquaranta.bsky.social` app password | `social.BlueskyAuth` row | App password rotated at bsky.social settings |
| Telegram Bot | `@topquaranta_bot` | `social.TelegramAuth` row | Token regenerated via @BotFather |
| Brevo SMTP | `admin@topquaranta.cat` | `.env::EMAIL_HOST_PASSWORD` | Brevo dashboard |
| Resend (cercol.team) | Resend account | (Stalwart MTA strategy) | Resend dashboard |
| Hetzner Cloud API | `HETZNER_API_TOKEN` | `.env` | Hetzner console |
| CDMON DNS | `CDMON_API_KEY` | `.env` | CDMON web panel |

Items marked TODO are open backlog. Adding a new integration
without filling its row is the kind of skip this policy catches.
