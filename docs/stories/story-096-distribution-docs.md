---
id: STORY-096
title: Write the user-facing install, first-run, unsigned-distribution, and uninstall documentation
status: draft
spec_clauses:
  - 13_Distribution_and_Release/02_INSTALLATION.md#1-where-to-download
  - 13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md#6-the-first-run-sequence
  - 13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#1-why-a-security-warning-appears
  - 13_Distribution_and_Release/08_UNINSTALL.md#1-what-a-complete-uninstall-removes
modules:
  - backend/platform/
acceptance_criteria:
  - STORY-096-AC-1
  - STORY-096-AC-2
  - STORY-096-AC-3
edge_cases: []
depends_on:
  - STORY-094
adrs:
  - ADR-0003
owner: coder
estimate: S
---

# STORY-096 — Write the user-facing install, first-run, unsigned-distribution, and uninstall documentation

## Goal

Ship the end-user distribution documentation. Provide a per-OS install guide (with the SHA256
verification steps), a first-run description (the silent data-directory creation, no setup wizard),
unsigned-distribution guidance (the macOS Gatekeeper / Windows SmartScreen unblock steps and the
Linux execute-permission step), and uninstall instructions (including deliberately removing the
application data directory). These follow the already-written spec distribution folder, adapted for
the repository's own docs tree.

## In scope

- An install guide covering macOS, Windows, and Linux, including where to download, the per-OS
  install steps, and how to verify a download against `SHA256SUMS`.
- A first-run description: no setup wizard, the main window opens directly, and the application
  silently creates its per-user data directory on first launch.
- Unsigned-distribution guidance: why the security prompt appears and the exact unblock steps per OS
  (macOS Gatekeeper "Open Anyway", Windows SmartScreen "More info → Run anyway", Linux execute
  permission).
- Uninstall instructions per OS, including how to deliberately remove the application data directory
  (which survives an app removal by design).

## Out of scope

- The PyInstaller specs and the release workflow — owned by STORY-094 and STORY-095.
- Any change to the vendored `13_Distribution_and_Release/` spec — this story adapts its content into
  the repository's user-facing docs, it does not edit the spec.

## Spec inputs

- `13_Distribution_and_Release/02_INSTALLATION.md#1-where-to-download` — the per-OS artifact names,
  the GitHub Releases source, and (Section 2) the SHA256 verification commands the install guide
  reproduces.
- `13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md#6-the-first-run-sequence` — the first-run
  sequence: no setup wizard, the main window opens directly, and the data directory plus default
  settings are created silently.
- `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#1-why-a-security-warning-appears` — why
  each OS shows a security warning for unsigned binaries, and (Sections 2–4) the per-OS unblock
  steps the guidance restates.
- `13_Distribution_and_Release/08_UNINSTALL.md#1-what-a-complete-uninstall-removes` — what a complete
  uninstall removes, including the application data directory that an app removal leaves behind by
  design.

## Design constraints

- The docs follow the repository-documentation writing standards (imperative mood, real per-OS
  commands and paths, tables for structured per-OS data) and cite ADR-0003's unsigned-distribution
  decision rather than restating its rationale.
- The install/first-run/uninstall content matches the data-directory locations resolved by
  `backend/platform/` (the module whose OS-appropriate application-data paths these docs describe).

## Acceptance criteria

### STORY-096-AC-1

Given the install documentation, when a user reads it, then it provides per-OS download and install
steps for macOS, Windows, and Linux and the SHA256 verification command for each.

### STORY-096-AC-2

Given the first-run and unsigned-distribution documentation, when a user reads it, then it describes
the silent first-run data-directory creation with no setup wizard and gives the per-OS security-prompt
unblock steps (macOS Gatekeeper, Windows SmartScreen, Linux execute permission).

### STORY-096-AC-3

Given the uninstall documentation, when a user reads it, then it gives the per-OS uninstall steps and
how to deliberately remove the application data directory that an app removal leaves behind.

## Test plan

- STORY-096-AC-1 — integration (docs content-presence), `tests/integration/test_distribution_docs.py`,
  `test_install_guide_covers_three_os_and_checksum_verification`.
- STORY-096-AC-2 — integration (docs content-presence), same file,
  `test_first_run_and_unsigned_unblock_steps_documented`.
- STORY-096-AC-3 — integration (docs content-presence), same file,
  `test_uninstall_and_data_directory_removal_documented`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-096.
- [ ] The distribution docs exist under the repository docs tree and cover all three operating
  systems.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.

## Notes

- **Docs-only deliverable.** The work is user-facing Markdown under the repository docs tree.
  Following the requirement that every story cite a real inventory module, the `modules:` cite
  `backend/platform/` — the module that resolves the OS-appropriate application-data directory these
  install/first-run/uninstall docs describe (where the app stores data and what a complete uninstall
  removes). Reported to the architect run as a deviation: a purely documentation story has no natural
  source module.
