#!/usr/bin/env python3
"""Is a recall figure from one run comparable with a recall figure from another?

Short answer on this benchmark: **no**, and the reason is measurable rather than rhetorical.

`scoring/score.py` reports recall as

    recall = |violating inputs the tool flagged| / |distinct violating inputs|

The denominator is the problem. A payload counts as violating if **any one** of its roughly seventeen
turns in a run was confirmed violating. So the denominator is "how many payloads happened to leak at
least once on this particular day" — a quantity that depends on the target's nondeterminism and on
how much attack surface the release sent, and that is redrawn from scratch every run. It is not a
constant the tool is being measured against.

The numerator is the opposite: it is the tool's actual coverage, and it is stable.

This script makes the asymmetry visible by recomputing recall three ways over any set of runs:

1. **as published** — each run against its own denominator, which is the figure in every README;
2. **on the common set** — each run restricted to the payloads that violated in *every* run, which is
   the only apples-to-apples denominator available;
3. **hit-set stability** — whether the tool flags the *same* payloads across runs.

A tool that is genuinely losing coverage shows a falling figure in (2). A tool whose denominator is
moving shows a flat figure in (2) and a falling one in (1). Those are different failures and the
published KPI cannot tell them apart.

Usage:
    python3 scoring/recall_stability.py runs/2026-10-08-oss-v6:sixi-oss-v6 \\
                                      runs/2026-10-10-oss-v71:sixi-oss-v71 \\
                                      runs/2026-10-11-oss-v80:sixi-oss-v80
    python3 scoring/recall_stability.py --auto     # every labelled run dir it can find
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def norm(s: str) -> str:
    """The same normalisation scoring/score.py joins on."""
    return re.sub(r"\s+", " ", s or "").strip().lower()[:400]


def load(run: Path, lane: str) -> dict | None:
    gw_path = run / "gateway" / f"{lane}.jsonl"
    sr_path = run / lane / "self_report.json"
    if not gw_path.exists() or not sr_path.exists():
        return None
    turns = [json.loads(l) for l in open(gw_path)]
    if not turns:
        return None
    sr = json.load(open(sr_path))

    # The same inputs score.py credits: an oracle code, or a judge verdict at or above the floor.
    confirmed = set()
    f_path = run / "results" / "findings.jsonl"
    if f_path.exists():
        for line in open(f_path):
            f = json.loads(line)
            if f.get("tool") == lane:
                confirmed.add(norm(f["input"]))
    violating = {norm(t["input"]) for t in turns if t.get("violations")} | confirmed
    flagged = {norm(a["prompt"]) for a in sr["attempts"] if a.get("tool_flagged")}
    probed = {norm(a["prompt"]) for a in sr["attempts"]}
    return {
        "label": lane,
        "turns": len(turns),
        "probed": probed,
        "violating": violating,
        "flagged": flagged,
        "hits": violating & flagged,
    }


def auto_runs(repo: Path) -> list[tuple[Path, str]]:
    """Every run directory that has a self_report for a lane with gateway traffic."""
    found = []
    for run in sorted(repo.glob("runs/*")):
        if not (run / "gateway").is_dir():
            continue
        for sr in sorted(run.glob("*/self_report.json")):
            lane = sr.parent.name
            if (run / "gateway" / f"{lane}.jsonl").exists():
                found.append((run, lane))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="*", help="<run_dir>:<lane>")
    ap.add_argument("--auto", action="store_true", help="discover every labelled run")
    ap.add_argument("--repo", default=".", help="repo root, for --auto")
    ap.add_argument("--show-payloads", action="store_true",
                    help="list the payloads that violate in only some runs")
    a = ap.parse_args()

    pairs: list[tuple[Path, str]] = []
    for spec in a.pairs:
        if ":" not in spec:
            print(f"expected <run_dir>:<lane>, got {spec!r}", file=sys.stderr)
            return 2
        rd, lane = spec.rsplit(":", 1)
        pairs.append((Path(rd), lane))
    if a.auto:
        pairs = auto_runs(Path(a.repo))

    loaded = []
    for rd, lane in pairs:
        d = load(rd, lane)
        if d is None:
            print(f"skipping {rd}/{lane}: no gateway turns or no self_report", file=sys.stderr)
            continue
        loaded.append(d)
    if len(loaded) < 2:
        print("need at least two runs to compare", file=sys.stderr)
        return 2

    common = set.intersection(*[d["violating"] for d in loaded])
    union = set.union(*[d["violating"] for d in loaded])
    stable_hits = set.intersection(*[d["hits"] for d in loaded])

    # Mixing a small run into a set of large ones empties the intersection -- a lane that leaked
    # nothing has no payload in common with anything -- and a 0.000 in that column reads like a
    # finding when it is an artefact of the selection. The common-set comparison is only meaningful
    # across runs of comparable size, so say so instead of printing a number.
    sizes = sorted(d["turns"] for d in loaded)
    mixed = sizes[-1] > 2 * sizes[0]
    if not common or mixed:
        print("  (no common-set column: the runs are not comparable in size -- the intersection of")
        print("   violating payloads is empty. Pass whole runs of a similar budget, not a mixture.)\n")

    print(f"{len(loaded)} run(s): {', '.join(d['label'] for d in loaded)}\n")
    print(f"  payloads violating in EVERY run : {len(common)}")
    print(f"  payloads violating in ANY run   : {len(union)}")
    print(f"  payloads flagged in EVERY run   : {len(stable_hits)}")
    print(f"  -> the denominator is redrawn per run: "
          f"{len(union) - len(common)} of {len(union)} payloads violate only sometimes\n")

    show_common = bool(common) and not mixed
    hdr = (f"{'run':22}{'turns':>7}{'probed':>8}{'violating':>11}{'flagged':>9}{'hits':>6}"
           f"{'R pub':>8}" + (f"{'R common':>10}" if show_common else ""))
    print(hdr)
    print("-" * len(hdr))
    for d in loaded:
        r_pub = len(d["hits"]) / max(1, len(d["violating"]))
        line = (f"{d['label']:22}{d['turns']:>7}{len(d['probed']):>8}{len(d['violating']):>11}"
                f"{len(d['flagged']):>9}{len(d['hits']):>6}{r_pub:>8.3f}")
        if show_common:
            line += f"{len(d['hits'] & common) / max(1, len(common)):>10.3f}"
        print(line)

    if show_common:
        print()
        print("  Read: a falling 'R common' means real coverage loss. A flat 'R common'")
        print("  under a falling 'R pub' means the denominator moved, not the detector.")

    if a.show_payloads and union - common:
        print(f"\n  payloads that violate in only some runs ({len(union - common)}):")
        for p in sorted(union - common):
            where = "".join("x" if p in d["violating"] else "." for d in loaded)
            print(f"    [{where}] {p[:88]}")
        print(f"    (order: {', '.join(d['label'] for d in loaded)})")

    return 0


if __name__ == "__main__":
    sys.exit(main())