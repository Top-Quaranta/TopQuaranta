# Data retention policy

What we keep, for how long, and why.

## Principle

The **ranking is the cultural artifact** — once a weekly top 40 is
published, it belongs to the historical record and stays forever.

The **signal data is transient raw material** — necessary to compute
this week's ranking, useless for reproducing a 3-year-old one once
the ranking itself is archived. After a reasonable window we archive
the raw rows to compressed files and drop them from the live DB.

Audit logs are **sacred**: nothing in an append-only audit log is
ever deleted.

## The tables

| Table | Retention in the live DB | Archived? | Notes |
|---|---|---|---|
| `ranking_rankingsetmanal` | **Forever** | — | The cultural artifact. R1 stores `algorithm_version` + `config_snapshot` so each row is self-describing. |
| `ranking_rankingprovisional` | Rolling (truncated + rebuilt daily) | — | Already ephemeral by design. |
| `ranking_senyaldiari` | **Last 2 years** | Older rows → CSV.gz at `/home/topquaranta/archive/senyal-YYYY.csv.gz`, then deleted from DB. | ~1,200 rows/day. At 10 years unchecked, 4.4M rows. Policy keeps DB size bounded. |
| `music_historialrevisio` | **Forever** | — | Staff revision decisions. Feeds the ML classifier + satisfies the audit obligation in `docs/product/definition.md` §Governance. |
| `music_staffauditlog` | **Forever** | — | R9: immutable log of destructive staff actions. See Φ4 public history at `/com-funciona/historial/` for the anonymized excerpt. |
| `music_canco`, `music_artista`, `music_album` | **Forever** | — | Domain objects. Deletion happens only on explicit staff action (cascade / SET_NULL per R2). |
| `music_artistadeezer`, `music_artistalocalitat` | With their parent `Artista`. | — | R10, R11: sole sources of truth. |
| `django_session` | Django defaults (`SESSION_COOKIE_AGE` = 2 weeks). | — | Nothing to do — Django clears expired sessions at login. |
| `axes_accessattempt`, `axes_accessfailurelog` | 6 months. | — | S4: brute-force logs. Keep enough history to detect patterns, not enough to create a privacy surface. Clear via `manage.py axes_reset_logs --age=180`. |
| `django_cache` | Managed by Django + TTL per entry. | — | S9 throttles + any future durable cache items. |
| `comptes_propostaartista` | **Forever** | — | A proposal's lifecycle is review → approve or reject → link to the created Artista. Archive is part of the audit trail. |
| `comptes_userartista` | **Forever** | — | Artist–user verification links. Rare and small volume. |

## The mechanics

Retention runs via `manage.py arxivar_senyal_vell`, scheduled quarterly
(1st of January / April / July / October at 05:00). The command:

1. Picks every `SenyalDiari` with `data < today − 730 days` (2 years).
2. Exports them to `/home/topquaranta/archive/senyal-YYYY.csv.gz`
   (partitioned by the calendar year of `data`). The CSV columns
   mirror the table exactly so the archive is a faithful snapshot.
3. After the gzip file is written and `fsync`ed, deletes the rows
   from the live DB inside `transaction.atomic()` — so a crash
   mid-archive leaves the rows in place rather than losing them.
4. Writes a status file at
   `/var/log/topquaranta/status/arxivar_senyal_vell.status` (same
   key=value format as `tq-run`) so `tq-health` surfaces failures.

Archive directory:

```
/home/topquaranta/archive/
├── senyal-2023.csv.gz   # ingested after 2026-01-01, covers 2023 rows
├── senyal-2024.csv.gz   # ingested after 2027-01-01, covers 2024 rows
└── ...
```

Each archive file is included in the daily backup (R14: `tq-backup`)
as long as it lives on the same disk. Moving archives to offsite
storage is part of Category O7 (offsite backups), not in scope here.

## How to restore an archived row

An archived row is **reproducible but not instantly queryable**:

```bash
gunzip -c /home/topquaranta/archive/senyal-2023.csv.gz \
    | grep '"canco_id": 12345' \
    | head
```

For bulk restore (e.g. an academic researcher asking for the 2023
signal):

```bash
gunzip -c /home/topquaranta/archive/senyal-2023.csv.gz \
    | psql -d topquaranta -c "COPY ranking_senyaldiari FROM STDIN CSV HEADER"
```

We accept that this is slow. The archive is cold storage by design.

## Why 2 years for `SenyalDiari`

Rationale:

- **1 year** is too short: we want "last week vs. same week last year"
  comparisons available to staff without a restore.
- **3+ years** keeps raw signal that nobody queries — the relevant
  signal has already flowed into `RankingSetmanal`.
- **2 years** is the conservative middle: supports year-over-year
  views and gives us a generous buffer for any "oh wait we need to
  recompute" emergency.

The threshold can be adjusted in `ingesta/management/commands/
arxivar_senyal_vell.py` if future practice shows we need differently.
Changing the policy is a documented action (CHANGELOG entry under
`### Changed`).

## GDPR / privacy note

TopQuaranta does not store personally identifiable information in
`SenyalDiari` — each row is "for track T on day D, Last.fm reported
playcount P and listeners L". No user is linked to these rows. This
retention policy is therefore about **keeping the DB small and the
backups cheap**, not about GDPR "right to be forgotten".

User account data lives in `comptes_usuari`, with its own deletion
path (account deletion request → hard delete; existing CASCADE on
UserArtista/PropostaArtista rows; StaffAuditLog references the user
by snapshot rather than FK).

## Backups (2026-07-05 — PII split)

The DB now carries community PII (profiles, DMs), so backup retention
is split by content. Decided by Miquel 2026-07-05; implemented in
`bin/tq-backup` + `bin/tq-backup-offsite` and mirrored offsite
(`docs/ops/backup-offsite.md`).

| Series | Contents | Where | Retention |
|---|---|---|---|
| `daily/tq-*` | full dump (with PII) | local + offsite tag `pii` | 7 days local; ≤90 days offsite |
| `weekly/tq-week-*` | full dump (with PII) | local | 30 days |
| `monthly/tq-month-pii-*` | full dump (with PII) | local | **90 days** |
| `monthly-safe/tq-month-safe-*` | sanitized dump — full schema, DATA of PII tables excluded | local + offsite tag `safe` | **12 months** |
| `.env` + `data/` | secrets, ad-hoc CSVs | offsite tag `pii` | ≤90 days |
| portades | cover images (no PII) | offsite tag `safe` | 12 months |

**Rule: no dump containing personal data outlives 90 days**, local or
offsite. The 12-month series is the sanitized dump: `--exclude-table-data`
on all of `comptes_*`, `auth_user*` (the custom user model keeps the
legacy table name), `music_staffauditlog`, `music_artistalastfmalias`
and `social_*auth` (channel tokens), plus `django_session` / `axes_*` /
`otp_*` / `django_admin_log`. The exclusion set is CI-guarded:
`topquaranta/tests/test_backup_offsite.py` fails when a new model with
a user FK is not covered.

Offsite retention is enforced **from the Mac** (quarterly
`restic forget --tag pii --keep-within 90d` + prune with the privileged
key) because the server-side B2 key is append-only and cannot delete.

**Legacy full monthlies** (`monthly/tq-month-2*.sql.gz`, created before
the split — currently May/June/July 2026) contain PII but keep their
original 365-day window: the 90-day policy applies forward only, and
deleting them earlier requires Miquel's explicit OK.

**GDPR consequence, stated plainly**: a deleted account persists in
full dumps for up to 90 days after deletion (backup exemption with a
declared maximum, standard practice); it never enters the 12-month
series. Offsite copies are restic-encrypted at origin — Backblaze only
ever stores ciphertext, which also covers the extra-EU transfer nuance.
