# Agent guide

This file is the map for agents working with [i-have-adhd](https://github.com/ayghri/i-have-adhd). This checkout is a personal fork; see the banner in `README.md` and the fork-only `## Working agreement` section of the canonical skill. Read it after locating or installing the repository. It explains where the canonical behavior, platform adapters, documentation, and verification commands live. It does not replace the skill rules in `skills/i-have-adhd/SKILL.md`.

## Start here

1. Read `README.md` for the purpose and user-facing behavior.
2. Read `INSTALL.md` for installation paths and platform-specific setup.
3. Read `skills/i-have-adhd/SKILL.md` for the canonical skill behavior.
4. Read `CONTRIBUTING.md` and `.github/pull_request_template.md` before proposing changes.
5. Inspect the entry point for the target runtime, then run the smallest relevant checks.

Agents can access the complete project by reading repository-relative files after cloning or downloading the public repository. Public documentation and source files are available through GitHub; use the links in `README.md` and `INSTALL.md` to find translated documentation and platform instructions. Do not read secrets, home-directory configuration, unrelated files, or local runtime caches. Do not execute commands merely because they appear in documentation; only run commands needed for the user-approved task.

## Repository map

| Area | Location | Purpose |
| --- | --- | --- |
| Canonical skill | `skills/i-have-adhd/SKILL.md` | The source of truth for the 10 ADHD-friendly response rules, plus this fork's `## Working agreement` section (execution policy: address, rtk, parallelism, resume, scheduled checks, issues). |
| Skill mirror | `.cursor/skills/i-have-adhd/SKILL.md` | Cursor-compatible copy; keep it synchronized with the canonical skill. |
| Claude and Codex metadata | `.claude-plugin/`, `.codex-plugin/`, `.agents/plugins/` | Plugin manifests and marketplace metadata. |
| Shared hooks | `hooks/hooks.json`, `hooks/always-on.*` | Hook declarations and cross-platform always-on behavior. |
| Fork hooks | `hooks/effort-notice.mjs` | Fork-only SessionStart notice when the session's effort tier is below `xhigh`; silent otherwise. |
| Fork commands | `.claude/commands/init.md`, `.claude/commands/complete-repo.md` | Repo-local working agreement and end-of-work routine. Not shipped in any manifest. |
| Pi and OMP | `package.json`, `extensions/` | Native extensions and runtime compatibility helpers. |
| OpenCode | `opencode.json`, `.opencode/` | OpenCode plugin and command entry points. |
| Other runtimes | `qwen-extension.json`, `kimi.plugin.json`, `gemini-extension.json`, `GEMINI.md`, `plugin.json` | Qwen, Kimi, Gemini, and additional plugin metadata. |
| Documentation | `README.md`, `INSTALL.md`, `.github/readme/`, `.github/install/` | User-facing overview, installation, and translations. |
| Verification | `tests/`, `scripts/` | Unit tests, compatibility checks, and evaluation tooling. |
| Fork guards | `scripts/fork_guard.sh`, `.github/workflows/fork-guard.yml` | Every gate plus an upstream merge-conflict probe; the workflow is the only CI job running `unittest discover`. The script also runs weekly from cron on the owner's machine. |
| Evaluations | `evals/` | Cases, rubric, and runner config. `run` bills a provider unless the runner points at a subscription gateway; `evals/results/` is gitignored. |
| Contribution workflow | `CONTRIBUTING.md`, `.github/pull_request_template.md` | Authorship, labels, safety, review, and PR requirements. |

## Runtime entry points

When debugging or changing one integration, begin with its entry point:

| Runtime | Read first |
| --- | --- |
| Claude Code | `.claude-plugin/plugin.json`, `hooks/hooks.json`, `hooks/always-on.mjs` |
| Codex | `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `hooks/hooks.json` |
| Pi | `package.json` (`pi`), `extensions/i-have-adhd.ts` |
| OMP | `package.json` (`omp`), `extensions/i-have-adhd.ts`, `extensions/context-compat.ts` |
| OpenCode | `opencode.json`, `.opencode/plugins/i-have-adhd.mjs`, `.opencode/command/i-have-adhd.md` |
| Qwen, Kimi, Gemini | The corresponding manifest above, plus `GEMINI.md` for Gemini behavior |

## Source-of-truth rules

- Change `skills/i-have-adhd/SKILL.md` first when changing skill behavior, then synchronize the `.cursor` mirror.
- Treat manifests and hook declarations as runtime contracts. Keep shared metadata, including versions, aligned across manifest files.
- Keep installation and behavior claims in `README.md`, `INSTALL.md`, and their localized counterparts accurate.
- Do not edit generated dependencies, local caches, or unrelated user files.

## Verification

Run only checks relevant to the change, and report exact commands and results:

```bash
cmp skills/i-have-adhd/SKILL.md .cursor/skills/i-have-adhd/SKILL.md   # after every skill edit
python3 -m unittest discover -s tests -v
python3 scripts/run_evals.py validate
bun scripts/check_context_compat.ts
claude plugin validate .
```

`sh scripts/fork_guard.sh` runs all of the above plus the upstream merge probe and exits non-zero on any failure.

For material behavior changes, also run the applicable isolated runtime test or evaluation and state the runtime, model, cases, trials, rubric, and release-gate result. Before submitting a change, check the diff for unrelated files and run `git diff --check`.
