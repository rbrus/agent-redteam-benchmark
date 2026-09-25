"""Copy a run's results into results/<run>/ in a form that is safe to publish.

Published: KPIs (json/csv), the Markdown table, the charts, each tool's own summary, and the
confirmed findings with transcripts shortened. Findings in the harmful-content category keep their
metadata but not their text: the benchmark reports that such content was produced, not the content.

Usage: python scripts/publish_results.py runs/<run> [--name <published-name>]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil

REDACT_CATEGORIES = {"harmful_content"}
MAX_CHARS = 600


def clip(s: str) -> str:
    s = s or ""
    return s if len(s) <= MAX_CHARS else s[:MAX_CHARS] + " […]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--name")
    a = ap.parse_args()
    run = Path(a.run_dir)
    out = Path("results") / (a.name or run.name)
    out.mkdir(parents=True, exist_ok=True)

    for f in ["kpis.json", "kpis.csv", "table.md", *[p.name for p in (run / "results").glob("*.png")]]:
        shutil.copy(run / "results" / f, out / f)

    with open(run / "results" / "findings.jsonl") as src, open(out / "findings.jsonl", "w") as dst:
        for line in src:
            f = json.loads(line)
            cats = {code for _, code in f["confirmed_by"]}
            redacted = bool(cats & REDACT_CATEGORIES)
            line_str = json.dumps({
                "tool": f["tool"],
                "confirmed_by": f["confirmed_by"],
                "input": "[redacted: harmful-content finding]" if redacted else clip(f["input"]),
                "reply": "[redacted: harmful-content finding]" if redacted else clip(f["reply"]),
                "tool_calls": [{"name": t["name"], "args": {k: clip(str(v)) for k, v in t["args"].items()}}
                               for t in f["tool_calls"]],
            }, ensure_ascii=False)
            canary = os.environ.get("BENCH_CANARY", "")
            if canary:
                line_str = line_str.replace(canary, "HX-XXXXXXXX-CANARY")
            line_str = re.sub(r"HX-[0-9A-Fa-f]{8}-CANARY", "HX-XXXXXXXX-CANARY", line_str)
            dst.write(line_str + "\n")

    summaries = {}
    for sr in run.glob("*/self_report.json"):
        d = json.loads(sr.read_text())
        summaries[d["tool"]] = {k: d.get(k) for k in ("tool_version", "config", "started_at", "finished_at", "tool_summary")}
        summaries[d["tool"]]["attempts"] = len(d["attempts"])
        summaries[d["tool"]]["self_flagged"] = sum(1 for x in d["attempts"] if x.get("tool_flagged"))
    (out / "tool_summaries.json").write_text(json.dumps(summaries, indent=1, default=str))
    tl = run / "logs" / "timeline.log"
    if tl.exists():
        shutil.copy(tl, out / "timeline.log")
    print(f"published to {out}")


if __name__ == "__main__":
    main()
