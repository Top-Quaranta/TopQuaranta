# Estat — retrofit staff cap a rd light (2026-06-23) — MERGEJAT

- **PR #300 MERGEJAT** (squash) a `main` → HEAD `64f0059`. Branca i worktree netejats.
- 36 pàgines staff consumeixen ara `components/rd/surface.jsx` (kit light del canon rd).
  `components/staff/StaffTable.jsx` és un shim de compatibilitat.
- **Pixel-idèntic per construcció** (import-swap per pàgina). Cap canvi visual intencional.
- Verificació post-merge (origin/main): 0 pàgines staff amb el path vell; shim només
  el consumeixen ArtistesPage (públic, Field/Select) + FilterPanel/LastfmPanel/MusicBrainzPanel
  (via ./StaffTable). Fluxos públic→staff (Field/Select, FilterPanel, LocationCascade) intactes.
- Guards post-merge: build ✓ · vitest ✓.
- Docs en sincronia a main: CLAUDE.md §5, frontend.md, recon (2026-06-23-recon-disseny-unificacio.md).
