---
description: End-of-work routine for this repo — runs the repo gates (mirror, tests, validators, diff, commit, PR, todos), drafts issues, then hands off to the global `complete` skill for session review, Notion and memory. Gates and PR are written without asking; Notion, memory and issues are proposed and wait.
---

```bash
cd /Users/M/work/i-have-adhd
cp skills/i-have-adhd/SKILL.md .cursor/skills/i-have-adhd/SKILL.md && cmp skills/i-have-adhd/SKILL.md .cursor/skills/i-have-adhd/SKILL.md
```

Fixed order: **A. repo gates (below) → B. the global `complete` skill**. Never start B while a gate in A is red. A skipped gate is fine; a silently skipped gate is not — name it and say why. When a gate fails and rtk's filtered output hides the cause, rerun it as `rtk proxy <cmd>`.

Mode asymmetry, state it before acting: **Phase 1-3 write without asking** (mirror, commit, push, PR). **Phase 4, Notion and memory only propose and wait.**

## A. Repo gates

### Phase 1 — tests and validators (~1s total)

1. `python3 -m unittest discover -s tests` — mandatory for `hooks/**`, `scripts/**`, `tests/**`, `extensions/**`, `.opencode/**`, any manifest. (0.5s; add `-v` when a failure needs case names.)
2. `python3 scripts/run_evals.py validate` — mandatory when `skills/i-have-adhd/SKILL.md` or `evals/**` changed. (0.04s)
3. `claude plugin validate .` — mandatory for `.claude-plugin/**`. It does **not** read `hooks/` or `skills/`; do not claim it as their guard. (0.35s)
4. `bun scripts/check_context_compat.ts` — mandatory for `extensions/**` only. If `bun` is absent, report "not run: bun missing"; never infer a result from reading the file. (0.02s)

Report each exact command and its real output. "Should pass" is not a result.

### Phase 2 — diff hygiene and doc consequences

1. `git diff --check`, then read the full diff plus `git status --short`.
2. Reject from the diff: unrelated files, absolute personal paths, anything copied out of `~/.claude`, secrets, drive-by reformatting.
3. Rule count changed in `SKILL.md`? `README.md:102` and `.github/readme/README.{ja,ko,pt-BR,vi,zh-CN}.md:62` each state "10 rules" — either the addition stays unnumbered, or all six files change in this commit.
4. Behavior changed? Bump the version in all six versioned manifests in the same commit: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `package.json`, `gemini-extension.json`, `qwen-extension.json`, `kimi.plugin.json`. Docs-only: no bump, and say so.

### Phase 3 — commit, PR, todo state

1. Branch `feature/<desc>` or `hotfix/<issue>`; commit; push. Never commit straight to `main`.
2. `gh pr create --base main` — no `--fill`, it replaces the template body. Fill `.github/pull_request_template.md`: one authorship category with agent/model disclosed, one `Target:` label, one `Author:` label, and a Verification section listing only commands actually run.
3. Reconcile the harness todo list: every item completed, or converted into a Phase 4 issue. Nothing left `in_progress`.
4. State the live-status line every time: the fork changes nothing on this machine until the marketplace source points at it (repo merged to `main`, or the local directory) **and** the plugin is reinstalled. This routine does not make anything live.

### Phase 4 — issues and measurement (draft only, do not create)

1. Routing: fork deltas → `mateuszchrobok/i-have-adhd`; upstream defects → `ayghri/i-have-adhd`, only with explicit consent given in this session. Search before drafting: `gh issue list --search "<keywords>" --state all`. Issue **content** and the duplicate rule belong to the global `complete` skill's Krok 4 — draft against it, do not restate it here.
2. Measurement: for any claim someone will re-measure (injected-ruleset size, eval pass rate, hook latency), either name the CI workflow that re-checks it on every push (`plugin-load-check.yml`, `pi-load-check.yml`, `cursor-skill-sync.yml`) or schedule the recurring check and state its interval, its pass condition, and the command that removes it. "We'll see" is not a plan.

## B. Handoff to the global `complete` skill

Invoke the skill named `complete` (`~/.claude/skills/complete/SKILL.md`) via the Skill tool — not this command again. Its six steps stand unchanged; nothing here overrides them, including its rule that Notion writes are proposed and wait.

Tell it two things so it does not re-derive work:

1. Krok 4 issues are already drafted in Phase 4 — review that draft rather than deriving a second one.
2. Krok 5 (A2A contracts) does not apply to this repo; expect it to say it skipped them.

Feed it exactly three inputs: the gate results (command → real output), the PR URL, and the Phase 4 issue draft. Its closing summary runs five sections, exactly at rule 9's cap. Summary language: Polish, informal, no honorifics.

## Not part of this routine

1. Merging the PR — a human reviews and merges.
2. Repointing the marketplace or reinstalling the plugin.
3. Editing anything outside this repo, including global harness configuration.
4. Opening upstream issues or PRs without explicit consent in this session.
