# Turning a Phase into Stories

Each phase in `01_PHASE_BREAKDOWN.md` is still too large for one Claude Code coding turn. The
spec already defines the right atomic unit — a **story** — in
`docs/v3_specification/14_Process_and_Traceability/02_STORY_FORMAT.md`. Reuse it verbatim rather than
inventing a different task format; this is what keeps the rewrite traceable back to the spec
and lets `just trace-check` mechanically prove nothing was skipped.

## Who writes the stories

For each phase, run this project's existing agent pipeline (already defined in
`.claude/agents/`) against that phase's spec folders, in order:

1. **`investigator`** — read-only pass over the phase's spec files (listed in
   `01_PHASE_BREAKDOWN.md`) and the *current* state of `src/ollama_llm_bench/` (what previous
   phases already built). Output: a map of what exists vs. what this phase still needs, and
   which spec clauses/modules are still unaddressed.
1. **`architect`** — turns the investigator's findings into a set of story files under
   `docs/stories/`, one per module or tightly-coupled module group, sized S/M/L per the
   spec's sizing rules (S = 1 module/1-3 AC, M = ≤3 modules/≤6 AC, L = ≤5 modules/≤10 AC,
   split if larger). The architect must set each story's `spec_clauses:` and `modules:`
   front-matter from the phase's spec inputs — **a story that cites no spec clause is
   rejected**, since an unlinked story is exactly how a requirement gets silently dropped.
1. **`coder`** — implements exactly one story at a time (per its own scoping rule: "Surgical
   implementation of one plan step at a time"). Never lets a coder session span multiple
   stories — that's how partial/half-tested code creeps in.
1. **`tester`** — writes the story's acceptance-criteria tests (Given/When/Then, table-driven,
   or Hypothesis invariant, per `05_ACCEPTANCE_CRITERIA_PATTERNS.md`) and runs `just check`.
1. **`docs-writer`** — updates `docs/architecture.md` / module docstrings if the story changed
   the public surface; this is cheap to do per-story rather than batched at the end.

Run `debugger` ad hoc whenever `tester` or CI surfaces a failure that isn't a quick fix.

## Why not just write all ~60 stories up front

The architect agent should generate a phase's stories from a fresh `investigator` pass at the
start of that phase, not all 60+ up front from this planning session. Reasons:

- A story written against Phase 6 before Phases 1-5 exist would have to guess at the exact
  shape of dependencies that don't exist yet — likely wrong in some detail, silently
  reintroducing the requirement-loss risk this whole plan exists to prevent.
- The module inventory's "Independent test target" and "Implementer notes" columns are exact
  enough that the architect agent can derive correct stories mechanically from the spec
  files — this isn't creative work that benefits from being done early.
- Re-running `investigator` at the start of each phase also catches drift (e.g. if Phase 3
  changed a Protocol signature Phase 6 was assuming).

## Per-phase story count guidance

Roughly one story per module-inventory row, occasionally two modules combined into one M/L
story when they're inseparable (e.g. `backend/yaml_formatter/` + `backend/task_files/`, which
share the same validation-severity model). Cross-cutting concerns that touch many modules
(e.g. "every `api.py` has an `icontract` decorator") become their own story rather than being
silently expected inside every other story — the architect should watch for these in Phase 0
and Phase 12 especially.

## Worked example: a Phase 1 story

This is the level of detail an `architect` agent should produce. Save as
`docs/stories/story-001-domain-enums-and-dtos.md`:

```markdown
---
id: STORY-001
title: Define the domain DTO and enum catalog as frozen msgspec Structs
status: ready
spec_clauses:
  - "10_Domain_and_Data/02_DTOS_AND_ENUMS.md#enum-catalog"
  - "10_Domain_and_Data/02_DTOS_AND_ENUMS.md#domain-records"
  - "16_Engineering_Standards/03_CODING_STANDARDS.md#cross-boundary-data-structures"
modules:
  - backend/domain
acceptance_criteria:
  - STORY-001-AC-1
  - STORY-001-AC-2
  - STORY-001-AC-3
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: L
---

## Goal
Provide every cross-boundary DTO and StrEnum the rest of the application imports from
`backend.domain`, exactly matching `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

## In scope
All 23 enums; all catalog and run-data domain records (`ProviderConfig`, `BenchmarkTask`,
`BenchmarkRun`, `BenchmarkResult`, etc.); the runtime-only service DTOs (`ChatRequest`,
`AppReadinessSnapshot`, `DriftWarning`, etc.); reusable constrained types via
`Annotated[..., msgspec.Meta(...)]`; patch records (`ResultPatch`, `RunStatusPatch`).

## Out of scope
Persistence (Phase 2), event payload structs (separate story in this phase — they're
domain-adjacent but owned by `backend/events`), any service logic.

## Spec inputs
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (full file — every record/enum is binding),
`16_Engineering_Standards/03_CODING_STANDARDS.md` §"Cross-boundary data structures".

## Design constraints
Every record: `msgspec.Struct(frozen=True, kw_only=True, gc=False)`. Every enum: `StrEnum`.
No `@dataclass` for anything in this module (the one exception in the coding standard is for
strictly-private `_internal/`-confined types, which this module — a pure DTO catalog — has
none of). No `dict[str, Any]` anywhere.

### STORY-001-AC-1
Given the enum catalog table in `02_DTOS_AND_ENUMS.md`, when `backend.domain` is imported,
then every one of the 23 listed enums exists as a `StrEnum` with exactly the member set the
spec lists (verified by a table-driven test enumerating the spec's own table).

### STORY-001-AC-2
Given any domain record class in `backend.domain`, when inspected via
`dataclasses`-equivalent introspection, then it is a `msgspec.Struct` with `frozen=True`,
`kw_only=True`, `gc=False` (verified by an architecture-test sweep over every class in the
module, per the project's `test_dtos_are_frozen_kw_only` convention named in the module
inventory).

### STORY-001-AC-3
Given `BenchmarkRun`, when constructed with a `judge_provider_id` set but no
`judge_provider_name` (or vice versa), then construction raises (the both-null-or-neither
invariant from the persistence schema's CHECK constraint must also be enforceable at the DTO
level via a `__post_init__`-equivalent msgspec validator, even though the hard DB-level
enforcement is Phase 2's job).

## Test plan
Unit tests only (`backend/domain/tests/`), no I/O. Hypothesis property test for the
constrained types (`CosineScore` rejects outside [0.0, 1.0], etc.).

## Definition of done
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` all pass
- [ ] `import-linter` confirms zero non-stdlib/non-msgspec imports
- [ ] ≥90% branch coverage
- [ ] `just trace` regenerates `traceability.yaml` with this story resolving its 3 spec clauses
- [ ] `01_MODULE_INVENTORY.md`'s `backend/domain` row needs no update (already accurate)
```

Every other story in every phase follows this same shape. The discipline that matters most:
**`spec_clauses:` must name real anchors in `docs/v3_specification/`, and `just trace-check` must be run
before a story is marked `done`** — that single check is what guarantees the rewrite can't
silently drop a requirement the way an unstructured task list could.
