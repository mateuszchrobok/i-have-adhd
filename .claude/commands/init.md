---
description: Working agreement for this fork of i-have-adhd — what we change, what breaks it, how to verify, how to ship.
---

```bash
cd /Users/M/work/i-have-adhd     # every command here is repo-relative
git status --short && git log --oneline -3
git remote -v                    # no `upstream`? add it once:
git remote add upstream https://github.com/ayghri/i-have-adhd.git
```

Then read, in this order: `AGENTS.md`, `skills/i-have-adhd/SKILL.md`, `CONTRIBUTING.md`, `hooks/hooks.json`.

## What this repo is

1. Personal fork of an active upstream (`ayghri/i-have-adhd`). Every local delta must survive `git pull upstream main`: additive, in its own block, never interleaved into upstream paragraphs.
2. `origin` is `mateuszchrobok/i-have-adhd`, default branch `main`. Marketplace installs from a source you choose — a GitHub repo (needs a merge to `main`) or a local directory (live from the working copy).
3. Personal rules — Polish informal address, rtk, parallelism + model tier, resume over restart, scheduled checks, findings become issues — live in one `## Working agreement` section of `skills/i-have-adhd/SKILL.md`, fenced by `<!-- fork-only: ... -->` and positioned **immediately above `## Pre-send check`**. That position was measured, not guessed: at end of file, after the pre-send filter's "If yes, send.", the same bytes cost 0.98 weighted points on a blind eval. Never numbered `### 11`+: `README.md:102` and `.github/readme/README.{ja,ko,pt-BR,vi,zh-CN}.md:62` each claim "10 rules", and numbering them falsifies six files.
4. Repo-local commands live in `.claude/commands/`: `/init` (this file, shadows the built-in `/init` inside this repo) and `/complete-repo`. Plain `/complete` cannot be used — the user-level skill `complete` wins that name, so a file named `complete.md` here would be dead. Neither command ships in any manifest.
5. One `SKILL.md` feeds Claude Code, Codex, Pi/OMP, OpenCode, Gemini, Qwen, Kimi. Keep prose runtime-neutral: name a vendor only as a parenthetical gloss, and hedge every harness feature ("if the harness ...").

## Invariants: break one and something real breaks

| Invariant | What breaks | Guard |
| --- | --- | --- |
| `.cursor/skills/i-have-adhd/SKILL.md` byte-identical to the canonical skill | CI job `cursor-skill in sync` fails on `cmp` | after EVERY skill edit: `cp skills/i-have-adhd/SKILL.md .cursor/skills/i-have-adhd/SKILL.md` |
| every hook exits 0 on every failure path | one throw blocks session start for every user | keep the outer `try`/`catch`, the `existsSync` guards, and the `timeout` in `hooks/hooks.json` |
| `SKILL.md` is injected IN FULL at `startup`, `resume`, `clear`, `compact` (flag `~/.claude/.i-have-adhd-always` exists here) | every added line is re-paid in every session, forever | delete a line before adding one; a new rule is one dense line, not a section |
| `name` reads `i-have-adhd` in all 8 manifests | runtimes disagree about what is installed | descriptions are per-runtime BY DESIGN (`plugin.json:3` Antigravity, `.claude-plugin/plugin.json:4` Claude Code, `gemini-extension.json:4` Gemini CLI, `qwen-extension.json:4` Qwen Code) — never homogenize them |
| one version identical across the six versioned manifests (`0.3.1` today) | runtimes report different versions | bump all six in one commit; agreement is checked by `claude plugin tag`, not by `validate` |

## Verify: command, and when it is required

| Command | Required when | Time |
| --- | --- | --- |
| `cmp skills/i-have-adhd/SKILL.md .cursor/skills/i-have-adhd/SKILL.md` | any `SKILL.md` edit, no exceptions | <0.01s |
| `python3 -m unittest discover -s tests` | `hooks/**`, `scripts/**`, `extensions/**`, `.opencode/**`, `tests/**`, any manifest | 0.5s |
| `python3 scripts/run_evals.py validate` | `evals/**`, `scripts/run_evals.py` | 0.04s |
| `claude plugin validate .` | `.claude-plugin/**` only — it reads nothing else (a `hooks.json` with `"hooks":"not-an-array"` passes) | 0.35s |
| `bun scripts/check_context_compat.ts` | `extensions/**` — it imports `extensions/context-compat` and nothing else | 0.02s |

All five together take about one second. There is no excuse to skip one. `hooks/**` is really guarded by `tests/test_always_on_hooks.py`; `package.json` by `scripts/check_pi_extension.py` in CI (`pi-load-check.yml`). Report the exact command and its real output; "should pass" is not a result.

`python3 scripts/run_evals.py run` costs provider money — ask first. Keep the runner isolation in `evals/runners.example.json` (`--setting-sources ""` for claude, `--ignore-user-config --ephemeral` for codex) and the explicit `--model` pin, or the always-on flag injects the ruleset into the BASELINE arm. `run` is resumable: rerun the same command after a network failure and completed `(case, trial, condition, runner)` rows are skipped, 2 retries per call.

## Ship it

```bash
git switch -c feature/<short-desc>        # never commit straight to main
git diff --check && git diff              # read the whole diff
gh pr create --base main                  # no --fill: it drops the PR template body
```

Fill `.github/pull_request_template.md`: exactly one authorship category with agent/model disclosed, one `Target:` label, one `Author:` label, and a Verification section listing only commands actually run. A `SKILL.md` behavior change also needs the evals section filled — runner, model, cases, trials, rubric, release-gate result — or a plain statement that it was not run and why.

Make the working copy live without pushing (directory source, best dev loop):

```bash
claude plugin uninstall i-have-adhd@i-have-adhd --scope user
claude plugin marketplace remove i-have-adhd        # fork and upstream share the name
claude plugin marketplace add /Users/M/work/i-have-adhd --scope user
claude plugin install i-have-adhd@i-have-adhd --scope user
claude plugin list --json                          # installPath must be the repo, not plugins/cache
```

`~/.claude/settings.json → extraKnownMarketplaces` declares the marketplace by name; it points at the fork today, and an entry naming `ayghri/i-have-adhd` would re-add upstream after any removal. `.agents/plugins/marketplace.json` uses `{"source": "local", "path": "./"}` so the Codex path follows whichever checkout the marketplace was added from — do not reintroduce a hardcoded upstream URL there. Restart Claude Code after the swap; the SessionStart hook only re-reads on a new session.

## Off-limits

1. `~/.claude/**`: no credentials, no transcripts, no other plugins. The only facts that matter here are whether `~/.claude/.i-have-adhd-always` exists and what `effortLevel`/`ultracode` are set to.
2. `~/.claude/plugins/cache/**`: generated. Edits there are wiped on reinstall and fix nothing in this repo.
3. `evals/results/`: gitignored, never committed.
4. Translated docs under `.github/`: upstream's job, unless a personal delta makes a stated claim false — the "10 rules" count is exactly such a claim.
5. Anything unrelated to the task. One PR, one concern.

## Answer style in this repo

Polish, informal `ty`, never `Pan`/`Pana`. The rules in `skills/i-have-adhd/SKILL.md` bind your own output here too: action first, numbered steps, lists capped at 5, no preamble, no closer. End the session with `/complete-repo`.
