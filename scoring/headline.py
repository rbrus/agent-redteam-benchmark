#!/usr/bin/env python3
"""The README's headline chart: every tool's best published run, with the latest sixi-scanner beside them.

One figure, because the top of the README has to survive being read once. It shows the two things a
reader asks first — how much did it find, and how much of what it reported was real — because a tool
that finds a lot and reports it badly is a tool nobody should act on, and a tool that reports a little
perfectly may simply have found very little.

The rows are the leaderboard as PROTOCOL §5 defines it: each tool's best published run, and the latest
sixi-scanner lane. The data comes from published `results/*/kpis.json` and from
`scoring/distinct.py`'s distinct-attack count, so the chart cannot claim a number the scripts do not
produce.

Usage: python3 scoring/headline.py --out results/headline.png [--baseline results/2026-09-24-baseline]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e7e6e2"
BLUE, ACCENT = "#2a78d6", "#0d366b"
GREY = "#b9b7b0"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()[:400]


def best_runs(baseline: str) -> dict:
    """One row per tool: its published baseline, plus the newest sixi-scanner lane."""
    rows = {t["tool"]: t for t in json.load(open(Path(baseline) / "kpis.json"))["tools"]}
    latest = max(
        (p for p in glob.glob("results/*/kpis.json") if "sixi-oss" in p),
        key=lambda p: Path(p).parent.name,
    )
    for t in json.load(open(latest))["tools"]:
        rows[t["tool"]] = t
    return rows, Path(latest).parent.name


def distinct_payloads(paths: list[str]) -> dict:
    """Distinct confirmed payloads per tool, from published findings.jsonl.

    Counting turns instead would let a tool that repeats one payload twenty times look like one that
    finds twenty — which is the bias PROTOCOL §7 documents and the reason this chart carries both.
    """
    out = defaultdict(set)
    for p in paths:
        f = Path(p) / "findings.jsonl"
        if not f.exists():
            continue
        for line in open(f):
            r = json.loads(line)
            out[r["tool"]].add(norm(r["input"]))
    return {k: len(v) for k, v in out.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/headline.png")
    ap.add_argument("--baseline", default="results/2026-09-24-baseline")
    a = ap.parse_args()

    rows, latest_name = best_runs(a.baseline)
    # latest_name is a directory name; the findings live under results/.
    dist = distinct_payloads([a.baseline, f"results/{latest_name}"])

    # The headline row is the latest sixi-scanner lane; its default-config lane is context, not a rival.
    headline = next((n for n in ("sixi-oss-v4", "sixi-oss", "sixi-oss-default") if n in rows), None)
    order = sorted(
        ((n, t) for n, t in rows.items()),
        key=lambda kv: -(kv[1]["violating_turns"] or 0),
    )
    # The chart's job is to introduce the current build, so it leads regardless of where it ranks.
    if headline:
        order = [kv for kv in order if kv[0] == headline] + [kv for kv in order if kv[0] != headline]

    labels = [n for n, _ in order]
    viol = [t["violating_turns"] or 0 for _, t in order]
    # A tool that files no self-flags has no precision to plot; drawing it as 0% would read as "every
    # flag was wrong", which is a different claim. Keep the gap and say so.
    prec = [t["precision"] for _, t in order]
    dists = [dist.get(n, 0) for n, _ in order]
    colors = [ACCENT if n == headline else GREY for n in labels]

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                         "xtick.color": MUTED, "ytick.color": INK2, "figure.facecolor": SURFACE})
    fig, axes = plt.subplots(
        1, 3, figsize=(12.6, 0.46 * len(labels) + 2.6),
        gridspec_kw={"wspace": 0.12, "width_ratios": [1, 1, 1]}, layout="constrained",
        sharey=True)
    y = list(range(len(labels)))

    def panel(ax, vals, title, note, xlabel, fmt, na="—"):
        nums = [0 if v is None else v for v in vals]
        ax.barh(y, nums, color=colors, height=0.62)
        for i, v in enumerate(vals):
            if v is None:
                ax.text(0.015, i, "  " + na, va="center", color=MUTED, fontsize=9)
            elif v:
                ax.text(v, i, "  " + fmt.format(v), va="center", color=INK, fontsize=9)
        ax.set_title(title, loc="left", color=INK, fontsize=11, pad=17)
        # The caveat goes directly under the title, where it is read, rather than below the axis where
        # a constrained layout tends to drop it.
        ax.text(0, 1.015, note, transform=ax.transAxes, fontsize=8.1, color=MUTED, va="bottom")
        ax.set_xlabel(xlabel, fontsize=8.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_xlim(0, (max(nums) or 1) * 1.24)
        if "flags" in na:
            ax.set_xticks([0, 0.1, 0.2, 0.3])
            ax.set_xticklabels(["0", "10%", "20%", "30%"])

    panel(axes[0], viol, "Confirmed violations found",
          "one run per tool, each at its own configuration",
          "turns an oracle or the blind judge confirmed", "{:.0f}")
    panel(axes[1], prec, "Of what it reported, how much was real",
          "finding a lot and reporting it badly is worse than not scanning",
          "precision (turn-weighted)", "{:.0%}", na="no flags")
    panel(axes[2], dists, "Distinct attacks that worked",
          "the count that does not reward re-sending one probe",
          "unique payloads, not repeats", "{:.0f}")
    for ax in axes[1:]:
        ax.tick_params(labelleft=False)
    # sharey shares the tick LOCATOR too, so the labels have to be set once, explicitly, on the
    # leftmost axis — otherwise all three panels fall back to indices.
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(labels, fontsize=9.5)
    axes[0].invert_yaxis()

    fig.get_layout_engine().set(rect=(0, 0, 1, 0.90), h_pad=0.10)
    # The subtitle rides inside the suptitle rather than as a second fig.text: with constrained_layout
    # a fixed-position fig.text lands on top of the suptitle.
    fig.suptitle(
        f"Every red-teaming tool on one Foundry agent — {latest_name} highlights the current sixi-scanner\n"
        "Same agent, same wire, same ten deterministic oracles and the same tool-blind judge for every tool.\n"
        "Conflict of interest: the benchmark's maintainer authors two of the tools shown.",
        x=0.006, ha="left", color=INK, fontsize=13.5, linespacing=1.7)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out, dpi=160)
    print(f"wrote {a.out} with {len(labels)} tools (headline: {headline}, run {latest_name})")
    for n, t in order:
        print(f"  {n:22} viol={t['violating_turns']:4} P={t['precision']} distinct={dist.get(n, 0)}")


if __name__ == "__main__":
    main()