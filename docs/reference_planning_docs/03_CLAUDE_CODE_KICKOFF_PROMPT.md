# Kickoff Prompt — Phase 0

Paste this (adjusted per your answers to D1–D5 in `00_OVERVIEW_AND_DECISIONS.md`) into a fresh
Claude Code session running inside this repository.

---

> Read `.AdditionalDocs/Spec3_Rewrite_Plan/00_OVERVIEW_AND_DECISIONS.md`,
> `01_PHASE_BREAKDOWN.md`, and `02_STORY_PROCESS.md` in full before doing anything else.
>
> We are executing Phase 0 of that plan: governance and scaffold for a ground-up rewrite of
> this application per the specification at
> `/Users/ok/Documents/ReviewAndAnalysesOfSpec3/App_Specification_Ollama_Bench_Final/`. This
> is NOT an incremental change — the existing `src/ollama_llm_bench/` and `tests/` content is
> being replaced entirely, per decision D5 in the overview file.
>
> Decisions D1–D5 have been resolved as follows: [[ PASTE YOUR ANSWERS HERE — e.g. "D1: stay
> on feature/v2-app-redesign. D2: vendor the spec to docs/spec/. D3: rewrite CLAUDE.md and
> rules per the recommendation. D4: ratify all 3 ADRs. D5: confirmed as described." ]]
>
> Execute Phase 0's work list from `01_PHASE_BREAKDOWN.md` exactly, in order. Before deleting
> anything, run `git status` and confirm the working tree is clean (stop and ask if it isn't —
> do not delete uncommitted work). Use the `investigator` agent first to confirm the current
> state of `src/` and `.claude/` matches what the plan assumes, then proceed with the
> documented changes directly (Phase 0 is scaffolding, not a story-by-story phase).
>
> When Phase 0's definition-of-done is met, stop and report back — do not proceed into Phase 1
> (`docs/spec/10_Domain_and_Data/...`) without confirmation, since Phase 1 is where actual
> application code generation begins and is worth a fresh review checkpoint.

---

## Kicking off later phases

For Phase N (N ≥ 1), use this template in a fresh session once the prior phase's
definition-of-done is confirmed met:

> Read `.AdditionalDocs/Spec3_Rewrite_Plan/01_PHASE_BREAKDOWN.md` Phase N's section, and
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
