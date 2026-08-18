"""Ops incidents feed for the weekly digest — errors + stuck crons.

The Setmanari has to answer "did anything break this week?", and the
answer lives on the box rather than in the DB:

  * `/var/log/topquaranta/errors.log` — every ERROR/CRITICAL record of
    the project (the `errors_file` handler in `settings/base.py`).
    Rotated weekly with `delaycompress`, so the previous segment is
    still plain text: we read `errors.log.1` + `errors.log` to cover a
    window that straddles a rotation.
  * `/var/log/topquaranta/status/*.status` — the per-cron tags written
    by `tq-run`. Classification is delegated to
    `health_report.gather_crons`, the very code `tq-health` runs every
    hour, so the weekly digest and the hourly watchdog can never
    disagree about what counts as an anomaly.

Everything is best-effort: a missing file, an unreadable directory or a
malformed line yields an empty result instead of an exception. The
digest must go out even when the filesystem isn't the production one
(tests, CI, a laptop).

# Spec: docs/architecture/analytics.md
"""

from __future__ import annotations

import datetime
import json
import re
from collections import Counter
from pathlib import Path

from django.conf import settings

from analytics.health_report import gather_crons

LOG_DIR = Path("/var/log/topquaranta")
STATUS_DIR = LOG_DIR / "status"

# `[2026-08-07 04:12:33,918] ERROR ingesta.deezer: message…` — the
# `verbose` formatter of settings/base.py. Traceback continuation lines
# don't match and are skipped: one incident, one line.
_LINE = re.compile(
    r"^\[(?P<data>\d{4}-\d{2}-\d{2})[^\]]*\]\s+"
    r"(?P<level>[A-Z]+)\s+(?P<logger>\S+):\s*(?P<msg>.*)$"
)

# Cap on distinct error groups surfaced; the rest is a "+N més" tail.
MAX_GRUPS = 5


def _lines(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            yield from fh
    except OSError:
        return


def _signatura(msg: str) -> str:
    """Collapse the varying parts of a message so repeats group.

    Numbers (ids, status codes, counts) and quoted names are the usual
    difference between two instances of the same failure, so they're
    masked before grouping. Truncated because the tail of a long
    message is rarely what distinguishes it.
    """
    return re.sub(r"\d+", "#", msg).strip()[:90]


def django_errors(
    since: datetime.date, until: datetime.date, *, log_dir: Path | None = None
) -> dict:
    """ERROR/CRITICAL records logged between `since` and `until`.

    Returns per-day counts (every day of the window, zeros included, so
    the digest can draw a flat sparkline) plus the most frequent
    distinct messages.  `disponible` distinguishes "no errors" from "no
    log file to read", which are very different pieces of news.
    """
    log_dir = log_dir or LOG_DIR
    per_dia: Counter[datetime.date] = Counter()
    grups: Counter[tuple[str, str]] = Counter()
    exemples: dict[tuple[str, str], str] = {}
    disponible = False

    for name in ("errors.log.1", "errors.log"):
        path = log_dir / name
        if not path.is_file():
            continue
        disponible = True
        for line in _lines(path):
            m = _LINE.match(line)
            if m is None:
                continue
            try:
                dia = datetime.date.fromisoformat(m["data"])
            except ValueError:
                continue
            if not (since <= dia <= until):
                continue
            per_dia[dia] += 1
            key = (m["logger"], _signatura(m["msg"]))
            grups[key] += 1
            exemples.setdefault(key, m["msg"].strip()[:160])

    dies = [since + datetime.timedelta(days=i) for i in range((until - since).days + 1)]
    return {
        "disponible": disponible,
        "total": sum(per_dia.values()),
        # One entry per day of the window, zeros included: "res dimarts,
        # 9 dijous" is the shape of the week the operator needs to see.
        "per_dia": [{"data": d, "count": per_dia.get(d, 0)} for d in dies],
        "top": [
            {"logger": logger, "msg": exemples[(logger, sig)], "count": n}
            for (logger, sig), n in grups.most_common(MAX_GRUPS)
        ],
        "altres": max(0, len(grups) - MAX_GRUPS),
    }


def _cron_meta(path: Path | None = None) -> dict:
    path = path or Path(settings.BASE_DIR) / "deploy" / "cron-meta.json"
    try:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def cron_anomalies(
    now_ts: int, *, status_dir: Path | None = None, meta_path: Path | None = None
) -> list[dict]:
    """Crons currently in a bad state (STALE / STUCK / FAIL / ORPHAN…).

    A point-in-time read: `tq-run` keeps only the last outcome per cron,
    so this is "what is broken right now", not "what broke on Tuesday
    and recovered". Silenced crons are kept (flagged) — the weekly
    report is exactly where a knowingly-muted failure should resurface.
    """
    status_dir = status_dir or STATUS_DIR
    meta = _cron_meta(meta_path)
    if not meta or not status_dir.is_dir():
        return []
    return [c for c in gather_crons(status_dir, meta, now_ts) if c.get("is_anomaly")]
