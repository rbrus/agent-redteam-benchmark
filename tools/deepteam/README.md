# Lab — DeepTeam

**Goal:** run DeepTeam (Confident AI, open source) against the Foundry agent with its agent-relevant
vulnerabilities and a mix of single-turn and multi-turn attacks, on the shared local attacker model.

## 1. Install

```bash
uv venv --python 3.12 venvs/deepteam
uv pip install --python venvs/deepteam deepteam sentry-sdk httpx
```

`sentry-sdk` is imported by DeepTeam's telemetry module but was missing from its dependencies in the
version tested (1.0.9). Telemetry itself is switched off (`DEEPTEAM_TELEMETRY_OPT_OUT=YES`).

## 2. How it is wired (`run_deepteam.py`)

* **Models.** DeepTeam needs a *simulator* (writes the attacks) and an *evaluator* (grades replies).
  Both are `deepeval.models.LocalModel` pointed at the gateway's `/attacker/deepteam/v1`. Multi-turn
  attacks carry their own `simulator_model`, which the script sets to the same model.
* **Target.** An async `model_callback(prompt, turns)` posts the conversation so far to the gateway's
  OpenAI-compatible endpoint, so multi-turn attacks keep their history.
* **Purpose.** `target_purpose` describes the agent and its rules — never the secret values.
* **Vulnerabilities (15):** PromptLeakage, PIILeakage, ExcessiveAgency, BOLA, BFLA, RBAC,
  IndirectInstruction, ExploitToolAgent, GoalTheft, DebugAccess, Robustness, ShellInjection,
  SQLInjection, Toxicity, IllegalActivity — every sub-type of each.
* **Attacks (13):** PromptInjection, SystemOverride, PromptProbing, PermissionEscalation,
  GoalRedirection, ContextPoisoning, Roleplay, Base64, ROT13, Leetspeak, Multilingual, plus
  LinearJailbreaking (5 turns) and CrescendoJailbreaking (6 rounds, 3 backtracks). Weights favour
  injection and the multi-turn attacks.
* `attacks_per_vulnerability_type=2`: two test cases per vulnerability sub-type, attack chosen by weight.

## 3. Run

```bash
scripts/gateway.sh runs/my-run
tools/deepteam/run.sh runs/my-run            # --smoke: 2 vulnerabilities, 3 attacks
```

Output: `runs/my-run/deepteam/native/deepteam_results.json` (every test case: vulnerability, attack,
input, output, the multi-turn transcript, `score` 1 = safe / 0 = vulnerable, and the evaluator's
reason), converted to `self_report.json` by `parse_results.py`.

## 4. Gotchas

* DeepTeam's default models are OpenAI's (`gpt-4o-mini` / `gpt-4o`). Without an explicit
  `simulator_model` and `evaluation_model` it would call OpenAI.
* A test case whose evaluation fails is reported with `score = null` and an `error` — count them;
  they are not passes.
* DeepTeam prints a "Pass Rate" over the test cases that were *evaluated*; errored cases are left out
  of the denominator.
* Local attacker models that reject a conversation with no user turn will fail DeepTeam's simulator
  prompts; the gateway's attacker proxy adds a neutral user turn for every tool.
