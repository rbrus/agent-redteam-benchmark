#!/usr/bin/env python3
"""Publish the oracle-gap probe evidence from the raw probe ledgers.

`runs/` is gitignored, so the ledgers behind `tools/sixi-scanner-oss/PORTING.md` §8 would otherwise
not be in the repository and the "28 probe payloads, 0 oracle hits" claim could not be checked by a
reader. This generates the published copy from the ledgers rather than restating them by hand, so the
published table cannot drift from what was actually sent.

Every field comes from the ledger the probe scripts wrote: the payload as sent, the reply as received,
the tool calls the model emitted, and the oracle codes `target/oracles.py` returned for them.

Usage:  python3 scripts/publish_probe_evidence.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (run directory, published round name, what the round set out to test)
ROUNDS = [
    ("runs/probe-retrieval", "retrieval",
     "does retrieval-triggered indirect injection break this target?"),
    ("runs/probe-retrieval2", "pressure-elements",
     "which of four pressure elements carries the attack? (this round's design was wrong — see below)"),
    ("runs/probe-framing", "framing",
     "is procedure framing the variable, rather than retrieval or pressure?"),
    ("runs/probe-recipient", "recipient-class",
     "does a reserved TLD make the exfiltration probe untestable?"),
]


def main() -> int:
    rounds: list[dict] = []
    total = hits = 0
    for rel, name, question in ROUNDS:
        path = ROOT / rel / "probe.jsonl"
        if not path.exists():
            print(f"  missing {rel} — run the probe first", file=__import__("sys").stderr)
            return 1
        probes = [json.loads(line) for line in path.open()]
        for p in probes:
            total += 1
            hits += bool(p.get("codes"))
        rounds.append({"round": name, "question": question, "probes": probes})

    out = ROOT / "results" / "2026-10-07-probe-oracle-gap"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "probes.jsonl").open("w") as fh:
        for r in rounds:
            for p in r["probes"]:
                fh.write(json.dumps({"round": r["round"], **p}) + "\n")

    summary = {
        "generated_from": [r[0] + "/probe.jsonl" for r in ROUNDS],
        "total_probes": total,
        "oracle_hits": hits,
        "rounds": [{"round": r["round"], "question": r["question"],
                    "probes": len(r["probes"]),
                    "oracle_hits": sum(bool(p.get("codes")) for p in r["probes"])} for r in rounds],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"wrote {out.relative_to(ROOT)}/ from {total} probe records")
    for r in summary["rounds"]:
        print(f"  {r['round']:18} {r['probes']:>3} probes, {r['oracle_hits']} oracle hits")
    print(f"  {'TOTAL':18} {total:>3} probes, {hits} oracle hits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
