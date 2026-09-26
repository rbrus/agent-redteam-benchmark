#!/usr/bin/env python3
"""Live peek at the four benchmark targets while a run is in flight.

Reads only the gateway log (ground truth side): re-runs the CURRENT oracles on every logged turn
and counts. The judge's half of `violating_turns` needs scoring/judge.py, so this is a lower bound —
it shows oracle violations and the distinct oracle codes, which is target 1 outright and the
oracle part of target 4.

Usage: BENCH_CANARY=... python3 live_kpis.py runs/2026-09-26-validation [label]
"""
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "target"))
from oracles import SEVERITY, check_reply, check_tool_call  # noqa: E402

CANARY = os.environ.get("BENCH_CANARY", "")
run = Path(sys.argv[1])
label = sys.argv[2] if len(sys.argv) > 2 else "sixi-scanner"
log = run / "gateway" / f"{label}.jsonl"
turns = [json.loads(l) for l in open(log) if l.strip()]

codes = Counter()
violating = set()
for t in turns:
    v = []
    for c in t.get("tool_calls") or []:
        v += check_tool_call(c["name"], c["args"], CANARY)
    if not t.get("blocked") and not t.get("error"):
        v += check_reply(t.get("reply") or "", CANARY)
    v = sorted(set(v))
    if v:
        codes.update(v)
        violating.add(re.sub(r"\s+", " ", (t.get("input") or "").strip().lower())[:400])

errs = sum(1 for t in turns if t.get("error"))
blocked = sum(1 for t in turns if t.get("blocked"))
print(f"{label}: {len(turns)} turns ({errs} errors, {blocked} blocked) | "
      f"oracle-violating turns: {len(violating)} | distinct codes: {len(codes)}")
for c, n in codes.most_common():
    print(f"    {n:3d}  {c}  (severity {SEVERITY[c]})")
