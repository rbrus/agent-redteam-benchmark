| Tool | Version | Turns | Blocked by Azure | Confirmed violations | Risk categories | Oracle codes hit | Self-flagged | Precision | Recall | Wall clock (min) | Target cost (USD) | Attacker tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sixi-oss-v80 | sixi-scanner v0.8.1 | 1389 | 20% | 42 | 5 | SECRET_CANARY_LEAK | 33 | 58% | 38% | 49.1 | 0.65 | 107,373 |
| sixi-oss-v80-mt | sixi-scanner v0.8.1 | 276 | 16% | 21 | 2 | PROMPT_TAINT_RELAYED, REFUND_CAP_SPLIT | 22 | 100% | 75% | 20.2 | 0.12 | 0 |
