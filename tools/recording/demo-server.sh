# Sourced by tools/record-screenshots and tools/record-intro: bring up the demo app
# for one recording, and take it down again however the recording ends.
#
# Its own port and its own throwaway data root, so it can neither collide with a
# `tools/run-demo` you already have open on 8011 nor rebuild that one's root under it.
# $RECORD_PORT overrides the port.

RECORD_PORT="${RECORD_PORT:-8015}"
BASE="http://127.0.0.1:${RECORD_PORT}"
export JOBSTUDIO_DEMO_ROOT="${TMPDIR:-/tmp}/jobstudio-recording"

need() { command -v "$1" >/dev/null || { echo "ERROR: $1 not found. $2" >&2; exit 1; }; }

check_node() {
    need node "Node 22 or later is needed to drive Chrome."
    node -e 'process.exit(typeof WebSocket === "function" ? 0 : 1)' || {
        echo "ERROR: node $(node --version) has no built-in WebSocket — Node 22 or later is needed." >&2
        exit 1
    }
}

start_demo() {
    if lsof -ti "tcp:${RECORD_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "ERROR: port ${RECORD_PORT} is busy. Set \$RECORD_PORT to a free one." >&2
        exit 1
    fi
    DEMO_LOG="$(mktemp)"
    tools/run-demo "$RECORD_PORT" >"$DEMO_LOG" 2>&1 &
    trap stop_demo EXIT
    for _ in $(seq 1 120); do
        curl -s -o /dev/null "$BASE/" && return 0
        sleep 0.5
    done
    echo "ERROR: the demo app did not come up on ${RECORD_PORT}. Its log:" >&2
    cat "$DEMO_LOG" >&2
    exit 1
}

# runserver_plus forks a reloader child, so stopping the job alone can leave the
# server listening: stop whatever holds the port, which this script just claimed.
stop_demo() {
    lsof -ti "tcp:${RECORD_PORT}" -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
    kill %1 2>/dev/null || true
    wait 2>/dev/null || true
    # run-demo writes this marker into every root it builds; nothing else has it.
    [ -f "$JOBSTUDIO_DEMO_ROOT/.jobstudio-demo" ] && rm -rf "$JOBSTUDIO_DEMO_ROOT"
    rm -f "$DEMO_LOG"
}
