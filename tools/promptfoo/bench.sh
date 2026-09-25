#!/usr/bin/env bash
# Benchmark-harness entry point: same interface as every other tool.
#   tools/promptfoo/bench.sh <run_dir> [--smoke]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$(mkdir -p "${1:?run_dir}" && cd "$1" && pwd)"; SMOKE="${2:-}"
LABEL=promptfoo
if [ "$SMOKE" = "--smoke" ]; then LABEL=promptfoo-smoke; export NUM_TESTS=1 FILTER_SAMPLE=12; fi
"$HERE/run.sh" "$LABEL" "$RUN_DIR/promptfoo/native"
python3 "$HERE/to_self_report.py" "$RUN_DIR"
