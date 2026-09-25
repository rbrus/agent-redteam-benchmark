#!/usr/bin/env bash
# Run NVIDIA garak against the benchmark gateway.
#
#   tools/garak/run.sh <run_dir> [--smoke]
#
# Native garak output (report.jsonl, hitlog.jsonl, report.html, console log) goes to
# <run_dir>/garak/native/, then parse_results.py writes <run_dir>/garak/self_report.json.
#
# Environment:
#   BENCH_GATEWAY_URL   gateway base URL (default http://127.0.0.1:8791)
#   GARAK_TOOL_LABEL    tool label used in gateway URLs (default: garak, or garak-smoke with --smoke)
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <run_dir> [--smoke]" >&2
  exit 2
fi
RUN_DIR=$1
shift
MODE=full
if [[ "${1:-}" == "--smoke" ]]; then MODE=smoke; fi

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

GATEWAY=${BENCH_GATEWAY_URL:-http://127.0.0.1:8791}
GATEWAY=${GATEWAY%/}
if [[ $MODE == smoke ]]; then LABEL=${GARAK_TOOL_LABEL:-garak-smoke}; else LABEL=${GARAK_TOOL_LABEL:-garak}; fi
PY="$ROOT/venvs/garak/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "garak venv not found: run 'uv venv venvs/garak && uv pip install --python venvs/garak garak' in the repo root" >&2
  exit 1
fi

mkdir -p "$RUN_DIR"
RUN_DIR=$(cd "$RUN_DIR" && pwd)
OUT="$RUN_DIR/garak"
NATIVE="$OUT/native"
mkdir -p "$NATIVE"

# Materialise the config for this run (gateway URL, tool label, report dir).
CFG="$NATIVE/garak.config.yaml"
sed -e "s#__GATEWAY__#${GATEWAY}#g" -e "s#__TOOL__#${LABEL}#g" -e "s#__REPORT_DIR__#${NATIVE}#g" \
  "$HERE/${MODE}.yaml" > "$CFG"
chmod 600 "$CFG"

if ! curl -fsS "$GATEWAY/health" > /dev/null; then
  echo "gateway not reachable at $GATEWAY/health" >&2
  exit 1
fi

# garak's OpenAI-compatible generator also looks for a key in the environment; the gateway ignores it.
export OPENAICOMPATIBLE_API_KEY=x
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1

STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[garak] mode=$MODE label=$LABEL gateway=$GATEWAY out=$NATIVE"
set +e
"$PY" -m garak --config "$CFG" 2>&1 | tee "$NATIVE/garak.console.log"
RC=${PIPESTATUS[0]}
set -e
FINISHED=$(date -u +%Y-%m-%dT%H:%M:%SZ)

VERSION=$("$PY" -c 'import garak; print(garak.__version__)')
cat > "$OUT/run_meta.json" <<EOF
{"mode": "$MODE", "label": "$LABEL", "gateway": "$GATEWAY", "started_at": "$STARTED",
 "finished_at": "$FINISHED", "exit_code": $RC, "tool_version": "$VERSION", "config": "${MODE}.yaml"}
EOF

"$PY" "$HERE/parse_results.py" "$RUN_DIR"
exit "$RC"
