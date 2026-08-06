---
id: STORY-096
title: Write the user-facing install, first-run, unsigned-distribution, and uninstall documentation
status: draft
spec_clauses:
  - 13_Distribution_and_Release/02_INSTALLATION.md#1-where-to-download
  - 13_Distribution_and_Release/02_INSTALLATION.md#2-verifying-the-download
  - 13_Distribution_and_Release/02_INSTALLATION.md#7-where-application-data-is-stored
  - 13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md#6-the-first-run-sequence
  - 13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#1-why-a-security-warning-appears
  - 13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#2-macos--gatekeeper
  - 13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#3-windows--smartscreen
  - 13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#5a-updating-re-triggers-the-first-run-flow-per-binary
  - 13_Distribution_and_Release/08_UNINSTALL.md#1-what-a-complete-uninstall-removes
  - 13_Distribution_and_Release/08_UNINSTALL.md#7-what-is-left-behind
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

**Blocked:** stays `draft` until STORY-094 is `done`.

Give a person who has just downloaded a release everything they need to run it. The repository
currently has no install-related documentation of any kind, so a user who downloads an unsigned
binary hits an operating-system security warning with nothing in the project telling them it is
expected or how to get past it. This story adds a small documentation subtree covering four things:
how to download and verify a release, what happens on first launch, how to clear each operating
system's security warning, and how to uninstall — including the data directory that deliberately
survives an uninstall.

## In scope

- A new `docs/distribution/` subtree with five files: `README.md` (an index linking the other
  four), `installation.md`, `first-run.md`, `unsigned-distribution.md`, and `uninstall.md`.
- **In `installation.md`:** the GitHub Releases download location; the exact per-OS artifact
  filenames `OllamaLLMBench-<version>-macos.dmg`,
  `OllamaLLMBench-<version>-windows-x86_64.zip`, `OllamaLLMBench-<version>-linux-x86_64.AppImage`,
  and the `SHA256SUMS` file; all three checksum-verification commands — `shasum -a 256` on macOS,
  `certutil -hashfile <file> SHA256` on Windows, `sha256sum` on Linux — and the instruction to
  delete and re-download rather than run an artifact whose checksum does not match; the per-OS
  install steps (drag to `Applications`; extract the `.zip` to a writable folder and run
  `OllamaLLMBench.exe` in place; `chmod +x` the AppImage); and the per-OS application-data
  directories: `~/Library/Application Support/OllamaLLMBench/`, `%LOCALAPPDATA%\OllamaLLMBench\`,
  and `$XDG_DATA_HOME/OllamaLLMBench/` falling back to `~/.local/share/OllamaLLMBench/`.
- **In `first-run.md`:** there is no setup wizard, the main window opens directly, and the
  application silently creates its data directory and default settings on the first successful
  launch.
- **In `unsigned-distribution.md`:** why the warning appears (no Apple Developer ID, no Apple
  notarization, no Windows Authenticode certificate — not a defect and not malware); the macOS
  click-through path **System Settings → Privacy & Security → Open Anyway → Open**, *plus* the
  `xattr -d com.apple.quarantine "/Applications/Ollama LLM Bench.app"` terminal fallback for when
  that path does not clear the block; the Windows **More info → Run anyway** path *plus* the
  right-click **Properties → Unblock** step for a `.zip` carrying the mark of the web; the Linux
  execute-permission step; and the fact that the allow decision is remembered **per binary**, so
  every update is a new binary and re-triggers the flow exactly once — once per update, never per
  launch.
- **In `uninstall.md`:** the per-OS uninstall steps, what a complete uninstall removes, and
  explicitly what an uninstall **leaves behind** — the application data directory (database, logs,
  settings, backups) survives by design and must be removed deliberately if the user wants it gone.

## Out of scope

- The PyInstaller specs and the release workflow — owned by STORY-094 and STORY-095. This story
  documents the artifacts they produce.
- Any change to the vendored `13_Distribution_and_Release/` specification. That folder is read-only;
  this story restates its user-facing content in the repository's own documentation tree.
- The `README.md` at the repository root — it links into `docs/`, and adding a link there is
  optional polish, not a criterion of this story.
- Any application code change. Nothing in `src/` is touched.

## Spec inputs

- `13_Distribution_and_Release/02_INSTALLATION.md#1-where-to-download` — the GitHub Releases source
  under the `sanyokkua` owner and the exact per-OS artifact filenames plus the `SHA256SUMS` file.
- `13_Distribution_and_Release/02_INSTALLATION.md#2-verifying-the-download` — the three per-OS
  checksum commands and the rule that an artifact whose checksum does not match is deleted and
  re-downloaded, never run.
- `13_Distribution_and_Release/02_INSTALLATION.md#7-where-application-data-is-stored` — the three
  per-OS application-data directory paths, and that the directory is separate from the application:
  replacing the application does not affect it, and removing the application does not remove it.
- `13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md#6-the-first-run-sequence` — no setup
  wizard, the main window opens directly, and the data directory plus default settings are created
  silently on the first successful launch.
- `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#1-why-a-security-warning-appears` — why
  each operating system warns about unsigned binaries, that ad-hoc signing does not remove the
  macOS prompt, and that the warning is not a sign of a defect or of malware.
- `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#2-macos--gatekeeper` — the seven-step
  Open-Anyway click-through and the `xattr -d com.apple.quarantine` terminal fallback.
- `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#3-windows--smartscreen` — the
  **More info → Run anyway** path and the `.zip` **Properties → Unblock** step for the mark of the
  web.
- `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md#5a-updating-re-triggers-the-first-run-flow-per-binary`
  — the allow decision is remembered per binary, so each new version re-triggers the security flow
  exactly once; it is one-time-per-update, not per-launch.
- `13_Distribution_and_Release/08_UNINSTALL.md#1-what-a-complete-uninstall-removes` — what a
  complete uninstall removes on each operating system.
- `13_Distribution_and_Release/08_UNINSTALL.md#7-what-is-left-behind` — what remains after an
  ordinary uninstall, above all the application data directory.

## Design constraints

- The documents follow the repository's documentation writing standards: imperative mood, real
  commands and real paths rather than placeholders, tables for per-OS structured data, a language
  tag on every fenced code block, and no duplication of content that already has an authoritative
  home — link to it instead.
- The unsigned-distribution rationale cites ADR-0003's decision rather than re-arguing it.
- The per-OS application-data paths documented here must be the paths `backend/platform/` actually
  resolves. If the two disagree, the module is authoritative and the mismatch is a defect to raise,
  not something to paper over in prose.
- Each documented artifact filename uses the literal `<version>` placeholder exactly as the
  specification writes it, so the documentation does not go stale on every release.

## Acceptance criteria

### STORY-096-AC-1

Given `docs/distribution/`, when the install documentation is read, then it names all three per-OS
artifact filenames and the `SHA256SUMS` file, gives the checksum-verification command for each
operating system (`shasum -a 256`, `certutil -hashfile`, `sha256sum`), gives the per-OS install
steps, and lists the three per-OS application-data directory paths.

### STORY-096-AC-2

Given `docs/distribution/`, when the first-run and unsigned-distribution documentation is read, then
it states that there is no setup wizard and that the data directory is created silently on first
launch, and it gives, for each operating system, both the primary way past the security prompt and
its fallback — macOS **Open Anyway** plus `xattr -d com.apple.quarantine`, Windows **More info →
Run anyway** plus the `.zip` **Unblock** step, Linux the execute-permission step — and states that
the allow decision is per binary, so every update re-triggers the flow exactly once.

### STORY-096-AC-3

Given `docs/distribution/`, when the uninstall documentation is read, then it gives the per-OS
uninstall steps, states that the application data directory is left behind by an ordinary
uninstall, and gives the per-OS path to remove to delete it deliberately.

## Test plan

- STORY-096-AC-1 — integration (documentation content presence; reads the Markdown files as text),
  `tests/integration/test_distribution_docs.py`,
  `test_install_doc_lists_artifacts_checksums_install_steps_and_data_paths`.
- STORY-096-AC-2 — integration (documentation content presence), same file,
  `test_first_run_and_unsigned_docs_give_both_unblock_paths_per_os_and_the_per_binary_rule`.
- STORY-096-AC-3 — integration (documentation content presence), same file,
  `test_uninstall_doc_gives_per_os_steps_and_the_surviving_data_directory_paths`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-096.
- [ ] `docs/distribution/` contains `README.md`, `installation.md`, `first-run.md`,
  `unsigned-distribution.md`, and `uninstall.md`, and `README.md` links to the other four.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

Nothing. No story's `depends_on` names STORY-096; it is terminal in the dependency graph.

**What to do on completion**

1. There is no story to flip `draft` → `ready` as a result of this one, so the flip checkbox above
   is satisfied vacuously — record that explicitly rather than leaving it ambiguous.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so flipping this
   story to `done` makes it stale — then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   If STORY-095 is still open it ranks first, since without it the artifacts these documents
   describe are never actually published. STORY-093, the phase closer, can only be picked up once
   every story it depends on is `done`.

## Notes

- **This adds a `docs/` subtree the documentation rule does not currently name.**
  `.claude/rules/repository-documentation.md` fixes the `docs/` tree as `stories/`, `adr/`,
  `v3_specification/`, `architecture/`, and `development/`. `docs/distribution/` is a sixth
  directory, disclosed here deliberately. The alternative — five loose files at the top of `docs/`
  — would conflict with that rule's own preference for grouping and would leave the tree flatter
  than any existing area. Nothing install-related exists anywhere under `docs/` today, so there is
  no established location to reuse.
- **No edge-case ids, on purpose.** The `edge_cases:` list is deliberately empty. An `EC-` id must
  be discharged by a proving test that exercises the behaviour; a documentation-presence test
  proves only that a sentence was written, not that the described behaviour holds. Attaching an
  edge case here would record false coverage in the traceability record.
- **Documentation-only deliverable.** The work is user-facing Markdown outside `src/`. Every story
  must cite at least one inventory module, so `modules:` cites `backend/platform/` — the module that
  resolves the per-OS application-data directory that AC-1 and AC-3 document. It is the closest
  real owner; a purely documentation story has no natural source module, which is disclosed here
  rather than hidden.
