#!/usr/bin/env bash
# Run promptfoo red teaming against the benchmark gateway.
#
#   tools/promptfoo/run.sh [label] [out_dir]
#
#   label     gateway attribution label; "promptfoo" for the benchmark run, "promptfoo-smoke" for
#             tests (default: promptfoo)
#   out_dir   where generated tests, results and logs go (default: tools/promptfoo/out/<label>-<ts>)
#
# Environment knobs (optional):
#   NUM_TESTS=<n>      override redteam.numTests from promptfooconfig.yaml
#   FILTER_SAMPLE=<n>  run only a random sample of n generated tests (smoke)
#   SKIP_GENERATE=1    reuse <out_dir>/redteam.yaml
#
# Two phases, both logged: `redteam generate` (attacker model only, no target turns) and
# `redteam eval` (target turns). Needs the gateway running (scripts/gateway.sh).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BENCH_TOOL="${1:-promptfoo}"
OUT="${2:-$HERE/out/$BENCH_TOOL-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

# shellcheck source=env.sh
source "$HERE/env.sh"
cd "$HERE"

PF=(npx --no-install promptfoo)
curl -fsS "$BENCH_GATEWAY/health" >/dev/null || { echo "gateway not reachable at $BENCH_GATEWAY" >&2; exit 1; }

VERSION="$("${PF[@]}" --version 2>/dev/null | tail -1)"
echo "promptfoo $VERSION  label=$BENCH_TOOL  out=$OUT"
cp promptfooconfig.yaml "$OUT/promptfooconfig.used.yaml"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
T0=$(date +%s)
MARK="$OUT/.start"; touch "$MARK"
echo "{\"tool\":\"promptfoo\",\"version\":\"$VERSION\",\"label\":\"$BENCH_TOOL\",\"started\":\"$(ts)\"}" >"$OUT/run-meta.json"

if [ "${SKIP_GENERATE:-0}" != "1" ]; then
  gen_args=(redteam generate -c promptfooconfig.yaml -o "$OUT/redteam.yaml" --force --no-progress-bar)
  [ -n "${NUM_TESTS:-}" ] && gen_args+=(-n "$NUM_TESTS")
  echo "[$(ts)] generate: ${gen_args[*]}"
  "${PF[@]}" "${gen_args[@]}" 2>&1 | grep -v -e ExperimentalWarning -e 'trace-warnings' | tee "$OUT/generate.log"
fi
T1=$(date +%s)

eval_args=(redteam eval -c "$OUT/redteam.yaml" -o "$OUT/results.json" "$OUT/results.html"
  -j 4 --no-share --no-cache --no-progress-bar --no-table)
[ -n "${FILTER_SAMPLE:-}" ] && eval_args+=(--filter-sample "$FILTER_SAMPLE")
echo "[$(ts)] eval: ${eval_args[*]}"
set +e
"${PF[@]}" "${eval_args[@]}" 2>&1 | grep -v -e ExperimentalWarning -e 'trace-warnings' | tee "$OUT/eval.log"
rc=${PIPESTATUS[0]}
set -e
T2=$(date +%s)

# promptfoo exits 100 when any test "fails" (= a vulnerability was flagged); that is a result, not
# a crash.
python3 - "$OUT/run-meta.json" "$VERSION" "$BENCH_TOOL" "$T0" "$T1" "$T2" "$rc" <<'PY'
import json, sys
path, version, label, t0, t1, t2, rc = sys.argv[1:]
m = json.load(open(path))
m.update(finished_epoch=int(t2), generate_seconds=int(t1) - int(t0), eval_seconds=int(t2) - int(t1), eval_exit_code=int(rc))
json.dump(m, open(path, "w"), indent=2)
PY
mkdir -p "$OUT/promptfoo-logs"
find "$PROMPTFOO_LOG_DIR" -type f -newer "$MARK" -exec cp {} "$OUT/promptfoo-logs/" \; 2>/dev/null || true

if [ -f "$OUT/results.json" ]; then
  python3 "$HERE/export_flags.py" "$OUT/results.json" "$OUT/flags.jsonl"
fi
echo "[$(ts)] done (eval exit $rc) -> $OUT"
[ "$rc" = 0 ] || [ "$rc" = 100 ]
