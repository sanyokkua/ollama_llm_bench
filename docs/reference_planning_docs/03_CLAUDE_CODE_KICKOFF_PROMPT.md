# Kickoff Prompt — Phase 0

Paste this into a fresh Claude Code session running inside this repository to continue Phase
0's remaining scaffold work.

______________________________________________________________________

> Read `docs/reference_planning_docs/00_OVERVIEW_AND_DECISIONS.md`,
> `01_PHASE_BREAKDOWN.md`, and `02_STORY_PROCESS.md` in full before doing anything else.
>
> We are executing Phase 0 of that plan: governance and scaffold for a ground-up rewrite of
> this application per the specification vendored in-repo at `docs/v3_specification/`.
>
> This repository is already on branch `feature/spec-v3-implementation` with the specification
> vendored at `docs/v3_specification/` and `.claude/` (CLAUDE.md plus all rule files) already
> rewritten to spec-v3 conventions. This session's job is the two things still outstanding:
> ratify the 3 proposed ADRs from
> `docs/v3_specification/15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md` into
> `docs/adr/0001..0003`, and build the rest of the Phase 0 scaffold (`pyproject.toml`,
> `justfile`, `docs/stories/`, CI workflows, and the other items) — see
> `01_PHASE_BREAKDOWN.md`'s Phase 0 section for the complete, current list.
>
> Execute Phase 0's work list from `01_PHASE_BREAKDOWN.md` exactly, in order. Before creating
> new scaffold files, run `git status` and confirm the working tree is clean (stop and ask if
> it isn't). Use the `investigator` agent first to confirm the current state of `src/` and
> `.claude/` matches what the plan assumes, then proceed with the documented changes directly
> (Phase 0 is scaffolding, not a story-by-story phase).
>
> When Phase 0's definition-of-done is met, stop and report back — do not proceed into Phase 1
> (`docs/v3_specification/10_Domain_and_Data/...`) without confirmation, since Phase 1 is where
> actual application code generation begins and is worth a fresh review checkpoint.

______________________________________________________________________

## Kicking off later phases

For Phase N (N ≥ 1), use this template in a fresh session once the prior phase's
definition-of-done is confirmed met:

> Read `docs/reference_planning_docs/01_PHASE_BREAKDOWN.md` Phase N's section, and
> `02_STORY_PROCESS.md`. Confirm Phase <N-1>'s definition-of-done is still met (`just check`
> green) before starting.
>
> Run the `investigator` agent over Phase N's spec inputs (listed in the phase section) and
> the current `src/ollama_llm_bench/` tree. Then run the `architect` agent to produce Phase
> N's stories under `docs/stories/`, following the worked example in `02_STORY_PROCESS.md`
> and the spec's own `14_Process_and_Traceability/02_STORY_FORMAT.md`. Do not implement
> anything yet — stop after the stories are written and list them for review.

Then, per story:

> Implement `docs/stories/story-0NN-<slug>.md` using the `coder` agent (one story only — do
> not start a second story in the same session). Hand off to the `tester` agent for the
> story's acceptance criteria, then `docs-writer` if the public surface changed. Run
> `just check` and `just trace` before marking the story `done`.

For Phase 10 (UI widgets), multiple stories from different sub-phases (10a-10h) can run as
parallel Claude Code sessions once Phase 9 is confirmed done — each session should be scoped
to exactly one widget folder's stories to avoid merge conflicts on shared files like
`compose.py` (which Phase 11 owns anyway — widget sessions should not touch it).

## Final phase checkpoint

After Phase 12, run `just trace-check` and paste its output into the chat before proceeding to
Phase 13 — a non-zero exit here means a requirement was missed somewhere in Phases 1-11 and
needs a remediation story before packaging work begins.
