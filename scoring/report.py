"""Render charts and a Markdown results table from <run_dir>/results/kpis.json + findings.jsonl.

Usage: python scoring/report.py <run_dir> [--out results/] [--drop-suffix -smoke]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e7e6e2"
BLUE = "#2a78d6"
SEQ = LinearSegmentedColormap.from_list("seq", ["#f0efec", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
RISKS = ["secret_leak", "system_prompt_leak", "cross_account_data", "unauthorized_action", "injection_followed",
         "harmful_content", "off_topic_compliance", "false_action_claim", "unsafe_markup"]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": MUTED, "ytick.color": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})


def hbar(rows, key, title, path, fmt="{:.0f}", xlabel=""):
    rows = [r for r in rows if r.get(key) is not None]
    rows = sorted(rows, key=lambda r: r[key])
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(rows) + 1.2))
    vals = [r[key] for r in rows]
    ax.barh([r["tool"] for r in rows], vals, color=BLUE, height=0.55)
    for i, v in enumerate(vals):
        ax.text(v, i, "  " + fmt.format(v), va="center", color=INK, fontsize=9)
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=12)
    ax.set_xlabel(xlabel)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlim(0, (max(vals) or 1) * 1.18)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def heatmap(tools, findings, path):
    m = defaultdict(Counter)
    for f in findings:
        for src, code in f["confirmed_by"]:
            risk = code if src == "judge" else {
                "SECRET_CANARY_LEAK": "secret_leak", "SYSTEM_PROMPT_LEAK": "system_prompt_leak",
                "CROSS_ACCOUNT_PII_LEAK": "cross_account_data", "INDIRECT_INJECTION_FOLLOWED": "injection_followed",
            }.get(code, "unauthorized_action")
            m[f["tool"]][risk] += 1
    risks = [r for r in RISKS if any(m[t][r] for t in tools)] or RISKS[:1]
    data = [[m[t][r] for r in risks] for t in tools]
    fig, ax = plt.subplots(figsize=(1.0 * len(risks) + 3, 0.5 * len(tools) + 1.8))
    vmax = max(max(row) for row in data) or 1
    ax.imshow(data, cmap=SEQ, vmin=0, vmax=vmax, aspect="auto")
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ax.text(j, i, str(v) if v else "–", ha="center", va="center", fontsize=9,
                    color="#ffffff" if v > vmax * 0.55 else INK)
    ax.set_xticks(range(len(risks)), [r.replace("_", "\n") for r in risks], fontsize=8)
    ax.set_yticks(range(len(tools)), tools)
    ax.tick_params(length=0)
    ax.set_xticks([x - 0.5 for x in range(1, len(risks))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(tools))], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Confirmed violating turns by risk (oracle + judge)", loc="left", color=INK, fontsize=12, pad=12)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    run = Path(a.run_dir)
    out = Path(a.out) if a.out else run / "results"
    out.mkdir(parents=True, exist_ok=True)
    k = json.load(open(run / "results" / "kpis.json"))
    rows = k["tools"]
    findings = [json.loads(l) for l in open(run / "results" / "findings.jsonl")]
    for r in rows:
        r["precision_pct"] = None if r["precision"] is None else 100 * r["precision"]
        r["cost_per_violation"] = (r["target_cost_usd"] / r["violating_turns"]) if r["violating_turns"] else None
        r["violations_per_100"] = 100 * r["violating_turns"] / max(1, r["reached_model"])

    hbar(rows, "violating_turns", "Confirmed violating turns per tool", out / "violating_turns.png")
    hbar(rows, "n_distinct_confirmed_risks", "Distinct risk categories confirmed", out / "distinct_risks.png")
    hbar(rows, "precision_pct", "Precision of the tool's own verdicts (%)", out / "precision.png", "{:.0f}%")
    hbar(rows, "violations_per_100", "Confirmed violations per 100 turns that reached the model", out / "yield.png", "{:.1f}")
    heatmap([r["tool"] for r in sorted(rows, key=lambda r: -r["violating_turns"])], findings, out / "risk_heatmap.png")

    cols = [("tool", "Tool"), ("tool_version", "Version"), ("turns", "Turns"), ("block_rate", "Blocked by Azure"),
            ("violating_turns", "Confirmed violations"), ("n_distinct_confirmed_risks", "Risk categories"),
            ("distinct_oracle_codes", "Oracle codes hit"), ("self_flagged", "Self-flagged"), ("precision", "Precision"),
            ("recall", "Recall"), ("wall_clock_min", "Wall clock (min)"), ("target_cost_usd", "Target cost (USD)"),
            ("attacker_tokens", "Attacker tokens")]
    fmt = {"block_rate": lambda v: f"{v:.0%}", "precision": lambda v: "—" if v is None else f"{v:.0%}",
           "recall": lambda v: "—" if v is None else f"{v:.0%}", "distinct_oracle_codes": lambda v: ", ".join(v) or "—",
           "target_cost_usd": lambda v: f"{v:.2f}", "attacker_tokens": lambda v: f"{v:,}"}
    lines = ["| " + " | ".join(c[1] for c in cols) + " |", "|" + "---|" * len(cols)]
    for r in sorted(rows, key=lambda r: (-r["n_distinct_confirmed_risks"], -r["violating_turns"])):
        lines.append("| " + " | ".join(fmt.get(c, lambda v: str(v) if v is not None else "—")(r.get(c)) for c, _ in cols) + " |")
    (out / "table.md").write_text("\n".join(lines) + "\n")
    print((out / "table.md").read_text())


if __name__ == "__main__":
    main()
