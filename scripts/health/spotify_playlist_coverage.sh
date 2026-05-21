#!/bin/bash
# scripts/health/spotify_playlist_coverage.sh
#
# Daily check (cost: one DB read of ≤ 20 rows; no API calls).
# Reads SpotifyPlaylist rows and reports the matched / total
# coverage ratio. Designed to surface "the cron ran OK but matched
# very few tracks" (silent ISRC degradation upstream).
#
# Exit codes:
#   0 = OK   (all rows ≥ 85% coverage, or rows that have never synced)
#   1 = WARN (≥1 row 50–85% coverage)
#   2 = CRIT (≥1 row < 50% coverage)
#
# Wraps music.health.check_spotify_coverage. No cache: the cost is
# tiny and we want a fresh read every cron tick.

set -u

APP_DIR="${TQ_APP_DIR:-/home/topquaranta/app}"
PY="$APP_DIR/.venv/bin/python"

out=$(
    cd "$APP_DIR" && \
    DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    "$PY" -m music.health spotify_coverage 2>&1
)
code=$?
echo "$out"
exit $code
