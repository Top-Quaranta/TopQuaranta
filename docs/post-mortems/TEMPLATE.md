# <Title> — YYYY-MM-DD

- **Date of incident:** YYYY-MM-DD (or range)
- **Severity:** critical / high / medium / low
- **Author:** <name>

## Impact

What did the end user / external system see? Quantify when
possible (errors per minute, requests dropped, hours of silence).

## Timeline

UTC clock. Compress days into ranges if the incident spanned them.

- HH:MM — first sign of trouble.
- HH:MM — detection (manual / monitoring / user report).
- HH:MM — diagnosis.
- HH:MM — fix applied.
- HH:MM — verified resolved.

## Root cause

The real cause, not the symptom. If the symptom was "500 on
/canco/<slug>", the root cause is one level deeper ("workers
picking up uncommitted models.py edits before migration applied,
because gunicorn was running with `--reload`").

## Fix applied

The immediate action that stopped the bleed. Whether it was the
right long-term fix is a different question; if the immediate fix
was a hack, say so.

## Prevention

Link to the rule in `docs/policies/` that prevents this shape from
recurring. If the rule did not exist before this incident, the
post-mortem is what brings it into being — link the new policy
entry here.

- Policy: `docs/policies/<file>.md` (specific section if useful)
- ADR (if any): `docs/decisions/NNNN-slug.md`

## Lessons learned

Free text. Things you'd say differently in hindsight, follow-up
work that didn't fit the immediate fix, related issues that this
nearly caught and didn't.
