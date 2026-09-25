#!/usr/bin/env bash
# DeepTeam against the benchmark gateway.  Usage: tools/deepteam/run.sh <run_dir> [--smoke]
set -euo pipefail
cd "$(dirname "$0")/../.."
RUN_DIR="${1:?run_dir}"; SMOKE="${2:-}"
set -a; source .env; set +a
LABEL=deepteam; [ "$SMOKE" = "--smoke" ] && LABEL=deepteam-smoke
export DEEPTEAM_TELEMETRY_OPT_OUT=YES DEEPEVAL_TELEMETRY_OPT_OUT=YES OPENAI_API_KEY=unused
mkdir -p "$RUN_DIR/deepteam/native"
venvs/deepteam/bin/python -W ignore tools/deepteam/run_deepteam.py "$RUN_DIR/deepteam/native" "$LABEL" $SMOKE 2>&1 | tee "$RUN_DIR/deepteam/native/console.log"
venvs/deepteam/bin/python tools/deepteam/parse_results.py "$RUN_DIR"
