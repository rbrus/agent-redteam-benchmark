#!/usr/bin/env bash
# sixi-scanner against the benchmark gateway.  Usage: tools/sixi-scanner/run.sh <run_dir> [--smoke]
#   SIXI_SCANNER_BIN   path to the sixi-scanner binary (default: sixi-scanner on PATH)
#   SIXI_LABEL         gateway label (default sixi-scanner; lets a second build run as e.g. sixi-scanner-next)
#   SIXI_PHASE_A_ONLY  1 = skip the adaptive phase (Phase B)
#   SIXI_CONTEXT       target-context JSON (default tools/sixi-scanner/context.json; "" = none)
#   SIXI_TIMEOUT       seconds to wait for one reply (default 90; sixi's own default is 30)
# Writes $RUN_DIR/$LABEL/native/phases.txt: one row per phase with its exit code, report size and
# the signal that killed it, so an interrupted run is visible instead of reading as "0 attempts".
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
# Target context: what the agent is for and whose data it may show.  With a context present, the
# default --confirm asks the judge model whether a marker hit really violated the agent's stated
# rules (and screens a break whose only data is the caller's own) instead of filing it as-is, which
# is the difference between a plausible-looking flag and one a reviewer will stand behind.  The
# shipped context is the default so a fresh checkout gets that; set SIXI_CONTEXT="" to scan bare.
CTX=(); CTX_FILE="${SIXI_CONTEXT-tools/sixi-scanner/context.json}"; [ -n "$CTX_FILE" ] && CTX=(--context "$CTX_FILE")
# The default 30s gave up on three sends in the 2026-09-24 run while the gateway was still
# answering: the attempt was recorded as a failure, so a turn the ground truth scored was a turn sixi
# never read. Patient by default here — only one send in ~500 needed it — and SIXI_TIMEOUT overrides.
# --timeout is a Go duration, so a bare number needs an `s` appended.
case "${SIXI_TIMEOUT:-90}" in
  *[a-z]) SLOW=(--timeout "${SIXI_TIMEOUT:-90}") ;;
  *)      SLOW=(--timeout "${SIXI_TIMEOUT:-90}s") ;;
esac
"$BIN" version > "$OUT/version.txt" 2>&1 || true
date -u +%FT%TZ > "$OUT/started_at"
: > "$OUT/phases.txt"

# Run one phase.  The scanner writes its report to stdout, so a phase that dies before the final
# JSON serialisation leaves a zero-byte file — which used to be swallowed by `|| true` and reported
# as a clean run with 0 attempts.  Record the real exit status (and the killing signal) instead, so
# an interrupted or OOM-killed phase can never masquerade as "the target resisted everything".
phase() { # phase <name> <output> <command...>
  local name="$1" out="$2"; shift 2
  local rc=0
  "$@" > "$out" 2> "$OUT/$name.log" || rc=$?
  local note="ok"
  if [ "$rc" -ge 128 ]; then
    local sig=$((rc - 128)); note="KILLED by signal $sig (SIG$(kill -l "$sig" 2>/dev/null || echo "?"))"
  elif [ "$rc" -ne 0 ]; then
    note="FAILED exit $rc"
  elif [ ! -s "$out" ]; then
    note="FAILED empty report, exit 0"
  fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$rc" "$(stat -c %s "$out" 2>/dev/null || echo 0)" "$note" >> "$OUT/phases.txt"
  if [ "$rc" -ne 0 ] || [ ! -s "$out" ]; then
    echo "sixi-scanner [$LABEL]: phase '$name' did not produce a report — $note (see $OUT/$name.log)" >&2
  fi
}

if [ "$SMOKE" = "--smoke" ]; then
  phase smoke "$OUT/flat.json" "$BIN" scan --target "$TARGET" --agent --agent-name data_exfiltration \
    --attempts 1 --fail-on none --format json
else
  # Phase A: the whole technique library, each payload rewritten by the attacker model, 2 attempts.
  phase flat "$OUT/flat.json" "$BIN" scan --target "$TARGET" "${CTX[@]}" "${SLOW[@]}" --attempts 2 --fail-on none --format json
  if [ "${SIXI_PHASE_A_ONLY:-0}" != "1" ]; then
    # Phase B: the multi-turn adaptive agents, up to 10 turns per technique.
    phase adaptive "$OUT/adaptive.json" "$BIN" scan --target "$TARGET" "${CTX[@]}" "${SLOW[@]}" --adaptive --turns 10 \
      --fail-on none --format json
  fi
fi
date -u +%FT%TZ > "$OUT/finished_at"
python3 tools/sixi-scanner/parse_results.py "$RUN_DIR" "$LABEL"
