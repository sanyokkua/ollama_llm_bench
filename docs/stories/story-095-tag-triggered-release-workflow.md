---
id: STORY-095
title: Add the tag-triggered release workflow that builds the three OS artifacts with SHA256SUMS under the semver policy
status: draft
spec_clauses:
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#3-cicd-overview
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#8-checksums-and-reproducibility
  - 13_Distribution_and_Release/06_VERSIONING_POLICY.md#7-version-tags-and-releases
  - 13_Distribution_and_Release/06_VERSIONING_POLICY.md#6-where-the-version-is-shown
modules:
  - ui/main_window/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-095-AC-1
  - STORY-095-AC-2
  - STORY-095-AC-3
  - STORY-095-AC-4
edge_cases: []
depends_on:
  - STORY-094
adrs:
  - ADR-0003
owner: coder
estimate: M
---

# STORY-095 — Add the tag-triggered release workflow that builds the three OS artifacts with SHA256SUMS under the semver policy

## Goal

Automate releases. Add the GitHub Actions release workflow triggered only by a pushed version tag
that re-runs the quality gate and the audit step, builds the per-OS artifacts (via STORY-094's
specs) on their native runners, generates a `SHA256SUMS` checksum file, and publishes them on the
GitHub Release for the tag. Adopt the semantic-versioning policy so the tag version, the version
embedded in the artifacts, and the version shown in the application (the About surface and the
status bar) are always the same value.

## In scope

- The `.github/workflows/release.yml` workflow triggered exclusively by a release-version tag push
  (for example `v*.*.*`), with no `schedule`, `workflow_dispatch`, or push-to-main trigger.
- The release job order: re-run lint/type-check/test, then `uv run pip-audit`, then the per-OS build
  matrix (native runner per OS), then package + checksum, then publish; a failed step cleans up so a
  release is never left half-published.
- Generating a `SHA256SUMS` file covering every published artifact.
- The semantic-versioning policy wired so the tag version equals the artifact-embedded version equals
  the version shown in the About dialog and the status bar.

## Out of scope

- The PyInstaller one-directory specs and the local artifact smoke-launch — owned by STORY-094 (this
  story's prerequisite).
- The user-facing install/first-run/uninstall documentation — owned by STORY-096.
- The PR-gate workflow (lint → type-check → test) — already established in Phase 0; this story adds
  the release-tag workflow only.

## Spec inputs

- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#3-cicd-overview` — CI is triggered by exactly
  two events; the release workflow runs on a release-version tag push, re-runs the quality gate on
  the tagged commit, then builds/packages/publishes; no other trigger is permitted (DD-36).
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#8-checksums-and-reproducibility` — every
  published artifact is accompanied by a SHA256 checksum; the `SHA256SUMS` file is the sole
  release-side integrity record; reproducible-build settings make builds tamper-evident.
- `13_Distribution_and_Release/06_VERSIONING_POLICY.md#7-version-tags-and-releases` — each release
  corresponds to a version tag; pushing it triggers the release pipeline; the tag version, the
  embedded version, and the version shown in the application are always the same value.
- `13_Distribution_and_Release/06_VERSIONING_POLICY.md#6-where-the-version-is-shown` — the installed
  version is shown in the About surface and in the main-window status bar; AC-3 asserts these equal
  the tag/artifact version.

## Design constraints

- The workflow's only triggers are `pull_request` (already present) and a release-tag `push`; adding
  a schedule, manual dispatch, or push-to-main artifact build is a defect against DD-36.
- Artifact builds happen only on a release-tag push, on each OS's native runner (macOS artifact
  arm64 only, DD-69).
- The binaries are unsigned; the `SHA256SUMS` file provides integrity, not authenticity (ADR-0003,
  D-R-11b) — there is no GPG/Ed25519 signing.

## Acceptance criteria

### STORY-095-AC-1

Given the release workflow, when it is triggered by a pushed release-version tag, then it re-runs the
quality gate and the audit step and then builds the three per-OS artifacts, and it is triggered by no
other event (no schedule, dispatch, or push-to-main).

### STORY-095-AC-2

Given a completed release build, when the artifacts are published, then a `SHA256SUMS` file
accompanies them listing the SHA256 checksum of every artifact.

### STORY-095-AC-3

For every release, the version in the pushed tag, the version embedded in the built artifacts, and
the version shown in the application's About surface and status bar are the same `MAJOR.MINOR.PATCH`
value.

### STORY-095-AC-4

Given a release step fails, when the workflow handles the failure, then the partially published
release and tag are cleaned up so a release is never left half-published.

## Test plan

- STORY-095-AC-1 — integration (workflow-config), `tests/integration/test_release_workflow.py`,
  `test_release_workflow_triggers_only_on_release_tag_and_builds_three_artifacts`.
- STORY-095-AC-2 — integration (workflow-config), same file,
  `test_release_publishes_sha256sums_for_every_artifact`.
- STORY-095-AC-3 — integration (`pytest-qt`), `tests/integration/test_version_consistency.py`,
  `test_tag_artifact_about_and_status_bar_versions_match`.
- STORY-095-AC-4 — integration (workflow-config), same file as AC-1,
  `test_failed_release_step_cleans_up_partial_release`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-095.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.

## Notes

- **Non-src deliverable.** The load-bearing work is `.github/workflows/release.yml`, outside `src/`;
  `__main__.py`/`compose.py` are not citable inventory module paths (the parser accepts only
  backtick-quoted `backend/…/`, `adapters/…/`, `ui/…/`). Following STORY-076/077's precedent for
  entry-point/compose work, the `modules:` cite the version-display surfaces the versioning policy
  names — `ui/main_window/` (status-bar version) and `ui/common_dialogs/` (About-dialog version) —
  which AC-3 asserts equal the tag/artifact version. This story is clearly M by acceptance-criterion
  count (four).
