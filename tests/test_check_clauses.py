"""The clause assertion engine — the instrument that can see what the rubric cannot."""

import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_clauses", ROOT / "scripts" / "check_clauses.py")
check_clauses = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_clauses)


class ClauseCatalogTest(unittest.TestCase):
    def setUp(self):
        self.clauses = {c["id"]: c for c in check_clauses.load_clauses(ROOT / "evals" / "clauses.jsonl")}

    def test_catalog_loads_and_every_pattern_compiles(self):
        self.assertGreaterEqual(len(self.clauses), 3)
        for clause in self.clauses.values():
            self.assertTrue(clause["assertions"])
            for assertion in clause["assertions"]:
                check_clauses.compile_pattern(assertion)

    def test_every_clause_names_a_working_agreement_section(self):
        skill = (ROOT / "skills" / "i-have-adhd" / "SKILL.md").read_text(encoding="utf-8")
        for clause in self.clauses.values():
            self.assertIn(clause["clause"], skill, f"{clause['id']} names a section that does not exist")

    def passes(self, clause_id, text):
        return all(r["passed"] for r in check_clauses.evaluate(text, self.clauses[clause_id]["assertions"]))

    def test_polish_address_separates_informal_from_honorific(self):
        self.assertTrue(self.passes("polish-address", "Zacznij od logów: sprawdź, czy kontener nie umiera na braku zmiennej."))
        self.assertFalse(self.passes("polish-address", "Proszę Pana, radzę sprawdzić logi kontenera."))
        self.assertFalse(self.passes("polish-address", "Start with the container logs and check the exit code."))

    def test_scheduled_check_requires_interval_condition_and_teardown(self):
        self.assertTrue(self.passes("scheduled-check", "Cron every 10 minutes asserting p95 under 400 ms; remove it with `crontab -e`."))
        self.assertFalse(self.passes("scheduled-check", "I'll watch p95 and tell you if it goes above 400 ms. Remove any time."))

    def test_finding_to_issue_requires_tracker_gap_and_decider(self):
        self.assertTrue(self.passes(
            "finding-to-issue",
            "Filed as an issue: the retry helper double-counts. I did not check whether the dashboard dedupes; a unit test on the counter settles it.",
        ))
        self.assertFalse(self.passes("finding-to-issue", "Noted, I'll keep it in mind."))

    def test_unknown_flag_is_rejected(self):
        with self.assertRaises(ValueError):
            check_clauses.compile_pattern({"pattern": "x", "flags": "z"})

    def test_must_not_match_inverts_the_result(self):
        assertion = {"kind": "must_not_match", "pattern": "forbidden", "flags": "", "description": "no forbidden word"}
        self.assertTrue(check_clauses.evaluate("all clear", [assertion])[0]["passed"])
        self.assertFalse(check_clauses.evaluate("this is forbidden", [assertion])[0]["passed"])


class FailUnderTest(unittest.TestCase):
    """A recurring check must fail on collapse, not on sampling noise."""

    def test_guard_uses_the_total_loss_threshold(self):
        body = (ROOT / "scripts" / "clause_guard.sh").read_text()
        self.assertIn("--fail-under 1", body)

    def test_flag_is_documented_as_defaulting_to_any_miss(self):
        body = (ROOT / "scripts" / "check_clauses.py").read_text()
        self.assertIn('"--fail-under"', body)
        self.assertIn("default is to fail on any miss", body)


class ClauseGuardScriptTest(unittest.TestCase):
    """The weekly guard spends model calls, so its refusal paths must be exact."""

    def setUp(self):
        self.script = ROOT / "scripts" / "clause_guard.sh"
        self.sh = shutil.which("sh")
        if not self.sh:
            self.skipTest("sh not available")

    def run_guard(self, base_url=None):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(Path.home())}
        if base_url is not None:
            env["ANTHROPIC_BASE_URL"] = base_url
        return subprocess.run(
            [self.sh, str(self.script)], check=False, capture_output=True, text=True, env=env
        )

    def test_refuses_without_a_gateway_url(self):
        # --setting-sources "" stops the CLI reading settings.json, so its env
        # block cannot supply this; inheriting a stale shell value is the bug.
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn("ANTHROPIC_BASE_URL is unset", result.stdout)

    def test_skips_without_spending_calls_when_the_gateway_is_down(self):
        result = self.run_guard("http://127.0.0.1:9")
        self.assertEqual(result.returncode, 0)
        self.assertIn("SKIP", result.stdout)

    def test_does_not_depend_on_the_scheduler_providing_USER(self):
        # The CLI fails immediately with USER unset (is_error, zero tokens, no
        # API call), and cron hands over a minimal environment.
        for script in ("clause_guard.sh", "fork_guard.sh"):
            with self.subTest(script):
                body = (ROOT / "scripts" / script).read_text()
                self.assertIn('USER="${USER:-$(id -un)}"', body)
                self.assertIn("export USER", body)

    def test_points_at_the_assertion_first_on_failure(self):
        body = self.script.read_text()
        self.assertIn("Suspect the assertion before the skill", body)


if __name__ == "__main__":
    unittest.main()
