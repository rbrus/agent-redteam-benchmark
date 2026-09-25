#!/usr/bin/env bash
# Azure AI Red Teaming Agent against the benchmark gateway.  Usage: tools/azure-redteam/run.sh <run_dir> [--smoke]
set -euo pipefail
cd "$(dirname "$0")/../.."
RUN_DIR="${1:?run_dir}"; SMOKE="${2:-}"
set -a; source .env; set +a
LABEL=azure-redteam; [ "$SMOKE" = "--smoke" ] && LABEL=azure-redteam-smoke
mkdir -p "$RUN_DIR/azure-redteam/native"
venvs/azure-redteam/bin/python -W ignore tools/azure-redteam/run_azure_redteam.py "$RUN_DIR/azure-redteam/native" "$LABEL" $SMOKE 2>&1 | tee "$RUN_DIR/azure-redteam/native/console.log"
venvs/azure-redteam/bin/python tools/azure-redteam/parse_results.py "$RUN_DIR" || true
