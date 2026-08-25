#!/usr/bin/env bash
# Bring up everything one stepped nttd session needs, in order, and tear it down on Ctrl-C.
#
#   ./apps/nttd/run_all.sh                          # air, tier 1, stepped
#   ./apps/nttd/run_all.sh --mode rail              # rail instead
#   ./apps/nttd/run_all.sh --tier t2 --fresh        # tier 2, playbooks reset from their seeds
#   ./apps/nttd/run_all.sh --sessions 3             # three sessions back to back, learning between
#
# FOUR PROCESSES, and the order matters:
#
#   1. `nttd server`    the engine's HTTP API on :8000. Runs no game by itself; one server serves
#                       any number of sessions, so it is started once and left up.
#   2. `nttd benchmark` creates a session, draws its world, starts OpenTTD on it, prints the
#                       SESSION ID and PARTICIPANT TOKEN, then waits for the end condition. It
#                       does not play.
#   3. `ns run`         the neuro-san server on :8085, serving the four nttd networks, plus NSFlow
#                       on :4175 where every tool call and its arguments are visible live.
#
# PORTS are deliberately 8085 and 4175, not the studio's usual 8080 and 4173. Those two are
# commonly already held — by another studio, a dev server, anything — and a port collision
# surfaces as a server that half-starts, which reads like a config error and is not one.
# Exported below rather than only set in .env, so they hold even with no .env present.
#   4. the runner       plays it, step by step, in the foreground.
#
# Steps 2 and 4 are the pair that has to agree: the runner needs the id and token that benchmark
# minted, and this script scrapes them from its output rather than making the operator carry them
# between terminals.
#
# STEPPED ONLY. Every config named below is a `_stepped` one. In realtime the clock runs whatever
# the agent does, which makes a slow turn a lost game month and every figure in the playbooks
# incomparable; the runner checks the mode and refuses rather than playing it badly.

set -euo pipefail

STUDIO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NTTD_DIR="${NTTD_DIR:-$STUDIO/nttd}"
WORKBENCH="${WORKBENCH:-$STUDIO/nttd-workbench}"
LOG_DIR="$STUDIO/logs/nttd"
mkdir -p "$LOG_DIR"

MODE="air"
TIER="t1"
SESSIONS=1
FRESH=""
EXTRA=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)     MODE="$2"; shift 2 ;;
        --tier)     TIER="$2"; shift 2 ;;
        --sessions) SESSIONS="$2"; shift 2 ;;
        --fresh)    FRESH="--fresh"; shift ;;
        *)          EXTRA+=("$1"); shift ;;
    esac
done

case "$TIER" in
    t1) CONF="config/benchmark/t1_256_flat_1001_stepped.conf" ;;
    t2) CONF="config/benchmark/t2_256_flat_1001_stepped.conf" ;;
    t3) CONF="config/benchmark/t3_512_hilly_2001_stepped.conf" ;;
    t4) CONF="config/benchmark/t4_512_hilly_2001_stepped.conf" ;;
    *)  echo "unknown tier '$TIER' (t1..t4)"; exit 1 ;;
esac
NETWORK="nttd_${MODE}_player"

[[ -d "$NTTD_DIR" ]]  || { echo "nttd engine not found at $NTTD_DIR"; exit 1; }
[[ -d "$WORKBENCH" ]] || { echo "nttd-workbench not found at $WORKBENCH (the game tools live there)"; exit 1; }
[[ -f "$NTTD_DIR/$CONF" ]] || { echo "scenario not found: $NTTD_DIR/$CONF"; exit 1; }

# The studio resolves `coded_tools.nttd.*` from here and `agents.neuro_san.coded_tools.*` from the
# workbench checkout. BOTH are needed: the player registries reference the workbench's game tools
# in place rather than copying them, so a fix there is a fix here.
export PYTHONPATH="$STUDIO:$WORKBENCH${PYTHONPATH:+:$PYTHONPATH}"
export AGENT_MANIFEST_FILE="${AGENT_MANIFEST_FILE:-registries/nttd/manifest.hocon}"
export AGENT_TOOL_PATH="${AGENT_TOOL_PATH:-coded_tools}"
export NTTD_API_URL="${NTTD_API_URL:-http://127.0.0.1:8000}"
export NEURO_SAN_SERVER_HTTP_PORT="${NEURO_SAN_SERVER_HTTP_PORT:-8085}"
export NSFLOW_PORT="${NSFLOW_PORT:-4175}"
NS_PORT="$NEURO_SAN_SERVER_HTTP_PORT"

echo "studio      $STUDIO"
echo "engine      $NTTD_DIR"
echo "game tools  $WORKBENCH (referenced in place)"
echo "scenario    $CONF"
echo "network     $NETWORK"
echo "sessions    $SESSIONS"
echo "agents      :$NS_PORT   nsflow :$NSFLOW_PORT   engine $NTTD_API_URL"
echo

PIDS=()
cleanup() {
    echo; echo "shutting down..."
    for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

start() {  # name, cwd, command
    echo "[$1] starting"
    ( cd "$2" && eval "$3" ) > "$LOG_DIR/$1.log" 2>&1 &
    PIDS+=($!)
}

wait_for() {  # url, what, seconds
    for _ in $(seq 1 "$3"); do
        curl -sf -m 2 "$1" >/dev/null 2>&1 && { echo "[$2] up"; return 0; }
        sleep 1
    done
    echo "[$2] did not come up; see $LOG_DIR"; return 1
}

# Leftovers from a previous run hold the ports and make the next start look like a config error.
pkill -f "nttd server"        2>/dev/null || true
pkill -f "neuro_san_studio"   2>/dev/null || true
pkill -f "nsflow"             2>/dev/null || true
sleep 1

# --- 1. the engine ------------------------------------------------------------------------
start "engine" "$NTTD_DIR" "uv run nttd server"
wait_for "$NTTD_API_URL/v1/public/actions" "engine" 90

# --- 2. the agent server ------------------------------------------------------------------
# Started BEFORE the world, so nothing slow happens after a live scored game has been created:
# a session whose clock is paused costs nothing to leave waiting, but a server that fails to load
# after the world exists has burned a session id.
start "studio" "$STUDIO" "python -m neuro_san_studio run"
for i in $(seq 1 90); do
    served="$(curl -sf -m 2 "http://localhost:$NS_PORT/api/v1/list" 2>/dev/null || true)"
    if echo "$served" | grep -q "$NETWORK" \
       && echo "$served" | grep -q "nttd_planner" \
       && echo "$served" | grep -q "nttd_watcher"; then
        echo "[studio] serving $NETWORK, nttd_planner, nttd_watcher after ${i}s"
        break
    fi
    [[ $i -eq 90 ]] && { echo "[studio] did not serve the networks; see $LOG_DIR/studio.log"; cleanup; }
    sleep 1
done

# --- 3 and 4. one world, then play it, per session ----------------------------------------
for round in $(seq 1 "$SESSIONS"); do
    echo; echo "================ session $round of $SESSIONS ================"
    BENCH_LOG="$LOG_DIR/benchmark.$round.log"
    start "benchmark.$round" "$NTTD_DIR" "uv run nttd benchmark --config $CONF"

    # Scrape the id and token benchmark printed, rather than making the operator copy them.
    # It generates a world and boots OpenTTD first, so this is a minute rather than instant.
    SESSION=""; TOKEN=""
    for _ in $(seq 1 300); do
        SESSION="$(grep -oE '[0-9]{8}-[0-9]{6}[a-z]{3}-[a-z]+-[a-z]+' "$BENCH_LOG" 2>/dev/null | head -1 || true)"
        TOKEN="$(grep -oE 'pt_[0-9a-f]{32}' "$BENCH_LOG" 2>/dev/null | head -1 || true)"
        [[ -n "$SESSION" && -n "$TOKEN" ]] && break
        sleep 1
    done
    [[ -n "$SESSION" && -n "$TOKEN" ]] || {
        echo "could not read a session id and token from $BENCH_LOG"
        echo "start it by hand and pass --session/--token to the runner"; cleanup
    }
    echo "session $SESSION"
    echo "token   ${TOKEN:0:11}..."   # truncated: a token in a shared terminal log is a leak

    # --fresh only on the FIRST round. Later rounds must keep the playbooks the previous round's
    # planner promoted into, or the learning loop resets every session and nothing compounds.
    ROUND_FRESH=""
    [[ $round -eq 1 ]] && ROUND_FRESH="$FRESH"

    cd "$STUDIO"
    python -m apps.nttd.runner \
        --session "$SESSION" --token "$TOKEN" --network "$NETWORK" \
        --scenario "$(basename "$CONF" .conf)" --new-session \
        $ROUND_FRESH ${EXTRA[@]+"${EXTRA[@]}"} || echo "(runner exited non-zero)"

    pkill -f "nttd benchmark" 2>/dev/null || true
    sleep 2
done

echo; echo "all sessions done. logs in $LOG_DIR"
echo "analysis:  cd $NTTD_DIR && uv run nttd analyze -s <session>"
echo "monitor:   cd $NTTD_DIR && uv run nttd monitor    then http://127.0.0.1:4281"
cleanup
