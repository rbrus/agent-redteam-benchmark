# Lab — sixi-scanner

**Goal:** run the full sixi-scanner technique library, then its multi-turn adaptive agents, against the
Foundry agent through the benchmark gateway.

sixi-scanner is a single Go binary. It ships 46 attack agents (36 single-shot "Phase A" scouts and 10
multi-turn "Phase B" adaptive agents) that resolve to 326 registered techniques, mapped to the OWASP LLM
Top 10, OWASP Agentic threats, MITRE ATLAS, the EU AI Act and GDPR. It speaks REST, A2A, MCP, WebSocket
and browser chat.

## 1. Install

sixi-scanner is distributed as a licensed binary; without a licence it runs in *unlicensed evaluation
mode*, which is what this benchmark used. Put the binary on your `PATH` or point `SIXI_SCANNER_BIN` at it.

```bash
sixi-scanner version
```

## 2. How it is wired

| Setting | Value | Why |
|---|---|---|
| `--target` | `http://127.0.0.1:8791/t/sixi-scanner/chat` | the gateway's REST endpoint |
| `--field` / `--reply-path` | defaults `message` / `reply` | match the gateway's JSON |
| `SIXI_ATTACKER_PROVIDER=openai` + `SIXI_ATTACKER_BASE_URL` | the gateway's `/attacker/sixi-scanner/v1` | the shared attacker model every tool uses |
| `SIXI_ATTACKER_RESIDENCY=local` | | the attacker runs on the same machine; the residency check passes |

`run.sh` makes two passes:

1. **Phase A, the whole library:** `sixi-scanner scan --attempts 2`. Each payload is rewritten by the
   attacker model for this target before it is sent, and gets up to two attempts.
2. **Phase B, adaptive:** `sixi-scanner scan --adaptive --turns 10`. Each adaptive technique runs a
   conversation of up to 10 turns, steered by the attacker model.

## 3. Run

```bash
scripts/gateway.sh runs/my-run          # in another terminal
tools/sixi-scanner/run.sh runs/my-run   # add --smoke for one agent, ~15 turns
```

Output: `runs/my-run/sixi-scanner/native/{flat,adaptive}.json` (the scanner's JSON report: every attempt
with payload, response, the technique's verdict and confidence, plus deduplicated findings with
OWASP / MITRE ATLAS mapping). `parse_results.py` turns them into the common `self_report.json`.

Other formats of the same result: `--format md | html | sarif | compliance | evidence`.

## 4. Reading the result

* `findings[]` — what sixi-scanner reports as vulnerabilities, with severity and evidence.
* `all_attack_attempts[]` — every attempt, including the defended ones.
* Exit code: `0` clean, `1` findings at or above `--fail-on`, `2` nothing assessed (e.g. the target
  never answered). The benchmark passes `--fail-on none` so the exit code never stops the run.

## 5. Gotchas

* **Judge on marker heuristics by default.** In Phase A, a technique's verdict comes from the markers
  it looks for in the reply (`judge_version: markers-2`). Against this target that flagged the
  authenticated customer's *own* data as a PII leak, and flagged some refusals. See the benchmark's
  lessons learned for the fix.
* The CLI has no turn budget: the size of a Phase A run is the size of the technique library times
  `--attempts`.
