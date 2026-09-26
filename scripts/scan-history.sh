#!/usr/bin/env bash
# Scan every blob in the full git history for secrets and identifying data.
# Fails on: AWS access keys, private keys, 12-digit AWS account ids, and email
# addresses outside a small allow-list. Run before every push; CI runs it too.
set -euo pipefail

allow_email='(noreply@anthropic\.com|@example\.(com|org|net)|@users\.noreply\.github\.com)'
patterns='AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|aws_secret_access_key[[:space:]]*=|(^|[^0-9])[0-9]{12}([^0-9]|$)'

revs=($(git rev-list --all))  # bash 3.2 (macOS) has no mapfile
status=0

if hits=$(git grep -nIE "$patterns" "${revs[@]}" -- . ':!uv.lock' ':!scripts/scan-history.sh' 2>/dev/null); then
  echo "Possible secrets or account ids in history:"; echo "$hits" | sort -u; status=1
fi

emails=$(git grep -hIoE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "${revs[@]}" -- . ':!uv.lock' 2>/dev/null \
  | sort -u | grep -vE "$allow_email" || true)
if [[ -n "$emails" ]]; then
  echo "Email addresses in committed files:"; echo "$emails"; status=1
fi

authors=$(git log --all --format='%ae%n%ce' | sort -u | grep -vE "$allow_email" || true)
if [[ -n "$authors" ]]; then
  # Informational only: the maintainer chose to publish their commit identity.
  echo "Note: commit identities use non-noreply emails (by maintainer's choice):"; echo "$authors" | sed 's/^/  /'
fi

[[ $status -eq 0 ]] && echo "History scan clean: ${#revs[@]} commits."
exit $status
