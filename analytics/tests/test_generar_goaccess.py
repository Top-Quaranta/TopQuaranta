"""generar_goaccess — the corpus it reads, and the corpus it must not.

Caddy rotates the TopQuaranta access log at 10 MiB keeping 5 segments,
so most history on disk lives in `topquaranta_access-<ts>.log.gz`. The
command used to read only the live file and reported success without
saying what interval that covered; on 2026-07-30 that was 1 h 32 min of
a nominal 30 days.

Every test runs the real command against a tmpdir corpus via
`--log-dir`, in `--dry-run` so nothing is written and goaccess is never
invoked.

# Spec: docs/architecture/analytics-goaccess.md
"""

from __future__ import annotations

import datetime
import gzip
import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from analytics.management.commands.generar_goaccess import (
    ROTATED_RE,
    _segment_files,
)

NOW = datetime.datetime.now(tz=datetime.timezone.utc)


def _rec(offset_hours: float, uri: str = "/top", ip: str = "1.2.3.4") -> dict:
    ts = (NOW - datetime.timedelta(hours=offset_hours)).timestamp()
    return {
        "ts": ts,
        "status": 200,
        "size": 1234,
        "duration": 0.001,
        "request": {
            "remote_ip": ip,
            "method": "GET",
            "uri": uri,
            "proto": "HTTP/2.0",
            "headers": {"User-Agent": ["curl/8.7.1"], "Referer": ["-"]},
        },
    }


def _write(path: Path, records: list[dict], gz: bool = False) -> None:
    body = "".join(json.dumps(r) + "\n" for r in records)
    if gz:
        with gzip.open(path, "wt") as fh:
            fh.write(body)
    else:
        path.write_text(body)


def _run(log_dir: Path, **kw) -> str:
    out = StringIO()
    call_command(
        "generar_goaccess",
        log_dir=str(log_dir),
        dry_run=True,
        stdout=out,
        **kw,
    )
    return out.getvalue()


def _lines_count(output: str) -> int:
    for line in output.splitlines():
        if "línies:" in line:
            return int(line.split("línies:")[1].strip().split()[0])
    raise AssertionError(f"no trobe el recompte a:\n{output}")


# ── corpus shapes ────────────────────────────────────────────────────


def test_live_file_only(tmp_path):
    """A corpus that is just the live file: every record is read.

    Property asserted: the line count — not the summary's segment copy.
    """
    _write(tmp_path / "topquaranta_access.log", [_rec(1), _rec(2), _rec(3)])
    out = _run(tmp_path)
    assert _lines_count(out) == 3


def test_live_plus_rotated_reads_the_whole_corpus(tmp_path):
    """The regression: rotated segments used to be invisible."""
    _write(
        tmp_path / "topquaranta_access-2026-07-28T14-32-51.275.log.gz",
        [_rec(50), _rec(49)],
        gz=True,
    )
    _write(
        tmp_path / "topquaranta_access-2026-07-29T03-46-02.809.log.gz",
        [_rec(30), _rec(29), _rec(28)],
        gz=True,
    )
    _write(tmp_path / "topquaranta_access.log", [_rec(2), _rec(1)])
    out = _run(tmp_path)
    assert _lines_count(out) == 7
    assert "2 rotats + 1 viu" in out
    assert "segments llegits: 3/3" in out


def test_coverage_interval_is_reported_not_the_days_asked_for(tmp_path):
    """D4: the summary must state the interval actually covered."""
    _write(tmp_path / "topquaranta_access.log", [_rec(3), _rec(1)])
    out = _run(tmp_path, days=30)
    assert "cobertura real:" in out
    first = (NOW - datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M")
    last = (NOW - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    assert first in out and last in out
    assert "(2.0 h)" in out


def test_records_older_than_cutoff_are_dropped(tmp_path):
    _write(tmp_path / "topquaranta_access.log", [_rec(24 * 40), _rec(1)])
    out = _run(tmp_path, days=30)
    assert _lines_count(out) == 1


# ── the glob ─────────────────────────────────────────────────────────


def test_glob_excludes_legacy_and_other_vhosts(tmp_path):
    """D2: only this vhost's rotated segments, nothing else."""
    _write(tmp_path / "topquaranta_access.log", [_rec(1)])
    _write(
        tmp_path / "topquaranta_access-2026-07-28T14-32-51.275.log.gz",
        [_rec(5)],
        gz=True,
    )
    # None of these may be read.
    _write(tmp_path / "topquaranta_legacy_access.log", [_rec(2)])
    _write(
        tmp_path / "topquaranta_legacy_access-2026-04-16T00-00-00.log.gz",
        [_rec(2)],
        gz=True,
    )
    _write(tmp_path / "access.log", [_rec(2)])
    _write(tmp_path / "cercol_api_access.log", [_rec(2)])
    _write(
        tmp_path / "cercol_api_access-2026-07-22T06-00-42.331.log.gz",
        [_rec(2)],
        gz=True,
    )
    # Near-misses on our own prefix (folded in from the old regex-only
    # test): a gz without the rotation stamp and a name that merely
    # contains ours.
    _write(tmp_path / "topquaranta_access.log.gz", [_rec(2)], gz=True)
    _write(
        tmp_path / "other_topquaranta_access-2026-07-28T14-32-51.275.log.gz",
        [_rec(2)],
        gz=True,
    )

    rotated, live = _segment_files(tmp_path)
    assert [p.name for p in rotated] == [
        "topquaranta_access-2026-07-28T14-32-51.275.log.gz"
    ]
    assert live.name == "topquaranta_access.log"

    out = _run(tmp_path)
    assert _lines_count(out) == 2, out
    assert "1 rotats + 1 viu" in out


# ── robustness ───────────────────────────────────────────────────────


def test_corrupt_gz_is_skipped_counted_and_named(tmp_path):
    """D3: never silent, never fatal."""
    _write(tmp_path / "topquaranta_access.log", [_rec(1), _rec(2)])
    bad = tmp_path / "topquaranta_access-2026-07-28T14-32-51.275.log.gz"
    bad.write_bytes(b"\x1f\x8b\x08\x00 not actually gzip at all")
    out = _run(tmp_path)
    # The good segment still made it.
    assert _lines_count(out) == 2, out
    assert "segments llegits: 1/2" in out
    assert "segments il·legibles: 1" in out
    assert bad.name in out


def test_truncated_gz_keeps_what_it_could_read(tmp_path):
    """A gz cut mid-stream: partial data survives, failure still named."""
    good = tmp_path / "topquaranta_access-2026-07-28T14-32-51.275.log.gz"
    _write(good, [_rec(10 + i) for i in range(50)], gz=True)
    raw = good.read_bytes()
    good.write_bytes(raw[: len(raw) // 2])
    _write(tmp_path / "topquaranta_access.log", [_rec(1)])
    out = _run(tmp_path)
    assert "segments il·legibles: 1" in out
    # Live file plus whatever survived the truncation.
    assert _lines_count(out) >= 1, out


def test_overlapping_segments_do_not_duplicate(tmp_path):
    """D3: same request present in two segments counts once."""
    shared = [_rec(5, uri="/artista/pavvla"), _rec(4, uri="/top")]
    _write(
        tmp_path / "topquaranta_access-2026-07-28T14-32-51.275.log.gz",
        [_rec(6)] + shared,
        gz=True,
    )
    _write(tmp_path / "topquaranta_access.log", shared + [_rec(1)])
    out = _run(tmp_path)
    # 6 records written, 2 of them duplicated → 4 unique.
    assert _lines_count(out) == 4, out
    assert "2 duplicades descartades" in out


def test_distinct_requests_sharing_a_timestamp_are_both_kept(tmp_path):
    """Dedup must key on the request, not on the timestamp alone."""
    a = _rec(3, uri="/top", ip="1.1.1.1")
    b = dict(a, request=dict(a["request"], uri="/mapa", remote_ip="2.2.2.2"))
    _write(tmp_path / "topquaranta_access.log", [a, b])
    out = _run(tmp_path)
    assert _lines_count(out) == 2, out
    assert "0 duplicades" in out


def test_malformed_json_lines_are_counted_as_skipped(tmp_path):
    path = tmp_path / "topquaranta_access.log"
    path.write_text(
        json.dumps(_rec(1)) + "\n" + "{not json\n" + "\n" + json.dumps(_rec(2)) + "\n"
    )
    out = _run(tmp_path)
    assert _lines_count(out) == 2
    assert "1 omeses" in out


def test_missing_log_dir_raises(tmp_path):
    with pytest.raises(CommandError, match="Caddy log dir not found"):
        _run(tmp_path / "nope")


def test_dir_without_any_topquaranta_segment_raises(tmp_path):
    _write(tmp_path / "cercol_api_access.log", [_rec(1)])
    with pytest.raises(CommandError, match="Cap segment"):
        _run(tmp_path)


def test_dry_run_writes_nothing(tmp_path):
    _write(tmp_path / "topquaranta_access.log", [_rec(1)])
    before = set(tmp_path.iterdir())
    out = _run(tmp_path)
    assert set(tmp_path.iterdir()) == before
    assert "DRY-RUN" in out
