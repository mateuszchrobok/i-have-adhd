// SessionStart hook (fork-only): one line when the effort tier is knowably
// below xhigh. Silent when settings.json already persists `ultracode`, and
// silent when the tier is simply unknown — CLAUDE_EFFORT is exported into the
// Bash tool environment but NOT into SessionStart hook processes, so treating
// its absence as "too low" printed a false alarm every session.
// Gated on the same opt-in flag as always-on.mjs. Never blocks session start.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

try {
  const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude");

  // Same opt-in as the always-on ruleset injection.
  if (!fs.existsSync(path.join(claudeDir, ".i-have-adhd-always"))) process.exit(0);

  // Persisted ultracode forces xhigh; nothing to remind about.
  let settings = {};
  try {
    settings = JSON.parse(fs.readFileSync(path.join(claudeDir, "settings.json"), "utf8"));
  } catch {}
  if (settings.ultracode === true) process.exit(0);
  if (settings.effortLevel === "xhigh") process.exit(0);

  // Only the session's own report can contradict the settings, and it is often
  // absent here. Absent means unknown, not low.
  const effort = (process.env.CLAUDE_EFFORT || "").trim();
  if (effort === "xhigh" || effort === "max") process.exit(0);

  const shown = effort || `settings.json effortLevel: ${settings.effortLevel || "unset"}`;
  process.stdout.write(
    `EFFORT NOTICE: ${shown}. Run /effort ultracode for xhigh plus dynamic workflow orchestration, or persist it with "ultracode": true in settings.json.\n`,
  );
} catch {
  // Never block session start.
  process.exit(0);
}
