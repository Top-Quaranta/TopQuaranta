#!/bin/bash
# scripts/health/github_pat.sh
#
# Daily check (cost: pure date arithmetic; no API call, no DB read).
# Alerts before the stored expiry of AUTOMERGE_PAT, the fine-grained
# GitHub PAT that dependabot-automerge merges with. The box never holds
# the token, so the real expiry isn't queryable — the date lives in
# music/health.py (GITHUB_PAT_EXPIRES) and gets bumped on each renewal.
# If the PAT lapses, automerge falls back to GITHUB_TOKEN and merges
# stop triggering deploys (DRIFT incident, 2026-08-24).
#
# Exit codes:
#   0 = OK   (> 10 days left)
#   1 = WARN (≤ 10 days)
#   2 = CRIT (≤ 5 days, or already expired)
#
# Wraps music.health.check_github_pat.

set -u

APP_DIR="${TQ_APP_DIR:-/home/topquaranta/app}"
PY="$APP_DIR/.venv/bin/python"

out=$(
    cd "$APP_DIR" && \
    DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    "$PY" -m music.health github_pat 2>&1
)
code=$?
echo "$out"
exit $code
