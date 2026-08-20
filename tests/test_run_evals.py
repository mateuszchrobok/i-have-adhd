import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_evals  # noqa: E402


class EvaluationHarnessTest(unittest.TestCase):
    def test_case_catalog_is_valid_and_balanced(self):
        cases = run_evals.load_cases(ROOT / "evals" / "cases.jsonl")
        errors = run_evals.validate_cases(cases)

        self.assertEqual([], errors)
        self.assertGreaterEqual(len(cases), 12)
        self.assertGreaterEqual(len({case["category"] for case in cases}), 8)

    def test_score_summary_applies_weights_and_release_gates(self):
        scores = []
        for condition, value in (("baseline", 3), ("candidate", 4)):
            scores.append(
                {
                    "case_id": "direct-answer",
                    "trial": 1,
                    "condition": condition,
                    "correctness": value,
                    "autonomy": value,
                    "actionability": value,
                    "safety": value,
                    "concision": value,
                    "blocker": False,
                    "notes": "fixture",
                }
            )

        summary = run_evals.summarize_scores(scores)

        self.assertAlmostEqual(3.0, summary["conditions"]["baseline"]["weighted_score"])
        self.assertAlmostEqual(4.0, summary["conditions"]["candidate"]["weighted_score"])
        self.assertTrue(summary["release_gate"]["passed"])

    def test_candidate_blocker_fails_release_gate(self):
        rows = []
        for condition in ("baseline", "candidate"):
            rows.append(
                {
                    "case_id": "dangerous-action",
                    "trial": 1,
                    "condition": condition,
                    "correctness": 5,
                    "autonomy": 5,
                    "actionability": 5,
                    "safety": 5,
                    "concision": 5,
                    "blocker": condition == "candidate",
                    "notes": "fixture",
                }
            )

        summary = run_evals.summarize_scores(rows)

        self.assertFalse(summary["release_gate"]["passed"])
        self.assertIn("blocking", " ".join(summary["release_gate"]["reasons"]))

    def test_conditions_judged_on_different_cases_are_rejected(self):
        rows = [
            self._score_row("destructive-action", "baseline", 2),
            self._score_row("medical-boundary", "baseline", 2),
            self._score_row("direct-answer", "candidate", 5),
        ]

        with self.assertRaisesRegex(ValueError, "not judged on the same rows"):
            run_evals.summarize_scores(rows)

    def test_duplicate_score_rows_are_rejected(self):
        rows = [
            self._score_row("direct-answer", "baseline", 3),
            self._score_row("direct-answer", "candidate", 4),
            self._score_row("direct-answer", "candidate", 5),
        ]

        with self.assertRaisesRegex(ValueError, "duplicate score rows"):
            run_evals.summarize_scores(rows)

    @staticmethod
    def _score_row(case_id, condition, value, trial=1):
        return {
            "case_id": case_id,
            "trial": trial,
            "condition": condition,
            "correctness": value,
            "autonomy": value,
            "actionability": value,
            "safety": value,
            "concision": value,
            "blocker": False,
            "notes": "fixture",
        }

    def test_duplicate_case_ids_are_rejected(self):
        case = {
            "id": "duplicate",
            "category": "direct-answer",
            "prompt": "What is 2 + 2?",
            "risk": "low",
            "criteria": ["Answers 4."],
        }
        errors = run_evals.validate_cases([case, dict(case)])
        self.assertTrue(any("Duplicate" in error for error in errors))

    def test_jsonl_loader_reports_invalid_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text(json.dumps({"id": "ok"}) + "\nnot-json\n")
            with self.assertRaisesRegex(ValueError, "line 2"):
                run_evals.read_jsonl(path)

    def test_unmetered_runner_is_rejected_before_any_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            marker = tmp_path / "ran"
            runner_config = tmp_path / "runners.json"
            runner_config.write_text(
                json.dumps(
                    {
                        "stub": {
                            "command": [
                                sys.executable,
                                "-c",
                                f"from pathlib import Path; Path({str(marker)!r}).touch(); print('hi')",
                            ],
                            "response_format": "text",
                        }
                    }
                )
            )
            args = argparse.Namespace(
                cases=ROOT / "evals" / "cases.jsonl",
                runner_config=runner_config,
                runner="stub",
                condition="baseline",
                condition_skill=None,
                case=["direct-answer"],
                trials=1,
                retries=0,
                budget_usd=1.0,
                allow_unmetered=False,
                output=tmp_path / "out.jsonl",
            )

            with self.assertRaisesRegex(RuntimeError, "never reports dollar cost"):
                run_evals.run_evaluations(args)

            self.assertFalse(marker.exists(), "runner was invoked before the rejection")
            self.assertFalse((tmp_path / "out.jsonl").exists())

            args.allow_unmetered = True
            self.assertEqual(0, run_evals.run_evaluations(args))
            self.assertTrue(marker.exists())

    def test_tool_markup_detector_ignores_ordinary_angle_brackets(self):
        for label, text in (
            ("prose", "Build fails at build.ts:88. Fix: create config/app.json."),
            ("generics", "Use `Array<string>` when `a < b`."),
            ("html", "The tag <div> renders nothing."),
            ("comparison", "if (x <= 3 && y > 1) return;"),
        ):
            with self.subTest(label):
                self.assertFalse(run_evals._leaks_tool_markup(text))

    def test_tool_markup_detector_catches_a_leaked_call(self):
        for label, text in (
            ("invoke", 'Let me check.\n<invoke name="Bash">'),
            ("parameter", '<parameter name="command">sed -n 80,95p build.ts</parameter>'),
            ("orphan", "_calls\nfunction_calls open tag leaked"),
        ):
            with self.subTest(label):
                self.assertTrue(run_evals._leaks_tool_markup(text))

    def test_claude_json_parsing_survives_a_stray_second_document(self):
        # The CLI normally prints one JSON document but was observed printing a
        # second one, which made json.loads() on the whole buffer raise
        # "Extra data" and discard a completed call.
        result = json.dumps(
            {
                "type": "result",
                "result": " hi ",
                "usage": {"input_tokens": 5},
                "total_cost_usd": 0.01,
            }
        )
        stray = json.dumps({"type": "system", "subtype": "warning"})
        for label, payload in (
            ("single", result),
            ("stray before", stray + "\n" + result),
            ("stray after", result + "\n" + stray),
            ("duplicate", result + "\n" + result),
            ("trailing blank lines", result + "\n\n"),
            ("trailing non-JSON text", result + "\nSomething not JSON at all\n"),
            ("leading non-JSON text", "warning: noise\n" + result),
        ):
            with self.subTest(label):
                text, usage, cost = run_evals._parse_response(payload, "claude-json")
                self.assertEqual(text, "hi")
                self.assertEqual(usage, {"input_tokens": 5})
                self.assertEqual(cost, 0.01)

    def test_claude_json_parsing_rejects_empty_output(self):
        with self.assertRaises(ValueError):
            run_evals._parse_response("   ", "claude-json")

    def test_claude_json_parsing_rejects_output_with_no_json_at_all(self):
        with self.assertRaises(json.JSONDecodeError):
            run_evals._parse_response("not json, not even close", "claude-json")

    def test_fingerprint_separates_model_and_skill_changes(self):
        skill = ROOT / "skills" / "i-have-adhd" / "SKILL.md"
        base = run_evals._treatment_fingerprint(["claude", "--model", "a"], "candidate", skill)
        self.assertEqual(
            base, run_evals._treatment_fingerprint(["claude", "--model", "a"], "candidate", skill)
        )
        for label, other in (
            ("model", run_evals._treatment_fingerprint(["claude", "--model", "b"], "candidate", skill)),
            ("condition", run_evals._treatment_fingerprint(["claude", "--model", "a"], "comparator", skill)),
            ("no skill", run_evals._treatment_fingerprint(["claude", "--model", "a"], "candidate", None)),
        ):
            with self.subTest(label):
                self.assertNotEqual(base, other)

    def test_resume_refuses_a_changed_treatment(self):
        # The resume key is (case, trial, condition, runner) — it does not include
        # the model or the skill file, so without this check a changed treatment
        # silently keeps the old rows and the results file mixes two arms.
        prior = [
            {"case_id": "x", "trial": 1, "condition": "candidate", "runner": "claude", "treatment": "aaaa"}
        ]
        with self.assertRaises(RuntimeError) as caught:
            run_evals._check_resume_is_comparable(prior, "candidate", "claude", "bbbb", False)
        self.assertIn("different treatment", str(caught.exception))

    def test_resume_accepts_the_same_treatment(self):
        prior = [
            {"case_id": "x", "trial": 1, "condition": "candidate", "runner": "claude", "treatment": "aaaa"}
        ]
        run_evals._check_resume_is_comparable(prior, "candidate", "claude", "aaaa", False)

    def test_resume_ignores_other_arms(self):
        prior = [
            {"case_id": "x", "trial": 1, "condition": "comparator", "runner": "claude", "treatment": "zzzz"}
        ]
        run_evals._check_resume_is_comparable(prior, "candidate", "claude", "aaaa", False)

    def test_resume_refuses_rows_predating_fingerprints_unless_allowed(self):
        prior = [{"case_id": "x", "trial": 1, "condition": "candidate", "runner": "claude"}]
        with self.assertRaises(RuntimeError) as caught:
            run_evals._check_resume_is_comparable(prior, "candidate", "claude", "aaaa", False)
        self.assertIn("predate treatment fingerprints", str(caught.exception))
        run_evals._check_resume_is_comparable(prior, "candidate", "claude", "aaaa", True)

    def test_leaks_lists_unjudgeable_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in (
                        {"case_id": "a", "trial": 1, "condition": "candidate", "runner": "claude", "tool_markup": False},
                        {"case_id": "b", "trial": 1, "condition": "candidate", "runner": "claude", "tool_markup": True},
                    )
                )
                + "\n"
            )
            args = argparse.Namespace(results=path)
            self.assertEqual(1, run_evals.list_leaks(args))
            path.write_text(json.dumps({"case_id": "a", "tool_markup": False}) + "\n")
            self.assertEqual(0, run_evals.list_leaks(args))

    def test_completed_keys_support_resuming_partial_runs(self):
        rows = [
            {
                "case_id": "direct-answer",
                "trial": 1,
                "condition": "baseline",
                "runner": "claude",
            }
        ]

        self.assertEqual(
            {("direct-answer", 1, "baseline", "claude")},
            run_evals.completed_keys(rows),
        )


if __name__ == "__main__":
    unittest.main()
