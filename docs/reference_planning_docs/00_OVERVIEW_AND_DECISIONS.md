# Ollama LLM Bench — Spec v3 Ground-Up Rewrite: Implementation Plan

**Status:** Governance decisions resolved; Phase 0 scaffold work in progress
**Purpose:** Defines how to divide the full rewrite of this application (per the specification
vendored in-repo at `docs/v3_specification/`) into ordered, traceable, independently
implementable tasks, so that a Claude Code session (or a sequence of them) can execute the
rewrite on this branch without losing any requirement.

This folder (`docs/reference_planning_docs/`) holds planning and reference material only —
nothing in it is itself a code change. It is not referenced by any `.claude/` convention; it
exists purely to record the phase/story breakdown for humans and future sessions to consult.

## Files in this package

| File | Purpose |
|---|---|
| `00_OVERVIEW_AND_DECISIONS.md` | This file — what the rewrite is, the current baseline, and what's still open. |
| `01_PHASE_BREAKDOWN.md` | The 13 ordered phases, each mapped to specific spec folders/files and module-inventory entries, with a definition-of-done per phase. |
| `02_STORY_PROCESS.md` | How each phase is broken further into spec-traceable "stories" using the spec's own story format, plus one worked example. |
| `03_CLAUDE_CODE_KICKOFF_PROMPT.md` | A ready-to-paste prompt for the Claude Code session that will execute Phase 0. |

## What this rewrite actually is

The new specification (`docs/v3_specification/00_Foundation/01_README.md`) is explicit: *"It
is not a record of any prior work. The application is specified as a new product."* It defines
a different architecture from the prior, now fully removed V2 implementation. `src/ollama_llm_bench/`
does not exist at all on this branch currently — the "Current codebase" column below describes
that prior V2 implementation for historical context only:

| Aspect | Current codebase | Spec v3 |
|---|---|---|
| Data structures | `@dataclass(frozen=True, slots=True, kw_only=True)` | `msgspec.Struct(frozen=True, kw_only=True, gc=False)` everywhere cross-boundary |
| Interfaces | `ABC` (`backend/core/interfaces.py` god-file) | `typing.Protocol` by default, one `protocols.py` per module, no god-file |
| Layering | `backend/core` + `backend/services` / `ui/qt_classes` + `ui/controllers` + `ui/widgets` | Three layers: `backend/` (Qt-free) → `adapters/` (new Qt-binding-glue layer) → `ui/` (PySide6) |
| Build backend | hatchling | `uv_build` |
| YAML | `pyyaml` | `ruamel.yaml` (comment-preserving) |
| New runtime deps | — | `msgspec`, `psygnal`, `structlog`, `icontract`, `platformdirs`, `click` |
| Concurrency | `QtBenchmarkFlowApi` / `BenchmarkExecutionTask(QRunnable)` | Synchronous Qt-free backend, one dedicated dispatcher thread (DD-38), `TaskRunner` Protocol port over `QThreadPool` |
| Provider IDs | (current scheme) | Internal auto-generated UUID4; `name` is the user-facing unique field (DD-33) |
| Architecture enforcement | Ruff + mypy | + `import-linter`, `pytest-archon`, `icontract` design-by-contract on every public `api.py` function |

The spec is **complete and self-contained**: 17 top-level folders, ~131 markdown files,
~40,000 lines, covering 8 UI screens, 62 modules, a 15-table SQLite schema, 71 numbered
design decisions (DD-01..DD-71), a 4-category/20+-leaf error taxonomy, 12 chart kinds, and
full NFR/distribution/risk documentation. Six parallel research passes confirm it is
implementation-ready with **zero blocking open questions** — see
`docs/v3_specification/15_Risks_and_Open_Questions/02_OPEN_QUESTIONS.md`.

## Current baseline

The rewrite is happening on `feature/spec-v3-implementation`. The spec is vendored in-repo at
`docs/v3_specification/` (read-only, committed) — every path reference in this planning
package uses that prefix.

`.claude/CLAUDE.md` and all 14 rule files under `.claude/rules/` are already rewritten to the
spec-v3 conventions (`msgspec.Struct`, Protocol-first, 3-layer architecture, `uv_build`, etc.).
`.claude/agents/` has all 7 recommended agents (architect, coder, debugger, docs-writer,
investigator, spec-conformance-reviewer, tester) and `.claude/skills/` has all 16 recommended
skills. `.claude/hooks/` has 11 shell scripts wired up via `.claude/settings.json`, there are 7
`hookify.*.local.md` rule files, and `.mcp.json` has the `context7` MCP server configured. See
`05_CLAUDE_SETUP_RECOMMENDATIONS.md` for the rationale behind this `.claude/` setup.

`src/ollama_llm_bench/` and `tests/` do not exist at all on this branch — this is a clean
slate, not a codebase with old content to strip out.

## What's still open

`docs/adr/` does not exist yet, and the three ADRs proposed in
`docs/v3_specification/15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md` (programmatic
Qt-Widgets theming, scoped reactive stores + event bus, `uv_build` + unsigned distribution)
remain `Status: proposed`, even though the rest of the spec already builds on them as settled.
Ratifying them — promoting them to `docs/adr/0001..0003` with status `accepted` — is part of
Phase 0, since rejecting any of them now would invalidate large parts of the spec already
approved by requesting this rewrite.

The rest of Phase 0's scaffold work is listed in `01_PHASE_BREAKDOWN.md`'s Phase 0 section.

## Why a phased, story-based breakdown (not one giant task)

1. **Context-window reality.** No single Claude Code session can hold all 131 spec files,
   62 module contracts, and the resulting ~15-20k lines of new code in context at once.
   The work must be split into units small enough for one focused session each, while each
   unit still has enough spec context attached to be correct on its own.
1. **Dependency order matters.** The module-layering map in
   `docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md` §3 is a strict inward-pointing DAG
   (`ui → adapters → backend feature services → backend shared infra`). Building UI before
   the backend services it depends on (or backend services before the domain/errors/events
   foundation) produces unimplementable stubs and rework.
1. **Traceability prevents requirement loss.** The spec already defines the exact mechanism
   for this in `14_Process_and_Traceability/`: a **story** cites the spec clauses, module
   paths, acceptance criteria, and edge-case ids it implements; a generated
   `traceability.yaml` plus a validator (`just trace-check`) fails the build if any spec
   clause, module, or `08-I` edge case has no story/test covering it. **This plan reuses that
   mechanism rather than inventing a parallel one** — see `02_STORY_PROCESS.md`.
1. **Verifiable gates per phase.** Each phase below ends with a concrete, scriptable
   definition-of-done (ruff, mypy --strict, import-linter, pytest-archon, pytest at the
   layer's coverage target) so a phase is either provably done or not — no partial-credit
   ambiguity for an agent to misjudge.

## How to use this package

1. Ratify the 3 proposed ADRs and complete the remaining Phase 0 scaffold work (see
   `01_PHASE_BREAKDOWN.md`'s Phase 0 section).
1. Read `01_PHASE_BREAKDOWN.md` for the phase sequence and what each phase must produce.
1. Read `02_STORY_PROCESS.md` to understand how phases turn into individual Claude Code
   work sessions.
1. Hand `03_CLAUDE_CODE_KICKOFF_PROMPT.md` to a Claude Code session to continue Phase 0. Every
   later phase is kicked off the same way — by invoking this project's own `investigator` →
   `architect` agents against the phase's spec folders (now at `docs/reference_planning_docs/`
   for this planning package, `docs/v3_specification/` for the spec itself) to produce that
   phase's stories, then
   `coder` → `tester` → `docs-writer` per story.
