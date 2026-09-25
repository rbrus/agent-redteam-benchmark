"""agent-probe JSON report -> the benchmark's self_report.json."""
import json, os, sys

run_dir = sys.argv[1]
d = json.load(open(os.path.join(run_dir, "agent-probe/native/report.json")))
MAP = {"Prompt Injection": "LLM01", "Guardrail Bypass": "LLM01", "System Prompt Leak": "LLM07",
       "Sensitive Info Disclosure": "LLM02", "Excessive Agency": "LLM06", "Improper Output Handling": "LLM05"}
attempts = [{"id": r["probe"]["id"], "category": r["probe"]["id"], "owasp": MAP.get(r["probe"]["category"], "other"),
             "prompt": r["probe"]["payload"], "response": r.get("evidence", ""),
             "tool_flagged": r.get("verdict") == "VULNERABLE", "multi_turn": False} for r in d["results"]]
out = {"tool": "agent-probe", "tool_version": os.environ.get("AGENT_PROBE_VERSION", "?"), "config": "fixed 12-probe battery",
       "started_at": d.get("start_time"), "finished_at": d.get("end_time"), "attempts": attempts,
       "tool_summary": {k: d.get(k) for k in ("total_probes", "vulnerable_count", "defended_count", "error_count")}}
json.dump(out, open(os.path.join(run_dir, "agent-probe/self_report.json"), "w"), indent=1)
print(f"agent-probe: {len(attempts)} attempts, {sum(a['tool_flagged'] for a in attempts)} flagged")
