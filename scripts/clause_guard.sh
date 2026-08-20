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

# cron hands over a minimal environment. The Claude CLI fails immediately —
# is_error, zero tokens, no API call — when USER is unset, so do not depend on
# the scheduler providing it. Verified: HOME+PATH+USER works; dropping USER and
# keeping SHELL or LOGNAME does not.
USER="${USER:-$(id -un)}"
export USER

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

# --fail-under 1: fail only when a clause collapses to zero. Two runs of the
# identical configuration scored 9/9 and 5/9 assertion-trials, so failing on any
# miss would cry wolf most weeks — the same defect already fixed once in the
# effort hook. A clause dropping to 0/3 is the signal worth waking up for.
python3 scripts/check_clauses.py --skill skills/i-have-adhd/SKILL.md --trials 3 --fail-under 1
status=$?

if [ "$status" -eq 0 ]; then
  printf 'OK: every clause assertion held on every trial\n'
else
  printf 'FAIL: a clause assertion did not hold — read the per-assertion counts above.\n'
  printf 'Before editing SKILL.md, read the responses: rerun with --output and check whether\n'
  printf 'the assertion is too narrow (evals/README.md, "Suspect the assertion before the skill").\n'
fi
exit "$status"
