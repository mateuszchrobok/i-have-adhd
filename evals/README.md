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

## Clause checks

The rubric measures reply shape. It cannot see whether a specific instruction fired — a per-response boolean disappears under a 1.06-point noise floor. `evals/clauses.jsonl` and `scripts/check_clauses.py` check that separately, by assertion rather than by judge:

```bash
python3 scripts/check_clauses.py --skill skills/i-have-adhd/SKILL.md --trials 3
python3 scripts/check_clauses.py --trials 3     # no skill at all, for contrast
```

No judging, no scoring, and a result that means something at three trials. Measured on this fork, 3 trials, sandboxed:

| clause | with the working agreement | bare model |
| --- | ---: | ---: |
| Address the reader directly | 3/3 | 3/3 |
| Monitored numbers get a scheduled check | 3/3 | 0/3 |
| Findings become issues | 3/3 | 0/3 |
| assertions passed | **24/24** | 8/24 |

Two rules learned building it:

1. **Run the model somewhere empty.** From inside the checkout, a prompt describing a hypothetical repo lets the model inspect the real tree, discover the scenario does not exist, and correctly refuse — which measures its honesty, not the clause. The runner now uses a temporary directory.
2. **Suspect the assertion before the skill.** Two apparent clause failures were regex gaps: `settle` did not match "Settling test:", and the not-checked pattern missed "haven't verified". Responses are saved to `--output`, so a widened pattern is re-scored offline for free. Never edit the skill to satisfy a pattern you have not first read the response against.

Parallelism, resume and rtk are not covered here: they describe dispatch a text-only runner cannot perform.
