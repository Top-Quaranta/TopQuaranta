#!/bin/bash
# scripts/health/spotify_premium_active.sh
#
# Weekly check (cost: one /v1/me call). Caches the result for 7
# days in /var/lib/topquaranta/health-cache/ so re-runs within the
# cache window are zero-cost. Cache is invalidated on `--force`
# or after the TTL.
#
# Exit codes (matching the bin/tq-health sub-check convention):
#   0 = OK   (product == "premium")
#   1 = WARN (transient API error)
#   2 = CRIT (Premium lapsed, refresh token revoked, or no OAuth row)
#
# Wraps music.health.check_spotify_premium so the testable logic
# stays in Python. The bash layer adds caching and exit-code mapping.

set -u

APP_DIR="${TQ_APP_DIR:-/home/topquaranta/app}"
PY="$APP_DIR/.venv/bin/python"
CACHE_DIR="${TQ_HEALTH_CACHE_DIR:-/var/lib/topquaranta/health-cache}"
CACHE_FILE="$CACHE_DIR/spotify_premium.cache"
# Weekly cadence: skip the API call if cache is fresher than this.
CACHE_TTL_SECONDS=$((7 * 24 * 3600))

FORCE=0
for arg in "$@"; do
    [[ "$arg" == "--force" ]] && FORCE=1
done

now=$(date +%s)

# Cache hit path: print the cached output and exit with the cached
# code. We persist the exit code alongside the message because the
# bash caller wants to fan it back out without re-running the check.
if [[ "$FORCE" == "0" && -f "$CACHE_FILE" ]]; then
    cached_at=$(stat -c %Y "$CACHE_FILE" 2>/dev/null || stat -f %m "$CACHE_FILE")
    age=$((now - cached_at))
    if (( age < CACHE_TTL_SECONDS )); then
        # Cache line format: "EXITCODE\tMESSAGE_JSON"
        line=$(head -1 "$CACHE_FILE")
        code="${line%%	*}"
        rest="${line#*	}"
        echo "$rest (cached ${age}s ago)"
        exit "$code"
    fi
fi

# Cache miss: actually call Spotify.
mkdir -p "$CACHE_DIR" 2>/dev/null || true

out=$(
    cd "$APP_DIR" && \
    DJANGO_SETTINGS_MODULE=topquaranta.settings.production \
    "$PY" -m music.health spotify_premium 2>&1
)
code=$?

# Persist the result. The TTL only matters on success/CRIT (we
# don't want to silence a transient WARN for a week); keep the
# WARN cache window short by truncating it to 1 hour.
if (( code == 1 )); then
    # WARN: short cache to recover quickly when the API stabilises.
    cache_window=3600
else
    cache_window=$CACHE_TTL_SECONDS
fi
printf "%d\t%s\n" "$code" "$out" > "$CACHE_FILE"
# Backdate the mtime so subsequent runs respect the per-severity
# cache window above (touch with a time in the past for WARN).
if (( cache_window != CACHE_TTL_SECONDS )); then
    backdate_to=$((now - (CACHE_TTL_SECONDS - cache_window)))
    touch -d "@$backdate_to" "$CACHE_FILE" 2>/dev/null || \
        touch -t "$(date -r "$backdate_to" +%Y%m%d%H%M.%S)" "$CACHE_FILE" 2>/dev/null || true
fi

echo "$out"
exit $code
