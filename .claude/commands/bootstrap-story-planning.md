---
description: Plan one already-existing ready story's implementation - validates readiness, grounds itself in cited spec clauses and layer skills, and produces a concrete plan via superpowers:writing-plans. Stops before any code is written.
argument-hint: <story-number>
---

You are planning the implementation of **story $1** of the Ollama LLM Bench v3 rewrite. This
command plans one story that the `architect` agent has already produced — it does not create
stories (`/bootstrap-phase` does that) and it does not write code. It stops once a plan exists.
It never invokes `coder`, `tester`, or `docs-writer`, and it never edits anything under `src/`.

## 1. Resolve the story file

Normalize `$1` to a zero-padded 3-digit number: `17`, `017`, and `STORY-017` must all resolve to
`017`. Glob `docs/stories/story-<NNN>-*.md`.

- Zero matches: stop. Report that no story with that number exists, and suggest running
  `/bootstrap-phase <N>` if the phase that would contain it hasn't been planned yet.
- Exactly one match: proceed.
- (There should never be more than one match — if there is, stop and report the conflict rather
  than guessing which file is authoritative.)

## 2. Read the story

Read the full story file — front-matter and body.

## 3. Validate readiness

- `status` must be `ready`.
  - If `draft`: stop. Report that the story needs architect refinement before it can be
    planned for implementation.
  - If `done`: stop and ask the user to confirm they actually want to re-plan an already-shipped
    story before continuing — note this explicitly rather than assuming.
  - If `in-progress` or `superseded`: stop and report the status; ask how the user wants to
    proceed.
- Every id in `depends_on` must have `status: done`. Check each dependency's story file
  directly. If any dependency is not `done`, stop and name exactly which dependency (its id,
  title, and current status) is blocking — do not proceed to plan around an unmet dependency.

## 4. Ground in the primary spec source

Read every reference listed in the story's `spec_clauses:` front-matter directly by opening the
real files under `docs/v3_specification/` (not just the story's own paraphrase of them) — the
plan must be grounded in the primary source.

## 5. Load the relevant skills and rules

From the story's `modules:` field, identify which architectural layer(s) it touches. Load, via
the `Skill` tool, from CLAUDE.md's Skills Reference table:

- Always: `three-layer-architecture`.
- Plus whichever of the following genuinely apply to this story's modules — this is the same
  set `coder.md` itself is required to load before writing code:
  - `msgspec-domain-modeling`
  - `protocol-first-interfaces`
  - `concurrency-and-cancellation`
  - `icontract-design-by-contract`
  - `error-taxonomy-and-redaction`
  - `pyside6-spec-ui`
  - `sqlite-persistence-conventions`
  - `secrets-and-provider-config`
  - `edge-case-coverage`
  - `testing-standard-pyqt`

Also read any `.claude/rules/*.md` file whose `Globs` column (see the Rules Reference table in
CLAUDE.md) matches a path under the story's `modules:`.

## 6. Produce the plan

Invoke the `superpowers:writing-plans` skill. Hand it as its requirements input:

- The story's acceptance criteria (written out in full from the story body).
- The story's edge cases (`edge_cases:` front-matter plus their descriptions from
  `docs/v3_specification/08_Cross_Cutting/08-I_edge_cases.md`).
- The spec citations read in step 4.
- The skills and rules identified in step 5.

The output is a concrete implementation plan for this one story.

## 7. Stop

Stop once the plan is produced. Do not invoke `coder`, `tester`, or `docs-writer`. Do not edit
anything under `src/`. Present the plan to the user for review before any further action.
