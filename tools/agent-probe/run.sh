#!/usr/bin/env bash
# agent-probe against the benchmark gateway.  Usage: tools/agent-probe/run.sh <run_dir> [--smoke]
#   AGENT_PROBE_BIN  path to the agent-probe binary (go install github.com/rbrus/agent-probe/cmd/agent-probe@latest)
set -euo pipefail
cd "$(dirname "$0")/../.."
RUN_DIR="${1:?run_dir}"; SMOKE="${2:-}"
set -a; source .env; set +a
BIN="${AGENT_PROBE_BIN:-agent-probe}"
LABEL=agent-probe; [ "$SMOKE" = "--smoke" ] && LABEL=agent-probe-smoke
OUT="$RUN_DIR/agent-probe/native"; mkdir -p "$OUT"
# The JSON report carries no version, so record the binary's own answer next to it.
"$BIN" version > "$OUT/version.txt" 2>&1 || { echo "agent-probe: '$BIN version' failed" >&2; exit 1; }
# agent-probe has a fixed 12-probe battery; smoke and full are the same run.
"$BIN" scan --target "${BENCH_GATEWAY_URL:-http://127.0.0.1:8791}/t/$LABEL/chat" --fail-on none \
  --format json -o "$OUT/report.json" > "$OUT/console.log" 2>&1 || true
python3 tools/agent-probe/parse_results.py "$RUN_DIR"
