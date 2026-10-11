# Project Playbook: Immich Desktop Client

Fork of [`AGENT-WORKFLOW-PLAYBOOK.md`](AGENT-WORKFLOW-PLAYBOOK.md) (the general playbook, next to
this file). This file holds only this project's answers (P1-P17), values, project-only rules and
incident evidence. It cites the general file by section and copies nothing; where they disagree on
a general rule the general file wins, on project values this file wins.

Project: a Windows tray app that mirrors watched folders to an Immich 3.x server
(`TotallyNotAHackerTrustMeIAmADolphin/immich-desktop-client`, branch `master`). One owner, no
production deployment. Map of record: issue #1.

## Section 0: answers P1-P17

> **Project rule P1: Human-only steps and owner approvals.** Logins and credentials (GitHub,
> Immich API key); publishing a release (the *Build release (draft)* workflow only creates a
> draft); anything that stops or replaces the owner's installed app or touches their real profile;
> the on-screen parts of release gate 3 (installer, tray menu, Tk dialogs, a real toast); code
> signing. **Merging is owner-initiated** (see P15).

> **Project rule P2: What no agent may touch by hand.** The real profile
> `%USERPROFILE%\.Immich-desktop-client` (`config.yaml`, `record.sqlite`, `icon.ico`); the installed
> exe and autostart entry `C:\Users\ich\.immich-desktop-client\immich-desktop-client.exe`; the real
> Immich library; the machine-wide single-instance port 47862 while the installed app runs; the
> remotes `upstream`, `guido`, `tkalfaoglu` (read-only reference, never merge their history). Demos
> and tests use a separate `USERPROFILE`/`HOME` and a throw-away Immich in Docker.

> **Project rule P3: Issue tracker, CLI, labels.** GitHub Issues via `gh` on
> `TotallyNotAHackerTrustMeIAmADolphin/immich-desktop-client` (`gh repo set-default` first in a
> fresh clone, else it targets upstream). Roadmap: issue #1. Labels: only `wontfix` exists of the
> default set; `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` are still to
> create (outward-facing, owner says go). `docs/agents/issue-tracker.md` and `triage-labels.md` are
> still to write via `setup-matt-pocock-skills`.

> **Project rule P4: Deploy window, command, verification.** No deployment; a release instead.
> Gates of `docs/releasing.md` (unit tests; integration tests against a disposable Immich 3.1;
> smoke test on Windows 11), then `VERSION` bump by PR, run *Build release (draft)*, check the
> draft, owner publishes. Rollback is a new patch release from the previous good sha. `ship.sh` and
> the deploy log of section 6 apply to releases only and are not written (not needed at this size).

> **Project rule P5: Parallelism, builder model, turn cap.** 1 to 3 builders on disjoint `Files:`
> lists; builder `sonnet`, `maxTurns: 150`; reviewer `opus`. Stacked PRs are allowed (owner's
> style; section 8, item 9 gives the mechanics).

> **Project rule P6: Test, lint, environment commands.** From the worktree
> `python -m pytest -q` (`pytest.ini`: `pythonpath = src`, `testpaths = tests`), targeted
> `python -m pytest -q tests/test_<area>.py`. No linter yet. Guard tests: none yet (first
> candidate: nothing may send `force` to `DELETE /assets`, ADR 0001). Integration
> (`IMMICH_TEST_URL=... python -m pytest tests/integration`) and smoke
> (`python tests/smoke/run_smoke.py`) are coordinator gates. One shared dependency environment
> (`pip install -r requirements-dev.txt`). Worktrees in
> `C:\Users\ich\Documents\claude\immich-desktop-client-work\work\`, review exports in `...\rev<p>`.

> **Project rule P7: Risk classes and top-class paths.** docs: `README.md`, `docs/**/*.md`,
> `CONTEXT.md`. config/ops: `.github/`, `*.spec`, `resources/installer-script.iss`, `VERSION`,
> `requirements*.txt`, `pytest.ini`, `.claude/agents/`. core: `src/` outside critical, `tests/`.
> critical: `src/immich.py`, `src/record.py`, delete/replace/migration paths, `src/config.py`,
> `src/settings.py`, `src/fatal.py`, the installer script, `.github/workflows/release.yml`.

> **Project rule P8: Enforcement table.** Tooling: unit tests on every PR
> (`.github/workflows/tests.yml`); release refuses an existing tag (`release.yml`). Instruction
> only: separate reviewer, merge on owner request, no secrets or personal config committed,
> squash-only merging, `master` integrity, never-force-delete (test coverage exists, guard test to
> add). Move a rule into tooling the first time it fails in prose. The table itself lives in
> `CLAUDE.md`.

> **Project rule P9: Domain invariants, irreversible paths.** The irreversible path is deleting
> from the owner's Immich library. Invariants (`CONTEXT.md`, ADR 0001): never force-delete (trash
> only); only an own upload is delete-eligible; a duplicate is never an own upload; an unreachable
> or empty watched root is skipped; a server below 3.0.0 is refused. Safe default: live delete and
> catch-up delete are separate off-by-default toggles. Weakening any of this needs the owner's
> explicit approval and a new ADR.

> **Project rule P10: Resource thresholds.** Default (95% of the 5-hour window, stop at 95%
> weekly), clean up above about 85% disk. No `nice` on Windows; one gate (integration or smoke) at
> a time; Docker torn down with `docker compose down -v`.

> **Project rule P11: Full-suite command, known reds.** `python -m pytest -q` on `master`'s merge
> commit, run by the coordinator once per release batch (baseline at 3.1.1: 150 passed, 4 skipped).
> Known-red list: empty (skips are not reds). A9 is not written; the suite is one command.

> **Project rule P12: Branch, PR, merge conventions.** `ticket-<n>` branches (`release-<v>` for
> version bumps), squash, `--body-file`, one closing keyword per issue, title `<title> (#N)`.
> English commits and PRs, no secrets. Trailers copied from the session's attribution block
> (`Co-Authored-By` + `Claude-Session` on commits; the "Generated with Claude Code" footer on
> PRs); `Co-authored-by` Guido only on commits re-implementing his features.

> **Project rule P13: Rules, glossary, memory files.** Rules: `CLAUDE.md`. Glossary: `CONTEXT.md`
> (not `GLOSSARY.md`: it exists and the `domain-modeling` skill writes it). Decisions: `docs/adr/`
> and map #1. History: issues and PRs (no `HISTORY.md` until `CLAUDE.md` grows). Memory: the
> project's Claude Code memory directory.

> **Project rule P14: Alert and monitoring duties.** No alerts log or digest. Session start: the
> hand-off file, `gh issue list`, `gh pr list`. After a release: user reports and
> maxdorninger/immich-desktop-client#5; a regression means a patch release (`docs/releasing.md`).

> **Project rule P15: Owner time zone, channel, decision list.** Europe/Berlin; replies in German,
> code, commits and issues in English; the session is the channel (no push). Pending decisions:
> "Not yet specified" in map #1 (code signing/SmartScreen, upstream follow-up, Guido). **Merging is
> not pre-authorised** (overrides the default): merge only when the owner says so. Outward-facing
> actions (publishing, creating labels, closing the owner's app) need a confirm.

> **Project rule P16: Plugin version; extra and optional skills.** mattpocock-skills **1.2.3**.
> Added: `wayfinder` is in use for map #1 (human-only; its `wayfinder:*` labels stay beside the
> triage labels). `git-guardrails-claude-code` is required and **not yet installed** (section 12 of
> the general file). The general table lists a `pr` skill that 1.2.3 does not ship: builders shape
> PR bodies by A6 alone until it appears.

> **Project rule P17: Human-only skill needed while the owner is away.** Default: by hand from the
> templates, flagged, never blocking. Releasing and merging are not artifacts and stay with the owner.

## Values by section

**Section 5 (reviewer model and stance).** Builder and reviewer are the same model family
(Claude); the blind-spot risk is accepted for this size of project, and mutation tests are the
check that does not depend on the reviewer's judgement. A one-line config/ops diff (for example a
`VERSION` bump) is read by the coordinator instead of a reviewer; say so in the PR.

**Section 8 (git).** Repo merge settings today: merge commits and rebase merging still allowed,
head-branch auto-delete off. `master` has no ruleset recorded ("`main` integrity: instruction
only"); no pre-push hook yet. Branches of merged PRs are deleted by hand.

**Section 12 (bootstrap), status as of 2026-10-11.** Done: playbooks, `CLAUDE.md`,
`.claude/agents/` definitions. To do, in this order: label set and `docs/agents/`, squash-only
settings, `git-guardrails-claude-code`, pre-push hook, linter, first guard test, `permissions.deny`
for the real profile paths.

## Project-only rules and evidence

- **Windows shell.** Shells are PowerShell and Git Bash. `land.sh`, `ship.sh` and A9 are not
  written; landing is `gh pr merge --squash --match-head-commit` by hand. `nice`, `timeout` and
  tmpfs rules of section 7 do not apply; use the tool timeout. *Evidence:* heredocs through the
  Bash tool collapse `\\` to `\` and broke Python test files holding Windows paths; write such
  files with the file tool or use forward slashes.
- **Command chains.** A failed `&&` chain does not stop a following separate command. *Evidence:*
  PR #44 was once created from the wrong branch (closed). Verify the branch before `gh pr create`;
  give absolute paths to background tasks (a `cd` in the same call as a restart did not take effect).
- **Single-instance lock.** The installed app and a source run share port 47862: quit one before
  starting the other, and never kill the owner's app without asking.
- **Real profile.** Never run a throw-away Immich under the real profile. *Evidence:* uploads were
  once written into the real `record.sqlite`. Copy `resources/icon.ico` into a demo profile.
- **Smoke test.** Needs Docker Desktop with Postgres in a named volume (fixed in PR #45), the
  installed app quit, and `IMMICH_DESKTOP_CLIENT_NO_DIALOGS=1` (else fatal-error windows block exit).
- **Tk.** Tk windows run only on the GUI thread via `GuiRunner`; the progress window polls a
  `Status` snapshot with `after()`. Builders touching UI say in the report that they could not
  verify it on screen (gate 3 stays with the owner).
- **5xx counts as unreachable** in `Status` after the retries; tests wanting a plain failed file
  use a 400.
