#!/bin/bash
# scripts/health/instagram_token.sh
#
# Daily check (cost: one DB read of the InstagramAuth row; no API call).
# Alerts before the long-lived IG token's stored expiry so the operator
# can re-authorize manually (the Meta app is in dev mode → no working
# auto-refresh). Real Meta expiry isn't queryable with our IG-Login
# token, so this uses the stored expires_at (paste+60d).
#
# Exit codes:
#   0 = OK   (> 10 days left, or not configured / DRY_RUN)
#   1 = WARN (≤ 10 days)
#   2 = CRIT (≤ 5 days, or already expired)
#
# Wraps music.health.check_instagram_token.

set -u

APP_DIR="${TQ_APP_DIR:-/home/topquaranta/app}"
PY="$APP_DIR/.venv/bin/python"

out=$(
    cd "$APP_DIR" && \
    DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    "$PY" -m music.health instagram_token 2>&1
)
code=$?
echo "$out"
exit $code
