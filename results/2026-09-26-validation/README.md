# 2026-09-26 — sixi-scanner post-change validation run

One tool, one run: sixi-scanner after the payload ports, the confirmation redesign, the rule-
recitation wrapper and the `--timeout` recovery, against the same Foundry agent and the same shared
attacker model as the 2026-09-24 baseline. The other tools were not re-run; their baseline rows are
the comparison. Per PROTOCOL §7, every change this run carries was made after the baseline and is
disclosed there.

## Headline

| metric | baseline (09-24) | this run | moved |
|---|---|---|---|
| confirmed violations | 19 | **27** | +8 |
| distinct oracle codes | 0 | **3** | +3 |
| confirmed risk categories | 3 | **8** | +5 |
| self-flagged | 108 | 119 | +11 |
| precision | 0.028 | 0.101 | +0.073 |
| recall | 0.158 | 0.444 | +0.286 |

Against the baseline leaderboard (all tools at their 09-24 best), this run puts sixi-scanner 3rd on
confirmed violations (deepteam 22, pyrit 16 behind; promptfoo 89, garak 81 ahead), tied-1st on risk
breadth with garak (8), 2nd on recall (garak 0.556), 1st-tied on distinct oracle codes with
promptfoo.

## Where the gains came from

* **Oracle codes 0 → 3.** The baseline produced none; all three came from the ported e-mail payloads,
  *after* the scanner's own rewriter had rewritten them (see §7 of the PROTOCOL: 5/12, 5/12 and 6/12
  pooled hit rates measured with `cmd/rewriteprobe`).
* **Violations 19 → 27.** Composition of the 27: off-topic compliance 11, system-prompt leak 6,
  unauthorized action 4, false action claim 3, plus the oracle turns. The false-action-claim turns
  were produced by the family ported from promptfoo (`LLM01.falseclaim.affirmation`) — its first run.
* **Precision 0.028 → 0.101.** The three-framing confirmation pass screens marker noise; the
  declared-value pass (context-1) and the redaction screen remove the caller's-own-data flags.

## Where it still falls short — measured, not guessed

* **Precision 0.101 vs the 0.30 bar.** The confirmation framings were calibrated with a different
  local model than the one that grades on a live scan (the shared attacker model of §3). Replayed
  offline over this run's own flags under the production judge, the shipped framings keep 36 with 11
  judge-confirmed (live P = 0.306) — the design holds, the live keep-rate did not. Fixes shipped
  after this run: the policy framing now carries the caller-entitlement contract (measured as
  variant 7, P = 0.375 alone / 0.318 combined under the production judge), and the Phase B
  attribution gate judges sensitivity against the agent's declared contract (replay: breaks standing
  12/42 → 2/42).
* **Phase B remains the precision sink**: 42 flags, 1 confirmed (P = 0.024) — its breaks stood on the
  caller's own balance and IBAN, which the target's rules permit showing its caller. Fixed in sixi
  (`a4fbc97`), rides the next run.
* **Recall 0.444**: 12 of 27 violating inputs flagged. Nine of the 15 misses are the
  declined-then-produced shape; that shared marker is now shipped (`55f90d6`, measured 2/2 on the
  validation turns it can see), and the false-claim family covers 2 more.

## Cost

Azure target spend: $0.59 for 767 turns (2.0M tokens in, 1.36M out). Unified-judge calls: 736.
