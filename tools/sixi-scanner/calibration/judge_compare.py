#!/usr/bin/env python3
"""Compare two confirm-judge models on the same recorded confirm-read turns.

For each turn (input, reply) asks the given model the contract-bearing grading question (variant 7)
and reports keeps, true positives (turns the unified judge confirmed) and precision — the numbers
that decide which local model ships as sixi-scanner's confirmation judge.

Usage: python3 judge_compare.py <judge_compare.json> <model> [base_url] [cache_suffix]
"""
import json, re, hashlib, importlib.util, os, sys
import httpx
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mc", os.path.join(HERE, "measure_confirm.py"))
mc = importlib.util.module_from_spec(spec); spec.loader.exec_module(mc)
purpose = json.load(open(mc.CONTEXT))["purpose"].strip()

model = sys.argv[2] if len(sys.argv) > 2 else "attacker"
base = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:11434/v1"
suffix = sys.argv[4] if len(sys.argv) > 4 else re.sub(r"[^A-Za-z0-9]+", "_", model)
CACHE = os.path.join(HERE, "cache", f"confirm_cache__{suffix}.jsonl")
cache = {}
if os.path.exists(CACHE):
    for line in open(CACHE):
        try: k, v = json.loads(line); cache[k] = v
        except Exception: pass

RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
recs = json.load(open(sys.argv[1]))
client = httpx.Client()

def ask(rec):
    p = mc.prompt(purpose, "adjudication candidate", "confirm-read turn",
                  rec["input"], rec["reply"], "confirm judge read", "7")
    h = hashlib.sha256(p.encode()).hexdigest()
    if h in cache:
        return rec, cache[h]
    r = client.post(f"{base}/chat/completions", json={"model": model, "messages": [
        {"role": "user", "content": p}]}, timeout=600)
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"(?s)\{.*\}", raw)
    v = {}
    if m:
        try: v = json.loads(m.group(0), strict=False)
        except json.JSONDecodeError:
            for mm in re.finditer(r"(?s)\{[^{}]*\}", m.group(0)):
                try:
                    c = json.loads(mm.group(0), strict=False)
                    if c.get("violation") is not None: v = c; break
                except json.JSONDecodeError: continue
    out = [bool(v.get("violation")), str(v.get("severity", "none")), str(v.get("reason", ""))[:100]]
    with open(CACHE, "a") as fh: fh.write(json.dumps([h, out]) + "\n")
    return rec, out

done = 0
with cf.ThreadPoolExecutor(4) as ex:
    for rec, d in ex.map(ask, recs):
        rec["verdict"] = d
        done += 1
        if done % 25 == 0: print(f"  {done}/{len(recs)}", flush=True)

RANK = RANK
def keep(r):
    d = r["verdict"]
    return bool(d[0]) and RANK.get(d[1], 0) >= 2
tp = [r for r in recs if keep(r) and r["violating"]]
fp = [r for r in recs if keep(r) and not r["violating"]]
viol_total = sum(1 for r in recs if r["violating"])
print(f"model={model}: keeps {len(tp)+len(fp)}/{len(recs)} | TP {len(tp)}/{viol_total} violating read | "
      f"FP {len(fp)} | precision {len(tp)/max(1,len(tp)+len(fp)):.3f}")
json.dump(recs, open(sys.argv[1].replace(".json", f"_scored_{suffix}.json"), "w"), indent=1)
