#!/usr/bin/env bash
# sixi-scanner against the benchmark gateway.  Usage: tools/sixi-scanner/run.sh <run_dir> [--smoke]
#   SIXI_SCANNER_BIN   path to the sixi-scanner binary (default: sixi-scanner on PATH)
#   SIXI_LABEL         gateway label (default sixi-scanner; lets a second build run as e.g. sixi-scanner-next)
set -euo pipefail
cd "$(dirname "$0")/../.."
RUN_DIR="${1:?run_dir}"; SMOKE="${2:-}"
set -a; source .env; set +a
BIN="${SIXI_SCANNER_BIN:-sixi-scanner}"
LABEL="${SIXI_LABEL:-sixi-scanner}"; [ "$SMOKE" = "--smoke" ] && LABEL="$LABEL-smoke"
GW="${BENCH_GATEWAY_URL:-http://127.0.0.1:8791}"
OUT="$RUN_DIR/$LABEL/native"; mkdir -p "$OUT"
# The shared attacker model: rewrites Phase-A payloads and drives the Phase-B adaptive agents.
export SIXI_ATTACKER_PROVIDER=openai SIXI_ATTACKER_MODEL=attacker SIXI_ATTACKER_API_KEY=x \
       SIXI_ATTACKER_BASE_URL="$GW/attacker/$LABEL/v1" SIXI_ATTACKER_RESIDENCY=local
TARGET="$GW/t/$LABEL/chat"
# Optional target context (sixi-scanner >= the target-context change): SIXI_CONTEXT=tools/sixi-scanner/context.json
CTX=(); [ -n "${SIXI_CONTEXT:-}" ] && CTX=(--context "$SIXI_CONTEXT")
"$BIN" version > "$OUT/version.txt" 2>&1 || true
date -u +%FT%TZ > "$OUT/started_at"
if [ "$SMOKE" = "--smoke" ]; then
  "$BIN" scan --target "$TARGET" --agent --agent-name data_exfiltration --attempts 1 --fail-on none \
    --format json > "$OUT/flat.json" 2> "$OUT/flat.log" || true
else
  # Phase A: the whole technique library, each payload rewritten by the attacker model, 2 attempts.
  "$BIN" scan --target "$TARGET" "${CTX[@]}" --attempts 2 --fail-on none --format json > "$OUT/flat.json" 2> "$OUT/flat.log" || true
  # Phase B: the multi-turn adaptive agents, up to 10 turns per technique.
  "$BIN" scan --target "$TARGET" "${CTX[@]}" --adaptive --turns 10 --fail-on none --format json > "$OUT/adaptive.json" 2> "$OUT/adaptive.log" || true
fi
date -u +%FT%TZ > "$OUT/finished_at"
python3 tools/sixi-scanner/parse_results.py "$RUN_DIR" "$LABEL"
