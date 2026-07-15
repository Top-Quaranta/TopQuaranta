# ADR-0016 — Feed artwork covers + `moviment` tipus

- **Status:** Accepted (2026-07-15), shipped INERT (gated OFF).
- **Context date:** 2026-07-15.
- Related: ADR-0015 (collaborator invitations), `docs/architecture/social.md`.

## Context

The feed covers are fully typographic. From the profile grid they read
flat, and when the #1 repeats for weeks the grid barely changes. We also
have an empty publication day (Thursday; Sunday is the newsletter) and a
recurring bit of untold story: the week's biggest mover almost never
coincides with the #1. Two approved mocks (`preview-portades-ig.html`,
`preview-dijous-i-fites.html`) validated a fix visually.

The hard constraint: the change must be **mergeable without altering a
single thing that currently goes out**.

## Decision

1. **Artwork covers**, gated by `feed_artwork_actiu` (default False). The
   cover slide (only the cover) gets a duotone artwork background: the
   #1's cover for tops, a 2×2/2×3 mosaic of the week's novetats. The
   treatment (`social/duotone.py`) is the mock's normative layer stack
   (greyscale + contrast 1.06 + brightness 1.02 → accent multiply → hue
   0.30 → readability veil). Colours come from the existing edition
   palette, never hardcoded. Cover source reuses the pipeline chain
   (local `/portades` jpg → Deezer → typographic fallback). Tops add a
   `Nº1 · artist · title` credit; the megacollab case degrades to the
   title. `feed_artwork_mosaic_max` caps the mosaic.

2. **`moviment` tipus**, gated by `moviment_actiu` (default False). A
   Thursday feed post over the Global top. Selection
   (`payload.build_moviment`) reuses `build_top`'s movement data: a
   direct top-10 entry wins, else the strongest rise, else — if below
   `moviment_pujada_minima` — omitted like an empty novetats window. New
   `SocialPost.TIPUS_MOVIMENT`, a Thursday `CALENDARI` slot, a renderer
   builder, and a caption. With the flag off the slot creates **no row**.

Both flags + the two params (`feed_artwork_mosaic_max`,
`moviment_pujada_minima`) are staff-editable from Configuració.

## Consequences

- **Inert merge.** Both defaults False; the covers never call `duotone`
  and are byte-identical (pinned by a no-regression test); the Thursday
  slot is a full no-op. No data/scoring change; the only migration adds
  config fields (inert defaults) + the choices enum.
- **Stories untouched** this cycle.
- **Repetition risk** (completely surfaced in the mock): when the #1
  doesn't change, the artwork grid repeats as much as the typographic
  one did. The Thursday moviment (a different protagonist most weeks)
  and the novetats mosaics mitigate it; a top-6 mosaic for the tops is a
  possible follow-up, not in this slice.
- **Fonts.** The mock used Google Fonts (Anton, Playfair) that happen to
  match the real brand fonts; sizes were tuned against the real Pillow
  render (see the PR's preview PNGs).
