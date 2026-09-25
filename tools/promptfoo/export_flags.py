#!/usr/bin/env python3
"""Turn promptfoo's results.json into one JSON line per target turn with promptfoo's own verdict.

Used for the protocol's "tool precision" / "tool recall" KPIs: the scoring stage joins these lines
to the gateway log on the user message text (`prompt` here == `input` in the gateway log; for a
multi-turn attack it is the last user message of that turn).

promptfoo grades a *test case*, not a turn. A failed test (success == false, no error) means
promptfoo reports a vulnerability. Turn-level attribution:
  * single-turn tests (basic, jailbreak-templates, datasets): the one turn carries the verdict;
  * iterative jailbreak: turns promptfoo's judge graded as a failure (graderPassed == false) are
    flagged; if the test failed but no turn carries a grader verdict, the final prompt is flagged;
  * crescendo: turns listed in successfulAttacks are flagged; fallback as above.
Tests that ended in an error (failureReason 2, or a grader that returned no parsable verdict)
are emitted with flagged = null.

Usage: export_flags.py results.json flags.jsonl
"""

from __future__ import annotations

import json
import sys


def _s(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def rows(result: dict):
    tc = result.get("testCase") or {}
    meta = {**(tc.get("metadata") or {}), **(result.get("metadata") or {})}
    rmeta = (result.get("response") or {}).get("metadata") or {}
    plugin = meta.get("pluginId")
    strategy = meta.get("strategyId") or "basic"
    grading = result.get("gradingResult") or {}
    # failureReason: 0 = pass, 1 = assertion failed (a finding; `error` then holds the grader's
    # reason), 2 = error (target / provider failure).
    is_error = result.get("failureReason") == 2 or any(
        (c.get("metadata") or {}).get("graderError") for c in grading.get("componentResults") or []
    )
    test_flagged = None if is_error else (not result.get("success"))
    base = {
        "tool": "promptfoo",
        "result_id": result.get("id"),
        "test_idx": result.get("testIdx"),
        "plugin": plugin,
        "strategy": strategy,
        "severity": meta.get("severity"),
        "test_flagged": test_flagged,
        "test_error": _s(result.get("error"))[:300] if is_error and result.get("error") else None,
        "reason": (grading.get("reason") or "")[:500],
    }

    history = rmeta.get("redteamHistory") if "redteamHistory" in rmeta else meta.get("redteamHistory")
    if history is not None and not history:
        return  # multi-turn attack that never reached the target (e.g. attacker errors)
    if history:
        succ = {_s(a.get("prompt")) for a in (rmeta.get("successfulAttacks") or meta.get("successfulAttacks") or [])}
        final = _s(rmeta.get("redteamFinalPrompt") or meta.get("redteamFinalPrompt") or "")
        turns = []
        for i, h in enumerate(history):
            p = _s(h.get("prompt", ""))
            gp = h.get("graderPassed")
            if test_flagged is None:
                f = None
            elif gp is not None:
                f = gp is False
            else:
                f = p in succ
            turns.append({"turn": i, "prompt": p, "output": _s(h.get("output", ""))[:2000], "flagged": f})
        if test_flagged and not any(t["flagged"] for t in turns):
            tgt = next((t for t in turns if final and t["prompt"] == final), turns[-1])
            tgt["flagged"] = True
        if test_flagged is False:
            for t in turns:
                t["flagged"] = False
        for t in turns:
            yield {**base, **t}
        return

    prompt = (result.get("vars") or tc.get("vars") or {}).get("prompt")
    if prompt is None:
        prompt = (result.get("prompt") or {}).get("raw", "")
    out = (result.get("response") or {}).get("output", "")
    yield {**base, "turn": 0, "prompt": _s(prompt), "output": _s(out)[:2000], "flagged": test_flagged}


def main() -> None:
    src, dst = sys.argv[1], sys.argv[2]
    d = json.load(open(src))
    results = d["results"]["results"]
    n = flagged = 0
    with open(dst, "w") as f:
        for r in results:
            for row in rows(r):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                n += 1
                flagged += bool(row["flagged"])
    print(f"export_flags: {len(results)} tests -> {n} turns, {flagged} flagged -> {dst}")


if __name__ == "__main__":
    main()
