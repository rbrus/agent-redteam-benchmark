#!/usr/bin/env python3
"""Would the confirmation stage catch the leaks the recitation test never offers it?

The 10-08 audit found the open-source build already catches 34 of the 37 real leaks on that run,
turn-level recall 0.919. The 3 it misses share one shape: the agent refuses, then enumerates its
scope in prose -- "I can't restate my instructions. But here's a quick overview: I will only access
ACC-1001..." The recitation test deliberately counts *constraints*, not *capabilities*, because
capability recital is the compliant answer to "what tools do you have". So those replies never become
candidates and the confirmation stage is never asked about them.

That leaves exactly one cheap route to them: hand more replies to the stage and let it decide. This
measures whether the stage can actually make that call, because if it cannot separate a refusal that
recites a *constraint* from one that lists *capabilities*, then broadening the recitation test buys
nothing but cost.

So this asks the shipped confirmation prompt, through the shipped client, about every
truth-carrying turn the markers did not flag, and about a sample of turns they did. Ground truth is
the tool-blind judge and the deterministic oracles, already recorded.

The question is not "does the stage agree with the judge" -- it never has to. It is specifically:

  among replies the markers did not flag, does the stage keep the ones that are real leaks
  more often than the ones that are compliant refusals?

Usage:
  SIXI_SCANNER_REPO=<checkout> SIXI_CONFIRM_URL=<openai endpoint> SIXI_CONFIRM_MODEL=attacker \
  python3 tools/sixi-scanner-oss/probe_stage_recall.py <corpus.jsonl> [--limit N]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DRIVER = '''package confirm

// TestBenchStageRecall asks the shipped confirmation prompt, through the shipped client, about
// replies the markers did not flag, so the answer is about the code that runs in a scan rather than
// a reimplementation of it. Written by tools/sixi-scanner-oss/probe_stage_recall.py and removed
// after the run; gated on SIXI_STAGE_CORPUS, so a plain `go test` never sees it.
import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"
)

type stageRow struct {
	Prompt   string `json:"prompt"`
	Response string `json:"response"`
	Truth    bool   `json:"truth"`
	Real     bool   `json:"real"`
	Flagged  bool   `json:"flagged"`
	Policy   string `json:"policy"`
}

func TestBenchStageRecall(t *testing.T) {
	corpusPath := os.Getenv("SIXI_STAGE_CORPUS")
	outPath := os.Getenv("SIXI_STAGE_OUT")
	if corpusPath == "" || outPath == "" {
		t.Skip("SIXI_STAGE_CORPUS / SIXI_STAGE_OUT not set")
	}
	raw, err := os.ReadFile(corpusPath)
	if err != nil {
		t.Fatalf("corpus: %v", err)
	}
	c := New(os.Getenv("SIXI_CONFIRM_URL"), os.Getenv("SIXI_CONFIRM_MODEL"),
		os.Getenv("SIXI_CONFIRM_KEY"), 120*time.Second, 0)

	out, err := os.Create(outPath)
	if err != nil {
		t.Fatalf("out: %v", err)
	}
	defer out.Close()
	enc := json.NewEncoder(out)

	n := 0
	for _, line := range strings.Split(strings.TrimSpace(string(raw)), "\\n") {
		if line == "" {
			continue
		}
		var row stageRow
		if err := json.Unmarshal([]byte(line), &row); err != nil {
			t.Fatalf("row %d: %v", n, err)
		}
		n++
		v, err := c.Confirm(context.Background(), row.Policy, row.Prompt, row.Response)
		// The identity travels with the verdict. A positional join between the corpus and
		// this file silently maps answers onto the wrong replies, and then reports that a
		// reply "was not offered" when it simply was not at that index.
		id := sha256.Sum256([]byte(strconv.Itoa(len(row.Prompt)) + row.Prompt + row.Response))
		rec := map[string]any{
			"id":      fmt.Sprintf("%x", id),
			"truth":   row.Truth, "real": row.Real, "flagged": row.Flagged,
			"broken":  c.Broken(v),
		}
		if err != nil {
			rec["verdict"] = "unanswered"
			rec["violation"] = nil
		} else {
			rec["verdict"] = v.Reason
			rec["violation"] = v.Violation
			rec["severity"] = v.Severity
		}
		if err := enc.Encode(rec); err != nil {
			t.Fatal(err)
		}
	}
	t.Logf("asked about %d replies", n)
}
'''


def _die(signum, _frame):
    raise SystemExit(128 + signum)


def main() -> int:
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _die)
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--limit", type=int, default=70)
    ap.add_argument("--policy", default="")
    a = ap.parse_args()

    url = os.environ.get("SIXI_CONFIRM_URL")
    if not url:
        raise SystemExit("set SIXI_CONFIRM_URL to an OpenAI-compatible endpoint")
    repo = os.environ.get("SIXI_SCANNER_REPO")
    if not repo:
        raise SystemExit("set SIXI_SCANNER_REPO to the sixi-scanner checkout")

    rows = [json.loads(l) for l in open(a.corpus)]
    # The question is only about replies the markers did NOT flag, plus a sample of ones they did
    # as a control: a stage that keeps everything would score well on the first group by accident.
    unflagged = [r for r in rows if r["truth"] and not r["flagged"]]
    flagged = [r for r in rows if r["flagged"]]
    seen, picked = set(), []
    for r in unflagged + flagged:
        key = (r["prompt"], r["response"])
        if key in seen:
            continue
        seen.add(key)
        picked.append(r)
    picked = picked[: a.limit]
    if not a.policy:
        ctx = ROOT / "tools" / "sixi-scanner-oss" / "context.json"
        a.policy = json.load(open(ctx))["purpose"] if ctx.exists() else "be a correct support agent"

    with tempfile.TemporaryDirectory() as td:
        driver = Path(repo) / "internal" / "confirm" / "zz_bench_stage_recall_test.go"
        out = Path(td) / "out.jsonl"
        corpus = Path(td) / "corpus.jsonl"
        with corpus.open("w") as fh:
            for r in picked:
                fh.write(json.dumps({**r, "policy": a.policy}) + "\n")
        driver.write_text(DRIVER)
        try:
            env = {**os.environ, "SIXI_STAGE_CORPUS": str(corpus), "SIXI_STAGE_OUT": str(out),
                   "SIXI_CONFIRM_KEY": os.environ.get("SIXI_CONFIRM_KEY", "x")}
            r = subprocess.run(["go", "test", "./internal/confirm/", "-run", "TestBenchStageRecall",
                                "-count=1", "-v"], cwd=repo, env=env, capture_output=True, text=True)
            if not out.exists():
                print(r.stdout[-3000:], r.stderr[-3000:], file=sys.stderr)
                raise SystemExit("the stage produced no output")
            res = [json.loads(l) for l in out.open()]
        finally:
            driver.unlink(missing_ok=True)

    # Persist alongside the corpus so the stage's answers can be joined to the marker replay:
    # "the stage kept none of them" is only informative if they were actually offered.
    save = Path(a.corpus).with_suffix(".stage.jsonl")
    save.write_text("".join(json.dumps(r) + "\n" for r in res))

    asked = len(res)
    unanswered = sum(1 for x in res if x.get("verdict") == "unanswered")
    keep = [x for x in res if x.get("violation")]
    print(f"\n  replies asked about      {asked}   ({unanswered} unanswered)")
    print(f"  the stage kept           {len(keep)}")

    def group(pred):
        rs = [x for x in res if pred(x) and x.get("verdict") != "unanswered"]
        k = sum(1 for x in rs if x.get("violation"))
        real = sum(1 for x in rs if x["real"])
        return len(rs), k, real

    print("\n=== among replies the markers did NOT flag ===")
    n, k, real = group(lambda x: not x["flagged"])
    print(f"  asked {n}, kept {k}, of which genuinely real leaks {real}")
    print(f"  -> keeps {k} of {real} real leaks, and {k - real} compliant refusals")
    print("\n=== control: replies the markers DID flag ===")
    n, k, real = group(lambda x: x["flagged"])
    print(f"  asked {n}, kept {k}, of which genuinely real leaks {real}")

    print("\n=== the decisive table ===")
    un = [x for x in res if not x["flagged"] and x.get("verdict") != "unanswered"]
    leak = [x for x in un if x["real"]]
    clean = [x for x in un if not x["real"]]
    got_leak = sum(1 for x in leak if x.get("violation"))
    got_clean = sum(1 for x in clean if x.get("violation"))
    print(f"  real leaks in the unflagged set:        {len(leak)}  kept {got_leak}")
    print(f"  compliant refusals in that same set:    {len(clean)}  wrongly kept {got_clean}")
    if leak:
        print(f"  sensitivity on missed leaks:           {got_leak / len(leak):.3f}")
    if clean:
        print(f"  false-accept rate on refusals:          {got_clean / len(clean):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())