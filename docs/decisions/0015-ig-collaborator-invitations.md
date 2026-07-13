# ADR-0015 — Instagram collaborator invitations for feed posts

- **Status:** Accepted (2026-07-13 — all tranches merged; flag ON in prod; first supervised batch 2026-07-06. The programmatic acceptance-read path was closed empirically — see §5.5 — and the definitive cycle is implemented: invite via API; acceptances marked manually from the staff panel; `caducada` at 14 days covers everything else)
- **Date:** 2026-07-03
- **Authors:** Miquel Matoses (+ Claude Opus 4.8)

## Context

We tag artists on Instagram feed carousels via `user_tags` (the
publisher builds one tag per artist per slide — see
`social/management/commands/publicar_social.py::_slide_tags` and
`social/payload.py::_instagram_urls_for_canco`). A `user_tags` mention
notifies the artist and links their handle, but it does **not** add them
as a *collaborator* (the IG "Invite Collaborator" feature that puts the
post on the invited account's own grid once they accept). Collaborator
invites are strictly more valuable for reach: the post appears on the
collaborator's profile and in their followers' feeds.

Two things converged to make this worth building now:

1. **Coverage is climbing.** IG-handle coverage of the working pool
   (latest PPCC top-40 + novetats of the last 4 weeks, deduped over
   principal + `artistes_col`) rose from **74/177 (41.8 %)** to
   **91/177 (51.4 %)** on 2026-07-03 after the "artistes sense
   Instagram" staff view (PR #305) let staff fill handles ranked by
   live-song count. More real handles → collaborator invites start to
   pay off.
2. **We now paginate novetats stories** (this same session): the
   novetats story is a paginated set with per-story `user_tags`
   (`social/renderer.py::render_stories_novetats`, param
   `ConfiguracioGlobal.novetats_stories_per_pagina`, default 4). The
   pagination + parity fix are already approved and shipping; the
   collaborator system is the natural next layer and should reuse the
   same per-container non-blocking guard.

The Graph API supports collaborator invites on feed posts (image and
carousel) through the `collaborators` field on the `/media` container
(`POST /<IG_USER_ID>/media` with
`collaborators=["handle1","handle2",...]`), and lets us poll acceptance
via `GET /<IG_MEDIA_ID>/collaborators`. **Stories do not support
collaborators** (confirmed against the Meta Media reference — stories
support `user_tags` only, since 2025-07-09; collaborators and product
tags are feed-only). So this system is **feed-only**; stories keep
`user_tags` mentions.

## Decision

Introduce an **inert, flag-gated collaborator-invitation layer** for IG
feed posts:

- A new model `InvitacioColaboracioIG` records every invite we send and
  its resolution (pending → accepted/rejected), keyed by `(artista,
  ig_media_id)`.
- A **slot policy** picks which artists to invite per post from the same
  ordered, deduped pool the tagger already builds, with acceptance
  history steering who gets a slot.
- A **per-collaborator non-blocking guard** at publish time mirrors the
  story guard from Fase 4.2: a bad handle is dropped and the next
  candidate substituted; if the pool empties, the post publishes with no
  collaborators. **Publication is never blocked by an invite.**
- A **cron poller** reconciles unresolved invites from
  `GET /<media>/collaborators` and feeds an acceptance rate into
  `MetricaPipeline`.
- Everything is off behind a **master flag defaulting to False**; all
  tunables live in `ConfiguracioGlobal`, nothing hardcoded.

Nothing in this ADR runs until `ConfiguracioGlobal.ig_collaboradors_actiu`
is switched on by staff — the model, migration, policy code and poller
ship dormant.

## Alternatives considered

- **`user_tags` only (status quo)** — simplest, already shipped. Keeps
  mentions but never gets us onto the collaborator's grid, so we leave
  the biggest reach lever unused. Rejected as the end state; kept as the
  fallback the guard degrades to.
- **Invite every taggable artist on every post** — no slot policy, just
  pass all handles as `collaborators`. Rejected: IG caps collaborators
  (see §5.1 note) and, more importantly, spamming invites to artists who
  keep rejecting burns goodwill; the A/B/C policy exists to be polite and
  to prioritise proven acceptors.
- **Pre-validate handles with `business_discovery` before inviting** —
  rejected as the primary mechanism: `business_discovery` only resolves
  business/creator accounts, is rate-limited, and returns nothing for
  private/personal handles, so it produces false negatives. We rely on
  the container error instead (see §5.3), keeping pre-validation as an
  optional future optimisation only if Meta ships a reliable check.

## Specification

### 5.1 Model `InvitacioColaboracioIG`

New app-local model in `social/models.py` (migration additive, no
backfill):

| Field | Type | Notes |
|---|---|---|
| `artista` | `FK(music.Artista, on_delete=PROTECT)` | who we invited |
| `username_snapshot` | `CharField(max_length=64)` | the bare handle at invite time (accounts get renamed; the snapshot is what we actually sent) |
| `ig_media_id` | `CharField(max_length=40, db_index=True)` | the published feed media the invite belongs to |
| `tipus_publicacio` | `CharField(choices=SocialPost.TIPUS_*)` | `top_ppcc` / `top_territorial` / `nous_albums` / `nous_singles` |
| `data_invitacio` | `DateTimeField(db_index=True)` | when we sent it (post publish time) |
| `estat` | `CharField(choices, default="pendent")` | `pendent` / `acceptada` / `rebutjada` |
| `data_resolucio` | `DateTimeField(null=True, blank=True)` | set by the poller when `estat` leaves `pendent` |

- `UNIQUE(artista, ig_media_id)` — one invite row per artist per post.
- `estat` choices constant
  `ESTATS = {"pendent","acceptada","rebutjada","caducada"}`. `caducada`
  (tranche 3b) = pending past the 14-day window; the policy treats it like
  `rebutjada` (category C, 90-day cooldown), closing the eternal-pending
  hole where an un-resolved invite blocked the artist forever.
- Indexes: `(estat, data_invitacio)` (poller scan window),
  `(artista, estat)` (category A/C lookup).
- `PROTECT` on the artist FK so a merge/delete can't silently orphan
  invite history (acceptance stats depend on it).

### 5.2 Slot policy

**Pool.** Reuse the tagger's expansion: for a post, take its entries,
expand principal + `artistes_col`, dedupe by artist, and order by **best
chart position** (top posts: the artist's best `posicio` on the post;
novetats: input order = recency). This is the *same* ordered pool the
renderer/tagger already produce — the policy consumes it, it does not
re-derive ranking.

**Categories** (per artist, from `InvitacioColaboracioIG` history):

- **A** — has `estat="acceptada"` on any past invite ("proven acceptor").
- **B** — never invited (no rows).
- **C** — only `rebutjada` and/or `pendent` rows, never accepted.

**Slots.** A post offers **3 collaborator slots** (`slots_total`,
configurable):

- **Slots 1–2 → category A**, taken in pool order (best position first),
  subject to cooldown. If fewer than 2 eligible A artists, **backfill
  from B** in pool order.
- **Slot 3 → the first B** not already used by slots 1–2.
- Category C artists are **not** offered a slot from the normal fill;
  they only return once their cooldown lets them re-enter as if fresh
  (they stay classified C, but a re-invite is allowed after the C
  cooldown). *(Design note: C never displaces an A or a fresh B; it only
  fills a slot that would otherwise go empty.)*

**Cooldowns** (configurable, defaults):

- **A: 15 days** since their last invite before re-inviting (don't pester
  proven collaborators every week).
- **C-rejected: 90 days** since the rejection before a re-invite.
- **Pending: never re-invited while still pending** — an unresolved
  invite blocks a new one for that artist until the poller resolves it.

**One policy for tops and novetats.** The categories, slots and
cooldowns are identical; only the pool source differs (chart position vs
recency), and that difference is already encoded in pool order.

**Empty-registry degradation (explicit + tested).** With an empty
`InvitacioColaboracioIG` table, *every* artist is category B, so the
policy simply returns the **first 3 of the ordered pool**. This is the
cold-start behaviour and MUST be covered by a test
(`test_slot_policy_empty_registry_returns_top3`).

### 5.3 Feed validation & fallback (never blocks publication)

**Mechanism: container error, not pre-validation.** At publish we set
`collaborators=[…]` on the `/media` container. Detection is the container
response:

- The container `POST` **succeeds** → collaborators accepted for
  *invitation* (acceptance by the artist is async, polled in §5.5).
- The container `POST` **errors** on a handle (invalid / private /
  non-existent) → we **drop that handle, substitute the next candidate
  from the ordered pool, and retry**. Repeat until the container
  succeeds or the pool is exhausted; if exhausted, publish with **no
  collaborators**. Every drop is logged with the API reason and (for the
  substituted-in artist) recorded so we don't lose the audit trail.

This is the **same guard shape** proven on the stories publish (Fase 4.2)
— leave-one-out identification of the offender, then substitution — lifted
to feed collaborators. We do **not** pre-validate with
`business_discovery` (unreliable for private/personal handles; see
Alternatives).

*Contrast with `user_tags`:* Meta tends to **silently drop** an invalid
`user_tags` entry (no error), whereas `collaborators` **errors** the
container — which is why the guard matters more here and why it must be
tested against a simulated container error, not just the happy path.

**Tests guaranteeing non-blocking publication:**

- `test_collab_bad_handle_substitutes_next_candidate` — first candidate
  errors, second is used, post publishes, drop logged.
- `test_collab_pool_exhausted_publishes_without_collaborators` — every
  candidate errors → container finally created with no `collaborators`,
  post still publishes.
- `test_collab_error_on_one_post_does_not_block_others` — mirrors the
  story guard: a failure on one post never aborts the run.

### 5.4 `ConfiguracioGlobal` parameters (staff-editable, nothing hardcoded)

All added to `ConfiguracioGlobal`, surfaced in `/staff/configuracio/`
(auto-reflected; map them to a new `SECTION_COL·LABORADORS` or the
existing distribution section):

| Field | Default | Meaning |
|---|---|---|
| `ig_collaboradors_actiu` | `False` | **master flag.** Off = the whole layer is dormant (no invites sent, no rows written). |
| `ig_collab_slots_total` | `3` | collaborator slots per post |
| `ig_collab_slots_acceptats` | `2` | slots reserved for category A |
| `ig_collab_cooldown_a_dies` | `15` | A re-invite cooldown |
| `ig_collab_cooldown_c_dies` | `90` | C-rejected re-invite cooldown |

The renderer/pagination knob `novetats_stories_per_pagina` (default 4,
shipped this session) is documented alongside these as part of the same
distribution surface.

### 5.5 Acceptance poller (cron)

New management command `social/management/commands/pollar_colaboracions_ig.py`:

- **Expiry pass (tranche 3b):** pending rows with `data_invitacio < now -
  14d` are set to `caducada` (with `data_resolucio`) — IG acceptance is
  immediate-or-never, so an un-resolved invite past the window is a soft
  decline. This closes the eternal-pending hole (such rows used to sit
  `pendent` forever, blocking the artist's re-invitation). Note: the
  14-day window is currently a module constant (`WINDOW_DIES`), not a
  `ConfiguracioGlobal` field — the one §5.4 tunable that is still
  hardcoded.
- Writes a **`MetricaPipeline`** row per run with the rolling acceptance
  rate (`acceptades / (acceptades + rebutjades + caducades)` — `caducada`
  is a non-acceptance), derived from registry state (idempotent per day)
  so the acceptance trend is visible on the pipeline dashboard.
- Cron cadence: hourly; gated on `ig_collaboradors_actiu` so it no-ops
  while the flag is off.
- *History:* the command originally also carried a reconcile pass
  (`GET /<media>/collaborators` per media, with a 2026-07-05 fail-safe
  and a 2026-07-06 temporary brake after the first live poll errored).
  That whole path was removed on 2026-07-13 when the empirical closure
  below proved programmatic acceptance reads unviable.

**Empirical closure of programmatic acceptance reads (2026-07-13).**
Verified against the first live batch's media (`18094840829027683`,
3 invitations pending at the time of both tests):

1. **Instagram Login (the app's token flavour):** the media node does
   not expose the `/collaborators` edge at all. 29 hourly poller ticks
   (2026-07-06 10:00 → 2026-07-07 04:00 UTC, token still valid)
   consistently returned code 100 `"Tried accessing nonexisting field
   (collaborators)"` on `graph.instagram.com` v19.0.
2. **Facebook Login, user token (v25.0; manual test by Miquel in the
   Graph API Explorer, 2026-07-13):** `GET /<media>/collaborators`
   responds **200 with empty `data`** — no error, but none of the 3
   invitations listed, while the Instagram app showed all 3 still
   PENDING in the collaborator editor (and no co-author on the post
   header). A user token does not expose pending invitations.
3. **Facebook Login, Page token:** would be the remaining candidate,
   but the app cannot generate one — Page permissions (including
   `pages_show_list`) are not available to its app type (verified in
   the Explorer, 2026-07-13).

Conclusion: programmatic acceptance reading is unviable with the
current app for **two independent reasons** (Instagram Login lacks the
edge; Facebook Login with a user token has the edge but returns it
empty for pending invitations, and the Page token is inaccessible).

**Definitive cycle (decided 2026-07-13):**

1. **Invite via API** at publish time (unchanged — §5.2/§5.3).
2. **Acceptances are marked manually from staff**, when Miquel
   observes them in the Instagram app. Minimal UI on the staff social
   panel: the invitation list with each row's estat and a single
   **"Marcar acceptada"** button that writes `estat=acceptada` +
   `data_resolucio`. There is deliberately **no "mark as rejected"
   action**: the automatic `pendent → caducada` pass at 14 days
   already covers both silence and rejection, which are the same
   thing to the policy (category C, 90-day cooldown).
3. **`caducada` is the only automatic terminal** — the poller keeps
   the expiry pass and the acceptance-rate metric, now read directly
   from the registry (`acceptades / resoltes`); the
   reconcile-against-Graph pass (and with it the temporary brake and
   `instagram_client.get_collaborators`) was removed when this cycle
   was implemented (same day). Staff endpoints:
   `GET /staff/social/invitacions/` +
   `POST /staff/social/invitacions/acceptar/` (audit action
   `collab_invitacio_acceptada`); UI on `/staff/social/instagram`.

For the record: as of 2026-07-13 none of the 3 invitations of the
2026-07-06 batch is accepted; they stay `pendent` until marked
accepted manually or expiring on 2026-07-20.

### 5.6 Story pagination + per-story mentions as permanent pipeline behaviour

The novetats story pagination shipped this session
(`render_stories_novetats`, per-story `user_tags` computed from the
visible items only) becomes the **permanent** novetats-story behaviour,
behind the master distribution gate that already governs publishing. The
top story set can adopt the same per-page-mention treatment later using
the identical structure; both reuse the **Fase 4.2 guard** (drop the
offending handle, retry, last-resort publish without mentions) so a bad
handle never blocks a story. Parameter `novetats_stories_per_pagina`
(default 4, clamp 1–8) is the single knob; coverage figures to size
expectations against: **91/177 handles (51.4 %)** on 2026-07-03.

### 5.7 PR plan (three tranches by activation risk)

1. **Mechanical + inert (this can merge freely):**
   - `InvitacioColaboracioIG` model + **additive** migration.
   - Slot-policy module (`social/collaboradors.py`) + full test suite
     (categories, cooldowns, empty-registry top-3, substitution guard) —
     pure functions, no side effects.
   - `ConfiguracioGlobal` flag + params (+ migration), default **off**.
   - Poller command, gated off.
   - No call site wired into `publicar_social` yet → zero runtime change.
2. **Already visually approved (covered by the 2026-07-03 checkpoint
   OK):** the novetats story **pagination** and the **collaborator-visibility
   parity fix**. These ship in the same session PR (see Fase 6) and need
   no further sign-off.
3. **Requires Miquel's activation (separate, gated switch-on):** flipping
   `ig_collaboradors_actiu` to True and wiring the policy into
   `publicar_social._publish_feed`, plus the **first real invite batch**.
   Done as a small follow-up PR reviewed live, so the first invites go
   out under supervision. *(Outcome: the wiring merged early as tranche
   3a, gated + inert — PR #308; the caducada expiry as 3b — PR #309; the
   flag flip + first supervised batch happened Monday 2026-07-06,
   top_territorial BAL.)*

## Consequences

- **Positive:** reach beyond mentions (posts land on collaborators'
  grids); a polite, history-aware invite policy; an acceptance metric to
  judge whether it's worth it; zero risk until the flag flips.
- **Negative / sharp-edged:**
  - IG's documented **max is 3 collaborators per post** (Meta Media
    reference, confirmed 2026-07-03: "up to 3 instagram usernames as
    collaborators", on feed image / reels / carousels — **not stories**).
    `social.collaboradors.GRAPH_MAX_COLLABORATORS = 3` hard-clamps
    `ig_collab_slots_total` to this. **Observed** in a create-only probe
    (2026-07-03): a feed `/media` container with **4** collaborators was
    accepted with **no error** (container id returned), and the
    `collaborators` field is **not readable back** off a container (`GET`
    → code 100 "nonexisting field"). So container-creation is lenient;
    the documented 3-limit is presumably enforced (or the extras dropped)
    at `media_publish`, which was **not** tested to avoid a real post.
    Net: keep the clamp at 3 (matches the docs); do not infer the API
    enforces it at create time.
  - `collaborators` **errors** the container on a bad handle (unlike the
    silent `user_tags` drop) — the guard is load-bearing, not a nicety.
    (The count-limit leniency above is separate: bad *handles* are
    expected to error; an over-count did not.)
  - Acceptance is async and often **never** happens; the 14-day poller
    window + "pending blocks re-invite" rule keep the queue from
    thrashing, but a chunk of invites will sit unresolved forever
    (treated as declined for stats after the window).
  - Stories can't use collaborators at all — this asymmetry (feed =
    collaborators + tags; stories = tags only) is permanent and must not
    be "fixed" by someone later trying to pass `collaborators` to a
    STORIES container.
- **Follow-up work:** tranche 3 wiring + first supervised batch; optional
  top-story per-page mentions (§5.6).

## Related

- Session (2026-07-03): parity fix + novetats story pagination + this
  spec; the 3 approved novetats stories published as
  `18110410429756692`, `18104543747028723`, `18096786196965624`.
- PRs / commits: PR #301 (collab tagging + visibility on tops), PR #305
  (artistes-sense-Instagram live-song sort), this session's PR.
- Meta reference: [IG Platform — Media / user_tags / collaborators](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/)
  (stories = `user_tags` only since 2025-07-09; `collaborators` feed-only).
- `docs/architecture/social.md` — the live publishing pipeline this
  extends.
