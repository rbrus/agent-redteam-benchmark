#!/usr/bin/env bash
# Full benchmark: every tool against the same gateway, in three lanes that share the attacker model.
#   scripts/run_all.sh <run_dir>
# Needs the gateway running with the same run_dir:  scripts/gateway.sh <run_dir>
set -uo pipefail
cd "$(dirname "$0")/.."
RUN="${1:?run_dir}"; mkdir -p "$RUN/logs"
set -a; source .env; set +a
step() { local name=$1; shift; echo "[$(date -u +%FT%TZ)] start $name" >> "$RUN/logs/timeline.log"
         "$@" > "$RUN/logs/$name.log" 2>&1; echo "[$(date -u +%FT%TZ)] end   $name rc=$?" >> "$RUN/logs/timeline.log"; }
lane_a() { step promptfoo tools/promptfoo/bench.sh "$RUN"; step deepteam tools/deepteam/run.sh "$RUN"; }
lane_b() { step pyrit tools/pyrit/run.sh "$RUN"; step garak tools/garak/run.sh "$RUN"; }
lane_c() { step agent-probe env AGENT_PROBE_BIN="${AGENT_PROBE_BIN:-venvs/agent-probe}" tools/agent-probe/run.sh "$RUN"
           step azure-redteam tools/azure-redteam/run.sh "$RUN"
           step sixi-scanner env SIXI_SCANNER_BIN="${SIXI_SCANNER_BIN:-venvs/sixi-scanner-baseline}" tools/sixi-scanner/run.sh "$RUN"; }
lane_a & lane_b & lane_c & wait
echo "[$(date -u +%FT%TZ)] all done" >> "$RUN/logs/timeline.log"
