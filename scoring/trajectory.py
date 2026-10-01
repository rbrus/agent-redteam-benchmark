"""Chart every tool's self-report quality — precision and recall of its own verdicts against the
gateway's ground truth — with sixi-scanner's published runs drawn as a path through the plane.

Reads only the published results (results/*/kpis.json); writes results/trajectory.png.

Usage: python scoring/trajectory.py [--results results] [--out results/trajectory.png]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from report import BLUE, GRID, INK, INK2, MUTED, SURFACE  # same look as the per-run charts

BASELINE = "2026-09-24-baseline"
PATH_TOOL = "sixi-scanner"
# Where each intermediate run's label sits (offset in points, alignment) so none crosses the path;
# a run not listed gets its label above its dot.
LABEL_AT = {
    "09-26 validation": ((0, 7), "center"),
    "09-27 final": ((7, -8), "left"),
    "09-27 release build": ((-7, -7), "right"),
    "09-28 confirm2": ((5, -10), "left"),
    "09-29 depth": ((-8, 2), "right"),
}


def run_label(name: str) -> str:
    """'2026-09-30-sixi-v9' -> '09-30 v9'."""
    return name[5:10] + " " + name[11:].removeprefix("sixi-").replace("-", " ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out")
    a = ap.parse_args()
    root = Path(a.results)
    out = Path(a.out) if a.out else root / "trajectory.png"

    base = json.load(open(root / BASELINE / "kpis.json"))["tools"]
    others = [t for t in base if t["tool"] != PATH_TOOL and t["precision"] is not None and t["recall"] is not None]
    unplotted = [t["tool"] for t in base if t["tool"] != PATH_TOOL and t not in others]

    path = []  # (label, recall, precision) per published run, oldest first (run dirs sort by date)
    for kp in sorted(root.glob("*/kpis.json")):
        row = next((t for t in json.load(open(kp))["tools"] if t["tool"] == PATH_TOOL), None)
        if row and row["precision"] is not None and row["recall"] is not None:
            path.append((run_label(kp.parent.name), row["recall"], row["precision"]))

    fig, ax = plt.subplots(figsize=(8.2, 5.4))
    ax.plot([r for _, r, _ in path], [p for _, _, p in path], color=BLUE, linewidth=2, solid_joinstyle="round",
            solid_capstyle="round", zorder=2, label=f"{PATH_TOOL}: {len(path)} runs, {path[0][0][:5]} → {path[-1][0][:5]}")
    ax.scatter([r for _, r, _ in path], [p for _, _, p in path], s=42, color=BLUE, edgecolors=SURFACE,
               linewidths=2, zorder=3)
    ax.scatter([t["recall"] for t in others], [t["precision"] for t in others], s=64, color=MUTED,
               edgecolors=SURFACE, linewidths=2, zorder=3, label="other tools, one run each (09-24)")

    for t in others:
        ax.annotate(t["tool"], (t["recall"], t["precision"]), xytext=(9, 0), textcoords="offset points",
                    va="center", color=INK2, fontsize=9.5)
    for label, r, p in path[1:-1]:
        offset, ha = LABEL_AT.get(label, ((0, 8), "center"))
        ax.annotate(label, (r, p), xytext=offset, textcoords="offset points", ha=ha, va="center",
                    color=MUTED, fontsize=8)
    (l0, r0, p0), (l1, r1, p1) = path[0], path[-1]
    ax.annotate(f"{PATH_TOOL}\n{l0}", (r0, p0), xytext=(9, 0), textcoords="offset points", va="center",
                color=INK, fontsize=9.5)
    ax.annotate(f"{PATH_TOOL} {l1}\nP {p1:.2f} · R {r1:.2f}", (r1, p1), xytext=(0, 14), textcoords="offset points",
                ha="center", va="bottom", color=INK, fontsize=9.5, fontweight="bold")

    ax.set_xlim(0, 0.72)
    ax.set_ylim(0, 0.34)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("Recall: share of the violations it caused that it reported", labelpad=8)
    ax.set_ylabel("Precision: share of its flags that were real", labelpad=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.tick_params(length=0)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Can you trust a red-teaming tool's own report?", loc="left", color=INK, fontsize=13, pad=26)
    ax.text(0, 1.02, "Each tool's verdicts scored against the gateway's ground truth (oracles + tool-blind judge). "
            "Up and right is better.", transform=ax.transAxes, color=INK2, fontsize=9)
    leg = ax.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK2, borderaxespad=0.2)
    for h in leg.legend_handles:
        h.set_alpha(1)
    if unplotted:
        fig.text(0.012, 0.012, f"Not plotted: {', '.join(unplotted)} flagged nothing, so they have no precision.",
                 color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
