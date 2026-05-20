# Shared infra — multi-tenant Caddy

The Hetzner CX22 (`188.245.60.20`) hosts more than just TopQuaranta. As
of May 2026 the server also serves `cercol-api` (and any other future
project we co-locate). A single Caddy instance fronts all of them.

## Layout

```
/etc/caddy/
├── Caddyfile               ← owned by TopQuaranta (this repo)
└── conf.d/
    ├── cercol-api.caddy    ← owned by the cercol-api repo
    └── <future>.caddy      ← one snippet per additional project
```

- The main `Caddyfile` ends with `import /etc/caddy/conf.d/*.caddy`,
  which loads every `.caddy` snippet from that directory at config
  parse time. An empty `conf.d/` is valid: the glob expands to zero
  matches and Caddy carries on.
- Each project's snippet contains only its own site blocks (e.g.
  `api.cercol.team { ... }`). It does not redeclare the global
  options block — that lives in the main Caddyfile.

## Ownership

| Path | Owner | Synced by |
|---|---|---|
| `/etc/caddy/Caddyfile` | TopQuaranta | `bin/tq-sync-infra` (this repo) |
| `/etc/caddy/conf.d/*.caddy` | the corresponding project | that project's deploy script |

The rules are mutual and hard:

1. **TopQuaranta never touches `/etc/caddy/conf.d/`.** Not for read,
   not for write, not for delete. `bin/tq-sync-infra` is the sole
   author of `/etc/caddy/Caddyfile`; the conf.d directory is invisible
   to it. The test
   `topquaranta/tests/test_deploy_safety.py::test_sync_infra_does_not_touch_confd`
   keeps that contract honest.
2. **Other projects never touch `/etc/caddy/Caddyfile`.** They install
   only their own snippet under `conf.d/` and reload Caddy. If a
   project ever needs to change the global options block (auto-TLS
   email, on-demand TLS, etc.), that change goes through the
   TopQuaranta repo via a PR to `deploy/Caddyfile`.

## Deploy contract for project snippets

Each project's deploy script must:

1. Write `<project>.caddy` to a working location in its own tree.
2. `sudo caddy validate --config /etc/caddy/Caddyfile` first (Caddy
   resolves the import, so a syntax error in any project's snippet
   surfaces here).
3. `sudo install -o root -g root -m 644 <project>.caddy
   /etc/caddy/conf.d/<project>.caddy` only after validation passes.
4. `sudo systemctl reload caddy` to pick up the change.

If validation fails the deploy aborts and Caddy keeps running with
the previous config. No partial application.

## Why this design

For four months the server ran with `deploy/Caddyfile` containing
every site for every project. Each TopQuaranta deploy ran
`tq-sync-infra`, which diffs `deploy/Caddyfile` against
`/etc/caddy/Caddyfile` and replaces the live file wholesale on
drift. Any block added manually to the live file (because it
belonged to a different repo) was silently deleted at the next TQ
deploy.

The `import /etc/caddy/conf.d/*.caddy` directive gives every
project its own write surface. TopQuaranta keeps the global block
and its own sites; other projects ship snippets that survive any
TQ deploy because TQ never reads or writes the conf.d directory.

## Quick checklist when onboarding a new project

- Add an A record at the DNS provider pointing the new hostname at
  `188.245.60.20`.
- In the new project's repo: create a `deploy/<project>.caddy`
  file with the site block. Validate it locally with the
  `caddy:2` Docker image before pushing.
- Add a deploy step that installs the snippet to
  `/etc/caddy/conf.d/<project>.caddy`, validates the merged config,
  and reloads Caddy.
- Do not touch `/etc/caddy/Caddyfile`. Do not touch any other
  project's snippet.
