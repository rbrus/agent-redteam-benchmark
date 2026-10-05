#!/usr/bin/env python3
"""Before/after chart for one tool: what a measured change did to its own report quality.

A scanner's headline number — violations found — moves with how hard it was pushed, so it cannot show
whether a change to the tool helped. Precision and recall cannot: they are computed against ground
truth for the violations the tool itself caused, so they measure the tool's judgement rather than its
volume. This chart plots only those two, per published run, so a regression is visible as a step down.

Usage: python3 scoring/trajectory_oss.py --runs results/2026-10-05-sixi-oss results/2026-10-06-sixi-oss-v4
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e7e6e2"
BLUE, ACCENT = "#2a78d6", "#0d366b"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--label", default="sixi-oss")
    ap.add_argument("--out", default="results/trajectory_oss.png")
    a = ap.parse_args()

    # Group by lane suffix: the budget-matched run and the shipped-defaults run are two configurations,
    # not four points on one line. Plotting them as one series would draw a "dip" between them that
    # never happened — the dip would be the difference between --rounds 14 and --rounds 1.
    lanes: dict[str, list] = {}
    for r in a.runs:
        k = json.load(open(Path(r) / "kpis.json"))
        for t in k["tools"]:
            if not t["tool"].startswith(a.label) or t["precision"] is None:
                continue
            # The lane is the configuration, not the build. Strip the version first, then the
            # configuration suffix: "sixi-oss-default" and "sixi-oss-v4-default" are the same lane.
            suffix = t["tool"][len(a.label):]
            lane = "default (shipped)" if suffix.endswith("-default") else "budget-matched"
            lanes.setdefault(lane, []).append((Path(r).name, t))
    if not lanes:
        raise SystemExit(f"no rows for {a.label} in the given runs")

    x = [0, 1]
    xticks = ["before\n(v0.3.0)", "after\n(v0.4.0)"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                         "xtick.color": MUTED, "ytick.color": MUTED, "figure.facecolor": SURFACE})
    fig, ax = plt.subplots(figsize=(9.2, 6.0))

    for li, (lane, rows) in enumerate(sorted(lanes.items(), key=lambda kv: -max(t["turns"] for _, t in kv[1]))):
        rows.sort(key=lambda rt: rt[1]["tool_version"])
        style = ["-", (0, (5, 2))][li % 2]
        for key, label, colour, marker, dy in [
                ("precision", "precision — of what it reported, was real", BLUE, "o", -20),
                ("recall", "recall — of what it broke, it reported", ACCENT, "s", 12)]:
            vals = [t[key] for _, t in rows]
            ax.plot(x[:len(vals)], vals, marker=marker, color=colour, linewidth=2.0, linestyle=style,
                    markersize=8,
                    label=f"{label} · {lane} ({rows[-1][1]['turns']:,} turns)", zorder=3)
            for xi, v in zip(x[:len(vals)], vals):
                ax.annotate(f"{v:.3f}", (xi, v), textcoords="offset points", xytext=(0, dy),
                            ha="center", fontsize=9.5, color=INK)

    for y, name in [(0.30, "precision target 0.30"), (0.56, "recall target 0.56")]:
        ax.axhline(y, color=MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
        # Left side: the right side is where the precision values and their labels sit.
        ax.text(-0.27, y + 0.018, name, fontsize=8.2, color=MUTED, ha="left")

    ax.set_xticks(x)
    ax.set_xticklabels(xticks, fontsize=9.5)
    ax.set_xlim(-0.30, 1.12)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("score", fontsize=9.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    # Below the plot: the top-left is where the recall lines end up.
    ax.legend(frameon=False, fontsize=8.4, loc="upper center", bbox_to_anchor=(0.5, -0.11),
              ncol=2)
    ax.set_title(
        "The rule-recitation marker: the same scanner, before and after\n"
        "one point per configuration per version; ground truth judged identically in all four runs",
        loc="left", color=INK, fontsize=12, pad=12)
    fig.tight_layout()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, dpi=160)
    print(f"wrote {a.out}")
    for lane, rows in lanes.items():
        for n, t in rows:
            print(f"  {lane:16} {n:24} P={t['precision']} R={t['recall']} viol={t['violating_turns']} turns={t['turns']}")


if __name__ == "__main__":
    main()