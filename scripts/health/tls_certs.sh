#!/bin/bash
# scripts/health/tls_certs.sh
#
# Hourly check (cost: one TLS handshake per configured endpoint).
# Opens a real connection with explicit SNI and reads `notAfter` from
# the certificate the endpoint ACTUALLY SERVES. It never looks at a PEM
# on disk: in the July 2026 incident the file was correct for a month
# while the served certificate was a different, expiring one.
#
# Endpoints and threshold live in ConfiguracioGlobal
# (`tls_endpoints_vigilats`, `tls_avis_dies`), editable from staff. The
# list ships EMPTY, so this is a no-op until the operator opts in.
#
# Exit codes:
#   0 = OK   (every endpoint above the threshold, or none configured)
#   1 = WARN (at least one endpoint inside the threshold)
#   2 = CRIT (at least one already expired, or unreachable)
#
# Wraps music.health.check_tls_certs.

set -u

APP_DIR="${TQ_APP_DIR:-/home/topquaranta/app}"
PY="$APP_DIR/.venv/bin/python"

out=$(
    cd "$APP_DIR" && \
    DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    "$PY" -m music.health tls_certs 2>&1
)
code=$?
echo "$out"
exit $code
