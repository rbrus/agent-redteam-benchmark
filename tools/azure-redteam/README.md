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
```

Output: `runs/my-run/azure-redteam/native/.scan_*/final_results.json` — a scorecard (attack success
rate by risk category and attack complexity) and every conversation with `attack_success`.

## 5. Fairness caveat

This is the one tool that **cannot use the benchmark's shared attacker model**. Its objectives, its
multi-turn adversarial model and its evaluator are Microsoft-hosted. That is the product as designed,
so it is benchmarked that way. Its objectives also come from Microsoft's own harm taxonomy rather than
this agent's business rules, so it probes content harms more than tool misuse.
