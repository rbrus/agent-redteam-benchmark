"""promptfoo flags.jsonl (from export_flags.py) -> the benchmark's self_report.json."""
import json, os, sys

run_dir = sys.argv[1]
nat = os.path.join(run_dir, "promptfoo", "native")
meta = json.load(open(os.path.join(nat, "run-meta.json")))
OWASP = {"prompt-extraction": "LLM07", "pii": "LLM02", "harmful:privacy": "LLM02", "cross-session-leak": "LLM02",
         "excessive-agency": "LLM06", "rbac": "LLM06", "tool-discovery": "LLM06", "debug-access": "LLM06",
         "shell-injection": "LLM06", "sql-injection": "LLM06", "beavertails": "harmful", "policy": "LLM01"}
def owasp(plugin):
    for k, v in OWASP.items():
        if plugin and plugin.startswith(k):
            return v
    return "other"
attempts = []
for i, l in enumerate(open(os.path.join(nat, "flags.jsonl"))):
    r = json.loads(l)
    attempts.append({"id": f"{r.get('result_id')}-{r.get('turn')}", "category": f"{r.get('plugin')}/{r.get('strategy')}",
                     "owasp": owasp(r.get("plugin")), "prompt": r.get("prompt", ""), "response": r.get("output", ""),
                     "tool_flagged": r.get("flagged", r.get("test_flagged")), "multi_turn": r.get("strategy") in ("crescendo", "jailbreak", "iterative-local")})
out = {"tool": "promptfoo", "tool_version": meta.get("version"), "config": "local-only redteam (remote generation off)",
       "started_at": meta.get("started"), "finished_at": meta.get("finished"), "attempts": attempts, "tool_summary": meta}
json.dump(out, open(os.path.join(run_dir, "promptfoo", "self_report.json"), "w"), indent=1)
print(f"promptfoo: {len(attempts)} attempts, {sum(1 for a in attempts if a['tool_flagged'])} flagged")
