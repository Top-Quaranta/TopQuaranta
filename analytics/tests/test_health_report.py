"""Tests for the health-report renderer + the Premium cache-hit fix.

The renderer is pure stdlib (no Django), so these run without a DB.

# Spec: docs/architecture/pipeline.md
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

from analytics import health_report as hr

UTC = dt.timezone.utc
_BASE = dt.datetime(2026, 5, 30, 6, 15, tzinfo=UTC)
NOW = int(_BASE.timestamp())


def _iso(hours_ago: float) -> str:
    return (_BASE - dt.timedelta(hours=hours_ago)).isoformat()


def _c(**kw):
    defaults = dict(
        name="x",
        status="OK",
        last_run_iso=_iso(1),
        max_age_h=2,
        skips=0,
        fails=0,
        silenced=False,
        now_ts=NOW,
    )
    defaults.update(kw)
    return hr.classify_cron(**defaults)


# ── classify_cron ────────────────────────────────────────────────────


def test_classify_ok():
    r = _c(status="OK", last_run_iso=_iso(1), max_age_h=2)
    assert r["state"] == "OK"
    assert not r["escalates"] and not r["is_anomaly"]
    assert r["display"].startswith("OK(")


def test_classify_stale_escalates():
    r = _c(status="OK", last_run_iso=_iso(40), max_age_h=26)
    assert r["state"] == "STALE"
    assert r["escalates"] and r["is_anomaly"]


def test_classify_stale_silenced_does_not_escalate():
    r = _c(status="OK", last_run_iso=_iso(40), max_age_h=26, silenced=True)
    assert r["state"] == "STALE"
    assert not r["escalates"]  # silenced: known/expected, no email
    assert "[silenced]" in r["display"]


def test_classify_stuck_lock():
    r = _c(status="SKIPPED_BY_LOCK", last_run_iso=_iso(40), max_age_h=26, skips=5)
    assert r["state"] == "STUCK"
    assert "5skips" in r["display"] and r["escalates"]


def test_classify_skip_within_threshold():
    r = _c(status="SKIPPED_BY_LOCK", last_run_iso=_iso(1), max_age_h=26, skips=2)
    assert r["state"] == "SKIP" and not r["escalates"]


def test_classify_fail():
    r = _c(status="ERROR", last_run_iso=_iso(1), max_age_h=26)
    assert r["state"] == "FAIL" and r["escalates"]


def test_classify_waiting_infrequent_is_benign():
    # A weekly/monthly cron with no status file yet: genuinely awaiting
    # its first run → benign WAITING, never escalates.
    r = _c(status=None, max_age_h=170)
    assert r["state"] == "WAITING" and not r["escalates"]
    assert not r["is_anomaly"]


def test_classify_missing_frequent_escalates():
    # A frequent cron (max_age within the escalate threshold) with no
    # status file at all: the tag was never written → MISSING, escalates.
    r = _c(status=None, max_age_h=2)
    assert r["state"] == "MISSING"
    assert r["escalates"] and r["is_anomaly"]


def test_classify_missing_frequent_silenced_does_not_escalate():
    r = _c(status=None, max_age_h=2, silenced=True)
    assert r["state"] == "MISSING"
    assert not r["escalates"]  # silenced: surfaced but no email
    assert r["is_anomaly"]


def test_classify_missing_threshold_boundary():
    # Exactly at the threshold is still "frequent" → MISSING; just over
    # it flips to benign WAITING.
    assert (
        _c(status=None, max_age_h=hr.WAITING_ESCALATE_MAX_AGE_H)["state"] == "MISSING"
    )
    assert (
        _c(status=None, max_age_h=hr.WAITING_ESCALATE_MAX_AGE_H + 1)["state"]
        == "WAITING"
    )


def test_classify_watchdog_crit_escalates_even_silenced():
    r = _c(status="OK", last_run_iso=_iso(1), max_age_h=26, skips=10, silenced=True)
    assert r["escalates"]
    assert "watchdog CRIT" in r["display"]


# ── gather_crons: orphan + missing surfacing ─────────────────────────


def _write_status(path: Path, *, status="OK", last_run_iso=None):
    last_run_iso = last_run_iso or _iso(1)
    path.write_text(
        "command=x\n"
        "args=\n"
        f"last_run={last_run_iso}\n"
        "exit_code=0\n"
        f"status={status}\n"
        "consecutive_skips=0\n"
        "consecutive_failures=0\n"
    )


def test_gather_surfaces_orphan_status_file(tmp_path):
    # A *.status file with no cron-meta entry must surface as ORPHAN
    # (escalating) instead of being silently ignored.
    _write_status(tmp_path / "obtenir_novetats.status")
    _write_status(tmp_path / "backfill_album_source.status")
    meta = {"obtenir_novetats": {"max_age_hours": 2, "skip_concern": 3}}
    rows = hr.gather_crons(tmp_path, meta, NOW)
    by_name = {r["name"]: r for r in rows}
    assert by_name["obtenir_novetats"]["state"] == "OK"
    assert "backfill_album_source" in by_name
    orphan = by_name["backfill_album_source"]
    assert orphan["state"] == "ORPHAN"
    assert orphan["escalates"] and orphan["is_anomaly"]


def test_gather_no_orphans_when_all_registered(tmp_path):
    _write_status(tmp_path / "obtenir_novetats.status")
    meta = {"obtenir_novetats": {"max_age_hours": 2, "skip_concern": 3}}
    rows = hr.gather_crons(tmp_path, meta, NOW)
    assert all(r["state"] != "ORPHAN" for r in rows)


def test_gather_missing_frequent_cron(tmp_path):
    # Frequent cron declared in meta but no status file → MISSING.
    meta = {"obtenir_novetats": {"max_age_hours": 2, "skip_concern": 3}}
    rows = hr.gather_crons(tmp_path, meta, NOW)
    assert rows[0]["state"] == "MISSING" and rows[0]["escalates"]


def test_gather_ignores_non_status_files(tmp_path):
    # .recover and .controller.json files are not cron tags.
    (tmp_path / "calcular_top.recover").write_text("date=2026-05-30\nattempts=1\n")
    (tmp_path / "enriquir_spotify_rebuigs.controller.json").write_text("{}\n")
    meta = {"calcular_top": {"max_age_hours": 170, "skip_concern": 1}}
    rows = hr.gather_crons(tmp_path, meta, NOW)
    assert all(r["state"] != "ORPHAN" for r in rows)


# ── render ───────────────────────────────────────────────────────────


def _all_ok_extras():
    return {
        "disk": {"used_pct": 42, "avail": "12G"},
        "web": [{"label": "Web SPA shell", "ok": True, "detail": "OK"}],
        "spotify": {
            "premium": {"severity": "OK", "message": "Premium OK", "ok": True},
            "coverage": {"severity": "OK", "message": "coverage fine", "ok": True},
        },
        "migrations_ok": True,
        "errors": {"count": 0, "last": []},
    }


def test_render_all_ok_header_and_legend():
    crons = [
        _c(name="obtenir_novetats", status="OK", last_run_iso=_iso(0), max_age_h=2)
    ]
    text, overall = hr.render(crons, _all_ok_extras(), NOW)
    assert overall == 0
    assert text.splitlines()[0].startswith("🟢 Tot OK")
    assert "LLEGENDA" in text
    assert "Ingesta i metadata" in text  # group header present
    assert "CEST" in text  # timestamps localised


def test_render_mixed_anomalies_header_and_section():
    crons = [
        _c(name="obtenir_novetats", status="OK", last_run_iso=_iso(0), max_age_h=2),
        _c(
            name="enriquir_spotify_rebuigs",
            status="OK",
            last_run_iso=_iso(40),
            max_age_h=26,
        ),  # STALE → escalates
        _c(name="calcular_top", status=None),  # WAITING
    ]
    extras = _all_ok_extras()
    extras["spotify"]["coverage"] = {
        "severity": "CRIT",
        "message": "no-verif coverage low",
        "ok": False,
    }
    text, overall = hr.render(crons, extras, NOW)
    assert overall == 1
    assert text.splitlines()[0].startswith("🔴")
    assert "ANOMALIES" in text
    assert "enriquir_spotify_rebuigs" in text
    assert "STALE" in text
    # The CRIT coverage is reflected in the executive summary / system.
    assert "coverage" in text.lower()


def test_render_disk_alert_escalates():
    extras = _all_ok_extras()
    extras["disk"] = {"used_pct": 95, "avail": "1G"}
    text, overall = hr.render([_c(name="x")], extras, NOW)
    assert overall == 1
    assert "Disc: 95%" in text


def test_render_git_drift_escalates_and_emits_drift_token():
    extras = _all_ok_extras()
    extras["git"] = {"ok": False, "detail": "DRIFT — 2 fitxer(s) out-of-band"}
    text, overall = hr.render([_c(name="x")], extras, NOW)
    assert overall == 1
    # "DRIFT" must appear so tq-health's email grep (STALE|STUCK|FAIL|DRIFT)
    # picks it up, and it must surface in the anomalies + SISTEMA sections.
    assert "DRIFT" in text
    assert "Git tree DRIFT" in text


def test_render_git_clean_is_ok():
    extras = _all_ok_extras()
    extras["git"] = {"ok": True, "detail": "OK (matches origin/main, clean)"}
    text, overall = hr.render([_c(name="x")], extras, NOW)
    assert overall == 0
    assert "Git tree: OK" in text


def test_render_git_absent_defaults_ok():
    # No "git" key (dev/CI/older tq-health) → treated as OK, no escalation.
    text, overall = hr.render([_c(name="x")], _all_ok_extras(), NOW)
    assert overall == 0
    assert "Git tree:" in text


def test_render_silenced_stale_not_red_header():
    crons = [
        _c(
            name="actualitzar_playlists_spotify",
            status="FAIL",
            last_run_iso=_iso(40),
            max_age_h=4,
            silenced=True,
        )
    ]
    text, overall = hr.render(crons, _all_ok_extras(), NOW)
    # Silenced failure: visible in its group with [silenced] but does
    # NOT flip the header / overall.
    assert overall == 0
    assert text.splitlines()[0].startswith("🟢")
    assert "[silenced]" in text


# ── relative_age / cest ──────────────────────────────────────────────


def test_relative_age():
    assert hr.relative_age(0) == "fa 0h"
    assert hr.relative_age(5) == "fa 5h"
    assert hr.relative_age(50) == "fa 2d 2h"


def test_cest_label_today_yesterday():
    assert "avui" in hr.cest_label(_iso(1), NOW)
    assert "ahir" in hr.cest_label(_iso(28), NOW)


# ── Premium cache-hit fix: emits valid JSON, no " (cached …)" suffix ──


def test_premium_cache_hit_emits_valid_json(tmp_path):
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "health"
        / "spotify_premium_active.sh"
    )
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    payload = {
        "severity": "OK",
        "message": "Premium OK for 31abc (product=premium)",
        "payload": {"product": "premium"},
    }
    # Cache line format: "EXITCODE\tMESSAGE_JSON" (fresh mtime → hit).
    (cache_dir / "spotify_premium.cache").write_text(f"0\t{json.dumps(payload)}\n")
    out = subprocess.run(
        ["bash", str(script)],
        env={**os.environ, "TQ_HEALTH_CACHE_DIR": str(cache_dir)},
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0
    line = out.stdout.strip().splitlines()[-1]
    # Must parse cleanly (the bug appended " (cached Xs ago)" → broke this).
    parsed = json.loads(line)
    assert parsed["message"] == payload["message"]
    assert "cache_age_seconds" in parsed
    assert "(cached" not in line


# ── anomaly_signature (stable dedup key, 2026-06-07) ───────────────


def _extras(**kw):
    base = {
        "disk": {"used_pct": 50},
        "web": [{"label": "Web SPA shell", "ok": True}],
        "spotify": {"premium": {"ok": True}, "coverage": {"ok": True}},
        "migrations_ok": True,
        "errors": {"count": 0},
        "git": {"ok": True},
    }
    base.update(kw)
    return base


def test_signature_ignores_age_and_error_count():
    """Same anomaly set, only age + (present) error count differ → same key."""
    a1 = _c(name="whisper", status="FAIL", last_run_iso=_iso(1), max_age_h=48)
    a2 = _c(name="whisper", status="FAIL", last_run_iso=_iso(20), max_age_h=48)
    assert hr.anomaly_signature([a1], _extras(errors={"count": 5})) == (
        hr.anomaly_signature([a2], _extras(errors={"count": 99}))
    )


def test_signature_stale_hours_do_not_change_it():
    s1 = _c(name="senyal", status="OK", last_run_iso=_iso(40), max_age_h=26)
    s2 = _c(name="senyal", status="OK", last_run_iso=_iso(300), max_age_h=26)
    assert s1["state"] == "STALE" and s2["state"] == "STALE"
    assert hr.anomaly_signature([s1], _extras()) == hr.anomaly_signature(
        [s2], _extras()
    )


def test_signature_changes_on_new_anomaly():
    a = _c(name="whisper", status="FAIL", last_run_iso=_iso(1), max_age_h=48)
    b = _c(name="senyal", status="FAIL", last_run_iso=_iso(1), max_age_h=26)
    assert hr.anomaly_signature([a], _extras()) != hr.anomaly_signature(
        [a, b], _extras()
    )


def test_signature_changes_on_threshold_crossing():
    a = _c(name="whisper", status="FAIL", last_run_iso=_iso(1), max_age_h=48)
    base = hr.anomaly_signature([a], _extras(errors={"count": 0}))
    assert base != hr.anomaly_signature([a], _extras(errors={"count": 1}))
    assert base != hr.anomaly_signature([a], _extras(disk={"used_pct": 92}))
    assert base != hr.anomaly_signature([a], _extras(git={"ok": False}))


def test_signature_excludes_silenced_nonescalating():
    sil = _c(name="x", status="FAIL", last_run_iso=_iso(1), max_age_h=48, silenced=True)
    esc = _c(name="y", status="FAIL", last_run_iso=_iso(1), max_age_h=48)
    assert not sil["escalates"]
    assert hr.anomaly_signature([esc, sil], _extras()) == (
        hr.anomaly_signature([esc], _extras())
    )


def test_print_signature_cli(tmp_path):
    """The `--print-signature` mode tq-health calls prints a 64-hex
    signature (not the report) and still exits with `overall`."""
    status_dir = tmp_path / "status"
    status_dir.mkdir()
    (status_dir / "whisper.status").write_text(
        "command=whisper\nlast_run=2026-05-30T00:00:00+00:00\nstatus=FAIL\n"
        "consecutive_failures=1\n"
    )
    meta = tmp_path / "cron-meta.json"
    meta.write_text(json.dumps({"whisper": {"max_age_hours": 48, "skip_concern": 1}}))
    root = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        [
            "python3",
            "-m",
            "analytics.health_report",
            "--status-dir",
            str(status_dir),
            "--meta-file",
            str(meta),
            "--extras-json",
            "{}",
            "--now",
            str(NOW),
            "--print-signature",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    sig = out.stdout.strip()
    assert out.returncode == 1  # one FAILing cron → overall anomaly
    assert len(sig) == 64 and all(ch in "0123456789abcdef" for ch in sig)
