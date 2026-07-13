"""Instagram collaborator slot policy — pure functions, no side effects.

# Spec: docs/decisions/0015-ig-collaborator-invitations.md

Tranche 1 (INERT): this module is imported by nobody in the publish
path yet. The acceptance poller and — later — `publicar_social` will
consume it once `ConfiguracioGlobal.ig_collaboradors_actiu` is on.

The core (`select_collaborators`, `publish_with_collaborator_guard`)
takes plain data + injected callables and touches neither the DB nor
the network, so it is exhaustively unit-testable. `PolicyConfig.from_config`
is the only Django-aware helper and just copies fields off a
`ConfiguracioGlobal` instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# ── Graph API hard limit ─────────────────────────────────────────────
# Instagram's Content Publishing API accepts at most THREE usernames in
# the `collaborators` array of a feed/reel/carousel container (it is not
# supported on stories at all). We clamp the staff-configurable
# `ig_collab_slots_total` to this ceiling so a mis-set config can never
# ask Meta for more than it allows.
# Ref: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/
GRAPH_MAX_COLLABORATORS = 3

# Estat strings (kept in sync with social.models.InvitacioColaboracioIG;
# duplicated as bare literals so this module stays import-cheap and pure).
ESTAT_PENDENT = "pendent"
ESTAT_ACCEPTADA = "acceptada"
ESTAT_REBUTJADA = "rebutjada"
# `caducada` (pending past the 14-day window) is treated exactly like a
# rejection by the policy: category C + the C cooldown from its resolution.
ESTAT_CADUCADA = "caducada"

# Categories.
CAT_A = "A"  # has accepted at least once
CAT_B = "B"  # never invited
CAT_C = "C"  # only rejected / caducada / pending, never accepted


@dataclass(frozen=True)
class PoolArtist:
    """One candidate from the ordered pool (best chart position first).
    `artista_id` keys the invite history; `username` is the bare handle."""

    artista_id: int
    username: str


@dataclass(frozen=True)
class InviteRecord:
    """A past `InvitacioColaboracioIG` row, reduced to what the policy
    needs. `data_resolucio` is None while still pending."""

    estat: str
    data_invitacio: datetime
    data_resolucio: datetime | None = None


@dataclass(frozen=True)
class PolicyConfig:
    slots_total: int = 3
    slots_acceptats: int = 2
    cooldown_a_dies: int = 15
    cooldown_c_dies: int = 90

    @classmethod
    def from_config(cls, cfg) -> "PolicyConfig":
        """Build from a `ranking.ConfiguracioGlobal` instance."""
        return cls(
            slots_total=cfg.ig_collab_slots_total,
            slots_acceptats=cfg.ig_collab_slots_acceptats,
            cooldown_a_dies=cfg.ig_collab_cooldown_a_dies,
            cooldown_c_dies=cfg.ig_collab_cooldown_c_dies,
        )


@dataclass(frozen=True)
class Selected:
    artista_id: int
    username: str
    categoria: str  # CAT_A / CAT_B / CAT_C


def effective_slots(config: PolicyConfig) -> int:
    """Slots we may actually use = min(configured total, Graph limit)."""
    return max(0, min(config.slots_total, GRAPH_MAX_COLLABORATORS))


# ── categorisation + eligibility ─────────────────────────────────────


def _category(records: list[InviteRecord]) -> str:
    if any(r.estat == ESTAT_ACCEPTADA for r in records):
        return CAT_A
    if records:
        return CAT_C
    return CAT_B


def _has_pending(records: list[InviteRecord]) -> bool:
    return any(r.estat == ESTAT_PENDENT for r in records)


def candidate_status(
    records: list[InviteRecord], config: PolicyConfig, now: datetime
) -> tuple[str, bool, str]:
    """`(categoria, elegible, motiu)` for one artist. Single source of
    truth for both the selector's eligibility gate and the dry-run's
    human-readable reason. A pending invite blocks regardless of
    category; A respects `cooldown_a_dies` since its last invite;
    C-rejected respects `cooldown_c_dies` since the rejection; B is
    always eligible."""
    cat = _category(records)
    if _has_pending(records):
        return cat, False, "pendent (invitació sense resoldre)"
    if cat == CAT_A:
        last = max((r.data_invitacio for r in records), default=None)
        if last is not None and (now - last).days < config.cooldown_a_dies:
            return (
                cat,
                False,
                f"cooldown A ({(now - last).days}d < {config.cooldown_a_dies}d)",
            )
        return cat, True, "acceptador (A)"
    if cat == CAT_C:
        rejections = [
            r for r in records if r.estat in (ESTAT_REBUTJADA, ESTAT_CADUCADA)
        ]
        if rejections:
            last_rej = max((r.data_resolucio or r.data_invitacio) for r in rejections)
            if (now - last_rej).days < config.cooldown_c_dies:
                return (
                    cat,
                    False,
                    f"cooldown C ({(now - last_rej).days}d < {config.cooldown_c_dies}d)",
                )
        return cat, True, "rebutjat (C) fora de cooldown"
    return CAT_B, True, "mai convidat (B)"


def _eligible(
    records: list[InviteRecord], categoria: str, config: PolicyConfig, now: datetime
) -> bool:
    """Cooldown + pending gate (bool view of `candidate_status`)."""
    return candidate_status(records, config, now)[1]


def select_collaborators(
    pool: list[PoolArtist],
    historic: dict[int, list[InviteRecord]],
    config: PolicyConfig,
    *,
    now: datetime,
) -> list[Selected]:
    """Pick up to `effective_slots(config)` collaborators from the
    ordered `pool`, per ADR-0015 §5.2:

      - Slots 1..`slots_acceptats` → eligible category A in pool order,
        backfilled from eligible B when A runs short.
      - Remaining slots → the next eligible B not already used.
      - Category C only fills slots still empty after A and B are
        exhausted (never displaces an A or a fresh B).

    Empty registry → every artist is B → returns the first
    `effective_slots` of the pool (cold start). Pure: `now` is injected."""
    eff = effective_slots(config)
    if eff <= 0:
        return []
    reserved = min(config.slots_acceptats, eff)

    elig: dict[str, list[PoolArtist]] = {CAT_A: [], CAT_B: [], CAT_C: []}
    for pa in pool:
        recs = historic.get(pa.artista_id, [])
        categoria = _category(recs)
        if _eligible(recs, categoria, config, now):
            elig[categoria].append(pa)

    selected: list[Selected] = []
    used: set[int] = set()

    def _take(candidates: list[PoolArtist], categoria: str, n: int) -> None:
        for pa in candidates:
            if len(selected) >= eff or n <= 0:
                return
            if pa.artista_id in used:
                continue
            selected.append(Selected(pa.artista_id, pa.username, categoria))
            used.add(pa.artista_id)
            n -= 1

    # Reserved A slots (backfill from B for whatever A can't fill).
    _take(elig[CAT_A], CAT_A, reserved)
    reserved_remaining = reserved - len(selected)
    _take(elig[CAT_B], CAT_B, reserved_remaining)
    # Open (non-reserved) slots → next B.
    _take(elig[CAT_B], CAT_B, eff - len(selected))
    # Anything still empty → C.
    _take(elig[CAT_C], CAT_C, eff - len(selected))
    return selected


# ── publish-time substitution guard (§5.3) ───────────────────────────


@dataclass(frozen=True)
class GuardResult:
    used: list[str]
    dropped: list[dict]  # [{"username": str, "reason": str}, ...]


class CollaboratorContainerError(RuntimeError):
    """The container failed even with zero collaborators — not a handle
    problem (bad image, auth, etc.). The caller decides what to do."""


def _find_offender(active: list[str], try_container) -> str | None:
    """Leave-one-out: the username whose removal lets the container pass,
    or None if no single removal fixes it (multiple bad / non-handle)."""
    for u in active:
        ok, _ = try_container([x for x in active if x != u])
        if ok:
            return u
    return None


def publish_with_collaborator_guard(
    ordered_usernames: list[str],
    slots: int,
    try_container,
    *,
    max_slots: int = GRAPH_MAX_COLLABORATORS,
) -> GuardResult:
    """Non-blocking collaborator publish (§5.3). Publication NEVER blocks
    on a bad handle.

    `ordered_usernames` is the ordered candidate pool (usernames);
    `slots` collaborators are attempted first, the rest are the
    substitution reserve. `try_container(usernames) -> (ok, bad_or_None)`
    creates the container (NO publish); it returns `(True, None)` on
    success, or `(False, bad_username | None)` on failure — the bad
    handle when Meta names it, else None (we then leave-one-out).

    On a handle failure the offender is dropped, the next reserve
    candidate substituted, and the container retried. When the pool is
    exhausted the post is published with NO collaborators (empty set).
    Raises `CollaboratorContainerError` only if the container fails even
    with zero collaborators (a non-handle problem).

    `max_slots` is the API ceiling to clamp `slots` against. It defaults
    to the collaborator limit (3); the story-mention publisher reuses
    this guard for `user_tags` with `max_slots=20` (Meta's per-image
    tag limit) — same drop/substitute/last-resort-empty semantics."""
    slots = max(0, min(slots, max_slots))
    active = list(ordered_usernames[:slots])
    reserve = list(ordered_usernames[slots:])
    dropped: list[dict] = []

    while True:
        ok, bad = try_container(list(active))
        if ok:
            return GuardResult(used=list(active), dropped=dropped)
        if not active:
            # Zero collaborators and still failing → not a handle issue.
            raise CollaboratorContainerError(
                bad or "container failed with no collaborators"
            )
        offender = bad if (bad in active) else _find_offender(active, try_container)
        if offender is None:
            # No single removal fixes it (multiple bad or the base is
            # broken) — drop one to guarantee progress; the loop will
            # eventually reach the empty-set case and either publish
            # clean or raise.
            offender = active[-1]
        dropped.append({"username": offender, "reason": "container rejected handle"})
        active = [u for u in active if u != offender]
        if reserve:
            active.append(reserve.pop(0))
