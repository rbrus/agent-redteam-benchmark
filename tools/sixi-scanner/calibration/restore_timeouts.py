#!/usr/bin/env python3
"""Restore the replies a scan abandoned before they arrived, from the gateway's own log.

A scanner-side timeout is not the target holding its ground: the gateway finished the turn and
logged the reply, the scanner just gave up waiting and recorded an error instead of a response.
That row can be calibrated like any other, because the reply exists — this script copies it from
the gateway log into a COPY of the run's native directory (the recording itself is never touched)
so `technique/calibration_external_test.go` can score it.

Usage:
  python3 restore_timeouts.py runs/<run>/sixi-scanner/native runs/<run>/gateway/sixi-scanner.jsonl /tmp/calrun

Writes <out>/flat.json (patched copy) and <out>/adaptive.json (verbatim copy). The original
directory is only read.
"""
import json
import os
import re
import shutil
import sys


def norm(s):
    """scoring/score.py's normalisation of an input, which is what the gateway log rows carry."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())[:400]


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    native, gateway_log, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    shutil.copy2(os.path.join(native, "adaptive.json"), os.path.join(out, "adaptive.json"))

    rows = {}
    with open(gateway_log) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                rows[norm(r.get("input") or "")] = r

    doc = json.load(open(os.path.join(native, "flat.json")))
    restored = 0
    for a in doc.get("all_attack_attempts", []):
        if not a.get("error"):
            continue
        row = rows.get(norm(a.get("payload_sent")))
        if not row or not (row.get("reply") or ""):
            print(f"  no gateway reply for {a['technique_id']} — left as an error", flush=True)
            continue
        a["target_response"] = row["reply"]
        a.pop("error", None)
        restored += 1
        print(f"  restored {a['technique_id']} ({len(row['reply'])} bytes)", flush=True)

    with open(os.path.join(out, "flat.json"), "w") as f:
        json.dump(doc, f)
    print(f"restored {restored} attempt(s) into {out}", flush=True)


if __name__ == "__main__":
    main()
