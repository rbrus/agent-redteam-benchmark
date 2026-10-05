"""Open-source sixi-scanner scan output -> the benchmark's self_report.json.

The open-source build (github.com/rbrus/sixi-scanner) reports differently from the licensed build the
earlier runs used, so it needs its own adapter rather than tools/sixi-scanner/parse_results.py:

* the JSON report carries `findings` (each with the exact prompt and reply behind it) and an
  `attempts` **count**, not a per-attempt list — so the flagged side can be read straight out of it;
* every individual send is logged to **stderr**, one line per attempt, as
  `  <technique-id>  r<round> a<attempt>  held | BREAK confidence <c> | no answer: <err>` — that is the
  ledger of what was actually probed, including the turns that held;
* the prompts are deterministic: with no `--seed`, attempt *k* of a technique is variant *k* of its
  published definition (`tech.Definition.Payload` skips the variants already tried and every technique
  has at least `--attempts` of them), so the payload set from `techdump` reconstructs every prompt.

So this script joins three things that all exist in the run directory or in the repo: the tool's own
JSON findings, the tool's own stderr ledger, and the gateway's replies. Nothing is inferred from a
model; a prompt the ledger and the catalogue disagree about is an error, not a guess.

Usage: python tools/sixi-scanner-oss/parse_results.py <run_dir> <label> [--techdump <json>]
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

# The benchmark's in-scope OWASP set (PROTOCOL §4). A technique in another OWASP category — LLM04
# training-data extraction, LLM09 misinformation, LLM10 availability — is out of scope for this
# agent and is counted as "other", the same treatment the licensed-build adapter gives it.
OWASP = {"LLM01", "LLM02", "LLM05", "LLM06", "LLM07"}

LEDGER = re.compile(
    r"^\s+(?P<id>(?:probe|agent)\.[\w.\-]+)\s+r(?P<round>\d+)\s+a(?P<attempt>\d+)\s+"
    r"(?P<verdict>held|BREAK|no answer)"
)


def norm(s: str) -> str:
    """The same normalisation scoring/score.py joins on: case, whitespace, first 400 chars."""
    return re.sub(r"\s+", " ", s or "").strip().lower()[:400]


def payload(variants: list[str], attempt: int, failed: list[int]) -> str:
    """Replicate tech.Data.Payload: attempt *k* is the first variant not yet tried.

    The engine appends every attempt index it has already used to `failed` and asks the definition for
    the next payload; the definition returns the first variant outside that set, and only wraps to
    `attempt % len(variants)` once every variant has been used. Mirroring it exactly is what lets the
    prompt be rebuilt from the published catalogue instead of guessed — and it is why a prompt can
    repeat inside one round, which the reply cursor below has to cope with.
    """
    n = len(variants)
    if not n:
        return ""
    if not failed:
        return variants[attempt % n]
    skip = set(failed)
    for i in range(n):
        if i not in skip:
            return variants[i]
    return variants[attempt % n]


def load_ledger(path: str) -> list[dict]:
    """Every send the tool made, in completion order, from its stderr progress lines."""
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path):
        m = LEDGER.match(line)
        if m:
            out.append({
                "technique_id": m.group("id"),
                "round": int(m.group("round")),
                "attempt": int(m.group("attempt")),
                "broke": m.group("verdict") == "BREAK",
                "error": line.strip() if m.group("verdict") == "no answer" else None,
            })
    return out


def load_replies(run_dir: str, label: str) -> dict[str, list[dict]]:
    """Gateway replies keyed by normalised input, in the order they arrived.

    A prompt is re-sent every round, so one prompt maps to several turns; they are consumed in
    chronological order, which is the order the ledger prints them in, because the tool finishes a
    whole round before starting the next.
    """
    by_input = defaultdict(list)
    p = os.path.join(run_dir, "gateway", f"{label}.jsonl")
    if not os.path.exists(p):
        return by_input
    for line in open(p):
        t = json.loads(line)
        by_input[norm(t["input"])].append(t)
    return by_input


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("label")
    ap.add_argument("--techdump", default="")
    a = ap.parse_args()
    run_dir, label = a.run_dir, a.label
    nat = os.path.join(run_dir, label, "native")

    report_path = os.path.join(nat, "scan.json")
    if not os.path.exists(report_path) or os.path.getsize(report_path) == 0:
        print(f"{label}: no readable scan report at {report_path}", file=sys.stderr)
        sys.exit(1)
    rep = json.load(open(report_path))

    dump = json.loads(subprocess_out(a.techdump)) if a.techdump else {}
    techs = {t["id"]: t for t in dump.get("techniques", [])}
    if not techs:
        # No catalogue supplied: recover the prompts from the findings, which carry them verbatim.
        techs = {f["technique_id"]: {"id": f["technique_id"], "category": f["category"], "variants": []}
                 for f in rep.get("findings", [])}

    ledger = load_ledger(os.path.join(nat, "scan.log"))
    replies = load_replies(run_dir, label)
    # prompts the tool itself flagged, from its own findings — the only source of its verdicts
    findings = rep.get("findings", [])
    flagged_prompts = {norm(f["evidence"]["prompt"]) for f in findings}

    attempts = []
    missing_prompt = set()
    cursor = defaultdict(int)
    # The engine walks each technique independently and re-tries a variant once every variant has been
    # used, so which prompt an attempt carried depends on the attempts that preceded it for the SAME
    # technique and round. Track that state rather than assuming attempt k == variant k.
    used: dict[tuple[str, int], list[int]] = defaultdict(list)
    for i, a_ in enumerate(ledger):
        tid = a_["technique_id"]
        key = (tid, a_["round"])
        variants = techs.get(tid, {}).get("variants", [])
        k = a_["attempt"]
        prompt = payload(variants, k, used[key])
        used[key].append(k)
        if not prompt:
            # A prompt the catalogue cannot supply. The tool's own evidence is authoritative for a turn
            # it flagged, so fall back to the finding recorded for this technique before giving up.
            f = next((f for f in findings if f["technique_id"] == tid), None)
            prompt = f["evidence"]["prompt"] if f and norm(f["evidence"]["prompt"]) in flagged_prompts else ""
        if not prompt:
            missing_prompt.add(f"{tid} r{a_['round']}a{a_['attempt']}")
            prompt = f"[unreconstructable prompt: {tid} r{a_['round']}a{a_['attempt']}]"

        n = norm(prompt)
        turn = None
        if n in replies and cursor[n] < len(replies[n]):
            turn = replies[n][cursor[n]]
            cursor[n] += 1

        cat = techs.get(tid, {}).get("category", "") or ""
        owasp = cat.split(":")[0].strip()
        attempts.append({
            "id": f"{label}-{i}",
            "technique": tid,
            "round": a_["round"],
            "attempt": k,
            "category": tid,
            "owasp": owasp if owasp in OWASP else "other",
            "owasp_full": cat,
            "prompt": prompt,
            "response": (turn or {}).get("reply", ""),
            "blocked": (turn or {}).get("blocked", False),
            "tool_flagged": bool(a_["broke"]),
            "error": a_["error"],
            "multi_turn": False,
        })

    # The report's own count is the tool's statement of how many sends it made; if the ledger we
    # parsed disagrees, one of the two is wrong and the run must not be scored on a guess.
    counted = rep.get("attempts")
    if isinstance(counted, int) and counted != len(ledger):
        print(f"{label}: ledger has {len(ledger)} attempts but the report counted {counted}",
              file=sys.stderr)

    by_sev = defaultdict(int)
    for f in findings:
        by_sev[f["severity"]] += 1

    version = open(os.path.join(nat, "version.txt")).read().strip() if os.path.exists(os.path.join(nat, "version.txt")) else "?"
    rd = lambda n: open(os.path.join(nat, n)).read().strip() if os.path.exists(os.path.join(nat, n)) else None
    out = {
        "tool": label,
        "tool_version": version,
        "config": f"open-source build, static payloads, single-turn; "
                  f"rounds={rep.get('options', {}).get('rounds')}, "
                  f"attempts={rep.get('options', {}).get('max_attempts_per_technique')}, "
                  f"concurrency={rep.get('options', {}).get('concurrency')}, "
                  f"recitation_threshold={rep.get('options', {}).get('recitation_threshold')}, "
                  f"confirmation={'on' if rep.get('confirmation') else 'off'}",
        "started_at": rep.get("started_at"),
        "finished_at": rep.get("finished_at"),
        "attempts": attempts,
        "tool_summary": {
            # The optional confirmation stage, if one ran. A run without the key had no stage, which
            # is not the same as a stage that confirmed nothing — so it is carried, not inferred.
            "confirmation": rep.get("confirmation"),
            "recitation_threshold": rep.get("options", {}).get("recitation_threshold"),
            "techniques": len(rep.get("options", {}).get("techniques", [])),
            "findings": len(findings),
            "by_severity": dict(by_sev),
            "untested_no_answer": rep.get("no_answer", []),
            "reported_attempt_count": counted,
            "target": rep.get("target"),
        },
    }
    json.dump(out, open(os.path.join(run_dir, label, "self_report.json"), "w"), indent=1)
    flagged = sum(x["tool_flagged"] for x in attempts)
    print(f"{label}: {len(attempts)} sends, {flagged} flagged by the tool, "
          f"{len(findings)} findings ({', '.join(f'{k}:{v}' for k, v in sorted(by_sev.items()))})")
    if rep.get("no_answer"):
        print(f"{label}: {len(rep['no_answer'])} technique(s) got no answer and were NOT counted as passes: "
              f"{', '.join(rep['no_answer'])}")
    if missing_prompt:
        print(f"{label}: WARNING — {len(missing_prompt)} prompt(s) could not be reconstructed from the "
              f"technique catalogue, so their joins to the gateway log are by position only", file=sys.stderr)
    if not attempts:
        print(f"{label}: NO ATTEMPTS — the stderr ledger is empty; the scan never ran or was "
              f"redirected away from scan.log", file=sys.stderr)
        sys.exit(1)


def subprocess_out(cmd: str) -> str:
    import subprocess
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True).stdout


if __name__ == "__main__":
    main()