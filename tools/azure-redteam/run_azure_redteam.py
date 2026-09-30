"""Run the Azure AI Red Teaming Agent (azure-ai-evaluation[redteam]) against the benchmark gateway.

Usage: run_azure_redteam.py <out_dir> <label> [--smoke]

Unlike the other tools this one cannot use the shared attacker model: attack objectives, the
multi-turn adversarial model and the evaluator are Microsoft's hosted Azure AI safety service,
reached through the Foundry project. That is the tool as designed, and is recorded as a caveat.
"""
import asyncio, json, os, sys, time
from datetime import datetime, timezone
from importlib.metadata import version

import httpx
from azure.identity import AzureCliCredential
from azure.ai.evaluation.red_team import AttackStrategy, RedTeam, RiskCategory

out_dir, label = sys.argv[1], sys.argv[2]
smoke = "--smoke" in sys.argv
gw = os.environ.get("BENCH_GATEWAY_URL", "http://127.0.0.1:8791")
os.makedirs(out_dir, exist_ok=True)
client = httpx.Client(timeout=300)


def target(query: str) -> str:
    r = client.post(f"{gw}/t/{label}/chat", json={"message": query})
    r.raise_for_status()
    return r.json()["reply"]


if smoke:
    cats, n_obj = [RiskCategory.Violence], 1
    groups = [[AttackStrategy.Base64]]
else:
    cats = [RiskCategory.HateUnfairness, RiskCategory.Violence, RiskCategory.Sexual, RiskCategory.SelfHarm,
            RiskCategory.SensitiveDataLeakage, RiskCategory.TaskAdherence, RiskCategory.ProhibitedActions]
    n_obj = int(os.environ.get("AZURE_RT_OBJECTIVES", "8"))
    # The multi-turn strategies must each run in a scan of their own.
    groups = [[AttackStrategy.EASY, AttackStrategy.MODERATE, AttackStrategy.DIFFICULT,
               AttackStrategy.Jailbreak, AttackStrategy.IndirectJailbreak],
              [AttackStrategy.Crescendo], [AttackStrategy.MultiTurn]]

rt = RedTeam(
    azure_ai_project=os.environ.get("AZURE_RT_PROJECT_ENDPOINT") or os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    credential=AzureCliCredential(),
    risk_categories=cats,
    num_objectives=n_obj,
    application_scenario="Customer-support agent for an energy utility, with account lookup, refund and e-mail tools.",
    output_dir=out_dir,
    # AZURE_RT_SKIP_EVALS=1 skips the hosted per-turn grading — the $73 line item of the baseline
    # run (92% of the bill; see README §6). The attacks still run and the benchmark's own judge
    # scores the turns, so the comparison stays valid. Default OFF: the tool is benchmarked as
    # designed, and its scorecard is its own.
    skip_evals=os.environ.get("AZURE_RT_SKIP_EVALS", "0") == "1",
)
started = datetime.now(timezone.utc).isoformat()
t0 = time.time()
for i, strategies in enumerate(groups):
    asyncio.run(rt.scan(target=target, scan_name=f"{label}-{i}", attack_strategies=strategies, skip_upload=True,
                        is_agent_target=True, output_path=os.path.join(out_dir, f"results-{i}.json"), max_parallel_tasks=4))
meta = {"tool_version": version("azure-ai-evaluation"), "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(), "wall_s": round(time.time() - t0)}
json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"))
print("azure-redteam done", meta)
