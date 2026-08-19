// SessionStart hook (fork-only): one line when the session's effort tier is below
// xhigh, so a persisted `ultracode` that the model or gateway refused is visible
// instead of silent. Silent — zero tokens — when the tier is already xhigh/max.
// Gated on the same opt-in flag as always-on.mjs. Never blocks session start.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

try {
  const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude");

  // Same opt-in as the always-on ruleset injection.
  if (!fs.existsSync(path.join(claudeDir, ".i-have-adhd-always"))) process.exit(0);

  const effort = (process.env.CLAUDE_EFFORT || "").trim();
  if (effort === "xhigh" || effort === "max") process.exit(0);

  // Did the user ask for ultracode persistently? Absent or unreadable settings => no.
  let persisted = false;
  try {
    persisted =
      JSON.parse(fs.readFileSync(path.join(claudeDir, "settings.json"), "utf8")).ultracode === true;
  } catch {}

  const shown = effort || "unset";
  process.stdout.write(
    persisted
      ? `EFFORT NOTICE: settings.json asks for ultracode but this session runs at "${shown}" — the model or gateway refused xhigh. Run /effort ultracode, or scale the plan to this tier.\n`
      : `EFFORT NOTICE: this session runs at "${shown}". Run /effort ultracode for xhigh plus dynamic workflow orchestration, or persist it with "ultracode": true in settings.json.\n`,
  );
} catch {
  // Never block session start.
  process.exit(0);
}
