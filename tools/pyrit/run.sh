#!/usr/bin/env bash
# Run Microsoft PyRIT against the benchmark gateway and produce self_report.json.
#
# Usage:
#   tools/pyrit/run.sh <run_dir> [--smoke]
#
#   <run_dir>   output directory; native output goes to <run_dir>/pyrit/native/,
#               the self-report to <run_dir>/pyrit/self_report.json
#   --smoke     short run, <= 40 target turns total (uses gateway tool label "pyrit-smoke")
#
# Settings come from the repo .env (sourced, never hardcoded). Gateway base URL is taken from
# BENCH_GATEWAY_URL (default http://127.0.0.1:8791).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PY="$REPO_ROOT/venvs/pyrit/bin/python"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <run_dir> [--smoke]" >&2
  exit 2
fi

RUN_DIR="$1"; shift || true
SMOKE=""
LABEL="pyrit"
for arg in "$@"; do
  case "$arg" in
    --smoke) SMOKE="--smoke"; LABEL="pyrit-smoke" ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

if [[ ! -x "$VENV_PY" ]]; then
  echo "error: venv missing. Run: uv venv venvs/pyrit && uv pip install --python venvs/pyrit pyrit" >&2
  exit 1
fi

# Load .env (endpoints/keys/model) without leaking it into the environment permanently.
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

export BENCH_GATEWAY_URL="${BENCH_GATEWAY_URL:-http://127.0.0.1:8791}"
export PYRIT_TOOL_LABEL="$LABEL"

mkdir -p "$RUN_DIR/pyrit/native"

echo "[pyrit] gateway=$BENCH_GATEWAY_URL label=$LABEL smoke=${SMOKE:-no} run_dir=$RUN_DIR"
"$VENV_PY" "$SCRIPT_DIR/pyrit_run.py" "$RUN_DIR" --label "$LABEL" $SMOKE
"$VENV_PY" "$SCRIPT_DIR/parse_results.py" "$RUN_DIR"
echo "[pyrit] self_report: $RUN_DIR/pyrit/self_report.json"
