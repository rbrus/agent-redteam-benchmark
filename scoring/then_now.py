#!/usr/bin/env python3
"""Then and now for sixi-scanner: the first build measured here against the current release.

One panel per KPI, one bar per published run, read straight from each run's kpis.json. Breadth (risk
categories) is drawn beside the wins on purpose: it is where the current release is not ahead.

Usage: python3 scoring/then_now.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e7e6e2"
OLD, MID, NEW = "#b9b7b0", "#7a9cc6", "#0d366b"

RUNS = [  # (run dir, lane in kpis.json, label, colour)
    ("results/2026-09-24-baseline", "sixi-scanner", "first build\ndev e69b4ed · 09-24", OLD),
    ("results/2026-09-30-sixi-v9", "sixi-scanner", "legacy best\nv9 · 09-30", MID),
    ("results/2026-10-08-sixi-oss-v6", "sixi-oss-v6", "open source\nv0.6.0 · 10-08", NEW),
]

# (title, value from a kpis row, format, higher is better)
PANELS = [
    ("Precision\nshare of its flags that were real", lambda r: r["precision"], "{:.2f}", True),
    ("Recall\nshare of its breaks it reported", lambda r: r["recall"], "{:.2f}", True),
    ("False alarms in its report\nflags the ground truth rejected",
     lambda r: round(r["self_flagged"] * (1 - r["precision"])), "{:d}", False),
    ("Wall clock (min)\none full scan", lambda r: r["wall_clock_min"], "{:.0f}", False),
    ("Attacker-model calls\nLLM inference per scan", lambda r: r["attacker_calls"], "{:,}", False),
    ("Risk categories confirmed\nbreadth: not where it leads",
     lambda r: r["n_distinct_confirmed_risks"], "{:d}", True),
]


def row(run_dir: str, lane: str) -> dict:
    k = json.load(open(Path(run_dir) / "kpis.json"))
    return next(t for t in k["tools"] if t["tool"] == lane)


def main() -> None:
    rows = [row(d, lane) for d, lane, _, _ in RUNS]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.6), facecolor=SURFACE)
    for ax, (title, get, fmt, up) in zip(axes.flat, PANELS):
        vals = [get(r) for r in rows]
        xs = range(len(vals))
        ax.bar(xs, vals, color=[c for *_, c in RUNS], width=0.62, zorder=2)
        top = max(vals) or 1
        for x, v in zip(xs, vals):
            ax.text(x, v + top * 0.03, fmt.format(v), ha="center", va="bottom",
                    fontsize=11, color=INK, fontweight="bold" if x == len(vals) - 1 else "normal")
        ax.set_ylim(0, top * 1.22)
        ax.set_title(title, fontsize=10.5, color=INK, loc="left", pad=8)
        ax.set_xticks(list(xs), [lbl for _, _, lbl, _ in RUNS], fontsize=8.2, color=INK2)
        ax.set_yticks([])
        ax.set_facecolor(SURFACE)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.text(1.0, 1.0, "higher is better" if up else "lower is better", transform=ax.transAxes,
                ha="right", va="bottom", fontsize=8, color=MUTED)
    fig.suptitle("sixi-scanner, then and now — same target, same gateway, oracles and judge",
                 x=0.01, ha="left", fontsize=14, color=INK, fontweight="bold")
    fig.text(0.01, 0.005, "Each bar is one published run in results/. False alarms = self-flagged × (1 − precision). "
             "The open-source build ran its LLM only as the optional confirmation stage.",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig("results/then_now.png", dpi=150, facecolor=SURFACE)
    print("wrote results/then_now.png")


if __name__ == "__main__":
    main()
