#!/usr/bin/env sh
# Weekly clause check: do the working-agreement clauses still fire?
#
# Unlike scripts/fork_guard.sh this SPENDS MODEL CALLS — nine per run — so it is
# a separate script and a separate cron line. Exit code is the whole contract.
#
#   ANTHROPIC_BASE_URL=http://gateway:port sh scripts/clause_guard.sh
#
# Weekly cron (remove with: crontab -e, delete the line):
#   15 9 * * 1 ANTHROPIC_BASE_URL=http://host:port /bin/sh /path/to/scripts/clause_guard.sh >> /tmp/i-have-adhd-clause-guard.log 2>&1

set -u
cd "$(dirname -- "$0")/.." || exit 1

printf '=== clause_guard %s ===\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# The runner inherits the environment, and `--setting-sources ""` deliberately
# stops the CLI reading settings.json — so its env block cannot supply this.
if [ -z "${ANTHROPIC_BASE_URL:-}" ]; then
  printf 'FAIL: ANTHROPIC_BASE_URL is unset; the runner would inherit whatever the shell exports\n'
  exit 1
fi

if ! curl -s -m 10 -o /dev/null "${ANTHROPIC_BASE_URL%/}/health"; then
  printf 'SKIP: gateway %s unreachable — not spending calls\n' "$ANTHROPIC_BASE_URL"
  exit 0
fi

python3 scripts/check_clauses.py --skill skills/i-have-adhd/SKILL.md --trials 3
status=$?

if [ "$status" -eq 0 ]; then
  printf 'OK: every clause assertion held on every trial\n'
else
  printf 'FAIL: a clause assertion did not hold — read the per-assertion counts above.\n'
  printf 'Before editing SKILL.md, read the responses: rerun with --output and check whether\n'
  printf 'the assertion is too narrow (evals/README.md, "Suspect the assertion before the skill").\n'
fi
exit "$status"
