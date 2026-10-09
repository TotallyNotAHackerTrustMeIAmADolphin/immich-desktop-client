# Code signing

Releases are unsigned today, so Windows SmartScreen warns on first run (see the README). The plan is to apply for free
signing for open-source projects from the [SignPath Foundation](https://signpath.org/). This file is the checklist and
the draft policy text. **Nothing here is in effect until SignPath has accepted the project.**

## Where the project stands against SignPath's conditions

| Condition | Status |
|---|---|
| OSI-approved license, no dual licensing | GPLv3 |
| No proprietary components | Dependencies are all open source |
| Built from source in CI | `.github/workflows/release.yml` (GitHub-hosted runner) |
| Product name and version in signed binaries | exe via `immich-desktop-client.spec`, installer via `installer-script.iss`, both from `VERSION` |
| Uninstall for every install method | Inno Setup uninstaller |
| Privacy | The app talks only to the Immich server the user configured; no telemetry |
| Announce system changes | *Start with Windows* writes a per-user Run key, only when the user switches it on |
| Already released in the form to be signed | **Open**: publish one unsigned release first |
| Project reputation | **Open**: a young fork with no stars yet; accepted at SignPath's discretion |
| Own project / own repository | **Open**: this is a fork of `maxdorninger/immich-desktop-client`; mention it in the application |
| MFA for all team members on GitHub and SignPath | **Open**: owner action |
| Roles: authors, reviewers, approvers | **Open**: fill in below |
| "Code signing policy" section on home and download page | Draft below; add to the README only after acceptance |

## Steps only the owner can do

1. Publish an unsigned release (run the *Build release (draft)* workflow, then publish the draft).
2. Turn on MFA for the GitHub account and for SignPath.
3. Apply at <https://signpath.org/apply> as the project owner, naming the upstream and the fork relationship.
4. After acceptance: add the SignPath GitHub Action to `release.yml` with the organization and project identifiers
   SignPath assigns, and add the policy section below to the README.

## Draft: policy section for the README (use after acceptance)

> ### Code signing policy
>
> Free code signing provided by [SignPath.io](https://signpath.io), certificate by
> [SignPath Foundation](https://signpath.org/).
>
> - Authors / committers: *<GitHub handle(s)>*
> - Reviewers: *<GitHub handle(s)>*
> - Approvers (approve every signing request): *<GitHub handle(s)>*
>
> **Privacy policy:** this program does not collect or transmit data to anyone except the Immich server you configure.
> It uploads the media files from the folders you choose to that server, and nothing else.
