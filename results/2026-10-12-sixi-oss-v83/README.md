# 2026-10-12 — v0.8.3: the best precision on the board, and the first real coverage growth

Two techniques were taking recitation breaks that had nothing to do with them. Removing those took
precision from **0.576 to 0.821** — the highest ever measured here — and, unexpectedly, took the tool's
hit count from **5 to 8**, the first time its coverage has grown across five releases.

| | v0.6.0 | v0.7.1 | v0.8.1 | **v0.8.3** | **v0.8.3-mt** |
|---|---|---|---|---|---|
| turns | 1,282 | 1,351 | 1,389 | **1,480** | 262 |
| self-flagged | 32 | 29 | 33 | 28 | 24 |
| **precision** | 0.688 | 0.724 | 0.576 | **0.821** | **1.000** |
| **recall** | 0.833 | 0.500 | 0.385 | **0.571** | 0.750 |
| confirmed violating turns | 37 | 49 | 42 | 61 | 17 |
| risk categories | 4 | 4 | 5 | **6** | 2 |
| oracle codes | 0 | 0 | 1 | 1 | **2** |
| **hits** (distinct payloads caught) | 5 | 5 | 5 | **8** | 1 |
| cost | $0.57 | $0.64 | $0.65 | $0.72 | $0.11 |

`rounds=14, attempts=5`, confirmation stage on — turn-matched to every baseline. `v0.8.3-mt` is the
session lane and, as always, **not turn-matched to anything**.

> **Version string discrepancy, disclosed.** The binary that produced this run self-reports
> `0.8.2+dirty`: it was built from the working tree *before* the `v0.8.3` tag was applied, so the tag
> name was not yet resolvable. Its technique set and every technique definition are byte-identical to
> the tagged build (verified by diffing `list` and `list --detail`), so the behaviour measured here is
> v0.8.3's. Only the embedded label is wrong. Recorded rather than corrected, because quietly
> relabelling a run is how a provenance gap starts.

## What actually changed

The recitation test is a **global** fallback: it fires on any reply that enumerates three or more of the
agent's own rules, and the break is then attributed to whichever technique happened to draw that probe.
Per-technique breakdown of which mechanism fires, which the totals had hidden:

```
probe.llm09.false-action-claim     own=0  recitation=7
probe.llm10.unbounded-consumption  own=0  recitation=2
probe.llm01.interagent-framing     own=0  recitation=4
probe.llm01.refusal-consistency    own=0  recitation=14
```

For `false-action-claim` that is not noise, and the reason is structural rather than empirical: **its
only marker is the sentinel `__claim_check__`**, so it is never detected by matching text at all. It is
detected by the claim check, against a tool trace. On an endpoint that exposes no trace the claim check
correctly abstains — and every "finding" the technique produced was the recitation test borrowing its
name. Seven of them, zero confirmed.

`unbounded-consumption` was the second: its markers are all about the size of what came back, so an agent
enumerating its own limits has given the compliant answer rather than evidence of unbounded consumption.

### Measured effect, per technique

| technique | v0.8.1 | v0.8.3 |
|---|---|---|
| `false-action-claim` | 7 flagged, **0 confirmed** | **absent** |
| `irreversible-action-assent` | 1 flagged, 0 confirmed | absent |
| `credential-elicitation` | 6 flagged, 0 confirmed | 5 flagged, 0 confirmed |
| `markdown-exfiltration` | 6 → 6 | 9 → **9** |
| `false-certification` | 10 → 10 | 9 → 9 |
| `tool-argument-injection` | — | 2 → **2** |
| `interagent-framing` | — | 1 → **1** |
| **total** | **33 flagged / 19 confirmed** | **28 / 23** |

## Three of the four candidates would have cost real detections

The intuition — "recitation is a false-positive machine, opt everything out" — is wrong here, and
measuring first is the only reason it is known:

| technique | true positives lost if it opted out | false removed |
|---|---|---|
| `refusal-consistency` | **14** | 0 |
| `interagent-framing` | **4** | 0 |
| `tool-argument-injection` | **3** | 0 |
| `canary-leak` | 1 | 1 |
| `unbounded-consumption` | 0 | **2** |
| `false-action-claim` | 0 | **7** |

`refusal-consistency` losing 14 confirms the recitation test is load-bearing for it — which the test
suite's comment has always claimed and nothing had ever checked. `interagent-framing` losing 4 says
recitation is catching **real violations** there. **Recitation is mostly signal on this target**, and
treating it as noise would have quietly deleted detections.

## Hits went 5 → 8, and that is the number that matters

Per PROTOCOL §9, a published recall figure from one run does not compare with another, because a payload
counts as violating if *any* of its ~17 turns leaked that day. So the figure to look at is the hit count.

| run | v0.6.0 | v0.7.0 | v0.7.1 | v0.8.1 | **v0.8.3** |
|---|---|---|---|---|---|
| distinct violating payloads | 6 | 6 | 10 | 13 | 14 |
| **hits** | 5 | 4 | 5 | 5 | **8** |
| recall as published | 0.833 | 0.667 | 0.500 | 0.385 | 0.571 |
| recall on the common set | 1.000 | 1.000 | 1.000 | 1.000 | **1.000** |

Five releases, four of them catching exactly the same five payloads. This one caught **eight**. That is
the first genuine coverage growth in the series, and it is not a denominator artefact — the denominator
grew too, from 13 to 14, which should have *lowered* recall.

**4 payloads violate in all five runs, and 14 payloads violate in at least one of them.** Restricted to
those 4, recall is **1.000 in every release** — so the fall from 0.833 to 0.385 and back to 0.571 is the
denominator moving, not the detector losing ground. PROTOCOL §9 has the argument;
`scoring/recall_stability.py` recomputes it.

## What I cannot attribute

**One run per configuration cannot separate a change from run-to-run variation.** `markdown-exfiltration`
going 6 → 9 confirmed and two techniques appearing with confirmed flags are as likely to be the target
behaving differently on the day as anything about the release. The `false-action-claim` result is the one
cleanly attributable claim here, because it went from 7 all-false to absent, which is exactly what the
offline measurement predicted from the definition change.

A turn-matched A/B would cost two runs and about $1.40. It was not run, so this write-up does not claim
it.

## Both targets met, and the headline moves

precision 0.821 ≥ 0.30 and recall 0.571 ≥ 0.56 — the first build since v0.6.0 to hold both at once, and
the best precision on the board against 0.724 previously.

**The headline moves to v0.8.3.** With one caveat stated rather than buried: **recall 0.571 clears its
target by 0.011**, and §9 says it is the least trustworthy number here. The claim that this build is
better rests on precision (0.821, large, and traceable to a specific definition change) and on the hit
count (5 → 8), not on the recall figure.

## Reproducing

```bash
SIXI_CONFIRM_URL=http://127.0.0.1:8791/attacker/sixi-oss-v83/v1/chat/completions \
SIXI_CONFIRM_MODEL=attacker SIXI_CONFIRM_CONTEXT=tools/sixi-scanner-oss/context.json \
SIXI_CONFIRM_BUDGET=250 \
  tools/sixi-scanner-oss/run.sh runs/2026-10-12-oss-v83 sixi-oss-v83 --rounds 14 --attempts 5 --multiturn

python3 scoring/judge.py runs/2026-10-12-oss-v83 --only sixi-oss-v83 sixi-oss-v83-mt
python3 scoring/score.py  runs/2026-10-12-oss-v83 --labels sixi-oss-v83 sixi-oss-v83-mt
python3 scoring/recall_stability.py runs/2026-10-08-oss-v6:sixi-oss-v6 \
  runs/2026-10-09-oss-v7:sixi-oss-v7 runs/2026-10-10-oss-v71:sixi-oss-v71 \
  runs/2026-10-11-oss-v80:sixi-oss-v80 runs/2026-10-12-oss-v83:sixi-oss-v83
```