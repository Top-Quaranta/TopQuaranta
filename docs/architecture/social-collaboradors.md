# Social — IG collaborator invitations (feed)

> Split out of `social.md` on 2026-07-06 (docs-size headroom), same
> pattern as `social-narrative.md`. Spec + probe findings:
> `docs/decisions/0015-ig-collaborator-invitations.md`.

## Overview (ADR-0015; live since 2026-07-06)

Inviting artists as IG **collaborators** (their handle on the post → it
lands on their grid too), a step up from `user_tags` mentions. **Feed /
reels / carousels only — Meta does not support collaborators on stories.**
Gated on the master flag `ConfiguracioGlobal.ig_collaboradors_actiu`
(default **False**; switched ON in prod for the first batch, 2026-07-06):
with it off the feed publish path is byte-identical to before (no
`collaborators` key ever reaches a container, no registry rows written).

## Pieces

- **`social.models.InvitacioColaboracioIG`** — one row per
  `(artista, ig_media_id)`: `username_snapshot`, `tipus_publicacio`,
  `data_invitacio`, `estat` (pendent/acceptada/rebutjada/**caducada**),
  `data_resolucio`. Artist FK is `PROTECT` (acceptance stats depend on the
  history). `caducada` = pending past the 14-day window; the policy treats
  it like a rejection.
- **`social/collaboradors.py`** — pure, side-effect-free policy.
  `select_collaborators(pool, historic, config, *, now)` picks ≤
  `effective_slots` candidates: A (has accepted) / B (never invited) /
  C (only rejected/caducada/pending); slots 1-`slots_acceptats` → A backfilled
  from B, remaining → next B, C only fills otherwise-empty slots;
  cooldowns A/C, pending never re-invited. `GRAPH_MAX_COLLABORATORS = 3`
  hard-clamps `ig_collab_slots_total` (Meta's documented max).
  `publish_with_collaborator_guard(usernames, slots, try_container)` is
  the non-blocking substitution guard (§5.3): drop the offending handle,
  substitute the next candidate, last resort publish with none — a bad
  handle never blocks publication.
- **`pollar_colaboracions_ig`** (hourly cron) reconciles fresh pending
  invites via `GET /<media>/collaborators` AND expires pending invites
  older than 14 days to `caducada` (closing the eternal-pending hole),
  then writes the acceptance rate to `MetricaPipeline`
  (`ig_collab_taxa_acceptacio`; `caducada` counts as a non-acceptance in
  the denominator). No-op while the flag is off; best-effort + idempotent.
  Fail-safe (2026-07-05): every fetch is logged raw before interpretation;
  an empty response — or one with none of the media's pending invitees —
  resolves nothing (no estat, no cooldown; a human reads the raw log).
  Temporary brake (2026-07-06): an invitee ABSENT from the response also
  stays `pendent` (warning logged) — only an explicit non-accepted
  `invite_status` resolves to `rebutjada` — until Meta's behaviour with
  pending invitees on `GET /<media>/collaborators` is verified end-to-end
  (the first live poll errored; diagnosis pending). The final
  absent→rebutjada mapping stays documented + tested in `reconcile_estat`.
- **Wiring** (tranche 3a): `publicar_social._publish_feed`, **gated on the
  flag**, builds the ordered pool from the payload (`payload.build_top` /
  `build_novetats` now carry `artistes_pool` = `[{id, username}]`, additive),
  applies the policy against the live registry, and passes
  `collaborators=[…]` to the parent container
  (`instagram_client.{create_carousel,upload_image}`, additive param). The
  guard wraps the parent create+FINISH so a handle error at create OR async
  processing triggers substitution. On a successful publish it writes one
  `InvitacioColaboracioIG` per sent handle (idempotent `get_or_create`);
  if `media_publish` raises, no rows are written (no orphans).
- **`simular_colaboradors_ig`** — read-only dry-run command: builds the real
  pool for the latest top + novetats, applies the policy against the live
  registry, and prints per-post the pool, each artist's category +
  eligibility, the ≤3 selected, and who's discarded (cooldown / no handle).
  Sends nothing, writes nothing, works with the flag off.
- **Config** (§5.4): `ig_collaboradors_actiu`, `ig_collab_slots_total`,
  `ig_collab_slots_acceptats`, `ig_collab_cooldown_a_dies`,
  `ig_collab_cooldown_c_dies` — staff-editable under a dedicated
  **Col·laboradors IG** section of `/staff/configuracio/`.

## Status

Activation: the flag was switched on and the first real invite batch went
out Monday 2026-07-06 (top_territorial BAL, 09:30 UTC cron). The
programmatic acceptance-read path was closed empirically on 2026-07-13
(ADR-0015 §5.5: Instagram Login lacks the `/collaborators` edge; a
Facebook-Login user token returns it empty for pending invitations, and a
Page token is inaccessible to the app type). Definitive design: invitation
via API, **manual resolution from staff**, `caducada` at 14 days as the
only automatic terminal. Acceptances are marked manually from the staff
social panel (single "Marcar acceptada" action; deliberately no manual
reject — `caducada` covers silence and rejection alike). The poller's
reconcile pass (and the temporary brake) are pending removal; ADR-0015
stays **Proposed** until that lands.

## Related

- Publishing pipeline: [`social.md`](social.md).
- Spec + probe findings: `docs/decisions/0015-ig-collaborator-invitations.md`.
- Modules: `social/collaboradors.py`,
  `social/management/commands/pollar_colaboracions_ig.py`,
  `social/management/commands/simular_colaboradors_ig.py`,
  `social/management/commands/publicar_social.py` (wiring).
