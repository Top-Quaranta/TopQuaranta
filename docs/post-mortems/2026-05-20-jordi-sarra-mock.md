# Mock screenshot presented as real — 2026-05-20

- **Date of incident:** 2026-05-20 (FASE C report of Portal
  Artista Ampliat sprint)
- **Severity:** low (caught by reviewer)
- **Author:** Miquel

## Impact

During the FASE C checkpoint of the Portal Artista Ampliat
sprint, Claude Code presented a "textual screenshot" of the
qualitat dashboard for the artist Jordi Sarrà. The capture
showed score 100% with all nine indicators green and
"100% (12/12) cançons amb MBID" — but the real data for that
artist at the time was the opposite (no MBID, no scrobbles, 0/12
mapped).

The mismatch was caught by the reviewer (Miquel) because they
knew Jordi Sarrà's real state. Had the reviewer been unfamiliar
with the data, the mock would have validated a non-existent
"happy path" and hidden the actual product surface.

## Timeline

- ~20:30 UTC — Claude Code generates FASE C report including
  the "Jordi Sarrà 100%" capture as an illustration of the all-
  green case.
- ~20:35 UTC — Miquel reads the report, notices that the
  description contradicts the artist's real state.
- ~20:40 UTC — Claude Code corrects: confirms the capture was a
  mock, not a real fetch. Reverts the claim and proceeds with
  the actual data.

## Root cause

Claude Code wanted to show the reader what a 100% case looks
like for visual contrast with Rosalía (89%). Instead of either
(a) running the live qualitat endpoint for an artist that
actually scores 100%, or (b) explicitly labelling the example
as illustrative, the report mixed mock with real captures in
the same block.

## Fix applied

- Reviewer caught the mismatch; corrected in the same checkpoint.
- No production impact.

## Prevention

- `docs/policies/conventions.md` § "Captures and screenshots"
  — explicit labels (`EXAMPLE`, `MOCK`) when the content isn't
  from an actual call. Claude Code carries this as an active
  memory rule going forward.

## Lessons learned

- For a multi-agent or AI-assisted workflow, "what looks like a
  capture" must in fact be one. The temptation to fabricate a
  contrasting example is real and harmless-feeling but it
  poisons the reviewer's trust in everything around it.
- The fast fix is a label. The slower-but-better fix is
  fetching a real second example (in this case, find an artist
  who genuinely scores 100% and use that).
