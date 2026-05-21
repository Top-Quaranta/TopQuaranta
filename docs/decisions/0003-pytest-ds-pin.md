# ADR-0003 — Pytest pins settings via `--ds=` to block env override

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** Miquel

## Context

`pytest.ini` already declared
`DJANGO_SETTINGS_MODULE = topquaranta.settings.test`. But
pytest-django gives env vars precedence over the ini key:
`--ds=` > `DJANGO_SETTINGS_MODULE` env var > `DJANGO_SETTINGS_MODULE`
in ini.

On the Hetzner server, management commands are commonly invoked
with `DJANGO_SETTINGS_MODULE=topquaranta.settings.web_server`
exported in the shell. When `pytest` happened to inherit that
env var, it silently used production settings — every `APIClient`
call inside the suite defaulted to `HTTP_HOST=testserver`, which
tripped `DisallowedHost` against the prod `ALLOWED_HOSTS` and
mailed `admin@`. Noise without value.

## Decision

Switch the `pytest.ini` setting to:

```ini
[pytest]
addopts = --ds=topquaranta.settings.test
```

`--ds=` is the highest-precedence channel in pytest-django; env
vars can no longer override it. The ini stays the source of truth.

## Alternatives considered

- **Assume shell discipline.** Rejected: silent env var
  inheritance is exactly the kind of trap that operator
  discipline doesn't catch.
- **Unset `DJANGO_SETTINGS_MODULE` in the pytest entry script.**
  Rejected: requires every invocation path to remember the
  unset; addopts is one place, applies universally.

## Consequences

- Positive: pytest always uses `settings.test` regardless of
  shell state. Tests run identically on the Mac and the server.
- Negative: a contributor who genuinely wants to run pytest
  against `settings.local` (rare) must pass `--ds=...` to
  override. Documented inline in `pytest.ini`.

## Related

- PR: #56
- Affected file: `pytest.ini` only.
