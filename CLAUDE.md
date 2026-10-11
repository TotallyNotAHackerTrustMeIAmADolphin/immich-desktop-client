# Immich Desktop Client: Coordinator Context

Workflow: `docs/agents/PROJECT-IMMICH-DESKTOP-CLIENT-PLAYBOOK.md` (fork of the general
`docs/agents/AGENT-WORKFLOW-PLAYBOOK.md`). This file is the short, always-true summary; the
playbook has the reasons. Owner speaks German: reply in German, keep code, commits, PRs and
issues in English.

## What this project is

A Windows tray app (Python, tkinter, pystray, watchdog; PyInstaller + Inno Setup) that mirrors
watched folders to an Immich 3.x server. Fork of `maxdorninger/immich-desktop-client`. Map and
decision log: issue #1. Glossary: `CONTEXT.md`. Decisions: `docs/adr/`.

## Phases

Done: revival for Immich 3.x (v3.0.0), status/progress feedback (v3.1.0).
Active: #46 tray icon fallback to `resources/icon.ico`; verification of gate 3 for 3.1.0.
Next: map #1 "Not yet specified" (code signing, upstream follow-up, Guido coordination).

## Ground rules

- The coordinator never edits code; builders work in a worktree, a separate reviewer reviews.
- Never touch the owner's real profile `%USERPROFILE%\.Immich-desktop-client`, the installed exe
  or the real Immich library. Demos: separate `USERPROFILE` plus a throw-away Immich.
- The client never force-deletes, deletes only own uploads, and only to trash (ADR 0001).
- Merge only when the owner asks. Publishing a release and anything outward-facing needs a confirm.
- Commit trailers: copy the attribution lines of the session's system reminder.

## Enforcement table

| Rule | Enforced by |
|---|---|
| Unit tests pass on every PR | `.github/workflows/tests.yml` (tooling) |
| Release refuses an existing tag | `release.yml` (tooling) |
| Never force-delete, own-upload-only delete | tests; guard test still to add (tooling, partly) |
| Separate reviewer, merge on owner request, no secrets or personal config committed | instruction only |
| `master` integrity (no force-push, squash only) | instruction only; repo still allows merge/rebase merges |

## How to dispatch

Agent tool, one ticket per PR in its own worktree under
`C:\Users\ich\Documents\claude\immich-desktop-client-work\`, branch `ticket-<n>`, skill `tdd`,
hand back after about 150 turns, 1 to 3 builders on disjoint files, stacked PRs allowed.
Tests: `python -m pytest -q` from the worktree. Integration and smoke tests are coordinator gates
(`docs/releasing.md`).

| Risk class | Paths | Gates |
|---|---|---|
| docs | `README.md`, `docs/**/*.md`, `CONTEXT.md` | coordinator reads the diff |
| config/ops | `.github/`, `*.spec`, `VERSION`, `requirements*.txt`, `pytest.ini` | 1 reviewer |
| core | `src/` outside critical, `tests/` | 1 reviewer |
| critical | `src/immich.py`, `src/record.py`, delete/replace/migration paths, `src/config.py`, `src/settings.py`, `src/fatal.py`, installer script, `release.yml` | 1 reviewer with mutation tests, integration gate |

## Session duties

At session start: read the hand-off file, `gh issue list`, `gh pr list`. One question per
message. Pending owner decisions live in map #1 "Not yet specified".

## Issue tracker / labels / domain docs

GitHub Issues via `gh` (run `gh repo set-default TotallyNotAHackerTrustMeIAmADolphin/immich-desktop-client`
in a fresh clone). Triage labels and `docs/agents/issue-tracker.md` are still to be set up.
Domain docs: `CONTEXT.md`, `docs/adr/`.

## Agent skills

Plugin `mattpocock-skills`. Agent-invoked skills are named in a brief as
`Load skill: mattpocock-skills:<name>`; human-only skills (`to-spec`, `to-tickets`, `triage`,
`wayfinder`, `handoff`, `retro`, ...) are started by the owner, else written by hand and flagged.
Review is a separate agent running `code-review`. Builder: `tdd`, `codebase-design`, `prototype`,
`diagnosing-bugs`, `resolving-merge-conflicts`. Skipped: `migrate-to-shoehorn`,
`scaffold-exercises`, `setup-ts-deep-modules`. Full table: playbook section 3.

## Directory map (verified 2026-10-11)

`src/` app code (`main`, `immich`, `record`, `config`, `settings*`, `status`, `notifier`,
`progress_window`, `applog`, `fatal`, `gui_runner`, `autostart`, `single_instance`);
`tests/` unit tests, `tests/integration`, `tests/smoke`; `resources/` icon and installer script;
`docs/` releasing, code signing, ADRs, agent playbooks; `.github/workflows/` tests and release.
