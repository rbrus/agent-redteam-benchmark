# Environment for running promptfoo in the benchmark. Sourced by run.sh.
# Usage: BENCH_TOOL=promptfoo-smoke source tools/promptfoo/env.sh

export BENCH_TOOL="${BENCH_TOOL:-promptfoo}"
export BENCH_GATEWAY="${BENCH_GATEWAY:-http://127.0.0.1:8791}"

# No hosted generation, no account, no telemetry, no sharing, no update checks.
export PROMPTFOO_DISABLE_REMOTE_GENERATION=true
export PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true
export PROMPTFOO_DISABLE_TELEMETRY=1
export PROMPTFOO_DISABLE_SHARING=1
export PROMPTFOO_DISABLE_SHARE_EMAIL_REQUEST=1
export PROMPTFOO_DISABLE_UPDATE=1
export PROMPTFOO_DISABLE_REDTEAM_MODERATION=true
# Fresh results in every run (no cached target replies).
export PROMPTFOO_CACHE_ENABLED=false

# Belt and braces: any code path that falls back to promptfoo's default OpenAI provider (e.g. a
# grader without an explicit provider) lands on the shared attacker, never on api.openai.com.
export OPENAI_API_KEY=x
export OPENAI_BASE_URL="$BENCH_GATEWAY/attacker/$BENCH_TOOL/v1"
export OPENAI_API_BASE_URL="$OPENAI_BASE_URL"

# Keep promptfoo's sqlite DB / logs inside the tool directory, not in ~/.promptfoo.
_pf_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Absolute path for the file:// attacker provider, so generated configs in any out dir resolve it.
export BENCH_PF_DIR="$_pf_dir"
export PROMPTFOO_CONFIG_DIR="$_pf_dir/.promptfoo"
export PROMPTFOO_LOG_DIR="$_pf_dir/.promptfoo/logs"

# node via nvm
if ! command -v node >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh" >/dev/null
fi
