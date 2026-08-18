#!/bin/bash
# scripts/health/spa_assets.sh
#
# Hourly check: the SPA shell Caddy serves, plus the two hashed assets
# that shell references, all resolve to real files in the Vite dist.
#
# Why the content-type assert and not just the status code: the SPA
# vhost ends in `try_files {path} /index.html` (deploy/Caddyfile), so a
# MISSING asset is served as the SPA shell with HTTP 200. A status-only
# check can therefore never fail on a stale, partial or half-written
# dist. Measured on prod 2026-07-31:
#
#   /assets/index-Cmw8JJjD.css   200  [text/css; charset=utf-8]
#   /assets/index-7Kggo81f.js    200  [text/javascript; charset=utf-8]
#   /assets/index-NOEXISTEIX.css 200  [text/html; charset=utf-8]   <-- fallback
#
# Asserting the content-type is the whole reason this check can fail.
#
# Exit codes:
#   0 = OK   (shell + CSS + JS served with the expected content-type)
#   1 = anomaly (transport, unexpected status, or wrong content-type)
#
# stdout: exactly one line, consumed verbatim by tq-health as the
# detail text of the "Web SPA shell" row.

set -u

BASE="${TQ_HEALTH_WEB_PUBLIC:-https://www.topquaranta.cat}"
TIMEOUT="${TQ_HEALTH_ASSET_TIMEOUT:-5}"
RETRY_WAIT="${TQ_HEALTH_RETRY_WAIT:-2}"

BODY=$(mktemp)
trap 'rm -f "$BODY"' EXIT

RETRIED=""

# Probe one URL. Sets P_CODE and P_CTYPE; body lands in $BODY.
# P_CODE is "000" when curl got no HTTP response at all.
#
# `-f` is deliberately absent: it turns a 404 into a non-zero exit and
# hides the status we want to report. `%{http_code}` already writes 000
# on a transport failure, so there is no `|| echo 000` either — that
# used to write the fallback ON TOP of curl's own 000 and the detail
# read "000000" (found 2026-07-31).
_probe() {
    local out
    out=$(curl -sSk --max-time "$TIMEOUT" -o "$BODY" \
        -w '%{http_code} %{content_type}' "$1" 2>/dev/null)
    P_CODE="${out%% *}"
    P_CTYPE="${out#* }"
    [[ "$P_CODE" == "$P_CTYPE" ]] && P_CTYPE=""
    [[ -z "$P_CODE" ]] && P_CODE="000"
    return 0
}

# One retry after a short wait before calling a transport failure red.
# A single dropped connection at the exact moment of the hourly tick is
# not a broken dist, and used to page as one. A probe that recovers on
# the retry stays green but is recorded in the detail line so the blip
# is not silent.
_probe_retry() {
    _probe "$1"
    if [[ "$P_CODE" == "000" ]]; then
        sleep "$RETRY_WAIT"
        _probe "$1"
        [[ "$P_CODE" != "000" ]] && RETRIED="${RETRIED}${RETRIED:+, }$2"
    fi
    return 0
}

# $1 url · $2 label · $3 expected content-type (ERE, anchored by caller)
# Sets FAIL and returns 1 on anomaly. The three branches are distinct on
# purpose: transport, server, and content each have a different cause
# and a different thing to go look at.
_check_asset() {
    _probe_retry "$1" "$2"
    if [[ "$P_CODE" == "000" ]]; then
        FAIL="$2 $1 → $P_CODE cap resposta HTTP (transport: connexió o timeout ${TIMEOUT}s)"
        return 1
    fi
    if [[ "$P_CODE" != "200" ]]; then
        FAIL="$2 $1 → HTTP $P_CODE (el servidor respon amb un estat inesperat)"
        return 1
    fi
    if ! grep -qiE "$3" <<<"$P_CTYPE"; then
        FAIL="$2 $1 → 200 però content-type '$P_CTYPE' (fallback try_files: l'asset no és al dist)"
        return 1
    fi
    return 0
}

# ── 1. The shell itself ────────────────────────────────────────────────
_probe_retry "$BASE/" "shell"
if [[ "$P_CODE" == "000" ]]; then
    echo "$BASE/ → $P_CODE cap resposta HTTP (transport: connexió o timeout ${TIMEOUT}s)"
    exit 1
fi
if [[ "$P_CODE" != "200" ]]; then
    echo "$BASE/ → HTTP $P_CODE (el servidor respon amb un estat inesperat)"
    exit 1
fi
if ! grep -q 'id="root"' "$BODY"; then
    echo "$BASE/ servit sense <div id=root> (build trencat?)"
    exit 1
fi

css_path=$(grep -oE '/assets/index-[A-Za-z0-9_-]+\.css' "$BODY" | head -1)
js_path=$(grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' "$BODY" | head -1)
if [[ -z "$css_path" ]]; then
    echo "index servit sense link CSS hashed (build Vite trencat?)"
    exit 1
fi
if [[ -z "$js_path" ]]; then
    echo "index servit sense <script module> hashed (build Vite trencat?)"
    exit 1
fi

# ── 2. The assets it references ────────────────────────────────────────
FAIL=""
if ! _check_asset "$BASE$css_path" "CSS" '^text/css'; then
    echo "$FAIL"
    exit 1
fi
if ! _check_asset "$BASE$js_path" "JS" '^(text|application)/javascript'; then
    echo "$FAIL"
    exit 1
fi

echo "OK ($css_path text/css, $js_path text/javascript)${RETRIED:+ — reintent OK: $RETRIED}"
exit 0
