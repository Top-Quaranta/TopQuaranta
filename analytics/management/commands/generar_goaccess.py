"""Generate the GoAccess HTML report from Caddy access logs.

Caddy writes JSON access logs for the TopQuaranta vhost at
`/var/log/caddy/topquaranta_access.log`. GoAccess supports JSON
natively, but the per-Caddy schema is verbose enough that pipelining
via a tiny Python pre-converter to Combined-Log-Format is more robust
across GoAccess versions than maintaining a custom JSON format string.

The output goes to `/var/cache/topquaranta/goaccess/report.html`,
which is served behind the staff-auth `/api/v1/staff/goaccess/`
endpoint. We never expose `/var/cache/...` to Caddy directly — the
Django proxy ensures only OTP-verified staff see it.

**The rotated segments count.** Caddy rotates the live file at 10 MiB
and keeps 5 (`roll_size`/`roll_keep` in `deploy/Caddyfile`), so most of
the history on disk lives in `topquaranta_access-<ts>.log.gz`. Reading
only the live file meant the report silently covered whatever slice
happened to be un-rotated: on 2026-07-30 that was 1 h 32 min and 4240
of 32746 available lines, reported as exit 0 under a "last 30 days"
label. Segments are streamed and merged chronologically here, and the
summary states the interval actually covered so a short one is visible
instead of implied.

Filtering: requests to `/api/`, `/static/`, `/assets/` are kept (we
want to see asset hot-paths in GoAccess), but the Django middleware
analytics layer ignores those — the two surfaces complement each
other instead of duplicating numbers.

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime
import gzip
import heapq
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

CADDY_LOG_DIR = Path("/var/log/caddy")
LIVE_LOG_NAME = "topquaranta_access.log"
REPORT_DIR = Path("/var/cache/topquaranta/goaccess")
REPORT_HTML = REPORT_DIR / "report.html"

# Rotated segments of the TopQuaranta vhost ONLY. Caddy names them
# `topquaranta_access-<RFC3339>.log.gz`. The anchored pattern is what
# keeps three neighbours in the same directory out of the report, each
# of which would silently poison the numbers:
#
#   topquaranta_legacy_access.log   pre-2026-04 vhost, a different site
#   access.log                      default-vhost dump, bare-IP probes
#   cercol_api_access[-<ts>].log.gz another project on the same box
#
# A looser glob (`topquaranta*access*.log.gz`) would swallow the legacy
# file. Enforced by test_glob_excludes_legacy_and_other_vhosts.
ROTATED_RE = re.compile(r"^topquaranta_access-[0-9TZ:.+-]+\.log\.gz$")


def _caddy_to_clf_line(rec: dict) -> str | None:
    """Convert one Caddy JSON access-log line to Combined Log Format.

    Combined Log Format (the format GoAccess understands by default):
      host ident authuser [date] "request" status size "referer" "ua"
    """
    req = rec.get("request") or {}
    ip = req.get("remote_ip") or req.get("client_ip") or "-"
    method = req.get("method") or "-"
    uri = req.get("uri") or "-"
    proto = req.get("proto") or "HTTP/1.1"
    status = rec.get("status") or 0
    size = rec.get("size") or 0
    headers = req.get("headers") or {}
    ua = (headers.get("User-Agent") or ["-"])[0]
    ref = (headers.get("Referer") or ["-"])[0]
    ts = rec.get("ts")
    if ts is None:
        return None
    try:
        dt = datetime.datetime.fromtimestamp(float(ts), tz=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None
    date_str = dt.strftime("%d/%b/%Y:%H:%M:%S +0000")
    request_str = f"{method} {uri} {proto}".replace('"', "'")
    ua = ua.replace('"', "'")
    ref = ref.replace('"', "'")
    return f'{ip} - - [{date_str}] "{request_str}" {status} {size} ' f'"{ref}" "{ua}"'


def _identity(rec: dict) -> tuple:
    """Key that makes two records the same request.

    Used only to drop duplicates where two segments overlap. Deliberately
    not the raw line: a byte-level compare (header ordering, a float that
    reserialises differently) would let a genuine duplicate through.
    """
    req = rec.get("request") or {}
    return (
        rec.get("ts"),
        req.get("remote_ip"),
        req.get("method"),
        req.get("uri"),
        rec.get("status"),
        rec.get("size"),
    )


def _segment_files(log_dir: Path) -> tuple[list[Path], Path | None]:
    """Return (rotated segments, live file or None).

    Caddy's rotated names carry an RFC3339 timestamp, so lexical order is
    chronological; sorting here only makes the run deterministic — the
    real ordering guarantee is the ts-keyed merge below.
    """
    rotated = sorted(
        (p for p in log_dir.glob("*.log.gz") if ROTATED_RE.match(p.name)),
        key=lambda p: p.name,
    )
    live = log_dir / LIVE_LOG_NAME
    return rotated, (live if live.exists() else None)


def _iter_records(path: Path, cutoff: float, stats: dict):
    """Stream (ts, rec) from one segment, oldest first.

    Line by line, never materialising the file: the box has 4 GB and a
    10 MiB segment gunzips to ~10 MiB of JSON, so holding six of them
    plus the report would be gratuitous.

    A truncated or corrupt `.gz` raises mid-iteration. Whatever was read
    before the error is kept, the segment is recorded in `stats` and the
    run continues — one bad segment must not cost us the other five, and
    it must not pass in silence either.
    """
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rt", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    stats["skipped"] += 1
                    continue
                try:
                    ts = float(rec.get("ts"))
                except (TypeError, ValueError):
                    stats["skipped"] += 1
                    continue
                if ts < cutoff:
                    continue
                yield (ts, rec)
    except (OSError, EOFError) as exc:
        # gzip.BadGzipFile subclasses OSError.
        stats["corrupt"].append(f"{path.name}: {type(exc).__name__} {exc}"[:120])


def _merged_records(paths: list[Path], cutoff: float, stats: dict):
    """Chronological merge across every segment, de-duplicated.

    `heapq.merge` keeps one record per segment in memory rather than
    sorting the corpus, and because it emits in ts order any pair of
    duplicates from an overlap arrives adjacent. So the dedup set only
    ever holds the records sharing the current timestamp — a handful —
    instead of the whole run.
    """
    streams = [_iter_records(p, cutoff, stats) for p in paths]
    current_ts = None
    seen_at_ts: set = set()
    for ts, rec in heapq.merge(*streams, key=lambda pair: pair[0]):
        if ts != current_ts:
            current_ts = ts
            seen_at_ts = set()
        ident = _identity(rec)
        if ident in seen_at_ts:
            stats["duplicates"] += 1
            continue
        seen_at_ts.add(ident)
        yield rec


class Command(BaseCommand):
    help = "Genera l'informe GoAccess sobre els logs de Caddy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Dies enrere a incloure (default 30).",
        )
        parser.add_argument(
            "--log-dir",
            default=str(CADDY_LOG_DIR),
            help=f"Directori dels logs de Caddy (default {CADDY_LOG_DIR}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mesura la cobertura i no escriu res (ni CLF ni informe).",
        )

    def handle(self, *args, **opts) -> None:
        log_dir = Path(opts["log_dir"])
        if not log_dir.is_dir():
            raise CommandError(f"Caddy log dir not found at {log_dir}")

        rotated, live = _segment_files(log_dir)
        paths = rotated + ([live] if live else [])
        if not paths:
            raise CommandError(f"Cap segment de topquaranta_access a {log_dir}")

        dry_run = opts["dry_run"]
        if not dry_run and shutil.which("goaccess") is None:
            raise CommandError("goaccess no està instal·lat (apt install goaccess).")

        days = max(1, int(opts["days"]))
        cutoff = (
            datetime.datetime.now(tz=datetime.timezone.utc)
            - datetime.timedelta(days=days)
        ).timestamp()

        stats: dict = {"skipped": 0, "corrupt": [], "duplicates": 0}
        counters: dict = {"ok": 0, "first": None, "last": None}

        def _consume(write) -> None:
            for rec in _merged_records(paths, cutoff, stats):
                line = _caddy_to_clf_line(rec)
                if line is None:
                    stats["skipped"] += 1
                    continue
                ts = float(rec["ts"])
                if counters["first"] is None:
                    counters["first"] = ts
                counters["last"] = ts
                if write is not None:
                    write(line + "\n")
                counters["ok"] += 1

        if dry_run:
            _consume(None)
            self.stdout.write(
                self.style.SUCCESS(
                    self._summary(counters, stats, paths, rotated, live, dry=True)
                )
            )
            return

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        # A file rather than piping to stdin so we can count lines for
        # the summary without consuming the iterator.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".clf", delete=False, dir=str(REPORT_DIR)
        ) as tmp:
            _consume(tmp.write)
            tmp_path = Path(tmp.name)

        if counters["ok"] == 0:
            tmp_path.unlink(missing_ok=True)
            raise CommandError("Cap línia vàlida; cancel·lo.")

        try:
            subprocess.run(
                [
                    "goaccess",
                    str(tmp_path),
                    "-o",
                    str(REPORT_HTML),
                    "--log-format=COMBINED",
                    "--no-progress",
                    # The title carries the interval the report ACTUALLY
                    # covers, not the --days that was asked for. Those two
                    # diverge whenever rotation has eaten the tail, and the
                    # label is what misled us on 2026-07-30.
                    "--html-report-title="
                    + self._interval(counters["first"], counters["last"]),
                    # Reasonable defaults for a behind-staff report.
                    "--ignore-crawlers",
                    "--anonymize-ip",
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            tmp_path.unlink(missing_ok=True)
            raise CommandError(
                f"goaccess falla: {exc.stderr.decode('utf-8', errors='replace')[:500]}"
            ) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        self.stdout.write(
            self.style.SUCCESS(self._summary(counters, stats, paths, rotated, live))
        )

    @staticmethod
    def _fmt(ts: float | None) -> str:
        if ts is None:
            return "?"
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

    @classmethod
    def _interval(cls, first_ts, last_ts) -> str:
        if first_ts is None or last_ts is None:
            return "TopQuaranta · cap dada"
        hours = (last_ts - first_ts) / 3600
        return (
            f"TopQuaranta · {cls._fmt(first_ts)} → {cls._fmt(last_ts)} "
            f"({hours:.1f} h)"
        )

    def _summary(self, counters, stats, paths, rotated, live, dry=False) -> str:
        first_ts, last_ts = counters["first"], counters["last"]
        hours = (last_ts - first_ts) / 3600 if first_ts and last_ts else 0.0
        head = (
            "DRY-RUN (res escrit)"
            if dry
            else f"Informe GoAccess generat: {REPORT_HTML}"
        )
        parts = [
            head,
            f"  cobertura real: {self._fmt(first_ts)} → {self._fmt(last_ts)} "
            f"({hours:.1f} h)",
            f"  segments llegits: {len(paths) - len(stats['corrupt'])}/{len(paths)} "
            f"({len(rotated)} rotats + {1 if live else 0} viu)",
            f"  línies: {counters['ok']} vàlides, {stats['skipped']} omeses, "
            f"{stats['duplicates']} duplicades descartades",
        ]
        if stats["corrupt"]:
            parts.append(f"  segments il·legibles: {len(stats['corrupt'])}")
            parts.extend(f"    ! {c}" for c in stats["corrupt"])
            logger.warning(
                "generar_goaccess: %d segment(s) il·legibles: %s",
                len(stats["corrupt"]),
                "; ".join(stats["corrupt"]),
            )
        return "\n".join(parts)
