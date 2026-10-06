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
	Truth       bool   `json:"truth"`
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
		if !brk && !def.SkipRecitation && RecitationThreshold(DefaultRecitationThreshold).Recites(row.Response) {
			brk, how = true, "recitation"
		}
		_ = enc.Encode(map[string]any{
			"technique_id": row.TechniqueID,
			"break":        brk,
			"how":          how,
			"reason":       score.Reason,
			"markers":      score.Markers,
			"negated":      score.Negated,
			"truth":        row.Truth,
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
    print("\n  false positives by technique:")
    for tid, n in sorted(Counter(r["technique_id"] for r in fp).items(), key=lambda kv: -kv[1]):
        print(f"    {n:>4}  {tid}")
    missed = [r for r in rows if r["truth"] and not r["break"]]
    print(f"\n  true turns the markers miss: {len(missed)}")
    for tid, n in sorted(Counter(r["technique_id"] for r in missed).items(), key=lambda kv: -kv[1]):
        print(f"    {n:>4}  {tid}")
    # persist for candidate evaluation
    Path(corpus).with_suffix(".replay.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
