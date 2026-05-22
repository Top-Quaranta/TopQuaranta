#!/usr/bin/env bash
# scripts/health/test_watchdog.sh
#
# REQUIRES BASH 4+ (associative arrays). macOS ships bash 3.2;
# install via `brew install bash` and run with `bash` on PATH, or
# rely on the Ubuntu CI runner which has bash 5+. Tested on prod.
#
# Smoke test for the FASE F watchdog logic in bin/tq-health.
# Runs the script against a fixture STATUS_DIR + cron-meta.json and
# asserts the watchdog escalates `silenced=true` rows that have
# `consecutive_failures >= 3`.
#
# Not part of pytest; called from a CI step or `make test-health`.
#
# Exit 0 = all assertions pass.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

STATUS_DIR="$TMP/status"
META_FILE="$TMP/cron-meta.json"
mkdir -p "$STATUS_DIR"

cat > "$META_FILE" <<'JSON'
{
  "fake_cron_silenced_failing": {
    "frequency_label": "Cada hora",
    "max_age_hours": 2,
    "silenced": true,
    "silenced_reason": "test"
  },
  "fake_cron_healthy": {
    "frequency_label": "Cada hora",
    "max_age_hours": 2
  }
}
JSON

# Fixture status file: silenced cron with 5 consecutive_failures.
# This is the exact shape the actualitzar_playlists_spotify cron had
# in production on the day this watchdog was written.
now=$(date -Iseconds)
cat > "$STATUS_DIR/fake_cron_silenced_failing.status" <<EOF
command=fake_cron_silenced_failing
args=
last_run=$now
exit_code=1
attempts=3
max_attempts=3
status=FAIL
consecutive_skips=0
consecutive_failures=5
EOF

cat > "$STATUS_DIR/fake_cron_healthy.status" <<EOF
command=fake_cron_healthy
args=
last_run=$now
exit_code=0
attempts=1
max_attempts=3
status=OK
consecutive_skips=0
consecutive_failures=0
EOF

# Patch bin/tq-health to use our fixture paths. We can't pass them
# via env because the script hardcodes them; we generate a temp copy
# with sed substitutions and run that instead. Avoids polluting the
# repo's bin/.
TQ_HEALTH="$TMP/tq-health-test"
sed \
    -e "s|/var/log/topquaranta/status|$STATUS_DIR|g" \
    -e "s|/home/topquaranta/app/deploy/cron-meta.json|$META_FILE|g" \
    -e "s|/home/topquaranta/app/.venv/bin/python|/usr/bin/env python3|g" \
    -e "s|/var/log/topquaranta/errors.log|$TMP/errors.log|g" \
    "$REPO_ROOT/bin/tq-health" > "$TQ_HEALTH"
chmod +x "$TQ_HEALTH"

out=$("$TQ_HEALTH" 2>&1 || true)
rc=$?

# Assertions.
echo "$out" | head -40

fail=0
if ! grep -q "fake_cron_silenced_failing" <<< "$out"; then
    echo "FAIL: silenced row not present in output"
    fail=1
fi
if ! grep -q "watchdog WARN" <<< "$out"; then
    echo "FAIL: watchdog tag not emitted for 5 consecutive_failures"
    fail=1
fi
if grep -q "watchdog WARN" <<< "$(echo "$out" | grep fake_cron_healthy)"; then
    echo "FAIL: watchdog tag wrongly emitted for healthy row"
    fail=1
fi

if (( fail == 0 )); then
    echo
    echo "OK: watchdog escalates silenced+failing rows past the silenced flag."
fi
exit $fail
