#!/usr/bin/env python3
"""Assert that the fork's working-agreement clauses actually fire.

The weighted rubric in run_evals cannot see these: measured paired-delta sd is
1.06 points, so a per-response boolean disappears into the noise (evals/README.md).
Clause adherence is checked by assertion instead — no judge, no scoring, and a
result that means something at three trials.

    python3 scripts/check_clauses.py --skill skills/i-have-adhd/SKILL.md --trials 3

Omit --skill to measure the bare model with no response-style skill at all.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_evals  # noqa: E402

DEFAULT_CLAUSES = ROOT / "evals" / "clauses.jsonl"
FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}


def compile_pattern(assertion: dict) -> re.Pattern[str]:
    flags = 0
    for letter in assertion.get("flags", ""):
        if letter not in FLAGS:
            raise ValueError(f"unknown regex flag {letter!r}")
        flags |= FLAGS[letter]
    return re.compile(assertion["pattern"], flags)


def evaluate(response: str, assertions: list[dict]) -> list[dict]:
    results = []
    for assertion in assertions:
        hit = bool(compile_pattern(assertion).search(response))
        expected = assertion["kind"] == "must_match"
        results.append(
            {
                "description": assertion["description"],
                "kind": assertion["kind"],
                "passed": hit is expected,
            }
        )
    return results


def load_clauses(path: Path) -> list[dict]:
    clauses = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for clause in clauses:
        for assertion in clause["assertions"]:
            if assertion["kind"] not in {"must_match", "must_not_match"}:
                raise ValueError(f"{clause['id']}: unknown kind {assertion['kind']!r}")
            compile_pattern(assertion)
    return clauses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clauses", type=Path, default=DEFAULT_CLAUSES)
    parser.add_argument("--runner-config", type=Path, default=ROOT / "evals" / "runners.example.json")
    parser.add_argument("--runner", default="claude")
    parser.add_argument("--skill", type=Path, help="omit to run with no skill at all")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--budget-usd", type=float, default=3.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    clauses = load_clauses(args.clauses)
    if args.validate_only:
        print(f"{len(clauses)} clause checks are valid.")
        return 0

    runner = json.loads(args.runner_config.read_text())[args.runner]
    response_format = runner["response_format"]
    rows: list[dict] = []

    sandbox_dir = tempfile.TemporaryDirectory(prefix="clause-check-")
    sandbox = sandbox_dir.name

    for trial in range(1, args.trials + 1):
        for clause in clauses:
            prompt = clause["prompt"]
            if args.skill:
                prompt = run_evals._condition_prompt(prompt, "candidate", args.skill)
            invocation = [*runner["command"]]
            if runner.get("budget_flag"):
                # Also acts as the separator that keeps a variadic `--tools ""`
                # from swallowing the prompt positional.
                invocation.extend([runner["budget_flag"], f"{args.budget_usd:.4f}"])
            invocation.append(prompt)
            # Run somewhere empty. These prompts describe hypothetical repos;
            # from inside this checkout the model can inspect the real tree,
            # discover the scenario does not exist, and correctly refuse — which
            # measures its honesty, not the clause.
            completed = subprocess.run(
                invocation,
                check=False,
                capture_output=True,
                text=True,
                cwd=sandbox,
            )
            if completed.returncode:
                detail = (completed.stderr or completed.stdout).strip()[:400]
                print(
                    f"runner failed on {clause['id']} trial {trial}: {detail}",
                    file=sys.stderr,
                )
                return 1
            text, _, _ = run_evals._parse_response(completed.stdout, response_format)
            results = evaluate(text, clause["assertions"])
            rows.append({"clause_id": clause["id"], "trial": trial, "results": results, "response": text})
            marks = "".join("." if r["passed"] else "F" for r in results)
            print(f"{clause['id']:<18} trial {trial}  {marks}")

    print()
    failures = 0
    for clause in clauses:
        subset = [r for r in rows if r["clause_id"] == clause["id"]]
        per = Counter()
        for row in subset:
            for result in row["results"]:
                per[result["description"]] += result["passed"]
        total = len(subset)
        worst = min(per.values()) if per else 0
        failures += sum(1 for value in per.values() if value < total)
        print(f"{clause['id']:<18} {worst}/{total} trials pass every assertion")
        for description, passes in per.items():
            flag = "" if passes == total else "   <-- "
            print(f"    {passes}/{total}  {description}{flag}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    print(f"\n{failures} assertion(s) did not hold on every trial.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
