"""SPA asset health check — the try_files trap and its blast radius.

`scripts/health/spa_assets.sh` runs for real against a stub HTTP server
on localhost (no network, no Django). The stub emulates the one Caddy
behaviour that made the previous status-only check unfalsifiable: the
SPA vhost ends in `try_files {path} /index.html`, so a MISSING asset is
served as the SPA shell with HTTP 200, not a 404.

The middle test is the one that matters. Before this check asserted
content-type, an absent CSS returned 200 and the row went green while
the dist was broken.

# Spec: docs/ops/runbook.md
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "health" / "spa_assets.sh"

CSS_PATH = "/assets/index-Cmw8JJjD.css"
JS_PATH = "/assets/index-7Kggo81f.js"

SHELL_HTML = (
    "<!doctype html><html><head>"
    f'<script type="module" crossorigin src="{JS_PATH}"></script>'
    f'<link rel="stylesheet" crossorigin href="{CSS_PATH}">'
    '</head><body><div id="root"></div></body></html>'
)


# ── stub server ──────────────────────────────────────────────────────


def _make_handler(routes: dict, drop_first: set):
    """routes: path -> (status, content_type, body).

    `drop_first` holds paths that must close the connection without a
    response on their FIRST hit, so curl reports no HTTP status at all
    (http_code 000) and the retry path gets exercised.
    """
    seen: set = set()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):  # noqa: N802 (stdlib naming)
            if self.path in drop_first and self.path not in seen:
                seen.add(self.path)
                self.close_connection = True
                try:
                    self.connection.close()
                except OSError:
                    pass
                return
            status, ctype, body = routes.get(self.path, (404, "text/plain", "nope"))
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # silence stderr noise
            pass

    return Handler


def _serve(routes: dict, drop_first: set = frozenset()):
    srv = HTTPServer(("127.0.0.1", 0), _make_handler(routes, set(drop_first)))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def _run(base: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        TQ_HEALTH_WEB_PUBLIC=base,
        TQ_HEALTH_ASSET_TIMEOUT="3",
        TQ_HEALTH_RETRY_WAIT="0",
    )
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60
    )


def _healthy_routes() -> dict:
    return {
        "/": (200, "text/html; charset=utf-8", SHELL_HTML),
        CSS_PATH: (200, "text/css; charset=utf-8", ".rd-band{color:red}"),
        JS_PATH: (200, "text/javascript; charset=utf-8", "export default 1"),
    }


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ── the three mandated cases ─────────────────────────────────────────


def test_css_and_js_real_is_green():
    """Everything served with the right content-type → exit 0."""
    srv, base = _serve(_healthy_routes())
    try:
        proc = _run(base)
    finally:
        srv.shutdown()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.startswith("OK "), proc.stdout
    assert CSS_PATH in proc.stdout
    assert JS_PATH in proc.stdout


def test_absent_css_served_as_spa_html_with_200_is_red():
    """The regression this whole check exists for.

    try_files serves the SPA shell for a missing asset: HTTP 200,
    content-type text/html. The old status-only assert passed this in
    green with a broken dist.
    """
    routes = _healthy_routes()
    routes[CSS_PATH] = (200, "text/html; charset=utf-8", SHELL_HTML)
    srv, base = _serve(routes)
    try:
        proc = _run(base)
    finally:
        srv.shutdown()
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "content-type" in proc.stdout
    assert "text/html" in proc.stdout
    assert CSS_PATH in proc.stdout
    # It must name the cause, not the misleading legacy text.
    assert "dist stale" not in proc.stdout


def test_no_http_response_at_all_is_red_and_says_000_once():
    """Nothing listening → transport branch, and the detail says 000.

    Guards the double-write bug: `%{http_code}` already emits 000, and
    the old `|| echo 000` appended a second one, so the detail read
    "000000".
    """
    proc = _run(f"http://127.0.0.1:{_free_port()}")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "000" in proc.stdout
    assert "000000" not in proc.stdout
    assert "transport" in proc.stdout


# ── the rest of the hardening ────────────────────────────────────────


def test_absent_js_served_as_spa_html_with_200_is_red():
    """Same trap on the module script, which was not checked at all."""
    routes = _healthy_routes()
    routes[JS_PATH] = (200, "text/html; charset=utf-8", SHELL_HTML)
    srv, base = _serve(routes)
    try:
        proc = _run(base)
    finally:
        srv.shutdown()
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert JS_PATH in proc.stdout
    assert "text/html" in proc.stdout


@pytest.mark.parametrize("status", [404, 500, 503])
def test_unexpected_status_is_reported_as_server_not_transport(status):
    routes = _healthy_routes()
    routes[CSS_PATH] = (status, "text/plain", "boom")
    srv, base = _serve(routes)
    try:
        proc = _run(base)
    finally:
        srv.shutdown()
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert f"HTTP {status}" in proc.stdout
    assert "transport" not in proc.stdout


def test_transport_blip_that_recovers_on_retry_is_green_but_recorded():
    """A dropped connection on the first hit must not page.

    It must still leave a trace, so a flapping edge is visible in the
    report instead of being silently swallowed.
    """
    srv, base = _serve(_healthy_routes(), drop_first={CSS_PATH})
    try:
        proc = _run(base)
    finally:
        srv.shutdown()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "reintent" in proc.stdout
    assert "CSS" in proc.stdout


def test_shell_without_root_div_is_red():
    routes = _healthy_routes()
    routes["/"] = (200, "text/html; charset=utf-8", "<html><body>buit</body></html>")
    srv, base = _serve(routes)
    try:
        proc = _run(base)
    finally:
        srv.shutdown()
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "root" in proc.stdout


def test_script_is_executable():
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} ha de ser executable"
