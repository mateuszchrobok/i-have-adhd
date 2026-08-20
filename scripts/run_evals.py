#!/usr/bin/env python3
"""Validate, run, and score paired response-quality evaluations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evals" / "cases.jsonl"
WEIGHTS = {
    "correctness": 0.35,
    "autonomy": 0.25,
    "actionability": 0.20,
    "safety": 0.10,
    "concision": 0.10,
}
CONDITIONS = {"baseline", "candidate", "comparator"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {number}: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}: line {number}: expected a JSON object")
        rows.append(row)
    return rows


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    return read_jsonl(path)


def completed_keys(rows: list[dict[str, Any]]) -> set[tuple[str, int, str, str]]:
    keys: set[tuple[str, int, str, str]] = set()
    for row in rows:
        fields = (row.get("case_id"), row.get("trial"), row.get("condition"), row.get("runner"))
        if isinstance(fields[0], str) and isinstance(fields[1], int) and all(
            isinstance(value, str) for value in fields[2:]
        ):
            keys.add(fields)  # type: ignore[arg-type]
    return keys


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    required = {"id", "category", "prompt", "risk", "criteria"}
    for index, case in enumerate(cases, start=1):
        missing = sorted(required - set(case))
        if missing:
            errors.append(f"Case {index}: missing fields: {', '.join(missing)}")
            continue
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"Case {index}: id must be a non-empty string")
        elif case_id in seen:
            errors.append(f"Duplicate case id: {case_id}")
        else:
            seen.add(case_id)
        if case["risk"] not in {"low", "medium", "high"}:
            errors.append(f"Case {case_id}: risk must be low, medium, or high")
        if not isinstance(case["criteria"], list) or not case["criteria"]:
            errors.append(f"Case {case_id}: criteria must be a non-empty list")
    return errors


def _validate_score(row: dict[str, Any], index: int) -> None:
    required = {"case_id", "trial", "condition", *WEIGHTS, "blocker", "notes"}
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"Score row {index}: missing fields: {', '.join(missing)}")
    if row["condition"] not in CONDITIONS:
        raise ValueError(f"Score row {index}: unsupported condition {row['condition']!r}")
    for metric in WEIGHTS:
        value = row[metric]
        if not isinstance(value, (int, float)) or not 1 <= value <= 5:
            raise ValueError(f"Score row {index}: {metric} must be between 1 and 5")
    if not isinstance(row["blocker"], bool):
        raise ValueError(f"Score row {index}: blocker must be boolean")


def _describe_rows(keys: list[tuple[str, Any]]) -> str:
    return ", ".join(f"{case_id}/trial {trial}" for case_id, trial in keys)


def _check_pairing(grouped: dict[str, list[dict[str, Any]]]) -> None:
    """Conditions are only comparable when judged on identical rows."""
    coverage = {
        condition: Counter((row["case_id"], row["trial"]) for row in rows)
        for condition, rows in grouped.items()
    }
    for condition, counts in sorted(coverage.items()):
        repeated = sorted(key for key, count in counts.items() if count > 1)
        if repeated:
            raise ValueError(
                f"{condition}: duplicate score rows for {_describe_rows(repeated)}"
            )
    baseline = coverage["baseline"]
    for condition, counts in sorted(coverage.items()):
        if condition == "baseline" or counts == baseline:
            continue
        details = []
        missing = sorted(set(baseline) - set(counts))
        if missing:
            details.append(f"missing {_describe_rows(missing)}")
        unmatched = sorted(set(counts) - set(baseline))
        if unmatched:
            details.append(f"unmatched {_describe_rows(unmatched)}")
        raise ValueError(
            f"{condition} was not judged on the same rows as baseline: "
            + "; ".join(details)
        )


def summarize_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(scores, start=1):
        _validate_score(row, index)
        grouped[row["condition"]].append(row)
    if "baseline" not in grouped or "candidate" not in grouped:
        raise ValueError("Scores must include baseline and candidate conditions")
    _check_pairing(grouped)

    conditions: dict[str, dict[str, Any]] = {}
    for condition, rows in sorted(grouped.items()):
        metrics = {
            metric: sum(float(row[metric]) for row in rows) / len(rows)
            for metric in WEIGHTS
        }
        conditions[condition] = {
            "rows": len(rows),
            **metrics,
            "weighted_score": sum(metrics[metric] * weight for metric, weight in WEIGHTS.items()),
            "blocking_findings": sum(bool(row["blocker"]) for row in rows),
        }

    baseline = conditions["baseline"]
    candidate = conditions["candidate"]
    reasons: list[str] = []
    if candidate["blocking_findings"]:
        reasons.append("Candidate has blocking safety or correctness findings.")
    if candidate["correctness"] < baseline["correctness"] - 0.1:
        reasons.append("Candidate correctness regressed by more than 0.1 points.")
    if candidate["safety"] < baseline["safety"] - 0.1:
        reasons.append("Candidate safety regressed by more than 0.1 points.")
    if candidate["weighted_score"] <= baseline["weighted_score"]:
        reasons.append("Candidate weighted score did not beat baseline.")

    return {
        "weights": WEIGHTS,
        "conditions": conditions,
        "release_gate": {"passed": not reasons, "reasons": reasons},
    }


def _condition_prompt(task: str, condition: str, skill_path: Path | None) -> str:
    if condition == "baseline":
        return task
    if skill_path is None:
        raise ValueError(f"--condition-skill is required for the {condition} condition")
    instructions = skill_path.read_text(encoding="utf-8")
    return (
        "Follow the response-style skill below while completing the task. "
        "Do not discuss or quote the skill.\n\n"
        f"<response_style>\n{instructions}\n</response_style>\n\n"
        f"<task>\n{task}\n</task>"
    )


def _last_result_document(output: str) -> dict[str, Any]:
    """Return the final result object from a `claude --output-format json` stdout.

    The CLI usually prints exactly one JSON document, but it intermittently
    appends a second document or a fragment of non-JSON text (observed twice in
    ~40 calls). `json.loads` on the whole buffer then dies with "Extra data" or
    "Expecting value" and a completed, already-paid-for call is thrown away.
    Decode documents in sequence, ignore trailing junk once at least one
    document is in hand, and keep the last one that looks like a result.
    """
    decoder = json.JSONDecoder()
    documents: list[dict[str, Any]] = []
    index = 0
    while index < len(output):
        while index < len(output) and output[index].isspace():
            index += 1
        if index >= len(output):
            break
        try:
            document, index = decoder.raw_decode(output, index)
        except json.JSONDecodeError:
            if documents:
                print(
                    f"warning: ignored {len(output) - index} trailing bytes of "
                    f"non-JSON runner output: {output[index:index + 120]!r}",
                    file=sys.stderr,
                )
                break
            next_brace = output.find("{", index + 1)
            if next_brace == -1:
                raise
            index = next_brace
            continue
        if isinstance(document, dict):
            documents.append(document)
    if not documents:
        raise ValueError("Runner produced no JSON document")
    for document in reversed(documents):
        if document.get("type") == "result" or "result" in document:
            return document
    return documents[-1]


TOOL_MARKUP = re.compile(r"<invoke\b|</?antml:|<parameter\s+name=|function_calls")


def _leaks_tool_markup(text: str) -> bool:
    """True when the model emitted literal tool-call markup.

    Under `--tools ""` the model has no legal action, and a prompt naming a file
    invites it to reach for one anyway. The result is not a datapoint about
    response style — it is the harness failing to give the model an outlet — so
    the call is re-rolled rather than handed to a judge.
    """
    return bool(TOOL_MARKUP.search(text))


def _parse_response(output: str, response_format: str) -> tuple[str, dict[str, Any], float | None]:
    if response_format == "text":
        return output.strip(), {}, None
    if response_format == "claude-json":
        payload = _last_result_document(output)
        return (
            str(payload.get("result", "")).strip(),
            payload.get("usage", {}) or {},
            payload.get("total_cost_usd"),
        )
    if response_format == "codex-jsonl":
        events = [json.loads(line) for line in output.splitlines() if line.strip()]
        text = ""
        usage: dict[str, Any] = {}
        for event in events:
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                text = item.get("text", text)
            if event.get("type") == "turn.completed":
                usage = event.get("usage", usage)
        return str(text).strip(), usage, None
    raise ValueError(f"Unsupported response format: {response_format}")


def _treatment_fingerprint(command: list[str], condition: str, skill_path: Path | None) -> str:
    """Identify what was actually being tested, so a resume cannot mix treatments.

    `completed_keys` deliberately keys on (case, trial, condition, runner) — that
    is what makes a run resumable. It also means changing the model or the skill
    file and rerunning into the same --output silently keeps the old rows. This
    fingerprint is written on every row and checked on resume.
    """
    skill = b"" if skill_path is None else skill_path.read_bytes()
    payload = "\x00".join([*command, condition]).encode("utf-8") + b"\x00" + skill
    return hashlib.sha256(payload).hexdigest()[:16]


def _check_resume_is_comparable(
    prior_rows: list[dict[str, Any]],
    condition: str,
    runner: str,
    fingerprint: str,
    allow_legacy: bool,
) -> None:
    same_arm = [
        row
        for row in prior_rows
        if row.get("condition") == condition and row.get("runner") == runner
    ]
    if not same_arm:
        return
    legacy = [row for row in same_arm if "treatment" not in row]
    if legacy and not allow_legacy:
        raise RuntimeError(
            f"{len(legacy)} prior row(s) for condition {condition!r} predate treatment "
            "fingerprints, so this run cannot prove they used the same model and skill "
            "file. Use a fresh --output, or pass --allow-legacy-resume if you are certain."
        )
    mismatched = sorted(
        {row["treatment"] for row in same_arm if row.get("treatment") not in (None, fingerprint)}
    )
    if mismatched:
        raise RuntimeError(
            f"Refusing to resume: prior rows for condition {condition!r} were produced by a "
            f"different treatment ({', '.join(mismatched)}; this run is {fingerprint}). The "
            "model, the runner command or the --condition-skill content changed. Use a fresh "
            "--output — mixing them in one file is undetectable afterwards."
        )


def list_leaks(args: argparse.Namespace) -> int:
    rows = read_jsonl(args.results)
    leaked = [row for row in rows if row.get("tool_markup")]
    if not leaked:
        print(f"{len(rows)} rows, no tool markup.")
        return 0
    print(f"{len(leaked)} of {len(rows)} rows leaked tool markup and are not judgeable:")
    for row in leaked:
        print(
            f"  {row.get('case_id')} trial {row.get('trial')} "
            f"{row.get('condition')}/{row.get('runner')}"
        )
    return 1


def run_evaluations(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    errors = validate_cases(cases)
    if errors:
        raise ValueError("\n".join(errors))
    unknown = sorted(set(args.case or []) - {case["id"] for case in cases})
    if unknown:
        raise ValueError(f"--case matched no evaluation case: {', '.join(unknown)}")
    config = json.loads(args.runner_config.read_text(encoding="utf-8"))
    runner = config[args.runner]
    command = list(runner["command"])
    response_format = runner.get("response_format", "text")
    if response_format != "claude-json" and not args.allow_unmetered:
        raise RuntimeError(
            f"The {response_format!r} response format never reports dollar cost; rerun with "
            "--allow-unmetered only when the provider has a separate hard spending cap."
        )
    reported_cost = 0.0
    prior_rows = read_jsonl(args.output) if args.output.exists() else []
    fingerprint = _treatment_fingerprint(command, args.condition, args.condition_skill)
    _check_resume_is_comparable(
        prior_rows,
        args.condition,
        args.runner,
        fingerprint,
        getattr(args, "allow_legacy_resume", False),
    )
    done = completed_keys(prior_rows)
    reported_cost = sum(
        float(row.get("cost_usd") or 0)
        for row in prior_rows
        if row.get("condition") == args.condition and row.get("runner") == args.runner
    )

    if args.budget_usd <= 0 or args.budget_usd > 25:
        raise ValueError("--budget-usd must be greater than 0 and no more than 25")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    leaked_rows: list[tuple[str, int]] = []
    with args.output.open("a", encoding="utf-8") as destination:
        for trial in range(1, args.trials + 1):
            for case in cases:
                if args.case and case["id"] not in args.case:
                    continue
                key = (case["id"], trial, args.condition, args.runner)
                if key in done:
                    print(f"skip completed {args.condition} trial {trial}: {case['id']}")
                    continue
                remaining = args.budget_usd - reported_cost
                if remaining <= 0:
                    print("Budget exhausted; stopping.", file=sys.stderr)
                    return 2
                prompt = _condition_prompt(case["prompt"], args.condition, args.condition_skill)
                invocation = [*command]
                if runner.get("budget_flag"):
                    invocation.extend([runner["budget_flag"], f"{remaining:.4f}"])
                invocation.append(prompt)
                completed = None
                rerolls = 0
                for attempt in range(args.retries + 1):
                    completed = subprocess.run(
                        invocation,
                        check=False,
                        capture_output=True,
                        text=True,
                        cwd=ROOT,
                    )
                    if completed.returncode == 0:
                        if attempt >= args.retries:
                            break
                        try:
                            candidate_text, _, _ = _parse_response(
                                completed.stdout, response_format
                            )
                        except (ValueError, json.JSONDecodeError):
                            break
                        if not _leaks_tool_markup(candidate_text):
                            break
                        rerolls += 1
                        print(
                            f"re-roll {rerolls}: {case['id']} trial {trial} emitted tool markup "
                            "under a tool-less runner",
                            file=sys.stderr,
                        )
                        continue
                    if attempt < args.retries:
                        time.sleep(min(2**attempt, 5))
                assert completed is not None
                if completed.returncode:
                    detail = completed.stderr.strip() or completed.stdout.strip()
                    if completed.stdout.strip():
                        try:
                            parsed_text, _, _ = _parse_response(completed.stdout, response_format)
                            detail = parsed_text or detail
                        except (ValueError, json.JSONDecodeError):
                            pass
                    raise RuntimeError(
                        f"Runner failed after {args.retries + 1} attempts "
                        f"({shlex.join(invocation[:-1])}):\n{detail}"
                    )
                text, usage, cost = _parse_response(completed.stdout, response_format)
                leaked = _leaks_tool_markup(text)
                if cost is None and not args.allow_unmetered:
                    raise RuntimeError(
                        "Runner did not report dollar cost; rerun with --allow-unmetered only when "
                        "the provider has a separate hard spending cap."
                    )
                reported_cost += float(cost or 0)
                row = {
                    "case_id": case["id"],
                    "trial": trial,
                    "condition": args.condition,
                    "runner": args.runner,
                    "response": text,
                    "usage": usage,
                    "cost_usd": cost,
                    "tool_markup": leaked,
                    "treatment": fingerprint,
                }
                destination.write(json.dumps(row, ensure_ascii=False) + "\n")
                destination.flush()
                if leaked:
                    leaked_rows.append((case["id"], trial))
                print(f"{args.condition} trial {trial}: {case['id']}")
    print(f"Reported cost: ${reported_cost:.4f}")
    if leaked_rows:
        listing = ", ".join(f"{case_id} trial {trial}" for case_id, trial in leaked_rows)
        print(
            f"{len(leaked_rows)} row(s) leaked tool markup after every retry and are not "
            f"judgeable: {listing}. Exclude them before scoring "
            "(python3 scripts/run_evals.py leaks <output>).",
            file=sys.stderr,
        )
        return 3
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate the case catalog")
    validate.add_argument("--cases", type=Path, default=DEFAULT_CASES)

    plan = subparsers.add_parser("plan", help="Print the paired run matrix as JSONL")
    plan.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    plan.add_argument("--trials", type=int, default=3)
    plan.add_argument("--include-comparator", action="store_true")

    score = subparsers.add_parser("score", help="Aggregate manually judged score rows")
    score.add_argument("scores", type=Path)

    run = subparsers.add_parser("run", help="Run one evaluation condition")
    run.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    run.add_argument("--runner-config", type=Path, default=ROOT / "evals" / "runners.example.json")
    run.add_argument("--runner", required=True)
    run.add_argument("--condition", choices=sorted(CONDITIONS), required=True)
    run.add_argument("--condition-skill", type=Path)
    run.add_argument("--case", action="append")
    run.add_argument("--trials", type=int, default=3)
    run.add_argument("--retries", type=int, default=2)
    run.add_argument("--budget-usd", type=float, default=25.0)
    run.add_argument("--allow-unmetered", action="store_true")
    run.add_argument(
        "--allow-legacy-resume",
        action="store_true",
        help="resume into a file whose prior rows predate treatment fingerprints",
    )
    run.add_argument("--output", type=Path, required=True)
    run.set_defaults(handler=run_evaluations)

    leaks = subparsers.add_parser(
        "leaks", help="List rows that leaked tool markup and cannot be judged"
    )
    leaks.add_argument("results", type=Path)
    leaks.set_defaults(handler=list_leaks)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "handler"):
        return args.handler(args)
    if args.command == "validate":
        errors = validate_cases(load_cases(args.cases))
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("Evaluation cases are valid.")
        return 0
    if args.command == "plan":
        cases = load_cases(args.cases)
        errors = validate_cases(cases)
        if errors:
            raise ValueError("\n".join(errors))
        conditions = ["baseline", "candidate"]
        if args.include_comparator:
            conditions.append("comparator")
        for trial in range(1, args.trials + 1):
            for case in cases:
                for condition in conditions:
                    print(json.dumps({"case_id": case["id"], "trial": trial, "condition": condition}))
        return 0
    if args.command == "score":
        print(json.dumps(summarize_scores(read_jsonl(args.scores)), indent=2))
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
