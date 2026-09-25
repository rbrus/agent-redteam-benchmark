#!/usr/bin/env bash
# Provision the benchmark target in YOUR Microsoft Foundry project.
#
#   export AZ_RESOURCE_GROUP=<rg> AZ_FOUNDRY_ACCOUNT=<AIServices account> AZ_FOUNDRY_PROJECT=<project>
#   infra/setup_foundry.sh
#
# Creates (idempotently):
#   1. RAI policy  bench-max-guard   — every content filter at its strictest, Prompt Shields on
#   2. deployment  gpt-5-nano-bench  — gpt-5-nano bound to that policy
#   3. agent       helios-support-bench — prompt agent with the benchmark instructions and tools,
#                                         with a freshly generated canary secret
# and writes FOUNDRY_PROJECT_ENDPOINT / BENCH_CANARY into .env.
#
# Needs: az CLI logged in, Contributor on the account, and a Foundry data-plane role on the project.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AZ_RESOURCE_GROUP:?}" "${AZ_FOUNDRY_ACCOUNT:?}" "${AZ_FOUNDRY_PROJECT:?}"
CAPACITY="${BENCH_DEPLOYMENT_CAPACITY:-1000}"   # thousands of tokens per minute

SUB=$(az account show --query id -o tsv)
ARM="https://management.azure.com/subscriptions/$SUB/resourceGroups/$AZ_RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$AZ_FOUNDRY_ACCOUNT"
API=2025-06-01

echo "1/3 RAI policy bench-max-guard"
az rest --method put --url "$ARM/raiPolicies/bench-max-guard?api-version=$API" \
  --body @infra/rai-policy-max-guard.json -o none

echo "2/3 deployment gpt-5-nano-bench (capacity ${CAPACITY}K TPM)"
sed "s/\"capacity\":1000/\"capacity\":$CAPACITY/" infra/deployment.json > /tmp/bench-deployment.json
az rest --method put --url "$ARM/deployments/gpt-5-nano-bench?api-version=$API" \
  --body @/tmp/bench-deployment.json -o none

echo "3/3 agent helios-support-bench"
ENDPOINT="https://$AZ_FOUNDRY_ACCOUNT.services.ai.azure.com/api/projects/$AZ_FOUNDRY_PROJECT"
CANARY="HX-$(python3 -c 'import secrets;print(secrets.token_hex(4).upper())')-CANARY"
BODY=$(mktemp)
python3 - "$CANARY" > "$BODY" <<'EOF'
import json, sys
ins = open("target/instructions.template.md").read().replace("{{CANARY}}", sys.argv[1])
tools = json.load(open("target/tools.json"))
print(json.dumps({"definition": {"kind": "prompt", "model": "gpt-5-nano-bench", "instructions": ins, "tools": tools},
                  "description": "Red-team benchmark target (fictional utility helpdesk)"}))
EOF
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  "$ENDPOINT/agents/helios-support-bench/versions?api-version=v1" -d @"$BODY" > /dev/null
rm -f "$BODY"

touch .env
grep -v -e '^FOUNDRY_PROJECT_ENDPOINT=' -e '^BENCH_CANARY=' .env > .env.tmp || true
{ cat .env.tmp; echo "FOUNDRY_PROJECT_ENDPOINT=$ENDPOINT"; echo "BENCH_CANARY=$CANARY"; } > .env
rm -f .env.tmp
echo "done — agent helios-support-bench is live; .env updated (canary kept out of git)."
