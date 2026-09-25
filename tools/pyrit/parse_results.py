#!/usr/bin/env python
"""Convert PyRIT native output into the benchmark's self_report.json schema.

Reads ``<run_dir>/pyrit/native/{attack_results,conversations,run_meta}.json`` (written by
``pyrit_run.py``) and writes ``<run_dir>/pyrit/self_report.json``.

One attempt is emitted per *target turn*. For a multi-turn attack the tool's success verdict
(``tool_flagged``) is attached only to the last turn of the conversation; earlier turns are null,
per the benchmark instructions. Uses only the standard library.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

VALID_OWASP = {"LLM01", "LLM02", "LLM05", "LLM06", "LLM07", "harmful", "other"}


def load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def build_attempts(records, conversations):
    attempts = []
    for rec in records:
        cid = rec.get("conversation_id")
        if not cid:
            continue
        turns = conversations.get(cid) or []
        # ordered target turns: each assistant message, paired with the preceding user text
        pairs = []
        last_user = None
        for t in sorted(turns, key=lambda x: x.get("sequence", 0)):
            if t["role"] == "user":
                last_user = t
            elif t["role"] == "assistant":
                pairs.append((last_user, t))
        if not pairs:
            continue

        # Backtracked / pruned branches (e.g. Crescendo) are extra target turns on the same attack;
        # append their pairs too, always unflagged (they are never the final verdict turn).
        pruned_pairs = []
        for pcid in rec.get("pruned_conversation_ids") or []:
            pturns = conversations.get(pcid) or []
            lu = None
            for t in sorted(pturns, key=lambda x: x.get("sequence", 0)):
                if t["role"] == "user":
                    lu = t
                elif t["role"] == "assistant":
                    pruned_pairs.append((lu, t))

        meta = rec.get("meta") or {}
        owasp = meta.get("owasp") if meta.get("owasp") in VALID_OWASP else "other"
        category = meta.get("category") or rec.get("attack_class") or "pyrit-attack"
        multi_turn = (len(pairs) + len(pruned_pairs)) > 1
        succeeded = rec.get("outcome") == "success"
        short = cid.replace("-", "")[:8]

        n = len(pairs)
        for i, (u, a) in enumerate(pairs):
            is_last = i == n - 1
            if multi_turn:
                flagged = bool(succeeded) if is_last else None
            else:
                flagged = bool(succeeded)
            attempts.append({
                "id": f"{short}-t{i + 1}",
                "category": category,
                "owasp": owasp,
                "prompt": (u or {}).get("text", "") if u else "",
                "response": a.get("text", ""),
                "tool_flagged": flagged,
                "multi_turn": multi_turn,
            })
        for j, (u, a) in enumerate(pruned_pairs):
            attempts.append({
                "id": f"{short}-p{j + 1}",
                "category": category,
                "owasp": owasp,
                "prompt": (u or {}).get("text", "") if u else "",
                "response": a.get("text", ""),
                "tool_flagged": None,
                "multi_turn": True,
            })
    return attempts


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: parse_results.py <run_dir>", file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1]).resolve()
    native = run_dir / "pyrit" / "native"

    records = load(native / "attack_results.json") or []
    conversations = load(native / "conversations.json") or {}
    meta = load(native / "run_meta.json") or {}

    attempts = build_attempts(records, conversations)

    flagged = sum(1 for a in attempts if a["tool_flagged"] is True)
    by_owasp: dict[str, int] = {}
    for a in attempts:
        by_owasp[a["owasp"]] = by_owasp.get(a["owasp"], 0) + 1
    by_outcome: dict[str, int] = {}
    for r in records:
        oc = r.get("outcome") or "none"
        by_outcome[oc] = by_outcome.get(oc, 0) + 1
    errors = [r.get("error") for r in records if r.get("error")]

    report = {
        "tool": "pyrit",
        "tool_version": meta.get("tool_version") or _pyrit_version(),
        "config": meta.get("config", ""),
        "started_at": meta.get("started_at", ""),
        "finished_at": meta.get("finished_at", ""),
        "attempts": attempts,
        "tool_summary": {
            "attack_records": len(records),
            "attempts_total": len(attempts),
            "attempts_flagged": flagged,
            "target_turns": meta.get("target_turns"),
            "wall_seconds": meta.get("wall_seconds"),
            "smoke": meta.get("smoke"),
            "attempts_by_owasp": by_owasp,
            "records_by_outcome": by_outcome,
            "errors": errors,
        },
    }

    out = run_dir / "pyrit" / "self_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"[pyrit] wrote {out} ({len(attempts)} attempts, {flagged} flagged)")
    return 0


def _pyrit_version() -> str:
    try:
        import importlib.metadata as m
        return m.version("pyrit")
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
