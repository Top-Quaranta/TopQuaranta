# Sprint process

When a sprint needs a written spec before the first commit, and
how that spec progresses through the lifecycle.

## Why this policy exists

Sprints completed across late May 2026 (Portal Artista Ampliat,
Workflow Sol·licituds, Multi-tenant Caddy) all benefited from a
spec written upfront. The narrative engine reset, by contrast,
was sized as a "library only" sprint and grew into a wired path
without an updated spec — the ensuing regression cost a follow-up
post-mortem (`docs/archive/post-mortems/2026-05-20-narrative-engine-
collapsed.md`).

The rule is not "every sprint needs a spec"; it's "sprints above a
certain shape always do, and the cost of being wrong about the
sizing is asymmetric — better err on the side of writing".

## Sprint sizes

### Small — no spec required

A change is small when:
- Touches one app.
- Touches at most one model (or none).
- No new actor enters the flow.
- Reverts cleanly with `git revert`.

Code first, PR description carries the rationale. Examples: a CI
config tweak, a single endpoint bug fix, a renamed copy string.

### Medium — mini-spec required (1-2 pages)

A change is medium when at least two of these are true:
- Two or more apps touched.
- Two or more models touched.
- A new actor (gestor, staff QA, external integration) enters
  the flow.
- A new state machine appears.
- The change introduces a contract a future caller must respect.

Write a mini-spec **before the first commit** of the sprint as
an ADR with `Status: Proposed`. The ADR is the contract the
sprint executes; it's promoted to `Accepted` when the sprint
merges. If the sprint deviates, the ADR is updated in the same
PR (not after the fact).

### Large — full spec + multiple ADRs + post-mortem if drifted

Three weeks or more of work, structural refactor, or two+ areas
that need their own contracts. The full spec lives at
`docs/architecture/<area>.md` for the things that survive; the
decisions live as ADRs; if the result deviates more than 30 %
from the spec, the sprint ends with a post-mortem.

## Spec lifecycle

```
ADR Proposed   ←  first commit of the sprint
    ↓
ADR Accepted   ←  sprint merges
    ↓
…time passes…
    ↓
ADR Superseded (by ADR-NNNN)  OR  Deprecated  OR  Resolved
    ↓
moved to docs/archive/decisions/ after 6 months at that status
```

## Restrictions added mid-sprint

The narrative engine post-mortem records a specific failure mode:
the requirement "always list the top 5" was added after the
detector design was already locked in. The detectors had been
sized assuming the body could be entirely scenario-driven; once
the top-5 listing took most of the budget, the scenarios lost
their narrative weight.

**Rule:** if a constraint is added to a sprint after the spec is
Accepted, the spec is re-opened (status back to Proposed) and the
architecture is re-evaluated before the constraint lands in code.
This is cheap in writing time and prevents the architecture from
collapsing under late additions.
