"""Generate the GoAccess HTML report from Caddy access logs.

Caddy writes JSON access logs at `/var/log/caddy/access.log`. GoAccess
supports JSON natively, but the per-Caddy schema is verbose enough
that pipelining via a tiny Python pre-converter to Combined-Log-Format
is more robust across GoAccess versions than maintaining a custom
JSON format string.

The output goes to `/var/cache/topquaranta/goaccess/report.html`,
which is served behind the staff-auth `/api/v1/staff/goaccess/`
endpoint. We never expose `/var/cache/...` to Caddy directly — the
Django proxy ensures only OTP-verified staff see it.

Filtering: requests to `/api/`, `/static/`, `/assets/` are kept (we
want to see asset hot-paths in GoAccess), but the Django middleware
analytics layer ignores those — the two surfaces complement each
other instead of duplicating numbers.
"""

from __future__ import annotations

import datetime
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

# The TopQuaranta vhost writes to its own file (the global
# `access.log` is the legacy default-vhost dump, mostly bot probes
# to the bare IP). `topquaranta_access.log` is the live Caddy
# tee for `topquaranta.cat` + `www.topquaranta.cat`; rotated by
# Caddy at 10 MiB into `topquaranta_access-<ts>.log.gz`.
CADDY_LOG = Path("/var/log/caddy/topquaranta_access.log")
REPORT_DIR = Path("/var/cache/topquaranta/goaccess")
REPORT_HTML = REPORT_DIR / "report.html"


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


class Command(BaseCommand):
    help = "Genera l'informe GoAccess sobre els logs de Caddy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Dies enrere a incloure (default 30).",
        )

    def handle(self, *args, **opts) -> None:
        if not CADDY_LOG.exists():
            raise CommandError(f"Caddy log not found at {CADDY_LOG}")
        if shutil.which("goaccess") is None:
            raise CommandError("goaccess no està instal·lat (apt install goaccess).")
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

        days = max(1, int(opts["days"]))
        cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
            days=days
        )

        # Convert JSON → CLF in a tempfile. We could pipe directly via
        # stdin but a file lets us count lines for the success log
        # without consuming the iterator.
        ok = 0
        skipped = 0
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".clf", delete=False, dir=str(REPORT_DIR)
        ) as tmp:
            with CADDY_LOG.open("r", errors="replace") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError:
                        skipped += 1
                        continue
                    ts = rec.get("ts")
                    if ts is not None:
                        try:
                            if (
                                datetime.datetime.fromtimestamp(
                                    float(ts), tz=datetime.timezone.utc
                                )
                                < cutoff
                            ):
                                continue
                        except (TypeError, ValueError):
                            pass
                    line = _caddy_to_clf_line(rec)
                    if line is None:
                        skipped += 1
                        continue
                    tmp.write(line + "\n")
                    ok += 1
            tmp_path = Path(tmp.name)

        if ok == 0:
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
            self.style.SUCCESS(
                f"Informe GoAccess generat: {REPORT_HTML} "
                f"({ok} línies, {skipped} omesos)"
            )
        )
