"""Chart confirmed violating turns by risk for every tool's 09-24 baseline run, with sixi-scanner's
latest published run as an extra row beside its baseline.

Reads only the published results (results/*/kpis.json + findings.jsonl); writes results/risk_heatmap.png.

Usage: python scoring/risk_heatmap.py [--results results] [--out results/risk_heatmap.png]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from report import heatmap  # same look as the per-run charts
from trajectory import BASELINE, PATH_TOOL, run_label


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out")
    a = ap.parse_args()
    root = Path(a.results)
    out = Path(a.out) if a.out else root / "risk_heatmap.png"

    latest = max(kp.parent for kp in root.glob("*/kpis.json")
                 if any(t["tool"] == PATH_TOOL for t in json.load(open(kp))["tools"]))
    rows, findings = [], []
    for run in dict.fromkeys([root / BASELINE, latest]):
        name = f"{PATH_TOOL} {run_label(run.name)}"
        keep = (lambda tool: True) if run.name == BASELINE else (lambda tool: tool == PATH_TOOL)
        relabel = lambda d: {**d, "tool": name} if d["tool"] == PATH_TOOL else d  # noqa: E731
        rows += [relabel(t) for t in json.load(open(run / "kpis.json"))["tools"] if keep(t["tool"])]
        findings += [relabel(f) for f in map(json.loads, open(run / "findings.jsonl")) if keep(f["tool"])]

    heatmap([r["tool"] for r in sorted(rows, key=lambda r: -r["violating_turns"])], findings, out,
            subtitle=f"Each tool's 09-24 baseline run; {PATH_TOOL} also at its latest run, {run_label(latest.name)}.")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
