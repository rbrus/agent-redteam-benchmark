#!/usr/bin/env bash
# Refuse to publish if any tracked file contains a private string.
#   scripts/check_public.sh           checks files git would commit
# The denylist (.secrets/denylist.txt, one literal per line) is never committed.
set -euo pipefail
cd "$(dirname "$0")/.."
DENY=.secrets/denylist.txt
[ -f "$DENY" ] || { echo "no $DENY — create it with your account/project names, IDs, e-mails, paths, keys"; exit 2; }
files=$(git ls-files --cached --others --exclude-standard)
bad=0
while IFS= read -r s; do
  [ -z "$s" ] && continue
  hits=$(echo "$files" | xargs -d '\n' grep -l -F -i -- "$s" 2>/dev/null || true)
  if [ -n "$hits" ]; then echo "PRIVATE STRING (${s:0:4}…) in:"; echo "$hits" | sed 's/^/   /'; bad=1; fi
done < "$DENY"
# generic secret shapes
if echo "$files" | xargs -d '\n' grep -n -E '(api[-_]?key|secret|password)["'"'"' :=]+[A-Za-z0-9/+]{24,}' 2>/dev/null | grep -v -e '\.example' -e 'node_modules' ; then bad=1; fi
[ $bad = 0 ] && echo "clean: no private strings in $(echo "$files" | wc -l) files"
exit $bad
