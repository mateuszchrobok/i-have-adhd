"""Every eval case must carry a screen verdict.

#12 cost a day: `error-report` named a file the model could not open, responses
went bimodal, and the mode explained R²=0.844 of that case's variance while the
treatment explained 0.111. The screen records which cases have that property.
The point of this test is that a NEW case cannot be added without classifying
it — otherwise the screen rots into a snapshot of one afternoon.
"""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLASSES = {"clean", "self-contained-by-fix", "dangling-referent", "needs-tools"}


class CaseScreenTest(unittest.TestCase):
    def setUp(self):
        self.screen = json.loads((ROOT / "evals" / "case_screen.json").read_text())
        self.cases = [
            json.loads(line)
            for line in (ROOT / "evals" / "cases.jsonl").read_text().splitlines()
            if line.strip()
        ]

    def test_every_case_is_screened(self):
        screened = set(self.screen["cases"])
        actual = {case["id"] for case in self.cases}
        self.assertEqual(
            actual - screened,
            set(),
            "a case exists with no screen verdict — classify it in evals/case_screen.json",
        )
        self.assertEqual(
            screened - actual,
            set(),
            "the screen names a case that no longer exists",
        )

    def test_every_verdict_uses_a_declared_class(self):
        for case_id, verdict in self.screen["cases"].items():
            with self.subTest(case_id):
                self.assertIn(verdict["class"], CLASSES)
                self.assertIn(verdict["class"], self.screen["_classes"])
                self.assertTrue(verdict["note"].strip(), "a verdict needs its reason")

    def test_the_fixed_case_really_is_self_contained(self):
        # error-report's screen verdict claims the prompt now carries what it
        # once asked the model to go and read. Check that, rather than trust it.
        prompt = next(c["prompt"] for c in self.cases if c["id"] == "error-report")
        for evidence in ("loadConfig", "readFileSync", "app.example.json", "do not ask to open"):
            self.assertIn(evidence, prompt)

    def test_needs_tools_cases_are_not_silently_treated_as_measurable(self):
        needs_tools = {
            case_id
            for case_id, verdict in self.screen["cases"].items()
            if verdict["class"] == "needs-tools"
        }
        self.assertTrue(needs_tools, "if nothing needs tools, say so explicitly")
        readme = (ROOT / "evals" / "README.md").read_text()
        self.assertIn("case_screen.json", readme, "the screen must be discoverable from the README")


if __name__ == "__main__":
    unittest.main()
