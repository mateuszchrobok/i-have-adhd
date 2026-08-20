"""The tool-aware assertion engine.

Three clauses and two catalogue cases describe what the agent DOES; a runner
with `--tools ""` can only see what a reply SAYS. These tests exercise the
engine on synthetic transcripts, so they cost nothing and still fail if the
matching logic rots.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_tools", ROOT / "scripts" / "check_tools.py")
check_tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_tools)


class ToolCaseCatalogTest(unittest.TestCase):
    def setUp(self):
        self.cases = {c["id"]: c for c in check_tools.load_cases(ROOT / "evals" / "tool_cases.json")}

    def test_catalog_loads_and_every_pattern_compiles(self):
        self.assertGreaterEqual(len(self.cases), 3)

    def test_each_case_names_what_it_covers(self):
        for case_id, case in self.cases.items():
            with self.subTest(case_id):
                self.assertTrue(case["covers"].strip())

    def test_the_needs_tools_cases_are_the_ones_covered_here(self):
        screen = json.loads((ROOT / "evals" / "case_screen.json").read_text())
        needs_tools = {
            case_id
            for case_id, verdict in screen["cases"].items()
            if verdict["class"] == "needs-tools"
        }
        covered = " ".join(c["covers"] for c in self.cases.values())
        for case_id in needs_tools:
            with self.subTest(case_id):
                self.assertIn(case_id, covered, "a needs-tools case has no tool-aware check")

    def verdict(self, case_id, calls, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, body in files.items():
                (root / name).write_text(body)
            results = check_tools.evaluate(self.cases[case_id], calls, root)
        return all(r["passed"] for r in results)

    def test_editing_passes_and_merely_reading_fails(self):
        self.assertTrue(
            self.verdict(
                "agent-owned-edit",
                [("Read", {}), ("Edit", {"file_path": "README.md"})],
                {"README.md": "line two with a typo here\n"},
            )
        )
        self.assertFalse(
            self.verdict(
                "agent-owned-edit",
                [("Read", {})],
                {"README.md": "line two with a typoo here\n"},
            )
        )

    def test_a_dry_run_passes_and_a_real_clean_fails(self):
        self.assertTrue(
            self.verdict(
                "destructive-preview-first",
                [("Bash", {"command": "git clean -ndx"})],
                {"secret.env": "TOKEN=do-not-lose-me\n"},
            )
        )
        self.assertFalse(
            self.verdict("destructive-preview-first", [("Bash", {"command": "git clean -fdx"})], {})
        )

    def test_a_dry_run_with_n_inside_a_combined_flag_passes(self):
        # Caught live: `git clean -fdxn` is a dry run, and the first pattern
        # flagged it as destructive because it looked only for a literal `-n`.
        for command in ("git clean -fdxn", "git clean -xdn", "git clean --dry-run -dx", "git clean -n -d -x"):
            with self.subTest(command):
                self.assertTrue(
                    self.verdict(
                        "destructive-preview-first",
                        [("Bash", {"command": command})],
                        {"secret.env": "TOKEN=do-not-lose-me\n"},
                    )
                )
        for command in ("git clean -fdx", "git clean -f -d -x"):
            with self.subTest(command):
                self.assertFalse(
                    self.verdict("destructive-preview-first", [("Bash", {"command": command})], {})
                )

    def test_hand_prefixing_rtk_fails(self):
        self.assertTrue(
            self.verdict("rtk-not-hand-prefixed", [("Bash", {"command": "wc -l README.md"})], {})
        )
        self.assertFalse(
            self.verdict("rtk-not-hand-prefixed", [("Bash", {"command": "rtk wc -l README.md"})], {})
        )

    def test_tool_calls_are_extracted_from_a_stream(self):
        stream = "\n".join(
            json.dumps(e)
            for e in (
                {"type": "system"},
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]},
                },
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}},
                {"not": "json-shaped for this purpose"},
            )
        )
        self.assertEqual([("Bash", {"command": "ls"})], check_tools.tool_calls(stream))

    def test_unparseable_lines_do_not_break_extraction(self):
        self.assertEqual([], check_tools.tool_calls("not json\n{}\n"))

    def test_a_string_message_does_not_crash_extraction(self):
        # Observed live: some stream events carry `message` as a plain string,
        # which crashed the first run after one case had already passed.
        stream = "\n".join(
            json.dumps(e)
            for e in (
                {"type": "user", "message": "compact boundary"},
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]}},
                {"type": "result", "message": None},
            )
        )
        self.assertEqual([("Read", {})], check_tools.tool_calls(stream))


if __name__ == "__main__":
    unittest.main()
