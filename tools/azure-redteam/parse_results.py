"""Azure AI Red Teaming Agent final_results.json -> the benchmark's self_report.json."""
import glob, json, os, sys

run_dir = sys.argv[1]
nat = os.path.join(run_dir, "azure-redteam", "native")
files = sorted(glob.glob(os.path.join(nat, ".scan_*", "final_results.json")), key=os.path.getmtime)
scans = [json.load(open(f)) for f in files]
d = {"attack_details": [a for x in scans for a in x.get("attack_details") or []],
     "scorecard": [x.get("scorecard") for x in scans]}
meta = json.load(open(os.path.join(nat, "meta.json")))
OWASP = {"sensitive_data_leakage": "LLM02", "task_adherence": "LLM06", "prohibited_actions": "LLM06"}
attempts = []
for i, a in enumerate(d.get("attack_details") or []):
    conv = a.get("conversation") or []
    multi = sum(1 for m in conv if m["role"] == "user") > 1
    for j in range(len(conv) - 1):
        if conv[j]["role"] == "user" and conv[j + 1]["role"] == "assistant":
            last = j + 1 == len(conv) - 1
            attempts.append({"id": f"{i}-{j}", "category": f"{a.get('risk_category')}/{a.get('attack_technique')}",
                             "owasp": OWASP.get(a.get("risk_category"), "harmful"), "prompt": conv[j]["content"],
                             "response": conv[j + 1]["content"],
                             "tool_flagged": bool(a.get("attack_success")) if last else None, "multi_turn": multi})
# A scan that was stopped before it finished has no final_results.json; its conversations are still
# evidence of what was sent, without the tool's verdict.
done_dirs = {os.path.dirname(f) for f in files}
for part in sorted(glob.glob(os.path.join(nat, ".scan_*", "*_results.jsonl"))):
    if os.path.dirname(part) in done_dirs:
        continue
    for k, line in enumerate(open(part)):
        conv = (json.loads(line).get("conversation") or {}).get("messages") or []
        for j in range(len(conv) - 1):
            if conv[j]["role"] == "user" and conv[j + 1]["role"] == "assistant":
                attempts.append({"id": f"partial-{os.path.basename(part)}-{k}-{j}", "category": os.path.basename(part).replace("_results.jsonl", ""),
                                 "owasp": "harmful", "prompt": conv[j]["content"], "response": conv[j + 1]["content"],
                                 "tool_flagged": None, "multi_turn": True})
out = {"tool": "azure-redteam", "tool_version": meta["tool_version"], "config": "Azure AI Red Teaming Agent (hosted objectives + evaluator)",
       "started_at": meta["started_at"], "finished_at": meta["finished_at"], "attempts": attempts, "tool_summary": d.get("scorecard")}
json.dump(out, open(os.path.join(run_dir, "azure-redteam", "self_report.json"), "w"), indent=1)
print(f"azure-redteam: {len(attempts)} attempts, {sum(1 for a in attempts if a['tool_flagged'])} flagged")
