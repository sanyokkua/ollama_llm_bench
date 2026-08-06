---
id: STORY-095
title: Complete the release workflow with real per-OS packaging, a version-consistency gate, and failure cleanup
status: draft
spec_clauses:
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#3-cicd-overview
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#4-ci-jobs
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#7-per-os-artifacts
  - 16_Engineering_Standards/08_CICD_AND_PACKAGING.md#8-checksums-and-reproducibility
  - 13_Distribution_and_Release/02_INSTALLATION.md#1-where-to-download
  - 13_Distribution_and_Release/06_VERSIONING_POLICY.md#6-where-the-version-is-shown
  - 13_Distribution_and_Release/06_VERSIONING_POLICY.md#7-version-tags-and-releases
modules:
  - ui/main_window/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-095-AC-1
  - STORY-095-AC-2
  - STORY-095-AC-3
  - STORY-095-AC-4
  - STORY-095-AC-5
edge_cases: []
depends_on:
  - STORY-094
adrs:
  - ADR-0003
owner: coder
estimate: M
---

# STORY-095 — Complete the release workflow with real per-OS packaging, a version-consistency gate, and failure cleanup

## Goal

**Blocked:** stays `draft` until STORY-094 is `done`.

Turn the release workflow from a skeleton that runs into one that actually ships. Pushing a version
tag today already re-runs the quality gate on three operating systems, runs the dependency audit,
runs PyInstaller per OS, writes a checksum file, and publishes a GitHub Release — but the step that
is supposed to turn each PyInstaller output into a downloadable artifact only prints a message, so
the release publishes nothing a user can install. This story replaces that placeholder with real
`.dmg`, `.zip`, and AppImage packaging under the published filenames, adds a gate that refuses to
release when the pushed tag and the project version disagree, and adds the cleanup that the
specification requires when a release step fails so a release is never left half-published.

## In scope

- **Real packaging.** Replace the `Package artifact` step's three `echo` placeholders in
  `.github/workflows/release.yml` with the actual per-OS packaging: build an ad-hoc-signed `.dmg`
  from the macOS one-directory `.app`, zip the Windows one-directory folder, and build an AppImage
  from the Linux one-directory tree — each staged into `dist-artifacts/` under the published
  filename for its OS. Also delete the now-stale comment above the PyInstaller step that says the
  `packaging/*.spec` files do not exist yet.
- **A version-consistency gate.** A workflow step that reads the `[project] version` value from
  `pyproject.toml`, compares it with the `MAJOR.MINOR.PATCH` in the pushed tag, and fails the
  release before any artifact is built when they differ.
- **Failure cleanup.** When any release step fails, delete the partially published GitHub Release
  and the tag, so a failed run leaves no half-published release behind.
- **Hardening the checksum and upload steps** so a run that produced no artifact fails rather than
  publishing an empty release: today the checksum step exits successfully when `dist-artifacts/`
  does not exist, and the upload step is set to only warn when it matches no file.
- **Regression locks** on the two behaviours the workflow already has correct — the tag-only trigger
  with a three-OS build matrix, and a `SHA256SUMS` file covering every artifact — so a later edit
  cannot silently remove them.

## Out of scope

- The PyInstaller one-directory spec files and the opt-in packaged-artifact build/smoke tier — owned
  by STORY-094, this story's prerequisite. The workflow already invokes
  `packaging/${{ matrix.os }}.spec`; this story consumes those specs' output and does not write
  them.
- The quality-gate, audit, and publish jobs' existing structure — already correct and unchanged
  except where a criterion below explicitly tightens them.
- The pull-request gate workflow — a separate workflow, untouched here.
- The user-facing install, checksum-verification, and first-run documentation — owned by STORY-096.
- Signing or notarizing anything. The binaries stay unsigned, and `SHA256SUMS` remains an integrity
  record only, never an authenticity guarantee (ADR-0003, D-R-11b).

## Spec inputs

- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#3-cicd-overview` — CI is triggered by exactly
  two events (DD-36): a pull request, and a push of a release-version tag matching `v*.*.*`. There is
  no `schedule`, no `workflow_dispatch`, no push-to-main artifact build. Artifact builds happen only
  on a release-tag push.
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#4-ci-jobs` — the release job runs after the
  build job, collects the per-OS artifacts and their checksums, and publishes them on the GitHub
  Release for the tag; **"If any step fails, the workflow cleans up the partially published release
  and the tag so a release is never left half-published."** This sentence is the whole basis of
  AC-5. The audit step (`pip-audit`) gates the release before any artifact is built.
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#7-per-os-artifacts` — the three artifact shapes
  the packaging step must produce: a macOS `.dmg` built from the ad-hoc-signed one-directory app
  bundle (arm64 only, DD-69), a Windows portable `.zip` of the one-directory folder with no
  installer, and a Linux AppImage of the one-directory tree.
- `16_Engineering_Standards/08_CICD_AND_PACKAGING.md#8-checksums-and-reproducibility` — every
  published artifact is accompanied by a SHA256 checksum; the `SHA256SUMS` file is the sole
  release-side integrity record; the build pins the source-date timestamp to the commit time and
  makes hash randomization deterministic so the build is tamper-evident.
- `13_Distribution_and_Release/02_INSTALLATION.md#1-where-to-download` — the exact published
  filenames the packaging step must produce: `OllamaLLMBench-<version>-macos.dmg`,
  `OllamaLLMBench-<version>-windows-x86_64.zip`,
  `OllamaLLMBench-<version>-linux-x86_64.AppImage`, plus the `SHA256SUMS` file.
- `13_Distribution_and_Release/06_VERSIONING_POLICY.md#7-version-tags-and-releases` — pushing a
  version tag triggers the release pipeline, and the version in the tag, the version embedded in the
  built artifacts, and the version shown in the application are always the same value.
- `13_Distribution_and_Release/06_VERSIONING_POLICY.md#6-where-the-version-is-shown` — the installed
  version is shown in exactly two places: the About surface and the main-window status bar.

## Design constraints

- The workflow's `on:` block stays exactly `push.tags: ["v*.*.*"]`. Adding a schedule, a manual
  dispatch, or a branch filter that targets the main branch is a defect against DD-36.
- The macOS artifact is arm64 only (DD-69); no Intel `.dmg` is produced and no universal binary is
  attempted.
- Each artifact is built on its own native runner in the existing matrix; no cross-compilation.
- `pyproject.toml`'s `[project] version` is the single version source. Nothing else in the
  repository declares a version, and this story must not introduce a second one (no
  `__version__` constant, no version file). The application resolves the version at runtime from the
  installed package metadata, so the PyInstaller bundle must carry that metadata for the resolution
  to succeed.
- The workflow tests are **static configuration tests**: they parse
  `.github/workflows/release.yml` with `ruamel.yaml` — already a runtime dependency of the project,
  declared in `pyproject.toml`'s `dependencies` — and assert on the parsed mapping. They never
  invoke `gh`, never call the GitHub API, and never run a build.

## Acceptance criteria

### STORY-095-AC-1

Given the parsed `.github/workflows/release.yml`, when its triggers and build matrix are inspected,
then its only trigger is a `push` of a tag matching `v*.*.*` — with no `schedule`, no
`workflow_dispatch`, and no branch push trigger — and its build job's matrix has exactly the three
entries `macos-latest`, `windows-latest`, and `ubuntu-latest`.

### STORY-095-AC-2

Given the parsed release workflow, when the publish path is inspected, then a `SHA256SUMS` file is
generated over every staged artifact and is among the files the publish step uploads, and the
checksum step fails rather than succeeding when the artifact staging directory is missing or empty.

### STORY-095-AC-3

For every release, the `MAJOR.MINOR.PATCH` value in the pushed tag, the `[project] version` in
`pyproject.toml`, the version embedded in the built artifacts, and the version the running
application shows in its About surface and its status bar are all the same value; when the tag and
`pyproject.toml` disagree, the release workflow fails before building any artifact.

### STORY-095-AC-4

Each build-matrix entry's packaging step produces a real, downloadable artifact under its published
filename:

| Matrix entry     | PyInstaller output          | Packaged artifact                                |
| ---------------- | --------------------------- | ------------------------------------------------ |
| `macos-latest`   | one-directory `.app` bundle | `OllamaLLMBench-<version>-macos.dmg`             |
| `windows-latest` | one-directory folder        | `OllamaLLMBench-<version>-windows-x86_64.zip`    |
| `ubuntu-latest`  | one-directory tree          | `OllamaLLMBench-<version>-linux-x86_64.AppImage` |

No matrix entry's packaging step consists solely of an `echo`.

### STORY-095-AC-5

Given a release step fails after the GitHub Release has been created, when the workflow finishes,
then a cleanup step has run that deletes the partially published release and its tag, so no
half-published release remains.

## Test plan

- STORY-095-AC-1 — integration (workflow configuration; parses the YAML with `ruamel.yaml`, runs no
  build), `tests/integration/test_release_workflow.py`,
  `test_release_workflow_triggers_only_on_a_version_tag_and_builds_three_os_entries`.
- STORY-095-AC-2 — integration (workflow configuration), same file,
  `test_release_publishes_sha256sums_and_fails_on_an_empty_artifact_directory`.
- STORY-095-AC-3 — two tests. Integration (workflow configuration), same file,
  `test_release_workflow_gates_on_tag_matching_pyproject_version`, asserting the version-check step
  exists, reads `pyproject.toml`, and is ordered before the build job. Plus integration,
  `packaging`-marked (STORY-094's opt-in tier),
  `tests/integration/test_packaged_artifact_version.py`,
  `test_packaged_artifact_shows_the_pyproject_version_in_about_and_status_bar`, asserting the
  launched artifact resolves the real version rather than the `0.0.0` fallback and renders it in
  both surfaces.
- STORY-095-AC-4 — integration (workflow configuration, one `@pytest.mark.parametrize` row per
  matrix entry), same file as AC-1, `test_each_matrix_entry_packages_its_published_artifact`.
- STORY-095-AC-5 — integration (workflow configuration), same file as AC-1,
  `test_a_failed_release_step_triggers_release_and_tag_cleanup`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-095.
- [ ] No packaging step in `.github/workflows/release.yml` is still a placeholder `echo`, and the
  stale "packaging/\*.spec files land in Phase 13" comment is gone.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

Nothing. No story's `depends_on` names STORY-095; it is terminal in the dependency graph.

**What to do on completion**

1. There is no story to flip `draft` → `ready` as a result of this one, so the flip checkbox above
   is satisfied vacuously — record that explicitly rather than leaving it ambiguous.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so flipping this
   story to `done` makes it stale — then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   If STORY-096 is still open it is the natural successor: it documents for users the very artifacts
   this story starts publishing, and it is the last piece of the release story. STORY-093 is the
   phase closer and can only be picked up once every story it depends on is `done`.

## Notes

- **The workflow already exists; this story completes it.** `.github/workflows/release.yml` is
  committed and 108 lines long. It already has the `v*.*.*` tag-only trigger, a three-OS
  `quality-gate` job, a `pip-audit` `audit` job, a three-OS `build` matrix that invokes
  `packaging/${{ matrix.os }}.spec`, a checksum step, and a `softprops/action-gh-release@v2`
  `publish` job. AC-1 and AC-2 are therefore **regression locks on behaviour that already exists**,
  not new work. The genuinely new work is AC-3, AC-4, and AC-5.
- **What the placeholder actually is.** The `Package artifact` step at lines 73–81 stages a
  `dist-artifacts/` directory and then runs a `case` whose three arms are bare `echo` statements
  (`"macOS .dmg packaging step …"`, `"Windows portable .zip packaging step"`,
  `"Linux AppImage packaging step"`). Nothing is packaged, so the checksum step finds an empty
  directory and the publish step uploads nothing. The stale comment on lines 69–70 states that the
  `packaging/*.spec` files "land in Phase 13" — untrue once STORY-094 is `done`, and to be deleted
  with the placeholder.
- **"Workflow-config test" made concrete.** The previous draft named a "workflow-config test" tier
  that does not exist, which made the story unimplementable as written. Every workflow criterion
  here is proven by parsing `.github/workflows/release.yml` with `ruamel.yaml` (already a runtime
  dependency) and asserting on the resulting mapping — file paths and function names are given in
  the Test plan.
- **Version display is already built; the gate and the bundle metadata are not.** Both display
  surfaces the versioning policy names already work: `compose.py`'s `_resolve_app_version()` reads
  `importlib.metadata.version("ollama-llm-bench")` and passes it to the About dialog (rendered by
  `ui/common_dialogs/_internal/about_view.py`, object name `common_dialogs.about.version`) and to
  the status bar (rendered by `ui/main_window/_internal/status_bar.py` as `v{app_version}`, object
  name `status_bar_version_label`). The two missing halves are that (a) nothing checks the pushed
  tag against `pyproject.toml`, and (b) `_resolve_app_version()` falls back to `"0.0.0"` when the
  package metadata is absent — which is exactly what happens in a PyInstaller bundle that does not
  carry the `.dist-info` directory. AC-3 covers both.
- **Non-`src` deliverable.** The load-bearing change is `.github/workflows/release.yml`, outside
  `src/`; `__main__.py` and `compose.py` are not citable inventory module paths (the parser accepts
  only backtick-quoted `backend/…/`, `adapters/…/`, `ui/…/`). Following STORY-076/077's precedent,
  the `modules:` cite the two version-display surfaces the versioning policy names and AC-3 asserts
  against: `ui/main_window/` (status bar) and `ui/common_dialogs/` (About dialog). The
  version-consistency gate and the packaging steps have no module owner.
