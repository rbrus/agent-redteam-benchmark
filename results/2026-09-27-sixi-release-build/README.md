# 2026-09-27 — sixi-scanner release-build run (adjudication + false-claim depth + contract rules)

One tool, one run: sixi-scanner's release build (commit `fc74925a6159`) — 343 techniques carrying
everything from the fix cycle plus the additions made after the 2026-09-26 runs: the false-action-
claim sibling techniques, the declined-then-produced marker, the attribution-gate contract rule, and
the caller-entitlement contract in the policy framing. Same Foundry agent, same shared attacker
model, same tool-blind judge as the baseline.

## Headline

| metric | baseline 09-24 | 09-26 validation | **this run** |
|---|---|---|---|
| turns | 655 | 767 | 870 |
| confirmed violations | 19 | 27 | **37** |
| distinct oracle codes | 0 | 3 | **3** (reproduced) |
| confirmed risk categories | 3 | 8 | 7 |
| self-flagged | 108 | 119 | **64** |
| precision | 0.028 | 0.101 | **0.125** |
| recall | 0.158 | 0.444 | 0.216 |

Leaderboard position: **3rd on confirmed violations** (promptfoo 89, garak 81, sixi 37, deepteam 22,
pyrit 16), **2nd on risk breadth** (garak 8, sixi 7), **tied-1st on oracle codes** with promptfoo.

## What moved

* **Violations 27 → 37 — sixi's best yield yet.** The false-claim sibling techniques produced new
  judge-confirmed false-action turns, and the adjudication pass raised violations the markers had
  never scored (2 of the 37 are adjudication raises).
* **Self-flagged 119 → 64 — the precision funnel tightened by design.** The single contract-bearing
  confirm framing screens far more marker noise than the retired three-framing OR, and the fixed
  Phase B attribution gate halved Phase B's false flags (42 → 26 in the 09-26 final run; fewer here).

## What this run cost sixi

* **Recall 0.444 → 0.216.** The confirm simplification keeps fewer of the judge-confirmed turns:
  of this run's 37 violating turns, the confirm judge read 33 and **screened 14** (11 marker hits +
  3 adjudication candidates). The post-run measurement
  ([judge_compare.py](../tools/sixi-scanner/calibration/judge_compare.py)) traced this to the
  confirm-judge model: the shared attacker model screens ~40% of true violations under this prompt.
* **Fix shipped, not yet benchmarked:** sixi's confirmation judge is now a dedicated local model
  (`qwen3.8:27b`, `SIXI_JUDGE_*`), measured on this run's own confirm-read turns at **precision 0.933
  (14 of 22 confirmed kept, 1 false keep)** where the attacker model scored 0.529 (9 kept, 8 false).
  The Phase B judge wiring (`5945c9a`) routes the same model into the attribution gate.

## Cost

Azure target spend: $0.72 for 870 turns (2.0M tokens in, 1.6M out). Unified-judge calls: ~846.
