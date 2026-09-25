#!/usr/bin/env bash
# Start the benchmark gateway in front of the Foundry agent.  Usage: scripts/gateway.sh [run_dir]
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
export BENCH_LOG_DIR="$(pwd)/${1:-runs/current}/gateway"
cd target
exec ../.venv/bin/uvicorn gateway:app --host 127.0.0.1 --port "${BENCH_GATEWAY_PORT:-8791}" --log-level warning
