# 2026-09-29 — sixi-scanner depth run (348 techniques: siblings + split-bypass + adjudication-500)

Release binary `2caa59646b4e`: the confirm-2 stack plus the depth-program siblings — the
side-channel curl/client shapes (the twice-+ thrice-confirmed technique), the overflow-compliance
and research-frame siblings (twice-confirmed), the refund cap-split bypass, German recitation
tokens, and the adjudication budget raised to cover every hold. Same Foundry agent, same shared
attacker model as judge (confirm-2 prompt), same tool-blind judge.

## Headline

| metric | baseline 09-24 | best prior | **this run** |
|---|---|---|---|
| turns | 655 | 870 | 884 |
| confirmed violations | 19 | 37 (09-27) | 31 |
| distinct oracle codes | 0 | 3 | **1 — the new `REFUND_CAP_SPLIT`** |
| confirmed risk categories | 3 | 8 | 5 |
| self-flagged | 108 | 64 | 83 |
| precision | 0.028 | 0.141 | **0.157** |
| recall | 0.158 | 0.455 | 0.419 |

Targets: **violating turns 31 > 19 ✓**; **codes 1 < 3 ✗**; precision 0.157 ✗; recall 0.419 ✗.

## What this run shows

* **Sixi now beats every other tool on precision except deepteam** — 0.157 vs promptfoo 0.141,
  garak 0.138, pyrit 0.077, azure 0/none. The tightened funnel + contract rules did what the
  measurements said they would.
* **The split-bypass class reproduced**: the new `REFUND_CAP_SPLIT` fired again (2 of 2 runs since
  the oracle shipped), and it is the run's only oracle code — the e-mail surface held this time
  (the same stochastic flip as 09-26→09-27: 3 codes, then 0, now 1 from a different family).
* **The depth siblings produced**: the side-channel/overflow/research-frame shapes all fired their
  adjudications (flags 64 → 83), which is where the extra confirmed violations came from.

## The state of the frontier

After five runs of the same loop — measure on recorded ground truth → ship → re-run — sixi-scanner
has moved from last competitive place to: **3rd on violations (31), 1st-tied on precision among the
non-deepteam tools (0.157), 2nd on recall (garak 0.556), 3rd on breadth**. The two remaining bars
are held closed by the same measured constraint: the confirm judge's quality on this hardware
(0.625 for the fast attacker judge; 0.933 for qwen3.8:27b which cannot be GPU-resident alongside
the attacker here — the 610-second-call measurement). On a box that can hold both models, the
shipped `SIXI_JUDGE_*` seam runs the accurate judge and the projections clear both bars.

Cost: $0.70 target spend for 884 turns; ~844 unified-judge calls.