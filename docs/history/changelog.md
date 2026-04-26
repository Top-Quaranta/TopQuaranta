# Changelog

> **Sprint-by-sprint history lives in [`roadmap.md`](./roadmap.md)**
> ("Sprints — completats"). This file keeps just the formal release
> tags. Detailed daily activity is in `git log`.
>
> Until the next release tag (`0.9.0` → `1.0.0`) this file is mostly
> dormant. Tag releases will repopulate it on a Keep-a-Changelog
> rhythm; meanwhile the source of truth for "what changed" is the
> roadmap + commit history.

Based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Dates UTC.

---

## [Unreleased]

Active development since `0.8.0`. See `roadmap.md` for the
sprint-level breakdown (Sprints A–J ter, April 2026).

Major lines: ranking algorithm v2.0; React SPA migration; community
platform (Grup C); MusicBrainz oracle; staff panel split + tests +
cache + ETag; editorial redesign of every public page with WCAG AA
baseline; gestor self-service edits; comprehensive a11y audit.

---

## [0.8.0] — 2026-04-16

Phase 8 legacy cleanup:

- Dropped pre-2026 legacy DB tables (Wagtail CMS, old image
  generation, legacy Telegram distribution).
- Removed legacy Wagtail admin service.
- Caddy config simplified.
- Ops monitoring (`tq-health`) + daily backups (`tq-backup`) +
  settings split completed.

---

## Earlier phases

See `roadmap.md` ("Phase status" table) for a summary of Phases 0–7
(scaffold, Last.fm ingestion, ranking algorithm port, metadata
pipeline, staff panel, legacy cleanup). No formal release tags for
those phases — the codebase lived as a rolling main branch until
0.8.0.
