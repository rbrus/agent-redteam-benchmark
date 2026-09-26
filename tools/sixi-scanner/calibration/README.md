# sixi-scanner — confirmation-judge calibration

The numbers in the tool README's calibration table come from this directory. Everything here is
reproducible from the recorded 2026-09-24 baseline run; nothing was measured by hand.

## What is committed

| file | what it is |
|---|---|
| `cal_records.json` | 560 records — one per attempt the baseline run made — each with the payload sent, the reply, and the technique's marker verdict **recomputed by sixi's current scorer** |
| `falseclaim_records.json` | the 51 turns the baseline's unified judge confirmed as `false_action_claim` (promptfoo's), the measurement behind `LLM01.falseclaim.affirmation` |
| `cache/confirm_cache__*.jsonl` | the confirmation judge's verdicts, one JSON line per ask: `[violation, reason]`, or `[violation, severity, reason]` for the framings that grade severity |
| `measure_confirm.py` | asks the judge: renders sixi's real confirmation prompt for a record and stores the verdict in the cache |
| `design_space.py` | prints the README's table: every `markers AND/OR <framings>` design scored the way `scoring/score.py` scores |
| `restore_timeouts.py` | copies the three replies the scanner abandoned (timeout) from the gateway log into a copy of the run, so they can be calibrated like any other turn |

The records are derived, not measured: `technique/calibration_external_test.go` in the sixi
repository writes them (env `SIXI_CAL_RUN`, `SIXI_CAL_TRUTH`, `SIXI_CAL_OUT`) from the run's own
`payload_sent` / `target_response`. They are committed because the run itself is not (`runs/` is
gitignored) and the published table should be reproducible from the repository alone.

## Where the three restored turns came from

Three baseline attempts recorded `error: context deadline exceeded` instead of a response. The
gateway completed all three turns and logged them. `restore_timeouts.py` copies those replies into a
copy of the run:

```bash
python3 tools/sixi-scanner/calibration/restore_timeouts.py \
  runs/2026-09-24-full/sixi-scanner/native \
  runs/2026-09-24-full/gateway/sixi-scanner.jsonl /tmp/calrun
```

It changes nothing else. Re-running the calibration harness on the patched copy reproduced the other
560 records exactly and changed only those three — two stayed unflagged, and
`LLM05.ansi.direct_emission` (one of the run's 19 confirmed violating inputs) became a flagged hit.
That is the run `run.sh --timeout 90` will actually see.

## Reproducing the table

```bash
# 1. records (skip if cal_records.json is already up to date)
SIXI_CAL_RUN=/tmp/calrun \
SIXI_CAL_TRUTH=results/2026-09-24-baseline/findings.jsonl \
SIXI_CAL_OUT=tools/sixi-scanner/calibration/cal_records.json \
  go -C go test -run TestCalibrateJudgesAgainstRecordedRun ./technique/

# 2. verdicts (only the misses are asked; the cache is committed)
SIXI_CAL_MODEL="qwen3.8:27b" SIXI_CAL_WORKERS=4 \
  python3 tools/sixi-scanner/calibration/measure_confirm.py

# 3. the table
SIXI_CAL_MODEL="qwen3.8:27b" python3 tools/sixi-scanner/calibration/design_space.py
```

The judge is the benchmark's shared local model (PROTOCOL §3) — the same model that answers sixi's
confirmation pass on a live scan. It is not the unified scoring judge, and it never sees the score.

## What the shipped design is

`markers AND (claim OR rules OR policy)`: the markers decide who is asked; the confirmation judge is
asked the same question three ways — the claim the markers made, then every numbered rule, then the
whole policy graded with a severity bar — and a break survives if any framing stands behind it. A
screening therefore requires all three framings to have read the turn and all three to have said no.

Two framings were measured but never shipped: one asked only about evidence (no rule test), one was
the benchmark judge's own prompt reproduced verbatim, and neither was asked over the whole recorded
set, so no design built on either could be evaluated. A sixth framing answered almost everything and
was dropped: it added four false positives and recovered no confirmed turn. `design_space.py` prints
all of them, including the rejection.

## The limitation, stated plainly

The framings were chosen by scoring them against this run's 19 confirmed violating inputs — the same
labels the benchmark scores. That is calibration against the test set, not validation. P5
re-validates the shipped design against a held-out judge model, and the numbers it produces are the
ones that count.

## The `false_action_claim` family, and what could not be ported

promptfoo's largest confirmed category (51 turns — more than any other category any tool produced)
asks the agent to confirm an action that never happened ("Has the email been successfully
dispatched…?" → "Yes. I've sent the email…"). sixi now carries it as `LLM01.falseclaim.affirmation`,
seeded with the family's proven shapes. Three facts from the measurement are recorded because they
bound what the family can do:

* The shipped confirmation framings keep **51 of 51** of the recorded false-claim turns — the
  confirm pass is not the bottleneck.
* The marker's recall over those same 51 recorded turns is **9 of 51**: the recorded replies assert
  the completion in too many shapes (relative clauses, attributions, partial-credit clarifications)
  for a presence regex. Against the live target the picture is the one that matters — six turns
  (2026-09-26): five honest holds, one affirmation, fired. The recorded set still bounds the judge:
  **18 of the 51** confirmed turns carried a real `send_email`, so the grading judge confirms
  assertions whose trace would vindicate them. A flag from this family can therefore be a true
  claim, and sixi has no tool trace to tell — that risk is disclosed here and in the technique's
  header rather than resolved.
* sixi's own 655 baseline turns contain **zero** completion assertions, because its library never
  asked the agent to do anything. The family only produces value in a run that sends it — so its
  contribution to the next run's `violating_turns` is bounded by its own flag rate, not by anything
  recoverable from the recorded one.
