#!/usr/bin/env sh
# Fork health check: every gate, plus whether the fork's personal deltas still
# merge cleanly with upstream. Exits 0 only when all of it passes, so it is safe
# to run from cron and act on the exit code alone.
#
#   sh scripts/fork_guard.sh            # from the repo root
#
# Weekly cron (remove with: crontab -e, delete the line):
#   0 9 * * 1 sh scripts/fork_guard.sh >> /tmp/i-have-adhd-fork-guard.log 2>&1

set -u
cd "$(dirname -- "$0")/.." || exit 1
status=0
fail() { printf 'FAIL: %s\n' "$1"; status=1; }

# cron hands over a minimal environment. The Claude CLI fails immediately —
# is_error, zero tokens, no API call — when USER is unset, so do not depend on
# the scheduler providing it. Verified: HOME+PATH+USER works; dropping USER and
# keeping SHELL or LOGNAME does not.
USER="${USER:-$(id -un)}"
export USER

printf '=== fork_guard %s ===\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

cmp skills/i-have-adhd/SKILL.md .cursor/skills/i-have-adhd/SKILL.md >/dev/null 2>&1 \
  || fail 'mirror drift: cp skills/i-have-adhd/SKILL.md .cursor/skills/i-have-adhd/SKILL.md'

python3 -m unittest discover -s tests >/dev/null 2>&1 || fail 'unit tests'
python3 scripts/run_evals.py validate >/dev/null 2>&1 || fail 'eval cases invalid'
command -v claude >/dev/null 2>&1 && { claude plugin validate . >/dev/null 2>&1 || fail 'plugin manifest'; }
command -v bun >/dev/null 2>&1 && { bun scripts/check_context_compat.ts >/dev/null 2>&1 || fail 'Pi/OMP context compat'; }

# The one thing no CI job can see: upstream moved, and the personal block no
# longer merges cleanly. Read-only — merge-tree writes nothing to the worktree.
if git remote get-url upstream >/dev/null 2>&1; then
  if git fetch --quiet upstream main 2>/dev/null; then
    behind=$(git rev-list --count HEAD..upstream/main 2>/dev/null || echo 0)
    if [ "$behind" -gt 0 ]; then
      printf 'upstream/main is %s commits ahead\n' "$behind"
      if git merge-tree --write-tree HEAD upstream/main 2>/dev/null | grep -q '^CONFLICT'; then
        fail "upstream merge conflicts ($behind commits ahead) — resolve by hand, keep the fork-only block"
      fi
    fi
  else
    printf 'SKIP: upstream unreachable\n'
  fi
else
  printf 'SKIP: no upstream remote (git remote add upstream https://github.com/ayghri/i-have-adhd.git)\n'
fi

[ "$status" -eq 0 ] && printf 'OK: gates green, fork deltas intact\n'
exit "$status"
