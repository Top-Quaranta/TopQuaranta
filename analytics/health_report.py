"""Human-readable renderer for the pipeline health report.

`bin/tq-health` gathers the raw facts (cron status files + cron-meta,
disk, web smoke, Spotify sub-checks, migrations, recent errors) and
delegates the PRESENTATION to this module: it classifies each cron,
groups them by logical area, converts timestamps to CEST, surfaces a
one-line executive summary + an Anomalies section, and prints a
legend so a first-time reader orients themselves.

Pure stdlib (no Django) so tq-health can run it on every hourly tick
without a Django setup. The cron-classification logic mirrors the old
inline bash exactly, so the exit code (`overall`: 0 ok / 1 anomalies)
— and therefore tq-health's email gate — is unchanged.

CLI:
    python3 analytics/health_report.py \
        --status-dir DIR --meta-file FILE \
        --extras-json '<json>' [--now EPOCH]
Prints the report to stdout, exits with `overall`.

# Spec: docs/architecture/pipeline.md
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

CEST = ZoneInfo("Europe/Madrid")

# Logical grouping of crons for the report. A cron not listed here
# falls into "Altres" so a newly-added cron never silently disappears.
CRON_GROUPS: list[tuple[str, list[str]]] = [
    (
        "Ingesta i metadata",
        [
            "obtenir_novetats",
            "obtenir_metadata_musicbrainz",
            "obtenir_metadata_lastfm",
            "obtenir_senyal",
            "detectar_anomalies_senyal",
            "inferir_genere",
            "inferir_percentatge_femeni",
        ],
    ),
    ("Enrichment Spotify", ["enriquir_spotify", "enriquir_spotify_rebuigs"]),
    (
        "Top i ranking",
        ["calcular_top_provisional", "calcular_top", "arxivar_senyal_vell"],
    ),
    (
        "Social i playlists",
        [
            "actualitzar_playlists_spotify",
            "actualitzar_playlists_spotify_weekly",
            "publicar_social",
            "publicar_canal_mastodon",
            "publicar_canal_bluesky",
            "publicar_canal_telegram",
            "generar_esborrany_newsletter",
            "enviar_newsletter",
            "renovar_token_instagram",
            "enviar_digest_setmanal",
        ],
    ),
    ("Portades", ["descarregar_portades"]),
    (
        "Manteniment i mètriques",
        [
            "netejar_caducades",
            "netejar_pendents_orfes",
            "netejar_pendents_no_ppcc",
            "snapshot_pipeline",
            "recollir_metrics_social",
            "recollir_metrics_gsc",
            "recollir_metrics_psi",
            "generar_goaccess",
            "analitzar_whisper",
            "tq-backup",
            "tq-recover",
            "tq-restore-test",
        ],
    ),
]

# A cron expected to run at least this often is treated as "frequent":
# if its status file is entirely ABSENT we surface it as an anomaly
# (the tag should already have been written) rather than the benign
# WAITING used for genuinely-infrequent weekly/monthly crons that may
# not have hit their first scheduled run yet. See classify_cron.
WAITING_ESCALATE_MAX_AGE_H = 48

# Watchdog escalation thresholds on consecutive skips/fails. The WARN
# threshold is per-cron (the `skip_concern` field in cron-meta.json):
# hourly crons tolerate a couple of long-running ticks, daily ones
# shouldn't skip at all. Before 2026-06-07 a uniform 3/10 was hardcoded
# here and `skip_concern` was dead config the watchdog never read.
DEFAULT_WARN_PERSISTENT = 3
DEFAULT_CRIT_PERSISTENT = 10

# State → emoji + whether it is an anomaly worth surfacing up top.
_EMOJI = {
    "OK": "🟢",
    "SKIP": "🟡",
    "WAITING": "⚪",
    "DISABLED": "⚪",
    "WARN": "🟠",
    "ORPHAN": "🟠",
    "MISSING": "🔴",
    "STALE": "🔴",
    "STUCK": "🔴",
    "FAIL": "🔴",
}


def _parse_iso(value: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def relative_age(age_h: int) -> str:
    """'fa 0h' / 'fa 5h' / 'fa 2d 3h'."""
    if age_h < 0:
        age_h = 0
    if age_h < 24:
        return f"fa {age_h}h"
    return f"fa {age_h // 24}d {age_h % 24}h"


def cest_label(last_run_iso: str, now_ts: int) -> str:
    """Absolute CEST time with an avui/ahir prefix, e.g.
    'avui 08:00 CEST' / 'ahir 05:00 CEST' / '27/05 02:00 CEST'."""
    dt = _parse_iso(last_run_iso)
    if dt is None:
        return last_run_iso or "?"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    local = dt.astimezone(CEST)
    now_local = _dt.datetime.fromtimestamp(now_ts, tz=CEST)
    days = (now_local.date() - local.date()).days
    if days == 0:
        prefix = "avui"
    elif days == 1:
        prefix = "ahir"
    else:
        prefix = local.strftime("%d/%m")
    return f"{prefix} {local:%H:%M} CEST"


def classify_cron(
    *,
    name: str,
    status: str | None,
    last_run_iso: str,
    max_age_h: int,
    skips: int,
    fails: int,
    silenced: bool,
    now_ts: int,
    skip_concern: int | None = None,
) -> dict:
    """Port of bin/tq-health's per-cron classifier. Returns a dict
    with state/display/age_h/escalates/is_anomaly. `escalates` is the
    cron's contribution to `overall`.

    `skip_concern` is the per-cron WARN threshold from cron-meta.json:
    the number of consecutive skips/fails at which a still-running (or
    repeatedly-failing) instance becomes suspicious. Daily crons declare
    1 (they shouldn't skip at all), hourly ones 3. Defaults to
    DEFAULT_WARN_PERSISTENT when unset.

    `status is None` means the status file is absent. That is benign
    only for genuinely-infrequent crons: a weekly/monthly job may simply
    not have hit its first scheduled run yet (state WAITING, never
    escalates). For a FREQUENT cron (expected at least every
    WAITING_ESCALATE_MAX_AGE_H hours) a missing status file means the tag
    was never written — the wrapper never ran (cron line dropped, tag
    mismatch, tq-run broken). That must NOT stay benign forever, so it is
    surfaced as MISSING and escalates (unless silenced). We split on the
    cron's own cadence because there is no timestamp to measure "how long
    absent" against (caught 2026-06-07: a never-written tag stayed an
    invisible WAITING)."""
    if status is None:
        if max_age_h and max_age_h <= WAITING_ESCALATE_MAX_AGE_H:
            return {
                "name": name,
                "state": "MISSING",
                "display": "MISSING (cap status file)",
                "age_h": None,
                "last_run": "(cap status file escrit)",
                "escalates": not silenced,
                "is_anomaly": True,
                "silenced": silenced,
            }
        return {
            "name": name,
            "state": "WAITING",
            "display": "WAITING",
            "age_h": None,
            "last_run": "(awaiting first run)",
            "escalates": False,
            "is_anomaly": False,
            "silenced": silenced,
        }

    last_dt = _parse_iso(last_run_iso)
    last_ts = int(last_dt.timestamp()) if last_dt else 0
    age_h = max(0, (now_ts - last_ts) // 3600)
    escalates = False

    # Watchdog escalation on persistent skips/fails. The WARN threshold
    # is the per-cron `skip_concern` (default 3); CRIT stays a fixed
    # ceiling, never below WARN.
    warn_at = (
        skip_concern if skip_concern and skip_concern > 0 else DEFAULT_WARN_PERSISTENT
    )
    crit_at = max(DEFAULT_CRIT_PERSISTENT, warn_at)
    persistent = max(skips, fails)
    watchdog_tag = ""
    if persistent >= crit_at:
        watchdog_tag = f" [watchdog CRIT, {persistent} consecutive]"
        escalates = True
    elif persistent >= warn_at:
        watchdog_tag = f" [watchdog WARN, {persistent} consecutive]"
        if silenced:
            escalates = True

    if age_h > max_age_h:
        if status == "SKIPPED_BY_LOCK" and skips > 0:
            state, display = "STUCK", f"STUCK({age_h}h, {skips}skips)"
        else:
            state, display = "STALE", f"STALE({age_h}h)"
        if silenced:
            display += " [silenced]"
        else:
            escalates = True
    elif status == "SKIPPED_BY_LOCK":
        state, display = "SKIP", f"SKIP({skips})"
    elif status == "DISABLED":
        # Feature gated off by a flag (e.g. tq-backup-offsite before
        # activation). A legitimate steady state: never escalates, never
        # an anomaly. The stale check above still applies — if the
        # wrapper itself stops running, the row goes STALE and alerts,
        # exactly like any other cron.
        state, display = "DISABLED", f"DISABLED({age_h}h)"
    elif status != "OK":
        state, display = "FAIL", "FAIL"
        if silenced:
            display += " [silenced]"
        else:
            escalates = True
    else:
        state, display = "OK", f"OK({age_h}h)"

    display += watchdog_tag
    is_anomaly = escalates or state in ("STALE", "STUCK", "FAIL")
    return {
        "name": name,
        "state": state,
        "display": display,
        "age_h": age_h,
        "last_run": cest_label(last_run_iso, now_ts),
        "escalates": escalates,
        "is_anomaly": is_anomaly,
        "silenced": silenced,
    }


def _read_status_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith(" "):
                k, _, v = line.partition("=")
                out[k] = v
    except OSError:
        pass
    return out


def _orphan_row(name: str, sf: dict[str, str], now_ts: int) -> dict:
    """A *.status file with no cron-meta entry. Either a tag written by a
    cron we forgot to register, or stale residue from a removed/renamed
    command. Surfaced (not silently ignored) so it gets cleaned up —
    `rm` the file or add the missing cron-meta entry. (Patró 5, auditoria
    2026-06-07.)"""
    last_iso = sf.get("last_run", "")
    return {
        "name": name,
        "state": "ORPHAN",
        "display": "ORPHAN (sense entrada a cron-meta)",
        "age_h": None,
        "last_run": cest_label(last_iso, now_ts) if last_iso else "(desconegut)",
        "escalates": True,
        "is_anomaly": True,
        "silenced": False,
    }


def gather_crons(status_dir: Path, meta: dict, now_ts: int) -> list[dict]:
    """Classify every cron declared in cron-meta.json, then surface any
    orphan *.status files that have no cron-meta entry."""
    rows: list[dict] = []
    known: set[str] = set()
    for name, m in meta.items():
        if name.startswith("_"):
            continue
        known.add(name)
        max_age = int(m.get("max_age_hours") or 0)
        silenced = bool(m.get("silenced"))
        skip_concern = m.get("skip_concern")
        f = status_dir / f"{name}.status"
        if not f.is_file():
            rows.append(
                classify_cron(
                    name=name,
                    status=None,
                    last_run_iso="",
                    max_age_h=max_age,
                    skips=0,
                    fails=0,
                    silenced=silenced,
                    now_ts=now_ts,
                    skip_concern=skip_concern,
                )
            )
            continue
        sf = _read_status_file(f)
        rows.append(
            classify_cron(
                name=name,
                status=sf.get("status", ""),
                last_run_iso=sf.get("last_run", ""),
                max_age_h=max_age,
                skips=int(sf.get("consecutive_skips") or 0),
                fails=int(sf.get("consecutive_failures") or 0),
                silenced=silenced,
                now_ts=now_ts,
                skip_concern=skip_concern,
            )
        )
    # Reconcile the OTHER direction: status files with no cron-meta entry.
    # tq-run writes <tag>.status; a tag with no registered metadata is an
    # inconsistency between the two consumers of the contract.
    try:
        files = sorted(status_dir.glob("*.status"))
    except OSError:
        files = []
    for f in files:
        stem = f.stem
        if stem in known or stem.startswith("_"):
            continue
        rows.append(_orphan_row(stem, _read_status_file(f), now_ts))
    return rows


# ── rendering ────────────────────────────────────────────────────────

_SEP = "━" * 52


def _ok_emoji(ok: bool) -> str:
    return "🟢" if ok else "🔴"


def render(crons: list[dict], extras: dict, now_ts: int) -> tuple[str, int]:
    """Return (report_text, overall). overall is 1 when anything
    anomalous is present, 0 otherwise — same gate tq-health emails on."""
    by_name = {c["name"]: c for c in crons}
    # Surface only genuinely-escalating crons at the top: a `[silenced]`
    # known issue stays visible in its group row but must not turn the
    # header red (it's expected). The header tracks `overall`.
    anomalies = [c for c in crons if c["escalates"]]

    disk = extras.get("disk", {})
    disk_pct = int(disk.get("used_pct") or 0)
    web = extras.get("web", [])
    spotify = extras.get("spotify", {})
    premium = spotify.get("premium", {})
    coverage = spotify.get("coverage", {})
    igtoken = extras.get("instagram", {}).get("token", {})
    migrations_ok = bool(extras.get("migrations_ok", True))
    errors = extras.get("errors", {})
    errors_count = int(errors.get("count") or 0)
    # Git working-tree drift on prod: out-of-band edits or a HEAD that
    # doesn't match origin/main. Absent in dev/CI → treated as OK.
    git = extras.get("git", {})
    git_ok = bool(git.get("ok", True))

    # ── overall (mirror bash) ──
    overall = 0
    if any(c["escalates"] for c in crons):
        overall = 1
    if disk_pct >= 90:
        overall = 1
    if any(not w.get("ok", True) for w in web):
        overall = 1
    if not premium.get("ok", True):
        overall = 1
    if not coverage.get("ok", True):
        overall = 1
    if not igtoken.get("ok", True):
        overall = 1
    if not migrations_ok:
        overall = 1
    if errors_count > 0:
        overall = 1
    if not git_ok:
        overall = 1

    sys_anomalies: list[str] = []
    if not git_ok:
        sys_anomalies.append(f"Git tree DRIFT: {git.get('detail', 'out-of-band')}")
    if disk_pct >= 90:
        sys_anomalies.append(f"Disc {disk_pct}% (>90%)")
    for w in web:
        if not w.get("ok", True):
            sys_anomalies.append(f"Web {w.get('label', '?')}")
    if not migrations_ok:
        sys_anomalies.append("DB migrations pendents")
    if errors_count > 0:
        sys_anomalies.append(f"{errors_count} errors Django avui")
    if not premium.get("ok", True):
        sys_anomalies.append(f"Spotify Premium {premium.get('severity', '?')}")
    if not coverage.get("ok", True):
        sys_anomalies.append(f"Spotify coverage {coverage.get('severity', '?')}")
    if not igtoken.get("ok", True):
        sys_anomalies.append(
            f"IG token {igtoken.get('severity', '?')}: {igtoken.get('message', '')}"
        )

    n_crons = len(crons)
    out: list[str] = []

    # ── executive summary ──
    total_anoms = len(anomalies) + len(sys_anomalies)
    when = _dt.datetime.fromtimestamp(now_ts, tz=CEST).strftime("%d/%m %H:%M CEST")
    if total_anoms == 0:
        out.append(f"🟢 Tot OK ({n_crons} crons, 0 anomalies) · {when}")
    else:
        brief = ", ".join(
            [f"{a['name']} {a['state']}" for a in anomalies[:3]] + sys_anomalies[:3]
        )
        out.append(f"🔴 {total_anoms} anomalies: {brief} · {when}")
    out.append("TopQuaranta · estat del pipeline")
    out.append("")

    # ── anomalies block ──
    if total_anoms:
        out.append(f"{_SEP}\n ANOMALIES\n{_SEP}")
        for a in anomalies:
            emoji = _EMOJI.get(a["state"], "🔴")
            out.append(f"{emoji} {a['name']} — {a['display']}")
            out.append(f"     darrer run: {a['last_run']}")
        for s in sys_anomalies:
            out.append(f"🔴 {s}")
        out.append("")

    # ── crons by group ──
    out.append(f"{_SEP}\n CRONS\n{_SEP}")
    listed: set[str] = set()
    groups = list(CRON_GROUPS)
    leftover = [n for n in by_name if not any(n in names for _, names in groups)]
    if leftover:
        groups = groups + [("Altres", sorted(leftover))]
    for title, names in groups:
        present = [by_name[n] for n in names if n in by_name]
        if not present:
            continue
        out.append(title)
        for c in present:
            listed.add(c["name"])
            emoji = _EMOJI.get(c["state"], "⚪")
            age = relative_age(c["age_h"]) if c["age_h"] is not None else "—"
            out.append(
                f"  {emoji} {c['name']:<32} {c['display']:<22} "
                f"{age:<8} {c['last_run']}"
            )
        out.append("")

    # ── system ──
    out.append(f"{_SEP}\n SISTEMA\n{_SEP}")
    disk_emoji = "🔴" if disk_pct >= 90 else ("🟠" if disk_pct >= 80 else "🟢")
    out.append(f"{disk_emoji} Disc: {disk_pct}% usat, {disk.get('avail', '?')} lliure")
    out.append(f"{_ok_emoji(errors_count == 0)} Errors Django avui: {errors_count}")
    for e in errors.get("last", [])[:3]:
        out.append(f"     {e}")
    for w in web:
        out.append(
            f"{_ok_emoji(w.get('ok', True))} {w.get('label', '?')}: "
            f"{w.get('detail', '')}".rstrip()
        )
    out.append(
        f"{_ok_emoji(migrations_ok)} DB migrations: "
        f"{'OK (schema matches code)' if migrations_ok else 'pendents — run tq-deploy'}"
    )
    git_detail = git.get("detail") or (
        "OK (matches origin/main, clean)" if git_ok else "DRIFT"
    )
    out.append(f"{_ok_emoji(git_ok)} Git tree: {git_detail}")
    out.append("")

    # ── spotify ──
    out.append(f"{_SEP}\n SPOTIFY\n{_SEP}")
    out.append(
        f"{_ok_emoji(premium.get('ok', True))} Premium: "
        f"{premium.get('severity', '?')} — {premium.get('message', '')}"
    )
    out.append(
        f"{_ok_emoji(coverage.get('ok', True))} Playlist coverage: "
        f"{coverage.get('severity', '?')} — {coverage.get('message', '')}"
    )
    out.append("")

    # ── social ──
    out.append(f"{_SEP}\n SOCIAL\n{_SEP}")
    out.append(
        f"{_ok_emoji(igtoken.get('ok', True))} IG token: "
        f"{igtoken.get('severity', '?')} — {igtoken.get('message', '')}"
    )
    out.append("")

    # ── legend ──
    out.append(f"{_SEP}\n LLEGENDA\n{_SEP}")
    out.append("🟢 OK(Xh)   darrer run fa X h, dins del llindar de freqüència")
    out.append("⚪ WAITING  programat però encara no ha corregut cap cop")
    out.append("🟡 SKIP(N)  saltat per lock (un run llarg en curs); normal si N baix")
    out.append("🟠 WARN     watchdog: N skips/fails consecutius; vigilar")
    out.append(
        "🟠 ORPHAN   status file sense entrada a cron-meta; cal netejar o registrar"
    )
    out.append(
        "🔴 MISSING  cron freqüent sense cap status file escrit; el tag no s'ha escrit mai"
    )
    out.append("🔴 STALE    sense córrer més enllà del llindar (diaris >36h, etc.)")
    out.append("🔴 STUCK    saltat per lock i ja passat de llindar")
    out.append("🔴 FAIL     últim run amb exit-code != 0")
    out.append("   [silenced] = anomalia coneguda/esperada; encara vermella al panell")

    return "\n".join(out).rstrip() + "\n", overall


def anomaly_signature(crons: list[dict], extras: dict) -> str:
    """Stable dedup key for the alert email: the IDENTITY of the current
    anomaly set, not its rendered text.

    Two reports that differ only in timestamps, ages ("fa Xh"), or
    monotonic counters (STALE/STUCK hours, today's Django error count)
    map to the SAME signature, so a persistent failure is emailed ONCE
    and only a NEW or CLEARED problem re-alerts. The components mirror
    `render`'s `overall` gate, but reduced to stable tokens: escalating
    crons by `(name, state)` (state tokens carry no numbers) plus a
    boolean per system threshold crossing. Caught 2026-06-07: the old
    signature grep'd the rendered report (timestamps + ages + error
    count) so every hourly tick produced a new key and re-spammed."""
    parts: list[str] = []
    for c in sorted(crons, key=lambda c: c["name"]):
        if c.get("escalates"):
            parts.append(f"cron:{c['name']}={c['state']}")
    disk = extras.get("disk", {})
    if int(disk.get("used_pct") or 0) >= 90:
        parts.append("disk:over90")
    for w in extras.get("web", []):
        if not w.get("ok", True):
            parts.append(f"web:{w.get('label', '?')}")
    spotify = extras.get("spotify", {})
    if not spotify.get("premium", {}).get("ok", True):
        parts.append("spotify:premium")
    if not spotify.get("coverage", {}).get("ok", True):
        parts.append("spotify:coverage")
    if not bool(extras.get("migrations_ok", True)):
        parts.append("migrations:pending")
    if not bool(extras.get("git", {}).get("ok", True)):
        parts.append("git:drift")
    if int(extras.get("errors", {}).get("count") or 0) > 0:
        parts.append("errors:present")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--status-dir", required=True)
    p.add_argument("--meta-file", required=True)
    p.add_argument("--extras-json", default="{}")
    p.add_argument("--now", type=int, default=None)
    p.add_argument(
        "--print-signature",
        action="store_true",
        help="Print the stable anomaly-set signature instead of the report "
        "(used by tq-health's email dedup). Exit code is still `overall`.",
    )
    args = p.parse_args(argv)

    now_ts = args.now if args.now is not None else int(_dt.datetime.now().timestamp())
    meta = json.loads(Path(args.meta_file).read_text())
    extras = json.loads(args.extras_json)
    crons = gather_crons(Path(args.status_dir), meta, now_ts)
    text, overall = render(crons, extras, now_ts)
    if args.print_signature:
        sys.stdout.write(anomaly_signature(crons, extras) + "\n")
    else:
        sys.stdout.write(text)
    return overall


if __name__ == "__main__":
    raise SystemExit(main())
