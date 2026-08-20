#!/usr/bin/env python3
"""Check what the agent DOES, not what its reply says it would do.

`run_evals.py` scores reply text under `--tools ""`. Three working-agreement
clauses and two catalogue cases describe dispatch — editing a file rather than
delegating it, previewing before deleting, not hand-prefixing rtk — and none of
them is visible to a text-only runner (evals/case_screen.json, issue #17).

This builds a throwaway git repository per case, runs the model against it with
tools enabled, and asserts over the tool-call transcript plus the resulting file
state.

    python3 scripts/check_tools.py --trials 2
    python3 scripts/check_tools.py --validate-only

Requires ANTHROPIC_BASE_URL to point at a reachable gateway; the runner inherits
the environment and this repo's shell exports a dead one.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evals" / "tool_cases.json"
KINDS = {"must_call", "must_not_call_matching", "file_matches", "file_not_matches"}

COMMAND = [
    "claude",
    "--print",
    "--output-format",
    "stream-json",
    "--verbose",
    "--no-session-persistence",
    "--setting-sources",
    "",
    "--disable-slash-commands",
    "--model",
    "claude-opus-4-8",
    "--permission-mode",
    "acceptEdits",
]


def load_cases(path: Path) -> list[dict]:
    cases = json.loads(path.read_text())["cases"]
    seen = set()
    for case in cases:
        if case["id"] in seen:
            raise ValueError(f"duplicate tool case id: {case['id']}")
        seen.add(case["id"])
        if not case["assertions"]:
            raise ValueError(f"{case['id']}: no assertions")
        for assertion in case["assertions"]:
            if assertion["kind"] not in KINDS:
                raise ValueError(f"{case['id']}: unknown kind {assertion['kind']!r}")
            if "pattern" in assertion:
                re.compile(assertion["pattern"])
            if "tool" in assertion:
                re.compile(assertion["tool"])
    return cases


def build_fixture(case: dict, root: Path) -> None:
    for name, body in case["files"].items():
        (root / name).write_text(body)
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    tracked = case.get("track", list(case["files"]))
    subprocess.run(["git", "add", *tracked], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=eval@local", "-c", "user.name=eval", "commit", "-qm", "fixture"],
        cwd=root,
        check=True,
    )


def tool_calls(stream: str) -> list[tuple[str, dict]]:
    calls = []
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            # Some stream events carry `message` as a plain string.
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append((block.get("name", ""), block.get("input") or {}))
    return calls


def evaluate(case: dict, calls: list[tuple[str, dict]], root: Path) -> list[dict]:
    results = []
    for assertion in case["assertions"]:
        kind = assertion["kind"]
        if kind == "must_call":
            passed = any(re.fullmatch(assertion["tool"], name) for name, _ in calls)
        elif kind == "must_not_call_matching":
            pattern = re.compile(assertion["pattern"])
            passed = not any(
                re.fullmatch(assertion["tool"], name)
                and pattern.search(str(args.get(assertion["field"], "")))
                for name, args in calls
            )
        else:
            target = root / assertion["path"]
            body = target.read_text() if target.exists() else ""
            hit = bool(re.search(assertion["pattern"], body))
            passed = hit if kind == "file_matches" else not hit
        results.append({"description": assertion["description"], "passed": passed})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    if args.validate_only:
        print(f"{len(cases)} tool cases are valid.")
        return 0
    if not shutil.which("claude"):
        print("claude not on PATH", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for trial in range(1, args.trials + 1):
        for case in cases:
            with tempfile.TemporaryDirectory(prefix="tool-case-") as tmp:
                root = Path(tmp)
                build_fixture(case, root)
                completed = subprocess.run(
                    [*COMMAND, case["prompt"]],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode:
                    print(
                        f"runner failed on {case['id']} trial {trial}: "
                        f"{(completed.stderr or completed.stdout).strip()[:300]}",
                        file=sys.stderr,
                    )
                    return 1
                calls = tool_calls(completed.stdout)
                results = evaluate(case, calls, root)
            rows.append(
                {
                    "case_id": case["id"],
                    "trial": trial,
                    "tools": [name for name, _ in calls],
                    # Keep the arguments: the first failure here was a too-narrow
                    # pattern, and without the raw command there was nothing on
                    # disk to check it against.
                    "calls": [{"tool": name, "input": str(args)[:300]} for name, args in calls],
                    "results": results,
                }
            )
            marks = "".join("." if r["passed"] else "F" for r in results)
            print(f"{case['id']:<26} trial {trial}  {marks}  tools={','.join(n for n, _ in calls) or '-'}")

    print()
    failures = 0
    for case in cases:
        subset = [r for r in rows if r["case_id"] == case["id"]]
        full = sum(all(x["passed"] for x in r["results"]) for r in subset)
        print(f"{case['id']:<26} {full}/{len(subset)} trials pass every assertion")
        for index, assertion in enumerate(case["assertions"]):
            passes = sum(r["results"][index]["passed"] for r in subset)
            flag = "" if passes == len(subset) else "   <-- "
            failures += passes < len(subset)
            print(f"    {passes}/{len(subset)}  {assertion['description']}{flag}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"\n{failures} assertion(s) did not hold on every trial.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
