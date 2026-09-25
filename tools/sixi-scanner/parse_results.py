"""sixi-scanner JSON results -> the benchmark's self_report.json."""
import json, os, sys

run_dir, label = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "sixi-scanner"
nat = os.path.join(run_dir, label, "native")
OWASP = {"LLM01", "LLM02", "LLM05", "LLM06", "LLM07"}
attempts = []
summary = {}
for part in ("flat", "adaptive"):
    p = os.path.join(nat, f"{part}.json")
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        continue
    d = json.load(open(p))
    summary[part] = {"attempts": len(d.get("all_attack_attempts") or []), "findings": len(d.get("findings") or []),
                     "by_severity": {}}
    for f in d.get("findings") or []:
        s = f.get("severity", "?")
        summary[part]["by_severity"][s] = summary[part]["by_severity"].get(s, 0) + 1
    for i, a in enumerate(d.get("all_attack_attempts") or []):
        cat = a.get("owasp_category") or "other"
        turns = a.get("turns") or a.get("conversation") or None
        attempts.append({
            "id": f"{part}-{i}",
            "category": a.get("technique_id", ""),
            "owasp": cat if cat in OWASP else "other",
            "prompt": a.get("payload_sent", ""),
            "response": a.get("target_response", ""),
            "tool_flagged": bool(a.get("success")),
            "multi_turn": part == "adaptive",
        })
version = open(os.path.join(nat, "version.txt")).read().strip() if os.path.exists(os.path.join(nat, "version.txt")) else "?"
rd = lambda n: open(os.path.join(nat, n)).read().strip() if os.path.exists(os.path.join(nat, n)) else None
out = {"tool": label, "tool_version": version, "config": "flat library (attempts=2, attacker rewrite) + adaptive (turns=10)",
       "started_at": rd("started_at"), "finished_at": rd("finished_at"), "attempts": attempts, "tool_summary": summary}
json.dump(out, open(os.path.join(run_dir, label, "self_report.json"), "w"), indent=1)
print(f"{label}: {len(attempts)} attempts, {sum(a['tool_flagged'] for a in attempts)} flagged")
