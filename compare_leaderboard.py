#!/usr/bin/env python3
"""Compare one scored run against the baseline leaderboard, tool by tool.

Usage: python3 compare_leaderboard.py <scored_run_dir> [--baseline results/2026-09-24-baseline]
       [--label sixi-scanner] [--extra-label name ...]
"""
import argparse
import json
from pathlib import Path


def load(run):
    p = Path(run) / "results" / "kpis.json"
    if not p.exists():
        p = Path(run) / "kpis.json"
    d = json.load(open(p))
    return {t["tool"]: t for t in d["tools"]}


def row(t):
    return {
        "turns": t["turns"], "viol": t["violating_turns"], "asr": t["asr"],
        "risky": t["n_distinct_confirmed_risks"], "flag": t["self_flagged"],
        "P": t["precision"], "R": t["recall"],
    }


def fmt(v, better_high=True):
    return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--baseline", default="results/2026-09-24-baseline")
    ap.add_argument("--label", default="sixi-scanner",
                    help="the tool under test; a run of a differently-labelled build (e.g. the "
                         "open-source sixi-oss) needs its own name here")
    ap.add_argument("--extra-label", nargs="*", default=[],
                    help="additional labels from this run to show on the leaderboard")
    a = ap.parse_args()
    base = load(a.baseline)
    new = load(a.run)
    label = a.label
    if label not in base and label in new:
        base_label_for_delta = None
    else:
        base_label_for_delta = label
    if label not in new:
        print(f"no {label} row in {a.run}/results/kpis.json yet"); return
    if base_label_for_delta is None:
        print(f"\n=== {label}: this run (no {label} row in the baseline to diff against) ===")
        b = None
    else:
        b = row(base[base_label_for_delta])
    n = row(new[label])

    print(f"\n=== {label}: this run vs its own baseline ===")
    print(f"{'metric':28} {'baseline':>10} {'this run':>10}  moved")
    if b is None:
        for k in ("turns", "viol", "risky", "flag"):
            print(f"{k:28} {'—':>10} {n[k]:>10}")
        for k in ("asr", "P", "R"):
            print(f"{k:28} {'—':>10} {fmt(n[k]):>10}")
    else:
        for k in ("turns", "viol", "risky", "flag"):
            better = n[k] > b[k]
            print(f"{k:28} {b[k]:>10} {n[k]:>10}  {'BETTER' if better else ('same' if n[k]==b[k] else 'WORSE')}")
        for k in ("asr", "P", "R"):
            bv, nv = b[k], n[k]
            if bv is None or nv is None:
                print(f"{k:28} {fmt(bv):>10} {fmt(nv):>10}  ?"); continue
            better = nv > bv
            print(f"{k:28} {bv:>10.3f} {nv:>10.3f}  {'BETTER' if better else ('same' if nv==bv else 'WORSE')}")

    print(f"\n=== leaderboard: every tool at its best, with this run's {label} ===")
    rows = [(name, row(t)) for name, t in base.items() if name != label]
    for extra in a.extra_label:
        if extra in new:
            rows.append((extra + " (NEW)", row(new[extra])))
    if label in new:
        rows.append((label + " (NEW)", row(new[label])))
    rows.sort(key=lambda x: -(x[1]["viol"] or 0))
    print(f"{'tool':22} {'turns':>6} {'viol':>5} {'asr':>6} {'risky':>5} {'P':>6} {'R':>6}")
    for t, r in rows:
        print(f"{t:22} {r['turns']:>6} {r['viol']:>5} {fmt(r['asr']):>6} {r['risky']:>5} {fmt(r['P']):>6} {fmt(r['R']):>6}")

    if label not in new:
        return
    sixi = n
    print(f"\n=== {label} (NEW) vs each competitor's baseline ===")
    for name, r in sorted(((name, row(t)) for name, t in base.items() if name != label),
                       key=lambda x: -(x[1]["viol"] or 0)):
        wins, losses = [], []
        if (sixi["viol"] or 0) > (r["viol"] or 0): wins.append("violations")
        elif (sixi["viol"] or 0) < (r["viol"] or 0): losses.append("violations")
        if (sixi["asr"] or 0) > (r["asr"] or 0): wins.append("asr")
        elif (sixi["asr"] or 0) < (r["asr"] or 0): losses.append("asr")
        if sixi["risky"] > r["risky"]: wins.append("risk breadth")
        elif sixi["risky"] < r["risky"]: losses.append("risk breadth")
        if r["P"] is None or (sixi["P"] is not None and sixi["P"] > r["P"]): wins.append("precision")
        elif sixi["P"] is not None and r["P"] is not None and sixi["P"] < r["P"]: losses.append("precision")
        if r["R"] is None or (sixi["R"] is not None and sixi["R"] > r["R"]): wins.append("recall")
        elif sixi["R"] is not None and r["R"] is not None and sixi["R"] < r["R"]: losses.append("recall")
        print(f"  vs {name:15} ahead: {', '.join(wins) or '—':34} behind: {', '.join(losses) or '—'}")


if __name__ == "__main__":
    main()
