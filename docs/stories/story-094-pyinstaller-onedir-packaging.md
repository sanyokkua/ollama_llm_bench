---
id: STORY-094
title: Add the per-OS PyInstaller onedir packaging specs and a local artifact smoke-launch check
status: draft
spec_clauses:
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#6-build-backend-and-packaging
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#7-per-os-artifacts
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#11-minimum-os-versions
  - 15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-011--cross-platform-packaging-drift-pyinstaller
modules:
  - backend/infra/
  - ui/main_window/
acceptance_criteria:
  - STORY-094-AC-1
  - STORY-094-AC-2
  - STORY-094-AC-3
edge_cases: []
depends_on:
  - STORY-081
adrs:
  - ADR-0003
owner: coder
estimate: M
---

# STORY-094 — Add the per-OS PyInstaller onedir packaging specs and a local artifact smoke-launch check

## Goal

Make the application buildable into a distributable desktop artifact per operating system. Add one
PyInstaller one-directory specification per OS — sharing the same Python entry point and differing
only in per-OS bundle metadata — producing a macOS arm64 `.dmg`, a Windows portable `.zip`, and a
Linux AppImage, with test code excluded from every bundle. Add a local post-build smoke-launch check
that starts the packaged artifact and exercises a minimal start/shutdown cycle, so a bundling defect
(a missing hidden import, data file, or Qt plugin) is caught before release.

## In scope

- A `packaging/` directory holding one PyInstaller `--onedir` spec per OS, all sharing the
  `__main__.py` entry point, with per-OS bundle metadata (icon, identity fields, minimum-OS
  declaration, OS-specific wrapper) and test code excluded.
- The per-OS artifact shapes: macOS one-directory app bundle → ad-hoc-signed `.dmg` (arm64 only),
  Windows one-directory folder → portable `.zip`, Linux one-directory tree → AppImage.
- A local artifact smoke-launch check that launches the built one-directory artifact and asserts a
  minimal start-then-clean-shutdown cycle.

## Out of scope

- The tag-triggered release CI workflow, SHA256SUMS generation, and the versioning policy — owned by
  STORY-095; this story produces the build specs and the local smoke check, not the release
  automation.
- The user-facing install/first-run/uninstall documentation — owned by STORY-096.
- The composition root, launch, and quit sequences the artifact runs — delivered by STORY-076..080
  and exercised headlessly by STORY-081 (this story's prerequisite).

## Spec inputs

- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#6-build-backend-and-packaging` — desktop
  binaries are built with PyInstaller one-directory mode (not single-file); one spec per OS sharing
  the entry point; test code excluded from every bundle.
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#7-per-os-artifacts` — the three artifacts:
  macOS ad-hoc-signed `.dmg` (arm64 only, DD-69), Windows portable `.zip` (no installer), Linux
  AppImage.
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#11-minimum-os-versions` — the minimum-OS
  declarations each bundle carries (macOS 11, Windows 10 1809+, glibc 2.35 Linux baseline).
- `15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-011--cross-platform-packaging-drift-pyinstaller`
  — R-011's mitigation: one spec file per OS with explicit hidden-import/data-file declarations and
  a post-build smoke test that launches the packaged artifact.

## Design constraints

- One-directory mode only; single-file mode is an anti-pattern (slow startup, per-launch temp
  extraction).
- The three specs share the `__main__.py` entry point and differ only in per-OS metadata; the
  packaged app must show the main window (`ui/main_window/`) and shut down cleanly, exactly as the
  headless smoke tier (STORY-081) proves from source.
- `packaging/` lives outside `src/`; the packaging specs are not application modules.

## Acceptance criteria

### STORY-094-AC-1

Given the `packaging/` directory, when the per-OS PyInstaller specs are present, then there is one
`--onedir` spec per operating system, all sharing the `__main__.py` entry point, each declaring its
per-OS bundle metadata and excluding test code.

### STORY-094-AC-2

Given a per-OS PyInstaller spec, when it is built, then it produces the specified artifact shape for
that OS (macOS one-directory app bundle for the `.dmg`, Windows one-directory folder for the `.zip`,
Linux one-directory tree for the AppImage).

### STORY-094-AC-3

Given a built one-directory artifact, when the local smoke-launch check runs it, then the artifact
starts, shows the main window, and shuts down cleanly.

## Test plan

- STORY-094-AC-1 — integration (build-config presence), `tests/integration/test_packaging_specs.py`,
  `test_one_onedir_spec_per_os_shares_entry_point_and_excludes_tests`.
- STORY-094-AC-2 — integration (build, local/on-demand), `tests/integration/test_packaging_build.py`,
  `test_spec_produces_expected_onedir_artifact_for_host_os`.
- STORY-094-AC-3 — integration (packaged-artifact smoke, local/on-demand),
  `tests/integration/test_packaged_artifact_smoke.py`,
  `test_packaged_artifact_launches_and_shuts_down_cleanly`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-094.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.

## Notes

- **Non-src deliverable.** The load-bearing work is the `packaging/*.spec` files outside `src/`; the
  `__main__.py`/`compose.py` composition-root files are not citable module paths in the inventory
  (the module-inventory parser only accepts backtick-quoted `backend/…/`, `adapters/…/`, `ui/…/`
  paths — which is why STORY-076/077 cited feature modules for their entry-point/compose work). This
  story follows that precedent: `modules:` cite `backend/infra/` (the launch/entry-point
  infrastructure the bundle runs, as STORY-076 did) and `ui/main_window/` (the window the
  smoke-launch check asserts appears). `pyinstaller` is already declared as a build dependency in
  `pyproject.toml`.
