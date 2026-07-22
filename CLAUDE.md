# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## What this project is

**Ollama LLM Bench** is a single-window, single-user PySide6 desktop application that
benchmarks Large Language Models served locally (Ollama, LM Studio, llama.cpp) or in the
cloud (OpenAI/Azure, Anthropic, Gemini). It is being built **from a complete, binding
specification** at `docs/v3_specification/` (17 top-level folders covering every UI screen,
service, data model, and quality requirement). There is no prior codebase to reverse-engineer
conventions from — this file, the rules, and the skills below are themselves derived from that
specification, not from existing code.

**Spec authority statement:** `docs/v3_specification/` is the single source of truth. Never
invent application behavior. Every non-trivial implementation decision should be traceable to a
specific spec file. If the spec is silent or ambiguous on something you need to decide, stop
and ask rather than guess.

## AI config locations

- `CLAUDE.md` — this file.
- `.claude/settings.json` — hooks and project settings.
- `.claude/agents/`, `.claude/skills/`, `.claude/rules/` — agent, skill, and rule definitions
  (reference tables below).
- `.claude/hooks/` — shell scripts invoked by `.claude/settings.json`.
- `.claude/hookify.*.local.md` — declarative pattern-blocking rules (hookify plugin format).
- `.mcp.json` (repo root) — project-scoped MCP servers.
- `.pre-commit-config.yaml` (repo root) — git-level quality gate, separate from but
  complementary to the hooks above (see `rules/linting.md` and `rules/testing.md`).
- `docs/stories/`, `docs/adr/` — the implementation-tracking artifacts (see
  `skills/story-and-traceability-workflow/`).

## Non-negotiable architecture constraints

These recur across nearly all of `docs/v3_specification/` and must hold on every turn, not
just when a relevant rule/skill happens to be loaded:

- **Three layers, strictly inward-pointing**: `backend/` (zero PySide6 imports, zero asyncio)
  → `adapters/` (the only layer allowed to import both PySide6 and backend) → `ui/` (PySide6
  widgets; reaches the backend only through Protocols and the adapters layer). `compose.py` is
  the single composition root and the only file allowed to wire concrete implementations.
- **`msgspec.Struct(frozen=True, kw_only=True, gc=False)`** for every cross-boundary data
  structure — never `@dataclass` for anything that crosses a module boundary, never
  `dict[str, Any]` for structured data.
- **`typing.Protocol` is the default interface mechanism.** `abc.ABC` only when shared
  base-class implementation logic is genuinely required. No single god-file of interfaces —
  every module owns its own `protocols.py`.
- **No `asyncio`, `anyio`, or `qasync` anywhere.** The backend is synchronous and Qt-free. A
  single dedicated dispatcher thread runs the benchmark pipeline; background work runs as
  blocking units on a `QThreadPool`-backed `TaskRunner`. Never complete a unit of work via a
  queued Qt signal from a non-GUI thread — the dispatcher blocks on a `Future` with no event
  loop running to deliver that signal.
- **Strictly serial execution.** At most one LLM inference call is in flight anywhere in the
  app at any moment, app-wide (not just per run) — enforced by the single `InferenceActivityStore`
  gate. This is a deliberate design constraint, not a tunable default; do not add a
  parallelism/concurrency setting for inference.
- **Single DB writer, no migrations, ever.** Exactly one SQLite write connection guarded by one
  lock. Schema evolves only through purely additive steps (new nullable column, new table, new
  index) within the same major version — never `UPDATE`/backfill/rewrite of existing rows. A
  newer-than-expected or cross-major schema is a hard startup error, not an auto-upgrade.
- **`provider_id` is an internal, auto-generated UUID4 — never shown or entered by the user.**
  `name` is the user-facing, unique display field. Historical runs/results store a *snapshot* of
  the name at the time they were created; renaming a provider later never rewrites history.
- **The judge produces no numeric score.** Final verdict is strictly binary (`PASS`/`FAIL`,
  never `UNKNOWN`); the cosine-similarity score is the only numeric quality value anywhere in
  the app.
- **`icontract` design-by-contract on every public `api.py` function**, guarding programmer
  invariants only — never user input, file content, or provider responses. A contract violation
  is a `ProgrammerError` that crashes the process; ordinary invalid input is handled as data,
  via the error taxonomy, not via a contract.
- **No telemetry, no auto-update mechanism, ever.**

## Commands

```bash
uv sync                      # install
just check                   # full local CI mirror: lint, format-check, typecheck, import-check, arch-test, test
just lint                    # ruff check
just format                  # ruff format (+ markdown/toml/yaml/sql formatters, see rules/formatting.md)
just typecheck                # mypy --strict
just import-check            # import-linter contracts
just arch-test                # pytest-archon + AST architecture tests
just test                    # pytest
just coverage-layers          # per-layer coverage gates (backend >=90%, view-models/controllers >=85%, widgets >=60%)
just trace                   # regenerate traceability.yaml (repo root) from docs/stories/
just trace-check             # fail if any spec clause, module, or edge case is uncovered
```

## How work is tracked

Work is tracked as **stories** under `docs/stories/`, one Markdown file per story, in the
format defined by `docs/v3_specification/14_Process_and_Traceability/02_STORY_FORMAT.md` — see
`skills/story-and-traceability-workflow/`. One story per coding session. Never mark a story
`done` without `just trace-check` passing and its acceptance criteria proven by a real test.

## Orchestration discipline

The top-level session orchestrates; it does not do large amounts of file-by-file editing in
its own context when a subagent could do it instead. Delegate a story's substantial
implementation, a research pass, or a review to one `Agent`/Task call and let that subagent make
as many internal tool calls as it needs in its own isolated context — don't spawn a subagent for
a single trivial lookup, and don't loop dozens of `Edit` calls yourself in the main session when
one `coder` delegation would do it more cleanly. Keep any one batch of parallel subagents to
roughly eight or fewer — beyond that, coordination overhead exceeds the benefit. Ask every
subagent to return a concise, structured summary (what changed, what's left), not a transcript.

## Quality gates — do not ignore or bypass

- A `ruff`/`mypy` issue reported in a file you touched must be fixed before you consider a story
  done. "Pre-existing" is not a valid reason to skip it — the lint/format hooks in
  `.claude/settings.json` only ever fire on files you've edited, so there is no legacy debt to
  hide behind in this rewrite. If something is genuinely out of scope of the current story, say
  so explicitly in the story's notes instead of silently leaving it.
- Never run `git commit --no-verify`/`-n`. Never delete or comment out a failing test to make a
  suite pass. Never weaken a `ruff`/`mypy` rule to silence a finding without raising it first.
- `.pre-commit-config.yaml` runs fast checks at commit time; the full test suite and
  `just trace-check` run at push time. Both are real git hooks (separate from the
  `.claude/settings.json` hooks above) — never bypass either.

## Self-discovery

Before assuming a convention, tool, or piece of context doesn't exist: check `.claude/skills/`
(via the Skill mechanism) for a relevant skill, check the MCP servers available to you (e.g.
`context7` for current third-party library documentation — see `.mcp.json`), and check
`docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md` for the module you're
working in. Don't rely solely on what's spelled out in your own immediate prompt.

## Never do this

- `@dataclass` for anything that crosses a module boundary (use `msgspec.Struct`).
- `abc.ABC` for a new interface unless it carries shared implementation logic (use `Protocol`).
- `import asyncio` / `import anyio` / `qasync` anywhere in `src/`.
- `setStyleSheet(...)` outside `src/ollama_llm_bench/ui/theme/`.
- A bare `except:` or `except Exception: pass`.
- A literal secret value (API key) anywhere in code, config, or a DB column — only an
  environment-variable *name* is ever stored.
- A UI controller holding a backend Store/Service Protocol directly — it may only hold its
  per-widget Gateway Protocol from the adapters layer.
- Marking a story `done` without `just trace-check` passing.

## Rules Reference

| Rule | Globs | Description |
|------|-------|-------------|
| [coding-style](rules/coding-style.md) | `src/**/*.py` | msgspec/Protocol conventions, naming, complexity limits |
| [project-structure](rules/project-structure.md) | `src/**/*.py`, `pyproject.toml` | The 3-layer tree, module public-surface contract, import-linter contracts |
| [concurrency-standard](rules/concurrency-standard.md) | `src/ollama_llm_bench/backend/**`, `src/ollama_llm_bench/adapters/qt_runnables/**` | Dispatcher thread, `TaskRunner`, `CancellationToken`, single-inference gate |
| [error-handling-standard](rules/error-handling-standard.md) | `src/**/*.py` | The 4-category error taxonomy, adapter-boundary translation, retry policy |
| [logging](rules/logging.md) | `src/**/*.py` | `structlog`, the two-stream `run.*`/`app.*` split |
| [testing](rules/testing.md) | `tests/**/*.py`, `src/**/tests/**/*.py` | Pyramid, `pytest-qt`, contract-test suites, per-layer coverage |
| [external-libraries](rules/external-libraries.md) | `pyproject.toml`, `src/**/*.py` | Approved/banned dependency table |
| [formatting](rules/formatting.md) | `*.py`, `*.md`, `*.toml`, `*.yaml`, `*.sql`, `pyproject.toml` | Ruff + multi-language formatting |
| [linting](rules/linting.md) | `*.py`, `pyproject.toml` | Ruff, mypy --strict, import-linter, pytest-archon, icontract |
| [uv-project](rules/uv-project.md) | `pyproject.toml`, `uv.lock` | `uv_build`, dependency management |
| [pyside6-app-development](rules/pyside6-app-development.md) | `src/ollama_llm_bench/ui/**/*.py`, `src/ollama_llm_bench/adapters/**/*.py` | Theme/token system, Gateway-only dependency rule, `QRunnable` pattern |
| [repository-documentation](rules/repository-documentation.md) | `*.md`, `docs/**/*.md` | README/docs structure for this rewrite |
| [code-documentation](rules/code-documentation.md) | `src/**/*.py` | Docstring style, `icontract` interplay |
| [traceability-and-stories](rules/traceability-and-stories.md) | `docs/stories/**/*.md`, `docs/adr/**/*.md` | Story/spec-citation discipline |

## Skills Reference

| Skill | Use when |
|-------|----------|
| [msgspec-domain-modeling](skills/msgspec-domain-modeling/) | Defining/modifying any cross-boundary DTO or enum |
| [protocol-first-interfaces](skills/protocol-first-interfaces/) | Defining a Protocol, or wiring a widget's Gateway |
| [three-layer-architecture](skills/three-layer-architecture/) | Creating a new module, unsure which layer it belongs in |
| [concurrency-and-cancellation](skills/concurrency-and-cancellation/) | Touching the pipeline, `TaskRunner`, cancellation, or the inference gate |
| [icontract-design-by-contract](skills/icontract-design-by-contract/) | Writing/reviewing a module's `api.py` |
| [error-taxonomy-and-redaction](skills/error-taxonomy-and-redaction/) | Raising/catching an exception, touching secrets or logs |
| [pyside6-spec-ui](skills/pyside6-spec-ui/) | Writing/reviewing a PySide6 widget, dialog, or theming code |
| [story-and-traceability-workflow](skills/story-and-traceability-workflow/) | Creating a story, finishing implementation work |
| [acceptance-criteria-authoring](skills/acceptance-criteria-authoring/) | Writing ACs for a story or tests for an AC |
| [edge-case-coverage](skills/edge-case-coverage/) | A story cites an `EC-` id, or you're deciding what edge-case tests a module needs |
| [testing-standard-pyqt](skills/testing-standard-pyqt/) | Writing any test |
| [adr-authoring](skills/adr-authoring/) | A decision is architecturally significant and costly to reverse |
| [secrets-and-provider-config](skills/secrets-and-provider-config/) | Touching provider credentials, `ProviderConfig`, settings import/export |
| [sqlite-persistence-conventions](skills/sqlite-persistence-conventions/) | Touching a persistence store or the SQLite schema |
| [create-mermaid-diagrams](skills/create-mermaid-diagrams/) | Creating or updating an architecture/flow diagram |
| [project-docs](skills/project-docs/) | Writing/updating project documentation outside a story file |

## Agents Reference

| Agent | Model | Use after |
|-------|-------|-----------|
| [investigator](agents/investigator.md) | Haiku | Starting any new phase/story — read-only mapping of what exists vs. what the spec requires |
| [architect](agents/architect.md) | Opus | Investigation complete — turns findings into `docs/stories/*.md` |
| [coder](agents/coder.md) | Sonnet | A story is `ready` — implements exactly one story |
| [tester](agents/tester.md) | Sonnet | `coder` finishes a story — writes its acceptance-criteria tests |
| [debugger](agents/debugger.md) | Sonnet (escalate to Opus after 2 failed attempts on the same bug) | A test or CI failure isn't a quick fix |
| [docs-writer](agents/docs-writer.md) | Haiku | A story's public surface changed, or an ADR is needed |
| [spec-conformance-reviewer](agents/spec-conformance-reviewer.md) | Opus | A story's implementation is done — independent re-derivation of its ACs from the spec, before marking it `done` |

## Context management

When compacting, preserve: the current phase/story being worked, the list of modified file
paths, any outstanding `mypy`/`ruff`/`import-linter` failures by file, current `pytest` failure
count and names, and any `# type: ignore[code]` decisions made and why.

## Communication

Communicate for the reader, not for the specification.

When asking questions, explaining decisions, reporting progress, or describing issues:

* Use plain, concrete language instead of internal terminology or abstractions.
* Describe the actual behavior, scenario, or problem, not the document structure that defines it.
* Never assume the reader will look up requirement IDs, acceptance criteria, phases, tickets, or other references.
* If you refer to a requirement, restate its relevant meaning in the current message. References are for traceability only, never as the primary explanation.
* Provide enough context for the reader to understand and answer without opening other documents.
* Prefer concrete examples over abstract descriptions whenever they improve clarity.
* Explain *what* is happening, *why* it matters, and *what decision or action* is needed.
* Recommend a reasonable default when appropriate instead of delegating every decision to the reader.

**Rule of thumb:** Every message should be understandable on its own. If the reader must navigate project documentation to understand your question, explanation, or recommendation, rewrite it.
