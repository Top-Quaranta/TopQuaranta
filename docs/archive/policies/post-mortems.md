# Post-mortems

When TopQuaranta writes a post-mortem and what shape that document
takes.

## Philosophy

A post-mortem is not a chronicle of blame. It's a structured
artefact that ends with a link to a rule in `docs/policies/` —
the rule that, had it existed and been enforced, would have
prevented the incident. If no policy covers the failure mode, the
post-mortem is what brings the new policy into being.

In a single-operator project, this matters even more: blame
collapses to "me", which is useless. What's useful is the
machine-checkable rule that catches the same mistake next time
even when the operator is fast or tired.

## Triggers

Write a post-mortem when:

1. **Production incident** — visible 5xx errors, data loss,
   silenced publication channel, or any user-visible breakage.
   Severity is reported in the post-mortem itself
   (critical/high/medium/low).
2. **Redesign of recent work** — a sprint finishes and within
   days we're rewriting parts of it. The post-mortem captures the
   spec drift that made the rewrite necessary.
3. **Decision reversed** — an ADR moves to `Status: Superseded`
   in less than 6 months. The post-mortem captures why; if the
   reason is process (we didn't think about X), it ends with a
   policy update.
4. **Mock or hallucinated artefact** — Claude Code (or any
   contributor) presents a captured output that wasn't actually
   captured. The post-mortem records the failure to mark
   illustrative material as such; the policy is `conventions.md`
   rule about explicit MOCK / EXAMPLE labels.

## Format

Copy `docs/archive/post-mortems/TEMPLATE.md` to `YYYY-MM-DD-<slug>.md`
where the date is the **incident date**, not the write-up date.

Each post-mortem ends with a `## Prevention` block that links to
the responsible policy:

```markdown
## Prevention

The rule that catches this next time:
- `docs/policies/identities.md` § "Rule 1 — Service auth always
  belongs to admin@topquaranta.cat"

If the rule did not exist before this post-mortem, link the new
policy entry instead.
```

## Where they live

- **`docs/archive/post-mortems/` (live):** every post-mortem stays here
  indefinitely.
- **No archive:** see `docs/policies/docs-maintenance.md` Rule 5.

## How to use the inventory

When designing a new sprint that touches a familiar shape (auth,
deploy, social distribution), grep `docs/archive/post-mortems/` for the
shape first. The previous incident's `## Prevention` link is the
fastest way to surface the policy you need to comply with.
