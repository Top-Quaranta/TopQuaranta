# Narrative engine collapsed under top-5 constraint — 2026-05-20

- **Date of incident:** observed 2026-05-20 during social
  investigation; degradation accumulated over weeks
- **Severity:** high (every weekly social post affected)
- **Status:** Resolved by ADR-0006, ADR-0007, ADR-0008 (2026-05-21)
- **Author:** Miquel

## Impact

The narrative engine for weekly social posts (Fase 4, eight
detectors a1-a8) is in production but produces text that "feels
always the same" across channels:

- Instagram + Telegram: positions `#1`, `#2`, `#3` are parsed as
  clickable hashtags pointing to random external content, so
  every caption leaks the audience out of the post.
- Instagram: `@username` mentions to artists were lost when the
  caption pipeline switched from `_caption_top_legacy` (which
  called `_artist_label(use_handle=True)`) to the new
  `compose_for_channel` narrative path (which doesn't).
- All channels: when a given week has only one scenario firing
  (e.g. only `a3_fall_from_top1` on 2026-05-18), the variable
  part of the body is one paragraph and the rest (top-5
  completion + CTA + hashtags) dominates. The result looks
  identical to every other one-scenario week.

## Timeline

- 2026-05-18 — Fase 4 PR 1 lands the narrative library
  (originally documented as "not wired yet"). At some point soon
  after (no clean commit identified), `captions.compose_for_channel`
  starts routing `top_ppcc`/`top_territorial` through the engine.
- 2026-05-18 to 2026-05-20 — three weekly cycles publish with the
  new path. Quality regression accumulates.
- 2026-05-21 — observed during the broader read-only social
  investigation.

## Root cause

Two layers:

1. **Constraint added post-design.** The original Fase 4 spec
   sized the scenario phrases as the body. The "always list the
   top 5" requirement was added later, taking most of the body
   budget. With small scenarios + heavy top-5 listing, the body
   is dominated by the fixed part and feels repetitive.
2. **Per-channel mention contract not preserved during wiring.**
   The legacy `_caption_top_legacy` called
   `_artist_label(use_handle=True)` for Instagram; the new
   narrative composers (in `social/narrative/composers/`) call
   `top5_bank.pick_long` which renders plain names. The IG
   `@handle` autolink path was lost in translation. The
   regression went undetected because IG's autolinking is silent
   when missing (no error, just plain text where `@user` should
   have been).
3. **Positional `#N` in templates.** Templates in
   `social/narrative/banks/hero.py` (22+ lines) and
   `banks/top5.py` (10+ lines) literally contain `al #1`, `al
   #{posicio}`. IG and Telegram parsers treat `#<digit>` as
   hashtag-clickable. Mastodon and Bluesky parsers require
   letters at the start of a hashtag, so they render as text;
   that's why Mastodon "felt fine".

## Fix applied

Not yet applied. This post-mortem captures the regression as the
trigger for a dedicated social refactor sprint.

Architecture-level fixes that the next sprint needs to land:

- Replace literal `#N` with an alternative: "núm. N", "lloc N",
  emoji digits (1️⃣ 2️⃣), or simply "al cim", "al 2", "al 3" in
  the contexts where the number alone is enough.
- Reintroduce the `@handle` path on Instagram via the narrative
  composers (the `_artist_label(use_handle=True)` helper still
  exists; the new composers need to call it explicitly).
- Re-evaluate the top-5 dominance: either compress the listing
  into a sub-line, drop it on channels with tight char budgets
  (Bluesky 300), or move it entirely to the carousel images.
- Add 2-3 detectors covering shapes the current 8 miss
  ("first-ever-in-top artist", "long-runner falls off", "stable
  week vs turbulent week").

## Prevention

- `docs/policies/sprint-process.md` § "Restrictions added
  mid-sprint" — the constraint "always list the top 5" was added
  to the engine after its initial design was set. The policy now
  requires re-opening the spec (Status: back to Proposed) when a
  restriction lands mid-flight.
- A future ADR on social composition will record the
  per-channel mention contract explicitly so future refactors
  can't silently drop it.

## Lessons learned

- "Wired silently" is the worst kind of release. The roadmap
  said "library only, not wired"; the code said wired. Drift
  between the two ate two weeks before anyone noticed. CI check
  proposed in `docs/policies/docs-maintenance.md` Rule 2 (PR
  template + needs-docs-review label) is meant to surface this
  shape.
- Cross-channel comparison catches what single-channel review
  misses. Reviewing Mastodon in isolation would suggest the
  engine is fine. Looking at IG + Telegram + Mastodon
  side-by-side surfaces the `#N` regression immediately.
