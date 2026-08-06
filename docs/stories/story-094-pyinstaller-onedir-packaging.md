---
id: STORY-094
title: Add the per-OS PyInstaller onedir packaging specs and an opt-in packaged-artifact smoke-launch tier
status: ready
spec_clauses:
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#6-build-backend-and-packaging
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#7-per-os-artifacts
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#11-minimum-os-versions
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#13-anti-patterns
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#3-test-layout
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment
  - 15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-011--cross-platform-packaging-drift-pyinstaller
modules:
  - backend/infra/
  - ui/main_window/
acceptance_criteria:
  - STORY-094-AC-1
  - STORY-094-AC-2
  - STORY-094-AC-3
  - STORY-094-AC-4
  - STORY-094-AC-5
edge_cases: []
depends_on:
  - STORY-081
adrs:
  - ADR-0003
owner: coder
estimate: M
---

# STORY-094 — Add the per-OS PyInstaller onedir packaging specs and an opt-in packaged-artifact smoke-launch tier

## Goal

Make the application buildable into a distributable desktop artifact per operating system. Add one
PyInstaller one-directory specification per OS — sharing the same Python entry point and differing
only in per-OS bundle metadata — producing the inputs for a macOS arm64 `.dmg`, a Windows portable
`.zip`, and a Linux AppImage, with test code excluded from every bundle. Add a smoke-launch check
that starts the packaged artifact and exercises a minimal start/shutdown cycle, so a bundling defect
(a missing hidden import, data file, or Qt plugin) is caught before release. Because a real
PyInstaller build takes minutes, the two build-dependent checks run only when the maintainer opts
in; the default gate keeps its existing time budget.

## In scope

- A new top-level `packaging/` directory holding exactly three PyInstaller `--onedir` spec files,
  named to match the runner labels the already-committed release workflow passes to PyInstaller:
  `packaging/macos-latest.spec`, `packaging/windows-latest.spec`, `packaging/ubuntu-latest.spec`.
- All three specs share the `src/ollama_llm_bench/__main__.py` entry point and differ only in per-OS
  bundle metadata: application icon, the identity fields from the specification's project-identity
  table (application name `Ollama LLM Bench`, macOS bundle identifier
  `com.sanyokkua.ollamallmbench`), the minimum-OS declaration, and the OS-specific packaging
  wrapper.
- Excluding test code from every bundle: neither the top-level `tests/` tree nor any colocated
  `src/ollama_llm_bench/**/tests/` package appears in a built artifact.
- The per-OS artifact shapes the specs must produce: a macOS one-directory `.app` bundle (the input
  to the `.dmg`), a Windows one-directory folder (the input to the portable `.zip`), and a Linux
  one-directory tree (the input to the AppImage).
- A new opt-in `packaging` pytest marker: registered in `pyproject.toml`'s `markers` list, gated on
  the `OLLAMA_BENCH_PACKAGING_TESTS` environment variable, and carrying the two checks that require
  a real build — the build itself and the packaged-artifact smoke launch.

## Out of scope

- Turning the built one-directory trees into the final `.dmg` / `.zip` / AppImage, the `SHA256SUMS`
  file, and the release publish — owned by STORY-095, which completes the existing release workflow.
  This story delivers the spec files that workflow already invokes, plus the local build checks.
- Editing `.github/workflows/release.yml`. The spec filenames above are chosen precisely so no
  workflow edit is needed: the committed workflow already runs
  `uv run --group build pyinstaller "packaging/${{ matrix.os }}.spec"` over the matrix
  `macos-latest` / `windows-latest` / `ubuntu-latest`.
- The user-facing install/first-run/uninstall documentation — owned by STORY-096.
- The composition root, launch, and quit sequences the artifact runs — delivered by STORY-076..080
  and exercised headlessly from source by STORY-081 (this story's prerequisite).
- The opt-in **live-server** test tier (`live_local` marker) — owned by STORY-086. That tier and
  this one are independent and must not share a marker name or an environment variable.

## Spec inputs

- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#6-build-backend-and-packaging` — desktop
  binaries are built with PyInstaller **one-directory** mode; there is one specification per
  operating system; the three share the same Python entry point and differ only in per-OS bundle
  metadata (icon, identity fields, minimum-OS declaration, OS-specific packaging wrapper); test code
  is excluded from every bundle.
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#7-per-os-artifacts` — the three artifacts:
  a macOS `.dmg` built from an **ad-hoc-signed** one-directory app bundle and **arm64 only**
  (DD-69), a Windows portable `.zip` with **no installer**, and a Linux AppImage.
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#11-minimum-os-versions` — the minimum-OS
  versions each bundle declares and targets: macOS 11, Windows 10 build 1809 or later, and a Linux
  glibc 2.35 baseline (built on the older-baseline runner so the glibc floor stays low).
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#13-anti-patterns` — single-file mode is an
  anti-pattern (per-launch temp extraction, slow startup); shipping a Windows installer is an
  anti-pattern; bundling test code into a release artifact is an anti-pattern.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#3-test-layout` — `--strict-markers` is on and the
  marker list lives in `[tool.pytest.ini_options]`, so the new `packaging` marker must be registered
  there or collection errors; cross-cutting tests live under the top-level `tests/` tree.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment` — slow checks are run
  locally on demand by the maintainer, and there is no scheduled/nightly workflow (DD-36); a
  minutes-long build therefore belongs behind an explicit opt-in, not in the default selection.
- `15_Risks_and_Open_Questions/01_RISK_REGISTER.md#r-011--cross-platform-packaging-drift-pyinstaller`
  — R-011's mitigation: one spec file per OS with explicit hidden-import and data-file declarations,
  plus a post-build smoke test that launches the packaged artifact.

## Design constraints

- One-directory mode only. A `--onefile` build, or a spec that produces a single-file executable, is
  a defect against the anti-pattern table, not a configuration choice.
- The three spec files share the entry point; anything that differs between them must be per-OS
  bundle metadata. A per-OS divergence in hidden imports or bundled data is allowed only where the
  OS genuinely requires it, and is commented in the spec file saying why.
- `packaging/` lives outside `src/` and holds no importable application module; the spec files are
  build inputs, not application code.
- The `packaging` marker and the `OLLAMA_BENCH_PACKAGING_TESTS` environment variable are **specific
  to this story**. STORY-086 introduces a separate opt-in tier with its own `live_local` marker and
  its own environment variable. Neither name may be reused across the two stories: reusing one would
  make opting into a local-server smoke run silently trigger a multi-minute PyInstaller build, and
  would couple two otherwise independent stories.
- A `packaging`-marked test that runs without its opt-in variable set is **skipped**, never failed —
  the default gate must stay green on a machine that has never built an artifact.
- The packaged artifact must reach the same state STORY-081's headless smoke tier proves from
  source: the main window (`ui/main_window/`) appears and the process shuts down cleanly with a
  zero exit status.

## Acceptance criteria

### STORY-094-AC-1

Given the repository, when the packaging specs are inspected, then `packaging/` contains exactly
three PyInstaller specs named `macos-latest.spec`, `windows-latest.spec`, and `ubuntu-latest.spec`,
each declaring one-directory mode, each naming `src/ollama_llm_bench/__main__.py` as its entry
point, and each excluding both `tests/` and every `src/ollama_llm_bench/**/tests/` package.

### STORY-094-AC-2

Each per-OS spec declares its operating system's required bundle metadata:

| Spec file                       | Artifact shape it builds    | Minimum-OS declaration it carries | Architecture |
| ------------------------------- | --------------------------- | --------------------------------- | ------------ |
| `packaging/macos-latest.spec`   | one-directory `.app` bundle | macOS 11                          | arm64 only   |
| `packaging/windows-latest.spec` | one-directory folder        | Windows 10 build 1809             | x86-64       |
| `packaging/ubuntu-latest.spec`  | one-directory tree          | glibc 2.35 baseline               | x86-64       |

### STORY-094-AC-3

Given the `OLLAMA_BENCH_PACKAGING_TESTS` opt-in variable is set, when the host operating system's
spec is built with PyInstaller, then the build succeeds and produces a one-directory output
containing the application executable and no test module.

### STORY-094-AC-4

Given a built one-directory artifact and the `OLLAMA_BENCH_PACKAGING_TESTS` opt-in variable set,
when the smoke-launch check runs the artifact, then the artifact starts, shows the main window, and
exits with a zero status within the check's time budget.

### STORY-094-AC-5

Given the `OLLAMA_BENCH_PACKAGING_TESTS` variable is unset, when the default `just check` and
`just test` selections run, then every `packaging`-marked test is skipped, no PyInstaller build is
started, and the suite passes.

## Test plan

- STORY-094-AC-1 — integration (build-config presence; reads the spec files as text, runs no build),
  `tests/integration/test_packaging_specs.py`,
  `test_three_onedir_specs_share_entry_point_and_exclude_test_code`.
- STORY-094-AC-2 — integration (build-config presence, one `@pytest.mark.parametrize` row per spec
  file), same file, `test_spec_declares_its_os_bundle_metadata`.
- STORY-094-AC-3 — integration, `packaging`-marked, `tests/integration/test_packaging_build.py`,
  `test_host_os_spec_builds_a_onedir_tree_without_test_modules`.
- STORY-094-AC-4 — integration, `packaging`-marked,
  `tests/integration/test_packaged_artifact_smoke.py`,
  `test_packaged_artifact_launches_and_shuts_down_cleanly`.
- STORY-094-AC-5 — architecture, `tests/architecture/test_packaging_tier_gating.py`,
  `test_packaging_marker_is_registered_and_skipped_without_opt_in`. Asserts the `packaging` marker
  appears in `pyproject.toml`'s `markers` list (so `--strict-markers` does not error at collection)
  and that collecting the two `packaging`-marked test files with the variable unset yields only
  skips.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-094.
- [ ] The `packaging` marker is registered in `pyproject.toml`, and neither its name nor its
  environment variable collides with STORY-086's `live_local` tier.
- [ ] `just check` still completes inside its usual time budget with the opt-in variable unset.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

| Story     | Condition                                                                      |
| --------- | ------------------------------------------------------------------------------ |
| STORY-095 | Immediately — STORY-094 is its only dependency, so flip `draft` → `ready` now. |
| STORY-096 | Immediately — STORY-094 is its only dependency, so flip `draft` → `ready` now. |

**What to do on completion**

1. With this story's acceptance-criteria tests passing, edit `status: draft` → `status: ready` in
   both `docs/stories/story-095-tag-triggered-release-workflow.md` and
   `docs/stories/story-096-distribution-docs.md`. Neither has any other dependency, so no further
   condition applies.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   The natural ranking is STORY-095 first (it turns these specs into published artifacts and is the
   only remaining blocker on a real release), then STORY-096 (the user-facing documentation for
   those artifacts).

## Notes

- **Spec filenames are pinned to the committed workflow, deliberately.**
  `.github/workflows/release.yml` already contains
  `uv run --group build pyinstaller "packaging/${{ matrix.os }}.spec"` under a build matrix of
  `macos-latest`, `windows-latest`, `ubuntu-latest`. Naming the spec files after the runner labels
  means this story lands standalone with **no** workflow edit, so it does not have to be merged
  together with STORY-095. Neither `packaging/` nor any `.spec` file exists in the repository yet —
  that half of the story is genuinely greenfield.
- **Why the two build checks moved behind a marker.** They were previously plain
  `tests/integration/` tests. `just check` runs
  `pytest tests/unit tests/integration tests/e2e src -q` on a roughly two-minute budget, of which
  `tests/integration` is about fifty seconds; a real PyInstaller build takes minutes and would make
  a hang indistinguishable from a normal run. `--strict-markers` is enabled, so an unregistered
  marker is a **collection error**, not a warning — registering `packaging` in `pyproject.toml` is
  mandatory, not optional.
- **Non-`src` deliverable.** The load-bearing artifacts are the `packaging/*.spec` files and the
  pytest marker, all outside `src/`. `__main__.py` and `compose.py` are not citable inventory paths
  (the module-inventory parser only accepts backtick-quoted `backend/…/`, `adapters/…/`, `ui/…/`
  paths), which is why STORY-076/077 cited feature modules for their entry-point and composition
  work. This story follows that precedent: `backend/infra/` (the launch/entry-point infrastructure
  the bundle runs, as STORY-076 did) and `ui/main_window/` (the window AC-4's smoke launch asserts
  appears). `pyinstaller>=6.0` is already declared in `pyproject.toml`'s `build` dependency group.
