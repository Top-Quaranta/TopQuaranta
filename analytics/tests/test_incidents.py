"""Tests for `analytics.incidents` — the ops feed behind the Setmanari."""

from __future__ import annotations

import datetime

from analytics import incidents

TODAY = datetime.date(2026, 8, 10)
SINCE = TODAY - datetime.timedelta(days=6)


def _write(log_dir, name, lines):
    (log_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_django_errors_groups_repeats_and_windows(tmp_path):
    _write(
        tmp_path,
        "errors.log",
        [
            # Same failure, different ids → one group of 2.
            "[2026-08-06 04:10:33,918] ERROR ingesta.deezer: Deezer 500 on artist 4821",
            "Traceback (most recent call last):",
            '  File "x.py", line 1, in <module>',
            "[2026-08-06 05:10:33,918] ERROR ingesta.deezer: Deezer 500 on artist 9134",
            "[2026-08-08 06:00:00,000] ERROR django.request: Internal Server Error: /x/",
            # Outside the window — must not be counted.
            "[2026-07-01 06:00:00,000] ERROR django.request: Internal Server Error: /y/",
        ],
    )

    out = incidents.django_errors(SINCE, TODAY, log_dir=tmp_path)

    assert out["disponible"] is True
    assert out["total"] == 3, "traceback lines and out-of-window rows must not count"
    assert [t["count"] for t in out["top"]] == [2, 1]
    assert out["top"][0]["logger"] == "ingesta.deezer"
    # Every day of the window is present, zeros included.
    assert len(out["per_dia"]) == 7
    assert {d["data"]: d["count"] for d in out["per_dia"]}[
        datetime.date(2026, 8, 6)
    ] == 2
    assert {d["data"]: d["count"] for d in out["per_dia"]}[
        datetime.date(2026, 8, 7)
    ] == 0


def test_django_errors_reads_across_a_rotation(tmp_path):
    """logrotate is weekly with delaycompress: the previous segment is
    still plain text and holds the start of the window."""
    _write(tmp_path, "errors.log.1", ["[2026-08-05 01:00:00,000] ERROR a.b: vell"])
    _write(tmp_path, "errors.log", ["[2026-08-09 01:00:00,000] ERROR a.b: nou"])

    out = incidents.django_errors(SINCE, TODAY, log_dir=tmp_path)

    assert out["total"] == 2


def test_django_errors_missing_file_is_not_zero_errors(tmp_path):
    """ "No log to read" and "no errors" are different news; the digest
    must be able to tell them apart."""
    out = incidents.django_errors(SINCE, TODAY, log_dir=tmp_path / "cap")

    # Property asserted: the file is reported as unavailable while the
    # error total stays 0 — nothing else about the payload's shape.
    assert out["disponible"] is False
    assert out["total"] == 0


def test_cron_anomalies_survives_a_missing_status_dir(tmp_path):
    assert incidents.cron_anomalies(0, status_dir=tmp_path / "cap") == []


def test_cron_anomalies_surfaces_a_failed_cron(tmp_path):
    status = tmp_path / "status"
    status.mkdir()
    (status / "obtenir_senyal.status").write_text(
        "status=FAIL\nlast_run=2026-08-10T04:00:00+00:00\nexit_code=1\n",
        encoding="utf-8",
    )
    meta = tmp_path / "cron-meta.json"
    meta.write_text(
        '{"_doc": "ignored", "obtenir_senyal": {"max_age_hours": 2}}', encoding="utf-8"
    )

    rows = incidents.cron_anomalies(
        int(datetime.datetime(2026, 8, 10, 6, tzinfo=datetime.UTC).timestamp()),
        status_dir=status,
        meta_path=meta,
    )

    assert [r["name"] for r in rows] == ["obtenir_senyal"]
    assert rows[0]["state"] == "FAIL"
