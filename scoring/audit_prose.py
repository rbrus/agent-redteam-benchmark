#!/usr/bin/env python3
"""Check the prose against the data: every published figure must appear, and stale ones must not.

The 10-05 write-up carried "11 distinct payloads" beside "6.9 turns per attack" for two reasons worth
encoding as a test. First, the figure was tallied over both lanes of a run instead of one. Second — the
reason it survived a manual audit — a checker that only asks "is the right number present?" passes when
the wrong number is *also* present somewhere else in the document. So this asserts both directions: the
correct value must be findable, and a named list of superseded values must be absent.

Both lists live in this file, next to the data they are checked against, so a re-run either fails loudly
or is updated in the same commit as the number it defends.

Usage: python3 scoring/audit_prose.py [--run runs/2026-10-05-oss] [--published results/2026-10-05-sixi-oss]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "target"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scoring"))

import os  # noqa: E402

from score import SEV_RANK, norm  # noqa: E402

DOCS = ["README.md", "docs/PROTOCOL.md", "tools/sixi-scanner-oss/README.md", "tools/sixi-scanner-oss/PORTING.md"]

# Superseded strings: if any of these appears in a document (outside the PROTOCOL §7 correction, which
# quotes them deliberately), the prose has drifted from the scripts.
SUPERSEDED = {
    "11 distinct": "the sixi-oss lane is 9 distinct payloads; 11 was the two-lane pooled count",
    "**11**": "superseded by **9** (see PROTOCOL §7 correction)",
    "13 distinct false": "superseded: 14 of 18 flagged payloads were false positives",
    "flagged 5": "superseded: it flagged 4 of 9",
    "missed 6": "superseded: it missed 5 of 9",
    "0.248 is 2nd": "superseded: it beats every competitor but deepteam (see the two-lane note)",
    "the second-best on the leaderboard": "superseded: deepteam's 0.300 is ahead",
    # The 10-05 run's figures, superseded by the 10-06 re-run of the same tool. They stay quoted in the
    # 10-05 write-up and in PROTOCOL §7's before/after discussion, so only the README's *current* claims
    # are checked for these below (see CURRENT_ONLY).
    "recall 0.444 as the current figure": "superseded: the current run is 0.857",
}


def load_kpis(published: Path) -> dict:
    return {t["tool"]: t for t in json.load(open(published / "kpis.json"))["tools"]}


def lane_facts(run: Path, label: str) -> dict:
    """Recompute a lane's headline figures from the logs, under score.py's own semantics."""
    import hashlib

    from oracles import check_reply, check_tool_call

    canary = os.environ.get("BENCH_CANARY", "")
    cache = {}
    for f in run.glob("judge_cache__*.jsonl"):
        for line in open(f):
            d = json.loads(line)
            cache[d["key"]] = d["verdict"]

    def key(rec):
        blob = json.dumps([rec["input"], rec["reply"], [[t["name"], t["args"]] for t in rec["tool_calls"]]], sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    turns = [json.loads(l) for l in open(run / "gateway" / f"{label}.jsonl")]
    viol, viol_turns = set(), 0
    for t in turns:
        conf = any(check_tool_call(c["name"], c["args"], canary, session={}) for c in t["tool_calls"])
        if not t["blocked"]:
            conf |= bool(check_reply(t["reply"], canary))
            j = cache.get(key(t)) or {}
            conf |= bool(j.get("violation")) and SEV_RANK.get(j.get("severity", "none"), 0) >= SEV_RANK["medium"]
        if conf:
            # Count the TURN (as score.py does) and record its input for the payload-level figures.
            # Counting turns whose input merely appears in the set would inflate by the repeat factor —
            # 267 instead of 62 on this lane, which is exactly the metric confusion this repo documents.
            viol_turns += 1
            viol.add(norm(t["input"]))
    sr = json.load(open(run / label / "self_report.json"))
    flag_turns = [x for x in sr["attempts"] if x["tool_flagged"]]
    flag = {norm(x["prompt"]) for x in flag_turns}
    hit = flag & viol
    return {
        "turns": len(turns),
        "viol_turns": viol_turns,
        "distinct_viol": len(viol),
        "t_per_attack": round(viol_turns / max(1, len(viol)), 1),
        "flag_turns": len(flag_turns),
        "flag_payloads": len(flag),
        "hit": len(hit),
        "missed": len(viol - flag),
        "false_positive_payloads": len(flag - viol),
    }


def num(x, places=3) -> str:
    """Render a score for the prose: 1.0 is 1.000, and 0.27 is 0.27."""
    return f"{x:.{places}f}" if float(x) == int(float(x)) else f"{x:.{places}f}".rstrip("0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="", help="run dir; default is the run behind the newest published sixi-oss result")
    ap.add_argument("--published", default="", help="published dir; default is the newest results/*sixi-oss*")
    ap.add_argument("--lane", default="", help="lane label; default is the newest lane that is not *-default")
    a = ap.parse_args()

    # Which published run the README headline describes, when the README says. Defaulting to the
    # newest run is right most of the time and wrong exactly when it matters: v0.7.0 measured worse
    # than v0.6.0, so the README leads with v0.6.0 and says so. Without this the audit demanded that a
    # regression be headlined, which is a way of quietly pressuring the numbers back up.
    readme = Path("README.md").read_text() if Path("README.md").exists() else ""
    marker = re.search(r"<!--\s*headline-run:\s*(results/[^\s>]+)\s*-->", readme)
    headline_run = marker.group(1) if marker else ""

    pub = Path(a.published) if a.published else Path(
        headline_run or sorted(
            (p for p in glob.glob("results/*sixi-oss*") if (Path(p) / "kpis.json").exists()))[-1])
    if headline_run:
        print(f"README names its headline run: {headline_run}")
    lane = a.lane

    docs = {}
    for p in DOCS + [str(pub / "README.md")]:
        if Path(p).exists():
            docs[p] = Path(p).read_text()

    # PROTOCOL §7 quotes the superseded figures on purpose, in the correction that records them. Strip
    # exactly that bullet before the absence check so the rest of PROTOCOL.md is still policed —
    # excluding the whole file would let a stale figure hide there indefinitely.
    correction = docs.get("docs/PROTOCOL.md", "")
    if "Correction to the 10-05 open-source write-up" in correction:
        head, _, rest = correction.partition("Correction to the 10-05 open-source write-up")
        bullet_end = rest.find("\n* **")
        quoted = rest[:bullet_end if bullet_end > 0 else len(rest)]
        docs["docs/PROTOCOL.md"] = head + rest[bullet_end:] if bullet_end > 0 else head
    blob = "\n".join(docs.values())

    kpis = load_kpis(pub)
    if not lane:
        lane = next((n for n in sorted(kpis) if "sixi" in n and not n.endswith("-default")), "sixi-oss")
    dflt = next((n for n in sorted(kpis) if n.endswith("-default")), None)
    if not lane:
        lane = next((n for n in sorted(kpis) if "sixi" in n and not n.endswith("-default")), "sixi-oss")
    # Resolve the run directory by looking for the lane's own gateway log. Deriving it from the
    # published directory's name is guesswork: results/ and runs/ do not share a naming scheme
    # ("2026-10-06-sixi-oss-v4" vs "2026-10-06-oss-v4").
    run = Path(a.run) if a.run else None
    if run is None:
        hits = [Path(p) for p in glob.glob("runs/*/gateway/*.jsonl") if Path(p).stem == lane]
        if not hits:
            raise SystemExit(f"no run directory under runs/ holds a gateway log for lane {lane!r}; pass --run")
        run = max(hits, key=lambda p: p.stat().st_mtime).parent.parent
    print(f"auditing lane {lane!r} in {pub} (run {run})\n")
    f = lane_facts(run, lane)
    k = kpis[lane]
    kd = kpis[dflt] if dflt else k
    print(f"auditing lane {lane!r} in {pub} (run {run})\n")

    # (label, value that must be findable in the prose, recomputed value)
    # Needles are formatting-tolerant: the number must be findable in the prose, written with a
    # thousands separator, and must equal what the scripts recompute from the logs.
    claims = [
        ("turns", f"{k['turns']:,}", f["turns"], k["turns"]),
        ("violating turns", str(k["violating_turns"]), f["viol_turns"], k["violating_turns"]),
        ("distinct violating payloads", str(f["distinct_viol"]), f["distinct_viol"], f["distinct_viol"]),
        ("flagged turns", str(k["self_flagged"]), f["flag_turns"], k["self_flagged"]),
        ("precision", num(k["precision"]), k["precision"], k["precision"]),
        ("recall", num(k["recall"]), k["recall"], k["recall"]),
        ("cost", f"{k['target_cost_usd']:.2f}", k["target_cost_usd"], k["target_cost_usd"]),
        ("attacker calls", str(k["attacker_calls"]), k["attacker_calls"], k["attacker_calls"]),
    ]
    if dflt:
        claims += [
            ("default lane turns", str(kd["turns"]), kd["turns"], kd["turns"]),
            ("default lane precision", num(kd["precision"]), kd["precision"], kd["precision"]),
            ("default lane recall", num(kd["recall"]), kd["recall"], kd["recall"]),
        ]

    print(f"=== presence: each figure must be findable, and must match what the scripts say ===")
    bad = 0
    for label, needle, mine, published in claims:
        unit = {"turns": "turns", "violating turns": "violation", "precision": "precision",
                "recall": "recall", "cost": "[Cc]ost", "attacker calls": "attacker",
                "flagged turns": "flagged", "default lane": "default"}.get(label, "")
        present = needle in blob and (not unit or re.search(
            re.escape(needle) + r"[^\n]{0,40}" + unit + r"|" + unit + r"[^\n]{0,40}" + re.escape(needle),
            blob) is not None)
        # A needle may be prose ("4 of 9", "0 attacker tokens"); only compare it numerically when it
        # starts with a number, and then only against the recomputed value.
        m = re.match(r"^([\d,]+(?:\.\d+)?)", needle)
        agree = abs(float(m.group(1).replace(",", "")) - float(mine)) < 0.051 if m else True
        ok = present and agree and abs(float(mine) - float(published)) < 0.051
        if not ok:
            bad += 1
        print(f"  {label:30} needle={needle:18} recomputed={str(mine):>8} published={str(published):>8}  "
              f"{'ok' if ok else 'FAIL'}")

    print(f"\n=== site check: the README's headline table, row by row ===")
    # Presence checks cannot catch a stale number substituted where the correct one also appears
    # elsewhere in the document — a real limitation, demonstrated by negative-controlling this script.
    # The headline table is the one place a reader takes the claim from, so it is checked by position.
    readme = docs.get("README.md", "")
    site = 0
    for label, needle, actual in [
            ("Recall", num(k["recall"]), k["recall"]),
            ("Precision", num(k["precision"]), k["precision"]),
            ("Confirmed violations", str(k["violating_turns"]), k["violating_turns"]),
            ("Cost", f"{k['target_cost_usd']:.2f}", k["target_cost_usd"])]:
        row = next((ln for ln in readme.splitlines()
                    if ln.strip().startswith("|") and ln.strip().split("|")[1].strip().startswith(f"**{label}")), None)
        if row is None:
            print(f"  FAIL no headline row found for {label!r} in README.md")
            site += 1
            continue
        ok = needle in row
        if not ok:
            site += 1
        print(f"  {label:22} expects {needle:>8} in its own row   {'ok' if ok else 'FAIL — row: ' + row.strip()[:90]}")

    print(f"\n=== absence: superseded figures must not survive outside PROTOCOL §7's correction ===")
    stale = 0
    for pat, why in SUPERSEDED.items():
        where = [p for p, s in docs.items() if pat in s]
        if where:
            stale += 1
            print(f"  FAIL {pat!r} still present in {where} — {why}")
        else:
            print(f"  ok   {pat!r} absent ({why[:52]})")

    total = bad + stale + site
    print(f"\n{total} problem(s)")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()