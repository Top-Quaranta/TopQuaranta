# GoAccess (Caddy log analysis)

`generar_goaccess` (cron 23:30 daily) reads every TopQuaranta access
segment under `/var/log/caddy` — the live `topquaranta_access.log`
plus the rotated `topquaranta_access-<ts>.log.gz` — converts the
per-line Caddy JSON into Combined Log Format with a small Python
preprocessor, and runs `goaccess` to produce
`/var/cache/topquaranta/goaccess/report.html`.

The HTML is **never served by Caddy directly** — only through the
Django proxy at `/api/v1/staff/analytics/goaccess/`, which requires
`IsStaff` (session + 2FA). That keeps Caddy access analytics behind
the same auth as the rest of the staff panel.

Complements the Django dashboard:

* The Django side measures **what people do** (events, conversions,
  funnel deltas).
* GoAccess measures **how the server responds** (404 leaderboard,
  bot traffic, hot files, geo distribution, asset-cache hit ratios).

GoAccess never writes to the Django DB; it's pure log analytics.

**Filesystem setup** (one-time, on a fresh box):

```bash
sudo apt install -y goaccess
sudo setfacl -m u:topquaranta:rx /var/log/caddy
sudo setfacl -m u:topquaranta:r  /var/log/caddy/topquaranta_access.log
sudo mkdir -p /var/cache/topquaranta/goaccess
sudo chown topquaranta:topquaranta /var/cache/topquaranta/goaccess
```

Caddy rotates the log automatically on size (10 MiB) into
`topquaranta_access-<ts>.log.gz`; the ACL needs to be re-applied to
the live file after a Caddy package upgrade if the file is recreated
from scratch (rare). The default ACL on the parent dir keeps new
rotated files reachable for traversal.

## Reading the whole corpus (2026-07-31)

Until 2026-07-31 the command read **only** the live file. Caddy
rotates at 10 MiB and keeps 5 (`roll_size`/`roll_keep`,
`deploy/Caddyfile`), so the report silently covered whatever slice
happened to be un-rotated at 23:30. On 2026-07-30 that was **1 h
32 min and 4240 of 32746 available lines**, reported as exit 0 under a
"last 30 days" label. Reading the rotated segments took the same run
from 1.5 h to 122 h of coverage.

**Segment selection.** The rotated glob is anchored on
`topquaranta_access-<RFC3339>.log.gz`. Three neighbours share
`/var/log/caddy` and each would silently poison the numbers if a
looser glob picked them up:

| File | What it is |
|---|---|
| `topquaranta_legacy_access.log` | pre-2026-04 vhost, a different site |
| `access.log` | default-vhost dump, mostly bare-IP bot probes |
| `cercol_api_access*` | another project deployed on the same box |

Enforced by `test_glob_excludes_legacy_and_other_vhosts`.

**Streaming, not loading.** Segments are read line by line through
`gzip` and merged by timestamp with `heapq.merge`, which holds one
record per segment rather than sorting the corpus — the box has 4 GB
and the disk sits at 86%. Because the merge emits in timestamp order,
duplicates from an overlapping segment arrive adjacent, so the dedup
set only ever holds the records sharing the current timestamp. Dedup
keys on request identity (ts, IP, method, URI, status, size), not on
the raw line: a byte compare would let a genuine duplicate through on
header reordering.

**A bad segment is never fatal and never silent.** A truncated or
corrupt `.gz` raises mid-iteration; whatever was read before the error
is kept, the segment is named in the summary and logged at WARNING,
and the remaining segments still get read.

**Coverage is reported, never asserted.** The summary states the
interval actually covered, first and last timestamp, and how many
segments were read of how many were found:

```
Informe GoAccess generat: /var/cache/topquaranta/goaccess/report.html
  cobertura real: 2026-07-26 10:12:32 UTC → 2026-07-31 12:20:54 UTC (122.1 h)
  segments llegits: 6/6 (5 rotats + 1 viu)
  línies: 32819 vàlides, 0 omeses, 0 duplicades descartades
```

The same interval becomes the HTML report title
(`--html-report-title`), replacing the `--days` label — those two
diverge whenever rotation has eaten the tail, and the label is exactly
what misled us. A short interval is therefore **visible**, but it does
not fail the command: how much coverage is acceptable is an operator
decision, not the reader's.

**Flags:** `--days` (default 30), `--log-dir` (tests point it at a
fixture corpus), `--dry-run` (measures coverage, writes nothing —
useful for checking the corpus without clobbering the good report).

**Retention is by size, not by time.** With `roll_size 10MiB` and
`roll_keep 5` and no `roll_keep_for`, the ceiling on disk is ~60 MiB,
so the days that fit depend entirely on traffic: ~6.7 days at the
observed 0.37 MiB/h baseline, but ~13 h under a crawler sweep (a
ClaudeBot pass on 2026-07-30 burned a full 10 MiB segment in 2 h 11).

**ACLs on the rotated files.** The `default:` ACL on `/var/log/caddy`
(`default:user:topquaranta:r--`) is what makes reading the rotated
segments possible at all: every `.log.gz` Caddy creates inherits read
access, so no per-file `setfacl` is needed after each rotation.
Verified 2026-07-31 against the oldest and newest segment on the box.
