"""Fork-only guards: the personal working agreement and the effort notice.

These protect deltas that `cmp` and `claude plugin validate` cannot see: a bad
upstream-merge resolution that drops the fork block, a rule renumbering that
falsifies the "10 rules" claim in six documents, and an effort hook that stops
failing open.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "i-have-adhd" / "SKILL.md"
MIRROR = ROOT / ".cursor" / "skills" / "i-have-adhd" / "SKILL.md"
SENTINEL = "<!-- fork-only: personal working agreement. Do not upstream. -->"
CLAUSES = (
    "## Working agreement",
    "### Address the reader directly",
    "### Shell goes through rtk",
    "### Parallelism and model tier",
    "### Resume, do not restart",
    "### Monitored numbers get a scheduled check",
    "### Findings become issues",
)


class WorkingAgreementTest(unittest.TestCase):
    def test_fork_block_survives_in_canonical_skill(self):
        body = SKILL.read_text(encoding="utf-8")
        self.assertIn(SENTINEL, body)
        for clause in CLAUSES:
            self.assertIn(clause, body, f"missing clause: {clause}")

    def test_mirror_is_byte_identical(self):
        self.assertEqual(SKILL.read_bytes(), MIRROR.read_bytes())

    def test_numbered_rules_still_stop_at_ten(self):
        # README.md and five translations claim "10 rules"; an 11th numbered
        # heading would falsify all six.
        body = SKILL.read_text(encoding="utf-8")
        self.assertIn("### 10. ", body)
        self.assertNotIn("### 11.", body)

    def test_polish_honorifics_are_named(self):
        body = SKILL.read_text(encoding="utf-8")
        for form in ("Pan", "Pani", "Pana", "Panu", "Panem"):
            self.assertIn(f"`{form}`", body)


class EffortNoticeHookTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_dir = Path(self.temp_dir.name) / "claude config"
        self.config_dir.mkdir()
        self.hook = ROOT / "hooks" / "effort-notice.mjs"

    def run_hook(self, effort=None, flag=True, settings=None, config_dir=None):
        if flag:
            (self.config_dir / ".i-have-adhd-always").touch()
        if settings is not None:
            (self.config_dir / "settings.json").write_text(json.dumps(settings))
        env = os.environ.copy()
        env["CLAUDE_CONFIG_DIR"] = str(config_dir or self.config_dir)
        env.pop("CLAUDE_EFFORT", None)
        if effort is not None:
            env["CLAUDE_EFFORT"] = effort
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        return subprocess.run(
            [node, str(self.hook)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_silent_when_settings_persist_ultracode(self):
        # Regression: CLAUDE_EFFORT is exported into the Bash tool environment
        # but NOT into SessionStart hook processes. Treating its absence as
        # "below xhigh" printed a false alarm on every session start.
        for effort in (None, "high", "medium"):
            with self.subTest(effort=effort):
                result = self.run_hook(effort=effort, settings={"ultracode": True})
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_xhigh_alone_still_earns_a_nudge(self):
        # effortLevel "xhigh" raises effort but does NOT turn on the standing
        # dynamic-workflow orchestration; only `ultracode: true` does. So this
        # config falls through to the notice on purpose.
        result = self.run_hook(effort=None, settings={"effortLevel": "xhigh"})
        self.assertIn("EFFORT NOTICE", result.stdout)
        self.assertIn("/effort status", result.stdout)

    def test_silent_at_top_tiers_reported_by_the_session(self):
        for effort in ("xhigh", "max"):
            with self.subTest(effort=effort):
                result = self.run_hook(effort=effort, settings={"effortLevel": "high"})
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "", f"expected silence at {effort}")

    def test_one_line_when_settings_ask_for_less(self):
        result = self.run_hook(effort=None, settings={"effortLevel": "high"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.strip().splitlines()), 1)
        self.assertIn("EFFORT NOTICE", result.stdout)
        self.assertIn("high", result.stdout)

    def test_names_the_session_tier_when_the_session_reports_one(self):
        result = self.run_hook(effort="medium", settings={})
        self.assertIn("EFFORT NOTICE: medium", result.stdout)

    def test_silent_without_the_opt_in_flag(self):
        result = self.run_hook(effort="low", flag=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_fails_open_on_a_missing_config_dir(self):
        result = self.run_hook(effort="low", config_dir=Path("/nonexistent-claude-dir"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_unreadable_settings_do_not_break_the_notice(self):
        (self.config_dir / "settings.json").write_text("{ not json")
        result = self.run_hook(effort="medium")
        self.assertEqual(result.returncode, 0)
        self.assertIn("EFFORT NOTICE", result.stdout)


class ShippedClaimsTest(unittest.TestCase):
    """Guards the claims that went stale once before, silently."""

    def injected_ruleset(self):
        # What hooks/always-on.mjs injects, minus its header line: the header
        # embeds the flag path, so its length is machine-dependent and cannot be
        # claimed in a document.
        body = re.sub(
            r"^---[^\S\r\n]*\r?\n[\s\S]*?\r?\n---[^\S\r\n]*(?:\r?\n|$)",
            "",
            SKILL.read_text(encoding="utf-8"),
        )
        return re.sub(r"(?:\r?\n)+$", "", body)

    def test_working_agreement_sits_above_the_pre_send_check(self):
        # What PR #7 bought, and what nothing guarded until now: at end of file,
        # after "If yes, send.", the same bytes measured 0.98 weighted points worse.
        body = SKILL.read_text(encoding="utf-8")
        self.assertLess(
            body.index("## Working agreement"),
            body.index("## Pre-send check"),
            "the working agreement must stay above the pre-send check",
        )

    def test_the_six_versioned_manifests_agree(self):
        manifests = [
            "package.json",
            "qwen-extension.json",
            "gemini-extension.json",
            "kimi.plugin.json",
            ".claude-plugin/plugin.json",
            ".codex-plugin/plugin.json",
        ]
        versions = {
            name: json.loads((ROOT / name).read_text())["version"] for name in manifests
        }
        self.assertEqual(
            len(set(versions.values())), 1, f"manifest versions disagree: {versions}"
        )

    def test_readme_states_the_real_injected_size(self):
        injected = self.injected_ruleset()
        claim = re.search(
            r"(\d+) lines / ~([\d.]+)k characters", (ROOT / "README.md").read_text()
        )
        self.assertIsNotNone(claim, "README no longer states the injected size")
        self.assertEqual(
            int(claim.group(1)),
            injected.count("\n") + 1,
            "README line count is stale",
        )
        self.assertAlmostEqual(
            float(claim.group(2)),
            len(injected) / 1000,
            delta=0.15,
            msg="README character count is stale",
        )


class HookRegistrationTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        self.entries = self.config["hooks"]["SessionStart"]

    def test_always_on_stays_first(self):
        # tests/test_always_on_hooks.py reads SessionStart[0]; keep it there.
        self.assertIn("always-on.mjs", self.entries[0]["hooks"][0]["command"])
        self.assertEqual(self.entries[0]["matcher"], "startup|resume|clear|compact")

    def test_effort_notice_is_registered_for_startup_and_resume(self):
        matches = [
            entry
            for entry in self.entries
            if "effort-notice.mjs" in entry["hooks"][0]["command"]
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["matcher"], "startup|resume")
        self.assertLessEqual(matches[0]["hooks"][0]["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
