---
description: Plan phase N of the v3 rewrite by running investigator + architect to produce that phase's story files, then stop before any implementation
argument-hint: <phase-number>
---

You are bootstrapping planning for **Phase $1** of the Ollama LLM Bench v3 rewrite. This
command only plans a phase — it produces story files under `docs/stories/` and then stops. It
never invokes `coder`, `tester`, or `docs-writer`, and it never touches `src/`.

Follow these steps in order. Stop and report immediately if any gate fails — do not create any
story files until every gate has passed.

## 1. Read the governing docs

Read in full:

- `docs/reference_planning_docs/01_PHASE_BREAKDOWN.md` — locate Phase $1's section and read its
  "Depends on", "Spec inputs", "Modules", "Work", and "Definition of done" subsections.
- `docs/reference_planning_docs/02_STORY_PROCESS.md` — the investigator → architect → coder →
  tester → docs-writer pipeline, the worked STORY-001 example, and the sizing rules (S = 1
  module/1-3 AC, M = ≤3 modules/≤6 AC, L = ≤5 modules/≤10 AC, split if larger).
- `docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md` — cross-reference
  the authoritative module list Phase $1 is supposed to cover; treat this, not your own
  judgment, as the source of truth for which modules belong to this phase.

## 2. Special-case Phase 0

If `$1` is `0`: Phase 0 is scaffold-only, not story-by-story (per
`docs/reference_planning_docs/03_CLAUDE_CODE_KICKOFF_PROMPT.md`). Do not run `investigator` or
`architect`. Instead, report Phase 0's status by checking:

- `docs/adr/` for the 3 accepted ADRs (programmatic Qt-Widgets theming, scoped reactive stores +
  event bus, `uv_build` + unsigned distribution).
- `pyproject.toml` for the `uv_build` backend and full dependency table.
- `justfile` for the full command set (`setup`, `lint`, `format`, `typecheck`, `import-check`,
  `arch-test`, `test`, `coverage-layers`, `trace`, `trace-check`, `check`).

Report which Phase 0 deliverables exist and which are missing, then stop. Do not proceed to
steps 3-6 below for Phase 0.

## 3. Gate checks (skip only for Phase 0, which returns above)

Run `just check` and confirm it is green. If it fails, stop and report the failure — do not
proceed.

Then verify every phase listed in Phase $1's "Depends on" (from step 1) is actually complete.
Do not assume this means only "Phase $1 minus 1" — the dependency DAG is not strictly linear
(Phase 10's sub-phases 10a-10h are the clearest example of this). For each dependency phase,
check the `status` front-matter of every story file under `docs/stories/*.md` whose `modules:`
field falls under that phase's module list; every such story must be `status: done`.

If any prerequisite phase is incomplete, stop and report exactly which stories/modules are
blocking — do not create any story files.

## 4. Run the investigator

Invoke the `investigator` agent (via the `Agent` tool), scoped explicitly to:

- Phase $1's exact spec-input paths (from step 1).
- The current state of `src/ollama_llm_bench/`.

Per `02_STORY_PROCESS.md`, this must be a fresh investigation pass, not a reuse of any prior
report — stale investigator output is exactly how spec drift from earlier phases goes unnoticed.

## 5. Run the architect

Feed the investigator's report to the `architect` agent to produce Phase $1's story files under
`docs/stories/`, following `docs/v3_specification/14_Process_and_Traceability/02_STORY_FORMAT.md`'s
schema exactly. Numbering is **global and sequential**: the architect must continue from the
highest existing `STORY-NNN` file under `docs/stories/`, not restart per phase.

If `$1` is `10`, explicitly pass along the sub-phase note from
`docs/reference_planning_docs/03_CLAUDE_CODE_KICKOFF_PROMPT.md`: stories should be scoped one
widget folder per story (10a-10h), and none may touch `compose.py` — Phase 11 owns that file.

## 6. Stop and report

Once the story files are written, stop. Do not invoke `coder`, `tester`, or `docs-writer`, and
do not edit anything under `src/`. Report:

- The list of story files created (or updated), with their `id`, `title`, and `status`.
- Any ADRs created along the way.
- Any gaps or ambiguities the investigator or architect surfaced.
- A suggestion to run `/bootstrap-story-planning <n>` next, for each newly created story, before
  any implementation begins.
