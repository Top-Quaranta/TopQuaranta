# Stalwart served an expired TLS certificate — 2026-07-26

- **Date of incident:** 2026-06-26 (silent breakage) to 2026-07-27
  (fixed); user-visible from 2026-07-26 14:35 UTC
- **Severity:** high (all mail clients blocked; server-to-server
  delivery unaffected)
- **Author:** Miquel
- **Status:** Resolved 2026-07-27

## Impact

From 2026-07-26 14:35 UTC every mail client connecting to
`mail.topquaranta.cat` got a certificate error. Spark showed
"Security certificate issue" and offered *Trust without Certificate*
or *Delete Account*. This hit both `topquaranta.cat` and
`cercol.team` accounts, because both domains' MX point at the same
host and there is no separate `mail.cercol.team`.

**No inbound mail was lost.** Neither domain publishes MTA-STS or
TLSA/DANE records, so sending MTAs used opportunistic TLS and did
not validate the certificate. Port 25 kept accepting and delivering
throughout. The blast radius was interactive client access only —
which is also why nothing alerted.

## Timeline

- **2026-04-27 14:35** — Caddy issues the cert. Around 14:43 it is
  pasted into Stalwart's config during setup. Both facts are visible
  in the RocksDB file mtimes.
- **2026-04-27 18:17** — `stalwart-cert-sync.{path,service}` and
  `stalwart-cert-sync.sh` are created to automate future renewals.
- **2026-06-26 02:13** — Caddy renews the certificate normally.
- **2026-06-26 03:11** — The path unit fires. The script copies the
  new PEM to `/etc/stalwart/certs/` and restarts Stalwart. It
  reports success. Stalwart keeps serving the April certificate.
- **2026-07-02 13:56** — Full server reboot. Still the April
  certificate.
- **2026-07-26 14:35** — The certificate expires. Clients start
  failing.
- **2026-07-27 ~08:30** — Reported. Recon confirms disk holds a
  valid cert (serial `0504…5147`, expiring Sep 24) while ports 25,
  465, 993 and 995 serve an expired one (serial `069D…DC89`).
- **2026-07-27 09:40** — Root cause found via the JMAP admin API.
- **2026-07-27 09:43** — New cert written to the live config,
  Stalwart restarted, all ports verified.

## Root cause

**Stalwart 0.16 does not read its certificate from a file.** Its
configuration lives in RocksDB and the certificate is an inline
property of an `x:Certificate` object. The value in the live config
was a frozen PEM copy pasted in on 2026-04-27.

The `STALWART_CERTIFICATE_DEFAULT_CERT=%{file:…}%` entries in
`/etc/stalwart/stalwart.env` *are* loaded into the process
environment — confirmed by reading `/proc/<pid>/environ` — but that
macro syntax predates 0.16 and is never evaluated. So the sync
script was copying PEM files into a directory no code path reads,
and the restart it performed could not help: there was nothing new
to load.

The deeper failure is that the script's success signal was
disconnected from the outcome it was supposed to produce. It checked
that `install` and `systemctl restart` returned 0. It never checked
what certificate was actually being served. A green run and a broken
server were indistinguishable.

## Fix applied

Immediate: read the live `x:Certificate` object over JMAP, write
Caddy's current cert and key into it, restart Stalwart, verify the
serial on 993, 465 and 25. All three now serve `0504…5147`, valid
until 2026-09-24, with full chain validation.

Durable: `deploy/stalwart-cert-sync.sh` rewritten to push over JMAP
instead of copying files, and to verify on the wire. It now:

- compares Caddy's on-disk serial with the serial actually served on
  993 and does nothing (**no restart**) when they match;
- checks cert and key are a real pair before writing anything;
- finds the certificate object by SAN instead of a hardcoded id;
- confirms the live config took the value *before* restarting;
- re-checks 993, 465 and 25 afterwards and **exits non-zero if any
  port still serves the old serial**;
- logs to `/var/log/stalwart-cert-sync.log` with timestamps and
  size-based rotation, because journald on this host does not
  persist — the June evidence was already gone by the time anyone
  looked.

Mechanism documented in [`docs/ops/infra.md`](../ops/infra.md); the
wrong claim in [`docs/EMAIL.md`](../EMAIL.md) ("llegeix el cert de
fitxer") corrected.

## Prevention

The failure mode is **an automation whose success signal does not
observe the state it claims to produce**. The rule that catches it
is the health-check discipline in
[`docs/policies/conventions.md`](../policies/conventions.md): an ops
script must assert the externally observable outcome, not the exit
codes of the commands it ran, and its own exit code must reflect
that assertion.

- Policy: `docs/policies/conventions.md` — ops scripts verify the
  observable outcome
- Related: `docs/ops/infra.md` § Stalwart TLS

## Follow-up: the same shape, found in the deploy pipeline

Auditing this incident's failure shape — *a check that cannot tell
"nothing changed" from "I could not look"* — turned up the same defect
in `bin/tq-deploy` (fixed 2026-07-27, separate PR).

It detected what changed with `git diff --name-only A B | grep -q X`
**inside an `if` condition**, where `set -e` does not apply. A git
failure made the condition false, which reads as "that path did not
change": the deploy skipped the venv sync and the SPA build, printed
`✓ Deploy complete` and exited 0. Now computed once, up front, by
`bin/tq-changed-files`, which exits 7 when git cannot answer.

Two related findings from the same audit:

- `deploy.yml` carried `script_stop: true` and a comment promising that
  any non-zero exit fails the workflow. Reading `action.yml` at both
  tags with `gh api` establishes that `script_stop` **was** a valid
  input at `appleboy/ssh-action@v1.2.0` and is **absent** from v1.2.5;
  the Dependabot bump in #32 changed only the version line, so the
  parameter was dropped silently. v1.2.5 offers no replacement. The
  guarantee now lives in the script block itself (`set -e` + absolute
  path) rather than in an action input.
- `/home/topquaranta/bin/tq-deploy` exists and is a **symlink to the
  same repo file** (identical sha256, verified 2026-07-27), so the
  relative-path hazard from a failed `cd` was latent rather than live.

**What is still not established**, and is recorded here so nobody
assumes otherwise: whether a non-zero remote exit actually turns the
GitHub job red. v1.2.5's `action.yml` documents nothing about
exit-status propagation, and the `drone-ssh` binary it downloads has
not been read. A deploy that succeeded proves nothing about the failure
path.

## Lessons learned

Three things stand out.

**A restart that "works" proves nothing.** Two independent restarts
happened with the correct file on disk — the script's own on 26 June
and a full reboot on 2 July — and both left the server serving the
old certificate. If a restart is supposed to change observable
state, check the observable state.

**Monitoring gap.** Nothing watches certificate expiry on the mail
ports. Caddy emails on issuance failure, but this was not an
issuance failure: Caddy did its job perfectly every time. A probe
that opens TLS on 993 and alerts under ~14 days remaining would have
caught this a fortnight early. Out of scope for this PR; worth doing
before the next renewal around 25 August.

**Two side findings, not fixed here.** `autoconfig.topquaranta.cat`
has been failing ACME for 23 attempts (HTTP-01 returns 500), so
Thunderbird autoconfig does not work; and `legacy.topquaranta.cat`
expired on 14 July. Both are separate from this incident.
