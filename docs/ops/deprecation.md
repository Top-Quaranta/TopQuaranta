# Deprecation policy

How TopQuaranta retires model fields, management commands, API endpoints,
and staff-panel features without ambushing consumers.

## Why we need this

R10 (Phase 9, Session 8) dropped `Artista.deezer_id`. Three ingest
management commands silently kept writing to it (`obtenir_novetats`,
`obtenir_metadata`, `fix_artista_principal`). The next hourly cron
failed with `TypeError: Artista() got unexpected keyword arguments:
'deezer_id'` — R10b. The fix took 30 minutes; the surprise took all
day to surface.

A deprecation policy is not about code. It's the written promise to
ourselves that the next breaking change goes through a visible,
dated, reviewable process rather than a single confident commit.

## Scope

This policy applies to anything that has consumers — inside the
codebase or outside it:

- **Model fields**: columns that other code reads / writes / filters on.
- **Management commands**: anything invoked from `manage.py`, cron, or
  scripts under `bin/`.
- **API endpoints** (`/api/v1/*`): external contract, see also
  `docs/architecture/web.md` — the two docs overlap on API changes and
  agree.
- **Staff panel features**: URLs, template blocks, audit-log action
  codes that queries depend on.
- **Ops scripts** (`bin/tq-*`): command-line flags, status-file
  keys consumed by `tq-health`.

It does NOT apply to internal implementation details that no other
module imports — a helper function in `music/ml.py` used only inside
that file is free to disappear in a single commit.

## The process

Before removing any item in scope:

### 1. Announce

Add the item to `docs/history/changelog.md` under `## [Unreleased]` → `### Deprecated`,
naming:
- **What** will be removed.
- **When** it will be removed (a concrete date or version).
- **What to use instead** (the replacement, with a short migration
  example if non-trivial).

Example:

> ### Deprecated
>
> - `Artista.deezer_id` (BigInteger column). Removed in 1.0.0
>   (earliest 2026-07-16). Use `ArtistaDeezer` M2M via
>   `artista.deezer_id_principal` property or
>   `artista.deezer_ids.values_list("deezer_id", flat=True)`.

### 2. Emit a visible warning in code

Pick the right mechanism for the item's surface:

| Surface | Mechanism |
|---|---|
| Python code path | `warnings.warn("X is deprecated, use Y", DeprecationWarning, stacklevel=2)` at the top of the deprecated function. |
| Model field | Add `help_text="DEPRECATED — see docs/DEPRECATION.md. Removed in X.Y.Z."` and keep a `DeprecationWarning` at every Python read/write site. |
| Management command | Log a visible warning in `handle()`: `self.stderr.write(self.style.WARNING("⚠ DEPRECATED: use tq-run <new-cmd> instead. Removed in 1.0.0."))`. |
| API endpoint | Add `X-Deprecated: true` response header + `X-Deprecation-Removal: 2026-07-16` + a warning in the response body for JSON payloads. Document in VERSIONING.md. |
| Staff panel feature | Banner at the top of the template: `⚠ Aquesta funció s'eliminarà el 2026-07-16. Utilitza …`. |

### 3. Wait

Minimum grace windows before removal:

| Scope | Minimum wait |
|---|---|
| Internal (cron, management command, staff feature, model field consumed only by our code) | **90 days** |
| External surface (`/api/v1/*` endpoints, response schema) | **180 days** |
| Data deletion (R14: SenyalDiari rows older than 2 years archived) | **Follow the retention policy** in `docs/ops/retention.md`. |

Windows are minimums, not defaults. If a deprecation lands in December,
you probably want to remove in March (~100 days) rather than exactly
day 91, so the removal doesn't collide with a release cycle.

### 4. Remove

At removal time:

- Move the `docs/history/changelog.md` entry from `### Deprecated` to `### Removed`
  under the actual release.
- For API removal, bump the `/api/v1/` → `/api/v2/` prefix as specified
  in VERSIONING.md; v1 stays live for another 180 days.
- For DB columns, land one migration per removal — never combine the
  drop with an unrelated schema change, so the removal is a clean
  bisect point.

## Exceptions

### Security fixes may skip the wait

A deprecated item that's a security hazard (leak, XSS vector, privilege
escalation path) gets removed immediately. The CHANGELOG entry goes
straight to `### Security` + `### Removed` in the same release. Note
the skipped wait in the entry so an auditor can reconstruct why the
grace window didn't apply.

### Experiments are not deprecations

A feature explicitly flagged as experimental in its first release
(`⚠ Experimental — API may change without notice`) can be changed or
dropped on any schedule. Experimental status must be declared up
front — not retroactively.

### Never-shipped code

A feature merged and then removed before any release tag has no
consumers. No deprecation window needed; a note in CHANGELOG under
`### Unreleased` is enough.

## Template for a deprecation entry

When you're about to deprecate something, open `docs/history/changelog.md` and
paste:

```markdown
### Deprecated

- `<thing>` — removed in <version>, earliest <YYYY-MM-DD>. Use
  `<replacement>` instead. <One-line rationale. Link to issue or PR
  if applicable.>
```

Then add the in-code warning, and move on.

## Historical record

Every deprecation that's been completed is preserved in
`docs/history/changelog.md` under the release where it was Removed. That's the
source of truth for "when did X go away?"
