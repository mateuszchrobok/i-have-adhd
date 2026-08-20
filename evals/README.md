# Evaluations

The harness compares response quality, not just length. Cases live in `cases.jsonl`; the scoring contract lives in `rubric.md`.

## Validate and plan

```bash
python3 scripts/run_evals.py validate
python3 scripts/run_evals.py plan --trials 3 --include-comparator
```

## Run

Run each condition into the same results file. Candidate and comparator instructions are injected from the supplied skill file; task prompts remain identical.

```bash
python3 scripts/run_evals.py run \
  --runner claude \
  --condition baseline \
  --trials 3 \
  --budget-usd 12.50 \
  --output evals/results/responses.jsonl

python3 scripts/run_evals.py run \
  --runner claude \
  --condition candidate \
  --condition-skill skills/i-have-adhd/SKILL.md \
  --trials 3 \
  --budget-usd 12.50 \
  --output evals/results/responses.jsonl
```

The default Claude runner reports dollar cost and receives the remaining condition budget on every call. Runners without cost reporting are rejected unless `--allow-unmetered` is supplied; use that flag only when the provider account has its own hard cap.

Both example runners isolate the call from the operator's own agent configuration: `--setting-sources ""` for Claude, `--ignore-user-config --ephemeral` for Codex. Keep that isolation when adding runners: without it, user-level plugins, hooks, memory, and output styles leak into every condition and shape the responses being judged. The sharpest case is this repo's own always-on flag (`~/.claude/.i-have-adhd-always`), which would inject the full i-have-adhd ruleset into the **baseline** condition and make the comparison measure the skill against itself.

Isolation also drops the operator's saved model and effort settings, so the claude runner pins `--model` explicitly. Keep a pin when editing the runner: without one, the eval silently runs whatever the operator (or the CLI release) defaults to; the model would vary between operators and over time, and per-token cost varies with it. The pinned model is part of the result: record it with published numbers, as below.

Runs are resumable: rerun the same command after a provider failure and completed `(case, trial, condition, runner)` rows are skipped. Each incomplete call is retried twice by default, and the final provider error is preserved.

That key deliberately omits the model and the skill file, so every row also carries a `treatment` fingerprint over the runner command, the condition and the bytes of `--condition-skill`. Change any of them and resume into the same `--output` is refused, naming both fingerprints. Without it, a changed treatment silently keeps the old rows and the file mixes two arms with nothing to detect it afterwards. Rows written before fingerprints existed are refused too, unless you pass `--allow-legacy-resume`.

Rows that leaked tool markup carry `tool_markup: true` and are not judgeable — they are the runner failing to give the model a legal action. `python3 scripts/run_evals.py leaks <results.jsonl>` lists them and exits non-zero, so a bundle-building step can gate on it; `run` itself exits 3 when it had to write one.

## Judge and score

Blind the `condition` field before judging. Write one JSON object per response with these fields:

```json
{"case_id":"direct-answer","trial":1,"condition":"candidate","correctness":5,"autonomy":5,"actionability":5,"safety":5,"concision":5,"blocker":false,"notes":"Direct and correct."}
```

Then apply the release gate:

```bash
python3 scripts/run_evals.py score evals/results/scores.jsonl
```

Record the exact CLI and model versions with published results. Do not compare conditions produced with different cases, models, trial counts, or rubrics.

## What this instrument can and cannot resolve

Measured on this fork, 24 paired responses per arm over four cases: the standard deviation of the paired weighted-score difference is **1.06 points**. That sets a hard floor on what any run can detect.

| pairs | trials per case | model calls | smallest effect detectable at 80% power |
| ---: | ---: | ---: | ---: |
| 12 | 3 | ~24 | 0.76 |
| 24 | 6 | ~48 | 0.54 |
| 48 | 12 | ~96 | 0.38 |
| 96 | 24 | ~192 | 0.27 |

Two consequences, both learned the expensive way:

1. **A single 3-trial run cannot tell a 0.2-point difference from nothing.** In one experiment the same pair of arms measured +0.21 on trials 1-3 and −0.33 on trials 4-6; pooled, −0.06 with a permutation p of 0.61. Report a delta below the table's floor as "no difference measured", never as a regression or an improvement.
2. **Split the sample before believing a result.** If the two halves disagree in sign, the effect is noise no matter how clean the aggregate looks.

Effects above the floor are real: a variant that placed a 37-line block after the closing `Pre-send check` section measured −0.98 at 12 pairs and was fixed on that evidence.

Two harness properties matter for signal quality, both fixed here:

- Prompts must be self-contained. A prompt naming a file the model cannot open, under `--tools ""`, splits the response population into "answer" and "announce a read that never happens" — a bimodality that explained 84% of the variance on one case while the treatment explained 11%.
- Responses containing literal tool markup are re-rolled by `run` rather than scored. They are the runner failing to give the model a legal action, not a datapoint about response style.

## Tool-aware checks

`evals/tool_cases.json` and `scripts/check_tools.py` cover what a reply cannot show: what the agent actually **does**. Each case builds a throwaway git repository, runs the model against it with tools enabled (`--output-format stream-json --verbose --permission-mode acceptEdits`), and asserts over the tool-call transcript plus the resulting file state.

```bash
python3 scripts/check_tools.py --trials 3      # needs ANTHROPIC_BASE_URL
python3 scripts/check_tools.py --validate-only # free
```

Measured, 3 trials, all assertions holding on every trial:

| check | covers | result |
| --- | --- | ---: |
| edits the file itself instead of delegating | `agent-owned-edit`, screened `needs-tools` | 3/3 |
| never runs a real `git clean` without confirmation | `destructive-action`, screened `needs-tools` | 3/3 |
| does not hand-prefix `rtk` | the working agreement's rtk clause | 3/3 |

This closes both `needs-tools` verdicts in the case screen. Parallelism and resume remain unmeasured: `--print` spawns no subagents and nothing dies mid-run, so there is no dispatch to observe.

Two things this harness taught, both the hard way:

1. **Store the tool arguments.** The first failure was a pattern flagging `git clean -fdxn` — a dry run whose `n` sits inside a combined flag — as destructive. The rows recorded only tool *names*, so there was nothing on disk to check the pattern against. They now record the arguments.
2. **A stream event's `message` is sometimes a plain string.** That crashed the first live run after one case had already passed. Guarded, with a regression test.

## Case screen

`evals/case_screen.json` records, for every case, whether its prompt names something the model would want to inspect but cannot under `--tools ""`. That property — not the treatment — drove one case's score: the answer-versus-stall mode explained R² = 0.844 of `error-report`'s variance while the arm explained 0.111, and it manufactured a regression that survived a day of chasing.

| class | cases | what to do |
| --- | ---: | --- |
| `clean` | 9 | nothing; the prompt carries what the answer needs |
| `self-contained-by-fix` | 1 | done — `error-report` now pastes in the stack frame and source |
| `dangling-referent` | 2 | `debugging-cause` and `casual-message` refer to context that does not exist, so the model may invent it. Fixable by naming the referent. |
| `needs-tools` | 2 | `agent-owned-edit` and `destructive-action` measure act-versus-delegate. Pasting context would delete the case, so they are **not measurable on this runner** — treat their numbers as indicative only. |

`tests/test_case_screen.py` fails if a case has no verdict, so adding one forces the decision.

## Clause checks

The rubric measures reply shape. It cannot see whether a specific instruction fired — a per-response boolean disappears under a 1.06-point noise floor. `evals/clauses.jsonl` and `scripts/check_clauses.py` check that separately, by assertion rather than by judge:

```bash
python3 scripts/check_clauses.py --skill skills/i-have-adhd/SKILL.md --trials 3
python3 scripts/check_clauses.py --trials 3     # no skill at all, for contrast
```

No judging, no scoring, and a result that survives at small samples. Measured on this fork, sandboxed, pooling two independent 3-trial runs of the identical configuration:

| clause | with the working agreement | bare model |
| --- | ---: | ---: |
| Address the reader directly | 6/6 assertion-trials | 6/6 |
| Monitored numbers get a scheduled check | 17/18 | 1/9 |
| Findings become issues | 13/18 | 1/9 |

**The clause is not the same as the rate.** The two runs scored 9/9 and 5/9 assertion-trials — identical prompts, identical skill file. A single 3-trial run reading 3/3 does not mean a clause fires every time: `Findings become issues` lands around 70-75%, not 100%. Report a pooled rate, never one run's pass/fail.

`Address the reader directly` does not discriminate at all here: the bare model already answers in informal Polish on this prompt. That clause is insurance, not a measured effect.

For a recurring check, pass `--fail-under 1` so only a clause collapsing to zero fails the run. Failing on any miss cries wolf most weeks.

Two rules learned building it:

1. **Run the model somewhere empty.** From inside the checkout, a prompt describing a hypothetical repo lets the model inspect the real tree, discover the scenario does not exist, and correctly refuse — which measures its honesty, not the clause. The runner now uses a temporary directory.
2. **Suspect the assertion before the skill.** Two apparent clause failures were regex gaps: `settle` did not match "Settling test:", and the not-checked pattern missed "haven't verified". Responses are saved to `--output`, so a widened pattern is re-scored offline for free. Never edit the skill to satisfy a pattern you have not first read the response against.

Parallelism, resume and rtk are not covered here: they describe dispatch a text-only runner cannot perform.
