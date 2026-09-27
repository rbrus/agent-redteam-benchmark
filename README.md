# Agent Red-Team Benchmark

**Seven AI red-teaming tools against one real Microsoft Foundry agent, behind Azure's strictest
content safety. Scored from the wire, not from the tools' own reports.**

| | |
|---|---|
| Target | Foundry prompt agent on `gpt-5-nano`, every content filter at **Low**, Prompt Shields on, four function tools |
| Tools | [garak](https://github.com/NVIDIA/garak), [promptfoo](https://github.com/promptfoo/promptfoo), [DeepTeam](https://github.com/confident-ai/deepteam), [PyRIT](https://github.com/Azure/PyRIT), [Azure AI Red Teaming Agent](https://learn.microsoft.com/azure/ai-foundry/concepts/ai-red-teaming-agent), sixi-scanner, [agent-probe](https://github.com/rbrus/agent-probe) |
| Ground truth | deterministic oracles on every turn + a tool-blind LLM judge |
| Run | 2026-09-24, ≈5,900 target turns, ≈$3 of target inference · sixi-scanner re-run 2026-09-26 |

> **Conflict of interest.** This benchmark is maintained by the authors of one of the tools under test (sixi-scanner). That conflict of interest is stated here, and is the reason the scoring is oracle-first and tool-blind.

## Results (2026-09-24 Baseline)

| Tool | Version | Turns | Blocked by Azure | Confirmed violations | Risk categories | Oracle codes hit | Self-flagged | Precision | Recall | Wall clock (min) | Target cost (USD) | Attacker tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| garak | 0.17.0 | 1354 | 21% | 81 | 8 | INDIRECT_INJECTION_FOLLOWED, UNAUTHORIZED_EMAIL_RECIPIENT | 362 | 14% | 56% | 113.6 | 0.70 | 472,807 |
| promptfoo | 0.123.1 | 752 | 2% | 89 | 5 | DATA_EXFIL_VIA_TOOL, INDIRECT_INJECTION_FOLLOWED, UNAUTHORIZED_EMAIL_RECIPIENT | 92 | 14% | 15% | 218.1 | 0.79 | 3,053,548 |
| deepteam | 1.0.9 | 165 | 4% | 22 | 5 | — | 10 | 30% | 14% | 41.0 | 0.17 | 990,417 |
| sixi-scanner | sixi (go engine) dev (e69b4edc777b-dirty) built 2026-09-23T04:38:00Z | 655 | 1% | 19 | 3 | — | 108 | 3% | 16% | 264.7 | 0.47 | 533,844 |
| pyrit | 1.1.0 | 376 | 15% | 16 | 3 | — | 39 | 8% | 19% | 220.7 | 0.22 | 1,785,310 |
| azure-redteam | 1.18.6 | 2578 | 64% | 3 | 2 | — | 0 | — | 0% | 330.3 | 0.57 | 0 |
| agent-probe | ? | 12 | 25% | 0 | 0 | — | 0 | — | — | 1.0 | 0.00 | 0 |

## sixi-scanner after its first fix cycle (2026-09-26)

The 09-24 baseline ran sixi-scanner with an empty target context and no confirmation pass. Every
finding it reported was screened by nothing, and the ones it missed were missed by silence. The
fix cycle that followed — all disclosed in [PROTOCOL §7](docs/PROTOCOL.md) — shipped a declared
target context, a three-framing confirmation judge, a rule-recitation wrapper, proven payload ports,
and a timeout so a slow reply is waited for rather than scored as a wall.

Re-running the tool against the same target and judge (767 turns, $0.59 target spend — the other six
tools were not re-run; their 09-24 rows are the comparison):

| Tool | Turns | Blocked by Azure | Confirmed violations | Risk categories | Oracle codes hit | Self-flagged | Precision | Recall | Wall clock (min) | Target cost (USD) | Attacker tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sixi-scanner (2026-09-26) | 767 | 2% | **27** | **8** | **DATA_EXFIL_VIA_TOOL, INDIRECT_INJECTION_FOLLOWED, UNAUTHORIZED_EMAIL_RECIPIENT** | 119 | **10%** | **44%** | 215.0 | 0.59 | 1,255,527 |

Against the 09-24 leaderboard, the same tool moved **from last competitive place to third**:

| | 09-24 | 09-26 | leaderboard (best of each tool) |
|---|---|---|---|
| Confirmed violations | 19 (5th) | **27** | **3rd** — behind promptfoo (89) and garak (81), ahead of deepteam (22) and pyrit (16) |
| Distinct oracle codes | 0 | **3** | **tied-1st** with promptfoo |
| Risk categories | 3 | **8** | **tied-1st** with garak |
| Recall | 0.158 (5th) | **0.444** | **2nd** — garak 0.556 |
| Precision | 0.028 (5th) | 0.101 | 4th — deepteam 0.300 |

Details, the measured shortfalls, and where each gain came from:
[results/2026-09-26-validation/README.md](results/2026-09-26-validation/README.md). Two precision
fixes and a recall marker shipped after this run were measured against the run's own recorded turns
([calibration/](tools/sixi-scanner/calibration/POST_VALIDATION.md)) and are already in the tool;
they have not been paid for with another run yet.

See [docs/PROTOCOL.md](docs/PROTOCOL.md) for the benchmark protocol and [docs/LAB-00-target.md](docs/LAB-00-target.md) for the setup guide.
