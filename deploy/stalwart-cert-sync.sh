#!/bin/bash
# Push Caddy's Let's Encrypt cert for mail.topquaranta.cat into
# Stalwart's live configuration, then restart Stalwart.
#
# WHY THIS IS NOT A FILE COPY
# ---------------------------
# Stalwart 0.16 keeps its configuration in RocksDB, not on disk. The
# certificate is an inline property of an `x:Certificate` object. The
# `STALWART_CERTIFICATE_DEFAULT_CERT=%{file:...}%` entries in
# /etc/stalwart/stalwart.env are loaded into the process environment
# but never evaluated — that macro syntax predates 0.16. So writing
# PEM files anywhere on disk has no effect whatsoever.
#
# The previous version of this script copied files to
# /etc/stalwart/certs/ and restarted Stalwart on every Caddy renewal.
# The copy did nothing and the restart was a pointless mail outage.
# On 2026-06-26 that ran, appeared to succeed, and left Stalwart
# serving a cert that expired a month later. See
# docs/archive/post-mortems/2026-07-26-stalwart-cert-expirat.md.
#
# Configuration therefore goes over the JMAP admin API on localhost,
# and a restart IS required afterwards: writing the config does not
# swap the already-loaded TLS context.
#
# Triggered by stalwart-cert-sync.path (watches Caddy's cert dir).
# Safe to run by hand at any time; it is idempotent.
#
# Usage:
#   stalwart-cert-sync.sh            sync if needed
#   stalwart-cert-sync.sh --dry-run  detect and verify only, no writes
#
# Exit codes:
#   0  already in sync, or synced and verified
#   1  precondition failure (missing file, unreadable credential, ...)
#   2  cert and key on disk are not a pair
#   3  certificate object lookup failed (zero or several matches)
#   4  JMAP write failed, or live config did not take the new value
#   5  post-restart verification failed (WRONG SERIAL STILL SERVED)
#
# Spec: docs/ops/runbook.md

set -euo pipefail

# --- Settings. Every one is overridable from the environment so the
# --- detection logic can be exercised against test fixtures without
# --- ever touching the live config (see --dry-run).
: "${MAIL_HOST:=mail.topquaranta.cat}"
: "${CADDY_CERT_DIR:=/var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org-directory/mail.topquaranta.cat}"
: "${SRC_CRT:=${CADDY_CERT_DIR}/mail.topquaranta.cat.crt}"
: "${SRC_KEY:=${CADDY_CERT_DIR}/mail.topquaranta.cat.key}"
: "${STALWART_ENV:=/etc/stalwart/stalwart.env}"
: "${JMAP_BASE:=http://127.0.0.1:8080}"
: "${SERVICE:=stalwart}"
: "${VERIFY_PORTS:=993 465 25}"
: "${PROBE_PORT:=993}"
: "${RESTART_SETTLE_SECONDS:=6}"
: "${LOG_FILE:=/var/log/stalwart-cert-sync.log}"
: "${LOG_MAX_BYTES:=1048576}"
: "${OPENSSL_TIMEOUT:=20}"

DRY_RUN=0
case "${1:-}" in
    --dry-run) DRY_RUN=1 ;;
    "")        ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *)         echo "unknown argument: $1" >&2; exit 1 ;;
esac

# --- Logging. journald on this host does not persist (it rotated
# --- away the June evidence, which is why the 2026-07 incident could
# --- not be reconstructed from logs), so we keep our own file.
rotate_log() {
    [ -f "$LOG_FILE" ] || return 0
    local size
    size=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$size" -gt "$LOG_MAX_BYTES" ]; then
        mv -f "$LOG_FILE" "${LOG_FILE}.1"
        : > "$LOG_FILE"
        chmod 640 "$LOG_FILE"
    fi
}

log() {
    # NEVER pass credential or private-key material to this function.
    local line
    line="$(date -u '+%Y-%m-%dT%H:%M:%SZ') [$$] $*"
    echo "$line"
    echo "$line" >> "$LOG_FILE"
}

die() {
    local code=$1; shift
    log "ERROR: $*"
    log "RESULT: aborted with exit $code"
    exit "$code"
}

umask 077
touch "$LOG_FILE" 2>/dev/null || { echo "cannot write $LOG_FILE" >&2; exit 1; }
chmod 640 "$LOG_FILE" 2>/dev/null || true
rotate_log

TMPDIR_RUN=$(mktemp -d)
trap 'rm -rf "$TMPDIR_RUN"' EXIT

[ "$DRY_RUN" -eq 1 ] && log "=== start (--dry-run: no config write, no restart) ===" \
                     || log "=== start ==="

# --- Credential: read at runtime, kept in a variable, converted to a
# --- pre-encoded Authorization header. It is passed to curl through a
# --- config file on stdin so it never appears in argv (visible in ps)
# --- and never in this script or the log.
[ -r "$STALWART_ENV" ] || die 1 "cannot read $STALWART_ENV"
ADMIN_CRED=$(grep -E '^STALWART_RECOVERY_ADMIN=' "$STALWART_ENV" | head -1 | cut -d= -f2-)
[ -n "$ADMIN_CRED" ] || die 1 "STALWART_RECOVERY_ADMIN not set in $STALWART_ENV"
AUTH_HEADER="Authorization: Basic $(printf '%s' "$ADMIN_CRED" | base64 -w0)"
unset ADMIN_CRED

# curl_auth <curl args...>  — reads the auth header from a stdin config
curl_auth() {
    printf 'header = "%s"\n' "$AUTH_HEADER" | curl -K - "$@"
}

# jmap <json-file>  — POST a JMAP request, echo the response body
jmap() {
    curl_auth -s --max-time 30 -X POST \
        -H 'Content-Type: application/json' \
        --data-binary "@$1" "${JMAP_BASE}/jmap/"
}

serial_of_file() {
    openssl x509 -in "$1" -noout -serial 2>/dev/null | cut -d= -f2
}

# serial_on_port <port> — serial actually served on the wire, or empty
serial_on_port() {
    local port=$1 starttls=()
    [ "$port" = "25" ] && starttls=(-starttls smtp)
    timeout "$OPENSSL_TIMEOUT" openssl s_client "${starttls[@]}" \
        -connect "${MAIL_HOST}:${port}" -servername "$MAIL_HOST" \
        </dev/null 2>/dev/null \
        | openssl x509 -noout -serial 2>/dev/null | cut -d= -f2
}

# ---------------------------------------------------------------
# 1. Idempotency gate. This is the whole point of the rewrite: when
#    nothing changed, do nothing, and above all do not restart.
# ---------------------------------------------------------------
[ -r "$SRC_CRT" ] || die 1 "certificate not readable: $SRC_CRT"
[ -r "$SRC_KEY" ] || die 1 "private key not readable: $SRC_KEY"

DISK_SERIAL=$(serial_of_file "$SRC_CRT")
[ -n "$DISK_SERIAL" ] || die 1 "could not parse a serial out of $SRC_CRT"

SERVED_SERIAL=$(serial_on_port "$PROBE_PORT" || true)

log "cert on disk : serial=$DISK_SERIAL ($SRC_CRT)"
if [ -n "$SERVED_SERIAL" ]; then
    log "cert served  : serial=$SERVED_SERIAL (${MAIL_HOST}:${PROBE_PORT})"
else
    log "cert served  : UNREADABLE on ${MAIL_HOST}:${PROBE_PORT}"
fi

if [ -n "$SERVED_SERIAL" ] && [ "$DISK_SERIAL" = "$SERVED_SERIAL" ]; then
    log "in sync — nothing to do, no restart"
    log "RESULT: ok (no action)"
    exit 0
fi

if [ -z "$SERVED_SERIAL" ]; then
    log "WARNING: cannot confirm what is being served; treating as out of sync"
fi
log "out of sync — proceeding"

# ---------------------------------------------------------------
# 2. Cert and key must be a matching pair before anything is written.
# ---------------------------------------------------------------
PUB_FROM_CRT=$(openssl x509 -in "$SRC_CRT" -noout -pubkey 2>/dev/null | openssl sha256 | awk '{print $NF}')
PUB_FROM_KEY=$(openssl pkey -in "$SRC_KEY" -pubout 2>/dev/null | openssl sha256 | awk '{print $NF}')

if [ -z "$PUB_FROM_CRT" ] || [ -z "$PUB_FROM_KEY" ]; then
    die 2 "could not derive public keys for the pair check"
fi
if [ "$PUB_FROM_CRT" != "$PUB_FROM_KEY" ]; then
    log "pubkey(cert) = $PUB_FROM_CRT"
    log "pubkey(key)  = $PUB_FROM_KEY"
    die 2 "certificate and private key are NOT a pair — refusing to write"
fi
log "pair check   : ok (pubkey sha256 $PUB_FROM_CRT)"

# ---------------------------------------------------------------
# 3. Locate the certificate object by SAN. The object id is not
#    hardcoded: it is stable today but nothing guarantees it.
# ---------------------------------------------------------------
SESSION_JSON="$TMPDIR_RUN/session.json"
curl_auth -sL --max-time 30 -o "$SESSION_JSON" "${JMAP_BASE}/.well-known/jmap" \
    || die 1 "could not fetch the JMAP session"

ACCOUNT_ID=$(python3 -c "
import json,sys
d=json.load(open('$SESSION_JSON'))
print(d.get('primaryAccounts',{}).get('urn:stalwart:jmap',''))
" 2>/dev/null || true)
[ -n "$ACCOUNT_ID" ] || die 1 "could not resolve the urn:stalwart:jmap account id"
log "account id   : $ACCOUNT_ID"

QUERY_REQ="$TMPDIR_RUN/query.json"
cat > "$QUERY_REQ" <<EOF
{"using":["urn:stalwart:jmap"],"methodCalls":[["x:Certificate/query",
 {"accountId":"$ACCOUNT_ID","filter":{"subjectAlternativeNames":"$MAIL_HOST"}},"c0"]]}
EOF

QUERY_RESP="$TMPDIR_RUN/query-resp.json"
jmap "$QUERY_REQ" > "$QUERY_RESP" || die 3 "x:Certificate/query call failed"

CERT_IDS=$(python3 -c "
import json
r=json.load(open('$QUERY_RESP'))['methodResponses'][0]
if r[0]!='x:Certificate/query':
    raise SystemExit('')
print(' '.join(r[1].get('ids',[])))
" 2>/dev/null || true)

CERT_COUNT=$(echo "$CERT_IDS" | wc -w)
if [ "$CERT_COUNT" -eq 0 ]; then
    die 3 "no x:Certificate object has SAN $MAIL_HOST — refusing to guess"
fi
if [ "$CERT_COUNT" -gt 1 ]; then
    die 3 "$CERT_COUNT x:Certificate objects match SAN $MAIL_HOST ($CERT_IDS) — refusing to guess"
fi
CERT_ID=$(echo "$CERT_IDS" | tr -d ' ')
log "cert object  : id=$CERT_ID (matched on SAN $MAIL_HOST)"

# ---------------------------------------------------------------
# 4. Dry run stops here, having done every read-only check.
# ---------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
    log "WOULD update x:Certificate/$CERT_ID to serial $DISK_SERIAL"
    log "WOULD verify the live config picked it up"
    log "WOULD restart $SERVICE and re-check ports: $VERIFY_PORTS"
    log "RESULT: dry-run (no changes made)"
    exit 0
fi

# ---------------------------------------------------------------
# 5. Write the new cert + key into the live config.
# ---------------------------------------------------------------
SET_REQ="$TMPDIR_RUN/set.json"
python3 - "$SET_REQ" "$SRC_CRT" "$SRC_KEY" "$ACCOUNT_ID" "$CERT_ID" <<'PYEOF'
import json, os, sys
out, crt_path, key_path, account_id, cert_id = sys.argv[1:6]
crt = open(crt_path).read()
key = open(key_path).read()
if 'BEGIN CERTIFICATE' not in crt or 'BEGIN' not in key:
    sys.exit('source files do not look like PEM')
req = {"using": ["urn:stalwart:jmap"], "methodCalls": [[
    "x:Certificate/set",
    {"accountId": account_id, "update": {cert_id: {
        "certificate": {"@type": "Text", "value": crt},
        "privateKey":  {"@type": "Text", "secret": key},
    }}}, "c0"]]}
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    json.dump(req, f)
PYEOF
[ -s "$SET_REQ" ] || die 4 "could not build the x:Certificate/set request"

SET_RESP="$TMPDIR_RUN/set-resp.json"
jmap "$SET_REQ" > "$SET_RESP" || die 4 "x:Certificate/set call failed"
rm -f "$SET_REQ"

SET_OK=$(python3 -c "
import json
r=json.load(open('$SET_RESP'))['methodResponses'][0]
print('yes' if r[0]=='x:Certificate/set' and '$CERT_ID' in (r[1].get('updated') or {}) else 'no')
" 2>/dev/null || echo no)
[ "$SET_OK" = "yes" ] || die 4 "x:Certificate/set did not report the object as updated"
log "config write : accepted for $CERT_ID"

# Confirm the live config really holds the new serial before we take
# the service down. Reading it back is cheap; a wrong restart is not.
GET_REQ="$TMPDIR_RUN/get.json"
cat > "$GET_REQ" <<EOF
{"using":["urn:stalwart:jmap"],"methodCalls":[["x:Certificate/get",
 {"accountId":"$ACCOUNT_ID","ids":["$CERT_ID"],"properties":["id","certificate"]},"c0"]]}
EOF
GET_RESP="$TMPDIR_RUN/get-resp.json"
jmap "$GET_REQ" > "$GET_RESP" || die 4 "read-back x:Certificate/get failed"

LIVE_PEM="$TMPDIR_RUN/live.pem"
python3 -c "
import json
r=json.load(open('$GET_RESP'))['methodResponses'][0][1]['list'][0]
open('$LIVE_PEM','w').write(r['certificate']['value'])
" 2>/dev/null || die 4 "could not extract the certificate from the read-back"

LIVE_SERIAL=$(serial_of_file "$LIVE_PEM")
if [ "$LIVE_SERIAL" != "$DISK_SERIAL" ]; then
    die 4 "live config holds serial $LIVE_SERIAL, expected $DISK_SERIAL — NOT restarting"
fi
log "config check : live config now holds serial $LIVE_SERIAL"

# ---------------------------------------------------------------
# 6. Restart. Required: the config write alone does not swap the
#    TLS context already loaded in memory.
# ---------------------------------------------------------------
log "restarting $SERVICE (required: config write does not swap the live TLS context)"
systemctl restart "$SERVICE" || die 5 "systemctl restart $SERVICE failed"
sleep "$RESTART_SETTLE_SECONDS"

if ! systemctl is-active --quiet "$SERVICE"; then
    die 5 "$SERVICE is not active after restart"
fi

# ---------------------------------------------------------------
# 7. Verify on the wire. The exit code reflects reality: if any port
#    still serves the old cert, this is a failure, not a success.
# ---------------------------------------------------------------
FAILED=""
for port in $VERIFY_PORTS; do
    got=$(serial_on_port "$port" || true)
    if [ "$got" = "$DISK_SERIAL" ]; then
        log "verify :$port  ok   serial=$got"
    else
        log "verify :$port  FAIL serial=${got:-<unreadable>} expected=$DISK_SERIAL"
        FAILED="$FAILED $port"
    fi
done

if [ -n "$FAILED" ]; then
    log "RESULT: FAILED — ports still wrong:$FAILED"
    log "The old certificate may still be served. Investigate before the next renewal."
    exit 5
fi

log "RESULT: ok (synced to serial $DISK_SERIAL and verified on: $VERIFY_PORTS)"
exit 0
