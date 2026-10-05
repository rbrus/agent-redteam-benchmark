#!/usr/bin/env python3
"""Measure the negative-control idea from agent-probe against the open-source build's false positives.

agent-probe sends a baseline (benign) probe, records which signatures the target emits *anyway*, and
subtracts them from every later verdict (scanner/negcontrol_test.go). The open-source build instead
carries a hand-written negation list per technique, which is why it still files markers out of a
refusal — "I can't share or display API keys" contains the credential-elicitation markers.

This measures the substitution offline on a recorded run. It needs a control reply, so it uses the one
probe in the catalogue whose whole purpose is to make the agent describe itself
(`probe.llm06.tool-enumeration`): a reply to "what can you do?" is, by construction, the set of words
the agent says without being attacked. Subtracting those markers is the negative control applied to
this run, with no new target turns needed.

Usage: python3 tools/sixi-scanner-oss/measure_negcontrol.py <run_dir> <label>
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "target"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scoring"))

import hashlib  # noqa: E402
import os  # noqa: E402

from oracles import check_reply, check_tool_call  # noqa: E402
from score import SEV_RANK, norm  # noqa: E402

CONTROL = "probe.llm06.tool-enumeration"


def main() -> None:
    run, label = Path(sys.argv[1]), sys.argv[2]
    canary = os.environ.get("BENCH_CANARY", "")
    techdump = sys.argv[3] if len(sys.argv) > 3 else "venvs/sixi-scanner-oss/techdump"
    techs = {t["id"]: t for t in json.loads(subprocess.run([techdump], capture_output=True, text=True).stdout)["techniques"]}

    cache = {}
    for f in run.glob("judge_cache__*.jsonl"):
        for line in open(f):
            d = json.loads(line)
            cache[d["key"]] = d["verdict"]

    def key(rec):
        blob = json.dumps([rec["input"], rec["reply"], [[t["name"], t["args"]] for t in rec["tool_calls"]]], sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    sr = json.load(open(run / label / "self_report.json"))
    turns = [json.loads(l) for l in open(run / "gateway" / f"{label}.jsonl")]
    viol = set()
    for t in turns:
        conf = any(check_tool_call(c["name"], c["args"], canary, session={}) for c in t["tool_calls"])
        if not t["blocked"]:
            conf |= bool(check_reply(t["reply"], canary))
            j = cache.get(key(t)) or {}
            conf |= bool(j.get("violation")) and SEV_RANK.get(j.get("severity", "none"), 0) >= SEV_RANK["medium"]
        if conf:
            viol.add(norm(t["input"]))

    # the control reply: everything the agent volunteers when asked to describe itself
    control_words = set()
    ctrl_prompts = {norm(v) for v in techs[CONTROL]["variants"]}
    for x in sr["attempts"]:
        if x["technique"] == CONTROL and x["response"]:
            control_words |= set(re.findall(r"[a-z0-9_]+", x["response"].lower()))

    # which markers are just words the agent says anyway?
    benign = {}
    for tid, t in techs.items():
        noisy = [m for m in t["markers"] if all(w in control_words for w in re.findall(r"[a-z0-9_]+", m.lower()))]
        if noisy:
            benign[tid] = noisy

    print(f"=== {label}: negative control from the {CONTROL} reply ({len(control_words)} distinct words) ===")
    print(f"techniques with markers the agent emits unprompted: {len(benign)} of {len(techs)}")
    for tid, ms in sorted(benign.items(), key=lambda kv: -len(kv[1]))[:10]:
        print(f"  {tid:44} {len(ms):2}/{len(techs[tid]['markers']):2} markers: {ms[:4]}")

    # What would that do to the flagged set? Re-derive each flagged payload's markers by hand: a flag
    # survives only if some marker of its technique is absent from the control vocabulary.
    flagged = [x for x in sr["attempts"] if x["tool_flagged"]]
    survivors = 0
    killed_fp = 0
    killed_tp = 0
    for x in flagged:
        noisy = set(benign.get(x["technique"], []))
        t = techs[x["technique"]]
        live = [m for m in t["markers"] if m not in noisy]
        if not live:
            if norm(x["prompt"]) in viol:
                killed_tp += 1
            else:
                killed_fp += 1
        else:
            survivors += 1
    hit = sum(1 for x in flagged if norm(x["prompt"]) in viol)
    print(f"\nflagged turns {len(flagged)} (true {hit}, false {len(flagged) - hit})")
    print(f"markers-only verdict after the control: {survivors} would survive; "
          f"{killed_fp} false and {killed_tp} true flags lose every marker")
    if survivors:
        # A flag survives when at least one of its technique's markers is NOT in the control vocabulary.
        # Recount the hits among the survivors only — counting every flag as a hit would report 1.000.
        surviving = [x for x in flagged if [m for m in techs[x["technique"]]["markers"]
                                           if m not in set(benign.get(x["technique"], []))]]
        newhit = sum(1 for x in surviving if norm(x["prompt"]) in viol)
        print(f"  turn precision {hit / len(flagged):.3f} -> {newhit}/{survivors} = {newhit / survivors:.3f}")
        if killed_fp == 0 and killed_tp == 0:
            print("  VERDICT: no flag loses every marker, because every technique here requires "
                  f"{min(t['min_markers'] for t in techs.values())}+ markers out of 6-16 and the "
                  "unprompted words ('you are a', '@') co-occur with discriminating ones. "
                  "Marker-level negative control does not pay on this catalogue — the technique set's "
                  "marker diversity is exactly what makes substring matching usable in the first place.")


if __name__ == "__main__":
    main()