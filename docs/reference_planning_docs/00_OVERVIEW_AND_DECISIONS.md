# Ollama LLM Bench — Spec v3 Ground-Up Rewrite: Implementation Plan

**Status:** Draft — for human review before handing to Claude Code
**Purpose:** Defines how to divide the full rewrite of this application (per
`App_Specification_Ollama_Bench_Final/`, the spec in
`/Users/ok/Documents/ReviewAndAnalysesOfSpec3/`) into ordered, traceable, independently
implementable tasks, so that a Claude Code session (or a sequence of them) can execute the
rewrite on this branch without losing any requirement.

This folder is scratch/planning material per this project's own `.claude/CLAUDE.md`
("Temporary or scratch artifacts ... live under `.AdditionalDocs/`"). Nothing in this folder
is itself a code change.

## Files in this package

| File | Purpose |
|---|---|
| `00_OVERVIEW_AND_DECISIONS.md` | This file — what the rewrite is, and decisions that need your sign-off before Claude Code starts. |
| `01_PHASE_BREAKDOWN.md` | The 13 ordered phases, each mapped to specific spec folders/files and module-inventory entries, with a definition-of-done per phase. |
| `02_STORY_PROCESS.md` | How each phase is broken further into spec-traceable "stories" using the spec's own story format, plus one worked example. |
| `03_CLAUDE_CODE_KICKOFF_PROMPT.md` | A ready-to-paste prompt for the Claude Code session that will execute Phase 0. |

## What this rewrite actually is

The new specification (`00_Foundation/01_README.md`) is explicit: *"It is not a record of
any prior work. The application is specified as a new product."* It defines a different
architecture from what's currently in `src/ollama_llm_bench/`:

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
~38,500 lines, covering 8 UI screens, 62 modules, a 15-table SQLite schema, 71 numbered
design decisions (DD-01..DD-71), a 4-category/20+-leaf error taxonomy, 12 chart kinds, and
full NFR/distribution/risk documentation. Six parallel research passes (notes preserved in
`/Users/ok/Library/.../outputs/spec_research/*.md` from this session, not committed) confirm
it is implementation-ready with **zero blocking open questions** — see
`15_Risks_and_Open_Questions/02_OPEN_QUESTIONS.md`.

## Why a phased, story-based breakdown (not one giant task)

1. **Context-window reality.** No single Claude Code session can hold all 131 spec files,
   62 module contracts, and the resulting ~15-20k lines of new code in context at once.
   The work must be split into units small enough for one focused session each, while each
   unit still has enough spec context attached to be correct on its own.
2. **Dependency order matters.** The module-layering map in
   `14_Process_and_Traceability/01_MODULE_INVENTORY.md` §3 is a strict inward-pointing DAG
   (`ui → adapters → backend feature services → backend shared infra`). Building UI before
   the backend services it depends on (or backend services before the domain/errors/events
   foundation) produces unimplementable stubs and rework.
3. **Traceability prevents requirement loss.** The spec already defines the exact mechanism
   for this in `14_Process_and_Traceability/`: a **story** cites the spec clauses, module
   paths, acceptance criteria, and edge-case ids it implements; a generated
   `traceability.yaml` plus a validator (`just trace-check`) fails the build if any spec
   clause, module, or `08-I` edge case has no story/test covering it. **This plan reuses that
   mechanism rather than inventing a parallel one** — see `02_STORY_PROCESS.md`.
4. **Verifiable gates per phase.** Each phase below ends with a concrete, scriptable
   definition-of-done (ruff, mypy --strict, import-linter, pytest-archon, pytest at the
   layer's coverage target) so a phase is either provably done or not — no partial-credit
   ambiguity for an agent to misjudge.

## Decisions that need your sign-off before Claude Code starts

These are real forks in the road. I did not pick silently — each has a recommendation, but
you should confirm before Phase 0 begins, because reversing course mid-rewrite is expensive.

### D1. Branch strategy
The repo is currently on `feature/v2-app-redesign` (which already shipped the existing V2
app — the one being thrown away). Your instruction was "the branch where we need do changes" —
**recommendation: keep working on `feature/v2-app-redesign`** (treat the wipe-and-rebuild as
new commits on this branch, matching what you described), rather than branching again. If you'd
rather preserve the current V2 implementation's history untouched and do the rewrite on a new
branch (e.g. `feature/v3-spec-rewrite`) cut from here, say so before Phase 0 — it's a one-line
`git checkout -b` change to the kickoff prompt either way.

### D2. Vendoring the spec into the repository
The spec currently lives outside this repo, at
`/Users/ok/Documents/ReviewAndAnalysesOfSpec3/App_Specification_Ollama_Bench_Final/` (a
separate mounted folder). A Claude Code session working purely inside
`ollama_llm_bench/` will not have it in context unless it's copied in.
**Recommendation: copy the entire `App_Specification_Ollama_Bench_Final/` folder into the
repo at `docs/spec/`** (read-only, committed) as the very first action of Phase 0. This makes
the spec self-contained with the code it describes, matches the spec's own claim to be
self-contained, and lets every later Claude Code session (and `investigator`/`architect`
agents) `Read`/`Grep` it directly. Confirm you're fine with ~3.6MB of markdown+HTML living in
the repo (it has 12 `mockup.html` files that are visually large but text-light).

### D3. Reconciling `.claude/CLAUDE.md` and `.claude/rules/*` with the new spec
The project's current `.claude/CLAUDE.md` and `.claude/rules/*.md` encode the **old**
conventions (dataclass, ABC-first, hatchling, pyyaml, `backend/core+services`). These directly
contradict the new spec's `16_Engineering_Standards/`. If left as-is, the `python-developer`
skill and every coding agent will keep nudging implementation back toward the old conventions.
**Recommendation: Phase 0 includes rewriting `.claude/CLAUDE.md` and the affected rule files
(`coding-style.md`, `project-structure.md`, `external-libraries.md`, `uv-project.md`,
`testing.md`, `formatting.md`) to mirror `16_Engineering_Standards/` verbatim** (the spec is
now the authority; the old rules describe a codebase that no longer exists after Phase 1).
`logging.md`, `pyside6-app-development.md`, and `repository-documentation.md` need targeted
edits (structlog instead of stdlib logging; the new concurrency/threading model; the new
`docs/stories`+`docs/adr` structure) rather than full rewrites.

### D4. The three unratified proposed ADRs
`15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md` lists three architecturally significant
decisions (programmatic Qt-Widgets theming, scoped reactive stores + event bus, `uv_build` +
unsigned distribution) still marked `Status: proposed`, not formally accepted — even though
the rest of the spec already builds on them as settled. **Recommendation: ratify all three as
part of Phase 0** (promote to `docs/adr/0001..0003`, status `accepted`) since rejecting any of
them now would invalidate large parts of the spec you've presumably already approved by asking
for this rewrite. Flagging only so it's a conscious choice, not a silent one.

### D5. Scope of "remove everything"
Confirm this means: delete `src/ollama_llm_bench/` and `tests/` entirely and rebuild from
empty per the spec's project structure; replace `docs/*.md` (they describe the old V2
architecture) with the spec-driven `docs/stories/`, `docs/adr/`, and a new
`docs/architecture.md`; keep `LICENSE`, `.git*`, `.editorconfig` (will be regenerated to spec's
values), and `.claude/agents/*` (the investigator/architect/coder/tester/docs-writer agents are
reusable — only their *inputs*, i.e. CLAUDE.md and rules, change per D3). Reset
`CHANGELOG.md` to a fresh `[Unreleased]` section noting the rewrite. If any of this is wrong,
tell me before Phase 0 runs `rm -rf`.

## How to use this package

1. Resolve D1–D5 above (or accept the recommendations).
2. Read `01_PHASE_BREAKDOWN.md` for the phase sequence and what each phase must produce.
3. Read `02_STORY_PROCESS.md` to understand how phases turn into individual Claude Code
   work sessions.
4. Hand `03_CLAUDE_CODE_KICKOFF_PROMPT.md` to a Claude Code session to begin Phase 0. Every
   later phase is kicked off the same way — by invoking this project's own `investigator` →
   `architect` agents against the phase's spec folders to produce that phase's stories, then
   `coder` → `tester` → `docs-writer` per story.
