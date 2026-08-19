<p align="center">
  <img src="./logo.png" alt="i-have-adhd" width="140" />
</p>
<p align="center">
  <strong align="center">ADHD-friendly outputs. No ADHD diagnosis needed!</strong>
</p>
<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/ayghri/i-have-adhd?style=flat" alt="License"></a>
</p>

<p align="center">
  <strong title="English" aria-label="English">🇬🇧</strong> ·
  <a href=".github/readme/README.zh-CN.md" title="简体中文" aria-label="简体中文">🇨🇳</a> ·
  <a href=".github/readme/README.pt-BR.md" title="Português (Brasil)" aria-label="Português (Brasil)">🇧🇷</a> ·
  <a href=".github/readme/README.ja.md" title="日本語" aria-label="日本語">🇯🇵</a> ·
  <a href=".github/readme/README.vi.md" title="Tiếng Việt" aria-label="Tiếng Việt">🇻🇳</a> ·
  <a href=".github/readme/README.ko.md" title="한국어" aria-label="한국어">🇰🇷</a>
</p>

> **This is a fork.** [mateuszchrobok/i-have-adhd](https://github.com/mateuszchrobok/i-have-adhd) tracks [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) and adds one unnumbered `## Working agreement` section at the end of `SKILL.md`: execution policy for this owner's setup — informal Polish address, `rtk` as the default shell, a parallelism cap and model tier, resume over restart, scheduled checks for monitored numbers, findings become issues. The 10 upstream rules are unchanged. Want the original? [Back to upstream](#back-to-upstream).

## Install

Claude Code. Fork and upstream both publish a marketplace named `i-have-adhd`, so an existing upstream install goes first:

```bash
claude plugin uninstall i-have-adhd            # skip both if you never installed upstream
claude plugin marketplace remove i-have-adhd
claude plugin marketplace add mateuszchrobok/i-have-adhd
claude plugin install i-have-adhd@i-have-adhd
```

Restart Claude Code, then type `/i-have-adhd`.

`claude plugin list` prints `i-have-adhd@i-have-adhd` for either one. The marketplace source is what tells them apart:

```bash
claude plugin marketplace list --json    # expect "repo": "mateuszchrobok/i-have-adhd"
```

Other harnesses: 🔗 [INSTALL.md](INSTALL.md), substituting `mateuszchrobok/i-have-adhd` for `ayghri/i-have-adhd`.

### Always-on

```bash
touch ~/.claude/.i-have-adhd-always    # inject the ruleset at every session start
rm ~/.claude/.i-have-adhd-always       # back to on-demand
```

The `SessionStart` hook fires only while that flag exists. This fork's `SKILL.md` makes the injection 170 lines / ~9.4k characters, paid once per session start, resume, clear and compact. `stop adhd mode` still turns it off for the current session.

### Dev loop

Iterate on a local checkout without pushing. Same name clash — only one `i-have-adhd` marketplace at a time:

```bash
claude plugin uninstall i-have-adhd
claude plugin marketplace remove i-have-adhd
claude plugin marketplace add /absolute/path/to/i-have-adhd   # repo root, not .claude-plugin/
claude plugin install i-have-adhd@i-have-adhd
```

Run `claude plugin validate .` after editing a manifest, and restart Claude Code after every edit — the plugin index and hooks are read at startup.

## What it does

A skill for your coding assistant that stops it from burying the answer. Action first. Steps numbered. No "Hope this helps!"


## What changes


<table>
<tr>
<td width="50%">

## Before

> Great question! Let me think about this. Your auth flow has a few moving pieces: the middleware, the token verification, and the cookie handling. Looking at `src/auth.ts`, the `verifyToken` function (around lines 42-58) seems to be using an older `jsonwebtoken` API. One approach would be to update the package and rewrite that function. After making the change, you'd want to run the auth tests to confirm nothing breaks. By the way, you might also want to look at your dependency versions overall. Hope this helps! Let me know if you want to dig deeper.

</td>

<td width="50%">

## After

> Run `npm install jsonwebtoken@latest`, then edit `src/auth.ts:42`.
>
> 1. Open `src/auth.ts`
> 2. Replace `verifyToken` (lines 42–58) with the snippet below
> 3. Run `npm test -- auth.spec.ts`
>
> Next: paste the first failing line if any test fails.

</td>
</tr>
</table>


## The rules

10 rules, plus this fork's unnumbered `## Working agreement` section. Full text in [SKILL.md](./skills/i-have-adhd/SKILL.md).

1. Lead with the next action.
2. Number multi-step tasks.
3. End with one concrete next step.
4. Suppress tangents.
5. Restate state every turn.
6. Specific time estimates (minutes, not "a bit").
7. Make wins visible.
8. Matter-of-fact errors.
9. Cap lists at 5 items.
10. No preamble. No recap. No closers.

## Upgrade

```bash
claude plugin marketplace update i-have-adhd
claude plugin update i-have-adhd@i-have-adhd
```

Restart Claude Code. To take upstream's changes first: `git fetch upstream && git merge upstream/main`, keep the `<!-- fork-only -->` block, push to the fork, then run the two commands above.

## Back to upstream

```bash
claude plugin uninstall i-have-adhd
claude plugin marketplace remove i-have-adhd
claude plugin marketplace add ayghri/i-have-adhd
claude plugin install i-have-adhd@i-have-adhd
```

## Credits

Loosely based on *The Adult ADHD Tool Kit* by J. Russell Ramsay and Anthony L. Rostain. Adapted for how an LLM should respond, not how a human should organize their day.

## License

MIT.

Star ⭐ if it saved you one scroll past one "Great question!"
