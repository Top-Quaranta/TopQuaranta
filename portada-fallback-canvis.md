# Portada fallback — change note (2026-06-22)

**PR:** https://github.com/Top-Quaranta/TopQuaranta/pull/287
**Branch:** `feat/portada-fallback` (base `main`) — NOT merged.

## Goal

Additive, non-regressive fallback chain for cover images so a cover
never renders broken when the self-hosted `-500` variant is missing on
disk. Desired chain, triggered only on load error:
`-500 → -250 → original Deezer URL → stop`.

## Files changed

- `web-react/src/components/Cover.jsx` — the one centralized cover
  component (used by canço + album hero covers). `onError` now walks an
  ordered chain held in a `step` state index instead of a single
  `localFailed` boolean. Idempotent + loop-guarded: `onError` advances
  once per failure and is a no-op past the end. `<picture>` avif/webp
  `<source>`s are dropped after the first fallback step so the browser
  can't keep preferring a 404'ing variant over the chosen `<img>` src.
  Happy path (the `-500` loads first try) is byte-for-byte unchanged.
- `web-react/src/lib/img.js` — new pure helper `portadaFallbackChain`
  building the ordered `[-500, -250, deezer]` src list (drops the Deezer
  step when there's no usable image URL). Unit-tested.
- `web-react/src/components/Cover.test.jsx` — NEW. jsdom test (per-file
  `// @vitest-environment jsdom`) firing real `error` events on the
  `<img>` to assert the `-500 → -250 → Deezer` advance, the no-loop
  terminal step, the `<source>` drop, and the no-`deezerId` plain-Deezer
  path. Plus `portadaFallbackChain` ordering tests.
- `web-react/package.json` / `package-lock.json` — added devDeps
  `jsdom`, `@testing-library/react`, `@testing-library/dom`.
- `docs/architecture/portades.md` — new "Stepped fallback chain"
  section documenting the contract.
- `docs/architecture/frontend.md` — cross-reference to it (satisfies the
  `web-react/` docs-coherence gate, which resolves to `frontend.md`).

## Handler design

`step` is an index into a per-render `chain` array
(`portadaFallbackChain`). `onError` does `if (canAdvance) setStep(s => s+1)`
where `canAdvance = step < chain.length - 1`. Once the chain is
exhausted the handler short-circuits → no setState → no render loop. The
`<img>` keeps its last src and the browser shows its native broken-image
affordance only if even Deezer fails.

## Test added + output

`Cover.test.jsx` — 7 assertions. Full SPA suite (what CI runs via
`npm test`):

```
Test Files  8 passed (8)
     Tests  60 passed (60)
```

(53 pre-existing + 7 new.)

## How CI was kept green

- CI `frontend-tests` job runs `npm test` (vitest) only — NOT
  `npm run lint`. The 3 changed files are still eslint-clean; the
  pre-existing repo-wide lint errors in other files are unaffected.
- jsdom is scoped per-file, so the other node-env tests don't change
  environment.
- Docs-coherence gate satisfied by touching `frontend.md` (the doc the
  `web-react/` prefix resolves to). Verified locally by running
  `scripts/check_docs_coherence.py`'s resolver over the diff → 0 misses.
- `npm run build` succeeds.
- All PR checks green: tests, migrations, lint, caddyfile,
  frontend-tests, docs-coherence, docs-novelty, docs-size, spec-path,
  markdownlint, link-checker, destructive-migrations.

## Preview artifacts

- `/tmp/portada-fix-demo.png` — **LOCAL FIX DEMO** (real render, not
  prod). The real `<Cover>` mounted in a throwaway harness served by
  `vite dev`, screenshotted with headless Chrome. The self-hosted
  `/portades/*` paths 404 under the dev server, so the browser fires
  real `onError`s and the chain recovers — the rendered cover (Joan
  Colomo "Ets un colom") shows `current <img> src` = the Deezer 500x500
  URL.
- `/tmp/prod-album-ets-un-colom.png` — **REAL PROD**
  (`https://www.topquaranta.cat/album/ets-un-colom`). Cover renders fine.
- `/tmp/prod-canco-anna.png` — **REAL PROD** — "Cançó no trobada"
  (the audit slug no longer exists).

## Honest caveat

The two audit URLs do NOT currently show a visibly broken cover: the
pre-existing single-step `-500 → Deezer` fallback in `Cover.jsx` already
recovers the album cover, and the canço slug is gone. Verified
empirically that for `/album/ets-un-colom` (deezer_id 985723691) every
self-hosted variant 404s while the Deezer original is 200. This change
is therefore the requested **hardening**: it inserts the missing
intermediate `-250` step (cheaper, same-origin, cached) and turns an
untested boolean into an explicit, unit-tested, loop-guarded chain — the
behavior the audit asked for, applied to all `Cover` slots.
