# History: evidence and superseded values

Why rules in `CLAUDE.md` exist. Newest first.

## 2026-11-06: playbook moved from a copy to the `docs/playbook` submodule

Before: `docs/playbook/` held a copy of `AGENT-WORKFLOW-PLAYBOOK.md` (2026-10-11) and a fork
`PROJECT-IMMICH-DESKTOP-CLIENT-PLAYBOOK.md`; `.claude/agents/` held copies of builder, reviewer and
researcher. Now: submodule of `agent-playbook`, project answers (P1-P17) in `CLAUDE.md`, agents from
the `playbook` plugin. Superseded values: `maxTurns: 150` now comes from the plugin; builder model
`sonnet` moved into `.claude/settings.json`. Section 12 status of 2026-10-11: playbooks, `CLAUDE.md`
and agent definitions done; to do in order: labels and `docs/agents/`, squash-only merge settings,
`git-guardrails-claude-code`, pre-push hook, linter, first guard test, `permissions.deny` for the
real profile paths. Repo merge settings then: merge commits and rebase still allowed, head-branch
auto-delete off, `master` without ruleset; merged branches are deleted by hand.

## Incidents behind project rules

- **Windows shell.** Heredocs through the Bash tool collapse `\\` to `\` and broke Python test files
  holding Windows paths. Write such files with the file tool or use forward slashes.
- **Command chains.** A failed `&&` chain does not stop a following separate command. PR #44 was
  once created from the wrong branch (closed); a `cd` in the same call as a restart did not take effect.
- **Real profile.** Uploads were once written into the real `record.sqlite` by a throw-away Immich
  run under the real profile.
- **Smoke test.** Postgres needed a named volume (fixed in PR #45).
