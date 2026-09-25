# Lab — agent-probe

**Goal:** run agent-probe's fixed battery of 12 OWASP LLM probes against the Foundry agent.

[agent-probe](https://github.com/rbrus/agent-probe) is a small, dependency-free Go scanner (Apache-2.0):
12 hand-written probes for prompt injection, system prompt leakage, jailbreaks, secret extraction,
tool abuse and output handling. Each probe decides by looking for its signature string in the reply.
It needs no attacker model. It is included as the minimal baseline: the least a scanner can do.

## 1. Install

```bash
go install github.com/rbrus/agent-probe/cmd/agent-probe@latest
# or: git clone https://github.com/rbrus/agent-probe && go build -o agent-probe ./cmd/agent-probe
```

## 2. Run

```bash
scripts/gateway.sh runs/my-run
AGENT_PROBE_BIN=$(command -v agent-probe) tools/agent-probe/run.sh runs/my-run
```

Under the hood:

```bash
agent-probe scan --target http://127.0.0.1:8791/t/agent-probe/chat --fail-on none --format json -o report.json
```

## 3. Reading the result

`report.json` lists each probe with `verdict` = `VULNERABLE` | `DEFENDED` | `ERROR` and the reply as
`evidence`. `--format sarif` gives the same result for GitHub code scanning.

## 4. Gotchas

* The battery is fixed: 12 turns, always the same payloads. It is a smoke test, not an assessment.
* Signature matching cannot see a leak that does not echo the probe's marker, for example a
  paraphrased system prompt.
