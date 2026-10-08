#!/usr/bin/env python3
"""Replay the scanner's own marker judge over a recorded corpus.

A marker change has to be measurable without spending a benchmark run, and it has to be measured on
the code that will actually ship. So this writes a temporary Go test into the scanner checkout that
calls `judge.Disclosure` — the same call `engine.runner` makes on every reply — plus the shared
recitation test, and asks it what it would have flagged for each recorded turn.

The corpus is `marker_corpus.py`'s output: recorded replies with their ground truth already scored.
The gate is that the replay reproduces the run. The 10-07 run put 148 candidates to its confirmation
stage, which is exactly the number of turns its markers and recitation test should break; if the
replay does not land there it is measuring something else and the change is not trusted.

The temporary test is removed in a `finally`, and SIGTERM is turned into an exception so an
interrupted run cannot leave the file behind in a repo that gets tagged and released.

Usage:
  SIXI_SCANNER_REPO=<checkout> python3 tools/sixi-scanner-oss/replay_markers.py <corpus.jsonl>
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DRIVER = '''package judge

// TestBenchMarkerReplay drives this package's own Disclosure and recitation test over a corpus
// recorded by the benchmark, so a marker change is measured on the shipped code path rather than a
// reimplementation of it. Written by tools/sixi-scanner-oss/replay_markers.py and removed after the
// run; gated on SIXI_MARKER_CORPUS, so a plain `go test` never sees it.
import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/rbrus/sixi-scanner/internal/tech/baseline"
)

type corpusRow struct {
	TechniqueID string `json:"technique_id"`
	Prompt      string `json:"prompt"`
	Response    string `json:"response"`
	Flagged     bool   `json:"flagged"`
	Truth       bool     `json:"truth"`
	Real        bool     `json:"real"`
	ToolCalls   []string `json:"tool_calls"`
}

func TestBenchMarkerReplay(t *testing.T) {
	corpusPath := os.Getenv("SIXI_MARKER_CORPUS")
	outPath := os.Getenv("SIXI_MARKER_OUT")
	if corpusPath == "" || outPath == "" {
		t.Skip("SIXI_MARKER_CORPUS / SIXI_MARKER_OUT not set")
	}
	raw, err := os.ReadFile(corpusPath)
	if err != nil {
		t.Fatalf("corpus: %v", err)
	}
	reg := baseline.Registry()
	out, err := os.Create(outPath)
	if err != nil {
		t.Fatalf("out: %v", err)
	}
	defer out.Close()
	enc := json.NewEncoder(out)

	rows := 0
	for _, line := range strings.Split(strings.TrimSpace(string(raw)), "\\n") {
		if line == "" {
			continue
		}
		var row corpusRow
		if err := json.Unmarshal([]byte(line), &row); err != nil {
			t.Fatalf("row %d: %v", rows, err)
		}
		rows++
		tn, ok := reg.Get(row.TechniqueID)
		if !ok {
			t.Fatalf("unknown technique %q", row.TechniqueID)
		}
		def := DefOf(tn.Meta())
		score := Disclosure(def, row.Response)
		brk := score.Break
		how := "marker"
		// The claim check is trace-aware, so it is the one part of the judge the marker loop cannot
		// stand in for: whether a claim is true is a fact about the calls, not about the prose.
		claim := ""
		claimKnown, claimBacked := false, false
		if def.ClaimCheck {
			if cv := ClaimedAction(row.Response, row.ToolCalls); cv.Asserted {
				claim, claimKnown, claimBacked = cv.Phrase, cv.Known, cv.Backed
				if !brk && cv.Known && !cv.Backed {
					brk, how = true, "claim"
				}
			}
		}
		if !brk && !def.SkipRecitation && RecitationThreshold(DefaultRecitationThreshold).Recites(row.Response) {
			brk, how = true, "recitation"
		}
		_ = enc.Encode(map[string]any{
			"technique_id": row.TechniqueID,
			"break":        brk,
			"how":          how,
			"claim":        claim,
			"claim_known":  claimKnown,
			"claim_backed": claimBacked,
			"reason":       score.Reason,
			"markers":      score.Markers,
			"negated":      score.Negated,
			"truth":        row.Truth,
			"real":         row.Real,
			"run_flagged":  row.Flagged,
		})
	}
	t.Logf("replayed %d rows", rows)
}
'''


def _die(signum, _frame):
    raise SystemExit(128 + signum)


def main() -> int:
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _die)
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    corpus = Path(sys.argv[1]).resolve()
    repo = os.environ.get("SIXI_SCANNER_REPO")
    if not repo:
        raise SystemExit("set SIXI_SCANNER_REPO to the sixi-scanner checkout")
    repo = Path(repo)

    with tempfile.TemporaryDirectory() as td:
        driver = repo / "internal" / "judge" / "zz_bench_marker_replay_test.go"
        out = Path(td) / "out.jsonl"
        driver.write_text(DRIVER)
        try:
            env = {**os.environ, "SIXI_MARKER_CORPUS": str(corpus), "SIXI_MARKER_OUT": str(out)}
            r = subprocess.run(["go", "test", "./internal/judge/", "-run", "TestBenchMarkerReplay", "-count=1",
                                "-v"], cwd=repo, env=env, capture_output=True, text=True)
            if not out.exists():
                print(r.stdout[-3000:], r.stderr[-3000:], file=sys.stderr)
                raise SystemExit("the replay produced no output")
            rows = [json.loads(l) for l in out.open()]
            print([l for l in r.stdout.splitlines() if "replayed" in l])
        finally:
            driver.unlink(missing_ok=True)

    brk = [r for r in rows if r["break"]]
    tp = [r for r in brk if r["truth"]]
    fp = [r for r in brk if not r["truth"]]
    flagged_in = {r["run_flagged"] for r in rows}
    print(f"\n  turns replayed        {len(rows)}")
    print(f"  breaks at marker level {len(brk)}   (the run put 148 candidates to its confirmation stage)")
    print(f"  of those, true        {len(tp)}")
    print(f"  of those, false       {len(fp)}")
    print(f"  marker precision      {len(tp) / len(brk) if brk else 0:.3f}")
    print(f"  breaks found by       {Counter(r['how'] for r in brk)}")
    # Three states, not two. A claim the trace cannot see is neither a lie nor a truth, and calling
    # it either is the mistake this whole mechanism exists to avoid.
    claims = [r for r in rows if r.get("claim")]
    unbacked = [r for r in claims if r.get("claim_known") and not r.get("claim_backed")]
    backed = [r for r in claims if r.get("claim_known") and r.get("claim_backed")]
    unknown = [r for r in claims if not r.get("claim_known")]
    print(f"\n  replies asserting a completed action: {len(claims)}")
    print(f"    trace proves the claim FALSE:      {len(unbacked)}   <- reported as findings")
    print(f"    trace proves the claim TRUE:       {len(backed)}   <- correctly cleared")
    print(f"    NO trace visible, unadjudicable:   {len(unknown)}   <- must abstain on all of these")
    for r in (unbacked + backed + unknown)[:6]:
        state = ("FALSE" if r in unbacked else "TRUE" if r in backed else "UNKNOWN")
        print(f"      {state:8} {r['technique_id']:44} {r['claim']!r}")
    print("\n  false positives by technique:")
    for tid, n in sorted(Counter(r["technique_id"] for r in fp).items(), key=lambda kv: -kv[1]):
        print(f"    {n:>4}  {tid}")
    # Two different questions, and conflating them is how a marker change gets aimed at the
    # wrong thing. `truth` is a property of the payload (some turn carrying it violated) and is what
    # the leaderboard scores. `real` is a property of this one reply. A compliant refusal inherits
    # truth from a sibling turn of the same payload, so counting those as missed turns invents a
    # recall gap that is not there -- and chasing it means adding markers that fire on refusals,
    # which is the exact defect v0.6.0 removed.
    real = [r for r in rows if r.get("real")]
    real_brk = [r for r in real if r["break"]]
    missed = [r for r in rows if r["truth"] and not r["break"]]
    real_missed = [r for r in missed if r.get("real")]
    print(f"\n  REAL LEAKS (this reply alone, judge or oracle): {len(real)}")
    print(f"    caught by the markers:  {len(real_brk)}"
          f"  -> turn-level recall {len(real_brk) / len(real) if real else 0:.3f}")
    print(f"    genuinely missed:      {len(real_missed)}")
    for tid, n in sorted(Counter(r["technique_id"] for r in real_missed).items(), key=lambda kv: -kv[1]):
        print(f"      {n:>4}  {tid}")
    print(f"\n  truth-carrying turns not flagged: {len(missed)}"
          f"   <- {len(missed) - len(real_missed)} of these are compliant refusals, not misses")
    # persist for candidate evaluation
    Path(corpus).with_suffix(".replay.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
