"""Slot policy + publish guard — pure unit tests (no DB, no network).

Covers ADR-0015 §5.2 (categories, cooldowns, slot fill, clamp, empty
registry) and §5.3 (substitution guard, pool exhaustion, per-post
isolation).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from social.collaboradors import (
    CAT_A,
    CAT_B,
    CAT_C,
    GRAPH_MAX_COLLABORATORS,
    CollaboratorContainerError,
    InviteRecord,
    PolicyConfig,
    PoolArtist,
    Selected,
    effective_slots,
    publish_with_collaborator_guard,
    select_collaborators,
)

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
CFG = PolicyConfig()  # defaults: total 3, acceptats 2, cooldown A 15 / C 90


def _pool(*names):
    """Ordered pool; artista_id = position so ids are stable + distinct."""
    return [PoolArtist(artista_id=i, username=n) for i, n in enumerate(names, 1)]


def _days_ago(n):
    return NOW - timedelta(days=n)


# ── §5.2 slot policy ─────────────────────────────────────────────────


def test_slot_policy_empty_registry_returns_top3():
    pool = _pool("a", "b", "c", "d", "e")
    out = select_collaborators(pool, {}, CFG, now=NOW)
    assert [s.username for s in out] == ["a", "b", "c"]
    assert all(s.categoria == CAT_B for s in out)


def test_fewer_than_pool_returns_all_when_pool_short():
    out = select_collaborators(_pool("a", "b"), {}, CFG, now=NOW)
    assert [s.username for s in out] == ["a", "b"]


def test_category_A_takes_reserved_slots_over_fresh_B():
    # a1 accepted long ago (eligible A); the rest are fresh B.
    hist = {1: [InviteRecord(estat="acceptada", data_invitacio=_days_ago(40))]}
    out = select_collaborators(_pool("a1", "b1", "b2", "b3"), hist, CFG, now=NOW)
    # 3 slots: a1 (A, reserved), then two B in pool order.
    assert [(s.username, s.categoria) for s in out] == [
        ("a1", CAT_A),
        ("b1", CAT_B),
        ("b2", CAT_B),
    ]


def test_A_backfills_from_B_when_not_enough_A():
    # slots_acceptats=2 but only one eligible A → one reserved slot
    # backfills from B, third slot is the next B.
    hist = {2: [InviteRecord(estat="acceptada", data_invitacio=_days_ago(40))]}
    out = select_collaborators(_pool("b1", "a1", "b2", "b3"), hist, CFG, now=NOW)
    assert [(s.username, s.categoria) for s in out] == [
        ("a1", CAT_A),  # reserved A slot
        ("b1", CAT_B),  # backfilled reserved slot (pool order)
        ("b2", CAT_B),  # open slot → next B
    ]


def test_A_within_cooldown_is_skipped():
    # a1 invited 10 days ago (< 15) → not eligible; falls to B fill.
    hist = {
        1: [
            InviteRecord(estat="acceptada", data_invitacio=_days_ago(40)),
            InviteRecord(estat="acceptada", data_invitacio=_days_ago(10)),
        ]
    }
    out = select_collaborators(_pool("a1", "b1", "b2"), hist, CFG, now=NOW)
    assert [s.username for s in out] == ["b1", "b2"]  # a1 on cooldown


def test_A_past_cooldown_is_eligible():
    hist = {1: [InviteRecord(estat="acceptada", data_invitacio=_days_ago(16))]}
    out = select_collaborators(_pool("a1", "b1"), hist, CFG, now=NOW)
    assert out[0].username == "a1" and out[0].categoria == CAT_A


def test_pending_blocks_reinvitation():
    # a1 has a pending invite → never re-invited while pending, even
    # though it also accepted before (category A).
    hist = {
        1: [
            InviteRecord(estat="acceptada", data_invitacio=_days_ago(40)),
            InviteRecord(estat="pendent", data_invitacio=_days_ago(3)),
        ]
    }
    out = select_collaborators(_pool("a1", "b1", "b2"), hist, CFG, now=NOW)
    assert "a1" not in [s.username for s in out]
    assert [s.username for s in out] == ["b1", "b2"]


def test_C_rejected_cooldown_90_days():
    # c1 rejected 50 days ago → still on the 90-day C cooldown.
    recent = {
        1: [InviteRecord("rebutjada", _days_ago(60), data_resolucio=_days_ago(50))]
    }
    out = select_collaborators(_pool("c1"), recent, CFG, now=NOW)
    assert out == []  # blocked, and no B/A to fill → empty
    # Past 90 days → eligible again, fills the otherwise-empty slot as C.
    old = {1: [InviteRecord("rebutjada", _days_ago(100), data_resolucio=_days_ago(95))]}
    out2 = select_collaborators(_pool("c1"), old, CFG, now=NOW)
    assert [(s.username, s.categoria) for s in out2] == [("c1", CAT_C)]


def test_C_caducada_treated_like_rejection_90_day_cooldown():
    # A caducada invite (expired pending) behaves exactly like a
    # rejection: category C, 90-day cooldown from its resolution.
    recent = {
        1: [InviteRecord("caducada", _days_ago(60), data_resolucio=_days_ago(50))]
    }
    assert select_collaborators(_pool("c1"), recent, CFG, now=NOW) == []
    old = {1: [InviteRecord("caducada", _days_ago(120), data_resolucio=_days_ago(100))]}
    out = select_collaborators(_pool("c1"), old, CFG, now=NOW)
    assert [(s.username, s.categoria) for s in out] == [("c1", CAT_C)]


def test_C_never_displaces_A_or_fresh_B():
    # Pool: c1 (eligible C, old rejection), a1 (eligible A), b1/b2 fresh B.
    hist = {
        1: [InviteRecord("rebutjada", _days_ago(200), data_resolucio=_days_ago(195))],
        2: [InviteRecord("acceptada", _days_ago(40))],
    }
    out = select_collaborators(_pool("c1", "a1", "b1", "b2"), hist, CFG, now=NOW)
    # A + 2 B fill all 3 slots; C is left out entirely.
    assert [(s.username, s.categoria) for s in out] == [
        ("a1", CAT_A),
        ("b1", CAT_B),
        ("b2", CAT_B),
    ]
    assert "c1" not in [s.username for s in out]


def test_C_only_fills_slots_left_empty():
    # Only c1 (eligible) + b1: b1 fills a slot, c1 fills the next empty one.
    hist = {
        1: [InviteRecord("rebutjada", _days_ago(200), data_resolucio=_days_ago(195))]
    }
    out = select_collaborators(_pool("c1", "b1"), hist, CFG, now=NOW)
    assert [(s.username, s.categoria) for s in out] == [
        ("b1", CAT_B),
        ("c1", CAT_C),
    ]


def test_clamp_slots_total_to_graph_limit():
    cfg5 = PolicyConfig(slots_total=5, slots_acceptats=2)
    assert effective_slots(cfg5) == GRAPH_MAX_COLLABORATORS == 3
    out = select_collaborators(_pool("a", "b", "c", "d", "e"), {}, cfg5, now=NOW)
    assert len(out) == 3  # never more than 3, whatever the config says


def test_slots_total_below_default_respected():
    cfg1 = PolicyConfig(slots_total=1, slots_acceptats=2)
    out = select_collaborators(_pool("a", "b", "c"), {}, cfg1, now=NOW)
    assert [s.username for s in out] == ["a"]


# ── §5.3 publish guard ───────────────────────────────────────────────


def _try_container_failing_on(bad_set):
    """Fake container creator: fails (naming the first bad handle) if any
    username in `bad_set` is present, else succeeds."""

    def _try(usernames):
        for u in usernames:
            if u in bad_set:
                return (False, u)
        return (True, None)

    return _try


def test_collab_bad_handle_substitutes_next_candidate():
    pool = ["bad", "u2", "u3", "u4"]
    res = publish_with_collaborator_guard(
        pool, slots=3, try_container=_try_container_failing_on({"bad"})
    )
    assert res.used == ["u2", "u3", "u4"]  # dropped bad, pulled reserve u4
    assert [d["username"] for d in res.dropped] == ["bad"]


def test_collab_pool_exhausted_publishes_without_collaborators():
    pool = ["b1", "b2", "b3"]
    res = publish_with_collaborator_guard(
        pool, slots=3, try_container=_try_container_failing_on({"b1", "b2", "b3"})
    )
    assert res.used == []  # published clean, no collaborators
    assert {d["username"] for d in res.dropped} == {"b1", "b2", "b3"}


def test_collab_offender_identified_by_leave_one_out_when_unnamed():
    # Container fails but never names the bad handle (bad=None) → the
    # guard leave-one-out finds it.
    def _try(usernames):
        if "poison" in usernames:
            return (False, None)  # unnamed failure
        return (True, None)

    res = publish_with_collaborator_guard(
        ["u1", "poison", "u3", "u4"], slots=3, try_container=_try
    )
    assert "poison" not in res.used
    assert res.used == ["u1", "u3", "u4"]
    assert [d["username"] for d in res.dropped] == ["poison"]


def test_collab_container_error_with_no_collaborators_raises():
    # Base image broken: fails even with zero collaborators.
    def _try(usernames):
        return (False, "media_error")

    try:
        publish_with_collaborator_guard(["u1"], slots=1, try_container=_try)
        assert False, "expected CollaboratorContainerError"
    except CollaboratorContainerError:
        pass


def test_collab_error_on_one_post_does_not_block_others():
    # The guard is stateless: post A's base is broken (raises), post B
    # publishes fine right after. A caller looping posts with a per-post
    # try/except (tranche 3) thus never lets one post block the rest.
    broken = lambda names: (False, "media_error")  # noqa: E731
    good = _try_container_failing_on(set())

    processed = []
    for name, tc in [("A", broken), ("B", good)]:
        try:
            res = publish_with_collaborator_guard(["x"], slots=1, try_container=tc)
            processed.append((name, res.used))
        except CollaboratorContainerError:
            processed.append((name, "SKIPPED"))
    assert processed == [("A", "SKIPPED"), ("B", ["x"])]
