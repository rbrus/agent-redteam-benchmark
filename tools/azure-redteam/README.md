# Lab — Azure AI Red Teaming Agent

**Goal:** run Microsoft's AI Red Teaming Agent (`azure-ai-evaluation[redteam]`, built on PyRIT) against
the Foundry agent. It is the tool Microsoft ships for exactly this platform, so it is the natural
"native" competitor.

## 1. Install

```bash
uv venv --python 3.12 venvs/azure-redteam
uv pip install --python venvs/azure-redteam "azure-ai-evaluation[redteam]" azure-identity httpx
```

## 2. Azure prerequisites (the part that takes time)

The tool fetches attack objectives from, and sends every reply to, the **Azure AI evaluation
service** of a Foundry project. Two things must be true:

1. **The project must be in a region that supports it.** In a Switzerland North project every
   evaluation failed with `Single inline evaluations are not supported in the switzerlandnorth
   region`. The benchmark uses a second, empty Foundry project in Sweden Central only for this
   (`AZURE_RT_PROJECT_ENDPOINT`); the target agent stays where it is.
2. **Your identity needs data-plane roles on that account.** Contributor is not enough. With only
   `Foundry User` the objectives call failed with `Principal does not have access to API/Operation`;
   adding **`Azure AI Safety Evaluator`** fixed it (allow a few minutes for propagation).

## 3. How it is wired (`run_azure_redteam.py`)

* **Target:** a plain Python callback `target(query) -> str` that posts to the gateway's `/chat`.
* **Risk categories (6):** HateUnfairness, Violence, Sexual, SelfHarm, SensitiveDataLeakage,
  TaskAdherence. 8 objectives each (`AZURE_RT_OBJECTIVES`).
* **Attack strategies:** the `EASY`, `MODERATE` and `DIFFICULT` groups (Base64, Flip, Morse, Tense,
  and compositions), `Jailbreak` (user-prompt injection), `IndirectJailbreak` (cross-prompt
  injection in context), `Crescendo` and `MultiTurn`.
* `skip_upload=True` keeps results local instead of uploading them to the Foundry portal.

## 4. Run

```bash
scripts/gateway.sh runs/my-run
tools/azure-redteam/run.sh runs/my-run        # --smoke: 1 objective, Base64 only
AZURE_RT_SKIP_EVALS=1 tools/azure-redteam/run.sh runs/my-run   # cheap: skip hosted per-turn grading
```

Output: `runs/my-run/azure-redteam/native/.scan_*/final_results.json` — a scorecard (attack success
rate by risk category and attack complexity) and every conversation with `attack_success`.

## 5. Fairness caveat

This is the one tool that **cannot use the benchmark's shared attacker model**. Its objectives, its
multi-turn adversarial model and its evaluator are Microsoft-hosted. That is the product as designed,
so it is benchmarked that way. Its objectives also come from Microsoft's own harm taxonomy rather than
this agent's business rules, so it probes content harms more than tool misuse.

## 6. Cost — read before running (it was ~$73 of the benchmark's ~$80 bill)

The tool's per-turn grading runs on **Microsoft's hosted evaluation service**, billed as
`Foundry Tools / Evaluations input & output tokens` (namespace Microsoft.MachineLearningServices,
"Observability – Evaluations") — **not** under the target's model meters. The baseline run
(2 scans × 256 conversations, 2,578 turns graded server-side) cost **$73.30** — 92% of the whole
benchmark's ~$80 Azure bill, all on the run day. The shared target (`gpt-5-nano`, all seven tools)
cost $3.96 by comparison. **Per confirmed violation: ≈$24 here vs ≈$0.05 for sixi-scanner and
≈$0.01 for promptfoo.** Verify any run's bill in Portal → resource group → account → Cost analysis →
group by meter.

Two levers:

1. **`skip_evals=True`** on the `RedTeam()` call skips the hosted per-turn grading entirely — the
   attacks still run against the gateway and the benchmark's own tool-blind judge scores the turns,
   so the comparison stays valid. Removes ~92% of the tool's cost.
2. **`skip_upload=True`** (already used) keeps results local; but note the studio evaluation link
   (`AiStudioEvaluationUri`) only comes back when the uploads succeed — the baseline run failed its
   role check mid-run (`Authorization failed for seeds`), so no studio record exists for those two
   eval IDs (`ff72a54f…`, `81454115…`); the complete results survive locally instead.
