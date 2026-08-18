# ADR-0017 — Pytest runs with `-n 4`, fixed, not `-n auto`

- **Status:** Accepted
- **Date:** 2026-08-18
- **Authors:** Miquel

## Context

The suite (1 952 tests) took 163 s in series. Measured on Miquel's Mac
(4 performance + 4 efficiency cores) on 2026-08-18:

| workers | time |
|---|---|
| series | 163 s |
| `-n 4` | 78 s (2.1×) |
| `-n 8` | 119 s — worse |

`-n auto` picks 8 on that Mac, and the workers scheduled on the
efficiency cores drag the whole run: xdist waits for the slowest
worker. GitHub's ubuntu runners have 4 real cores. A fixed `-n 4`
is right on both machines.

## Decision

`pytest-xdist==3.8.0` in `requirements-dev.txt`, and `-n 4` appended to
`addopts` in `pytest.ini`, next to the `--ds=` pin from ADR-0003
(unchanged).

## Alternatives considered

- **`-n auto`.** Rejected: measured slower on the Mac (8 workers).
- **`-n logical` / per-machine env override.** More knobs for no gain;
  `-n 4` is correct on the two machines that run the suite.

## Consequences

- Positive: local + CI suite in ~75-80 s.
- Negative: a single-test run pays xdist start-up (~2 s). Pass `-n 0`
  to opt out (`pytest -n 0 path/to/test.py::test_x`).
- Test isolation is now enforced by construction: a test that leaks
  state across modules will fail nondeterministically under xdist.
  That is a feature.

## Related

- ADR-0003 (the `--ds=` pin, which stays).
- Affected files: `pytest.ini`, `requirements-dev.txt`.
