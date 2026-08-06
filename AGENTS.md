# Ollama LLM Bench — how to work here

## Where this stands

Ollama LLM Bench is a single-window, single-user PySide6 desktop app that benchmarks LLMs served
locally (Ollama, LM Studio, llama.cpp) or in the cloud (OpenAI/Azure, Anthropic, Gemini).

**Stack.** Python 3.13, PySide6, msgspec, SQLite (single writer), pytest + pytest-qt, uv, ruff,
mypy --strict, import-linter, pytest-archon.

**State.** A v3 rewrite in progress, built entirely from `docs/v3_specification/` — there is no
prior codebase to reverse-engineer conventions from. 117 story files and 19 ADRs so far. The
active unit of work lives in `docs/stories/`; check for any story whose front-matter status isn't
`done` (Claude Code's SessionStart hook prints this as "Stories in progress").

**The spec is the authority.** `docs/v3_specification/`. Never invent behaviour; if it's silent
or ambiguous on something you must decide, stop and ask with a recommended default.

## The loop

Six phases. No feature code before a story (PLAN) exists.

| Phase  | Exit condition                                                       | Command                                          |
| ------ | -------------------------------------------------------------------- | ------------------------------------------------ |
| ORIENT | State read, unit of work named                                       | `git status`; read `docs/stories/`               |
| SPEC   | Mapped what exists vs. what the spec requires                        | `investigator` agent on `docs/v3_specification/` |
| PLAN   | A story exists under `docs/stories/` with cited spec clauses and ACs | `architect` agent                                |
| BUILD  | Story implemented, its AC tests written                              | `coder`, then `tester`                           |
| VERIFY | Gate green and spec conformance independently confirmed              | `just check`; `spec-conformance-reviewer`        |
| CLOSE  | Traceability regenerated, story marked `done`                        | `just trace`, `just trace-check`                 |

**Don't assume a convention, tool, or module doesn't exist — check first.** Before ORIENT
concludes, check for a relevant skill, check connected MCP servers (e.g. `context7` for
third-party docs), and check the module inventory
(`docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md`). Don't rely solely
on your own prompt.

**Advance without asking.** When VERIFY surfaces new gaps, plan and build them. Stop only to:

1. resolve a spec that's ambiguous or silent — ask, with a recommended default;
1. report a gate that's gone red twice for the same cause;
1. raise a decision that's architecturally significant and costly to reverse (write an ADR);
1. do anything irreversible or outside the repo — merge/push to `master`, tag, publish;
1. report new information contradicting the approved spec — never resolve that silently in code.

## Definition of Done

**Gate:** `just check` — lint, format-check, typecheck, import-check, arch-test, then the full
pytest run (`tests/unit tests/integration tests/e2e src`). ~2 minutes normally.

A unit of work is done when the gate is green **and** the implementation matches the spec cited
in the story. Tests passing against the wrong behaviour is not done.

- **Baseline first.** A ruff/mypy finding in a file you touched must be fixed — "pre-existing" is
  not an excuse here, since the lint/format hooks only ever fire on files you've edited.
- **Never accept "pre-existing and unrelated" without the exclusion test** — re-run with only the
  suspect file ignored, compare failure lists, record that output beside the claim.
- **Verify against blast radius, not module scope.** Run the full gate whenever a change can open
  a modal/dialog, block a thread, touch `compose.py` or startup/shutdown ordering, add/change an
  EventBus subscription or queued signal, or touch a shared fixture/`conftest.py`/Gateway
  Protocol — see "What will bite you" for what happens when you skip this.
- **A hang is a result.** ~2 minutes is normal; materially longer means hung — kill it and
  diagnose. No `pytest-timeout` is configured, so a blocking dialog produces no output at all.
- **Never run two full-suite verifications concurrently** — see "What will bite you".

Closing checklist — evidence, not assertion:

- [ ] Every acceptance criterion met, named with the test that proves it
- [ ] `just check` green, tail pasted; diffed against baseline, no new findings
- [ ] `just trace-check` passing
- [ ] Docs/ADRs updated for anything that changed the public surface
- [ ] Next step stated

## Git protocol

This repo does not use per-task branches — work happens directly on one long-lived feature branch.

```
master                                   protected — never developed on directly
  └── feature/spec-v3-implementation     the one working branch; all story work happens here
```

1. Stay on the current long-lived feature branch (`git branch --show-current`). Don't create a
   per-task sub-branch.
1. One story = a short commit series on that branch, Conventional Commits scoped to the story:
   `feat(story-097): ...`, `test(story-097): ...`, `fix(story-097): ...`, `docs(story-097): ...`.
1. Commit as you go within a story; don't batch a whole story into one commit.
1. Never `--no-verify`, never `--force`/`--force-push` — blocked outright, see Non-negotiables.
1. **Never merge, push to, or develop directly on `master`.** Final review and merge is the
   user's call, not the agent's.

## Delegation

You are the orchestrator: the main session holds the plan and the decisions, not file dumps or
test-log transcripts. Delegate anything shaped "read N files, come back with a conclusion."

| Work                                                                   | Delegate to                 |
| ---------------------------------------------------------------------- | --------------------------- |
| Map what exists vs. what a phase's spec requires (read-only)           | `investigator`              |
| Turn investigator findings into `docs/stories/*.md`                    | `architect`                 |
| Implement exactly one ready story                                      | `coder`                     |
| Write a story's acceptance-criteria tests                              | `tester`                    |
| Diagnose a red gate that isn't a one-line fix                          | `debugger`                  |
| Update README/architecture docs/ADRs after a story ships               | `docs-writer`               |
| Independent re-derivation of ACs from spec before marking a story done | `spec-conformance-reviewer` |

Never delegated: the decision about what the next step is, and the judgment about whether the
work satisfies the spec. Keep any batch to roughly eight or fewer subagents.

## Non-negotiables

| Rule                                                                                                                                                                                                                                      | Enforced by                                                                                                                                                                                                                                                                                                                                                                            |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No `@dataclass` across a backend/adapters boundary — use `msgspec.Struct(frozen=True, kw_only=True, gc=False)`                                                                                                                            | `hookify:block-dataclass-cross-boundary` + `tests/architecture/test_dtos.py`                                                                                                                                                                                                                                                                                                           |
| No `asyncio`/`anyio`/`qasync` anywhere in `src/`                                                                                                                                                                                          | `hookify:block-asyncio-imports`                                                                                                                                                                                                                                                                                                                                                        |
| At most one LLM inference call in flight app-wide                                                                                                                                                                                         | `tests/architecture/test_ui_gate_access.py`, `test_stability_dispatcher_thread_only.py`                                                                                                                                                                                                                                                                                                |
| No `setStyleSheet()` outside `ui/theme/`                                                                                                                                                                                                  | `hookify:block-setstylesheet-outside-theme` + `test_ui_theme_style_authority.py`, `test_main_window_style_authority.py`, `test_ui_shared_style_authority.py`                                                                                                                                                                                                                           |
| No bare `except:` / `except Exception: pass`                                                                                                                                                                                              | `hookify:block-bare-except`                                                                                                                                                                                                                                                                                                                                                            |
| No literal secret value anywhere (env-var name only)                                                                                                                                                                                      | `hookify:block-secret-literal`                                                                                                                                                                                                                                                                                                                                                         |
| Layers point inward only: `backend` never imports PySide6; `adapters` never imports `ui`; only `compose.py` wires concrete adapters; a UI controller holds only its own Gateway Protocol, never a backend Store/Service Protocol directly | import-linter contracts "Backend layer is Qt-free", "Only compose.py wires concrete adapters", "Adapters never import the UI layer" + `test_compose_line_budget.py` + per-widget boundary tests (`test_main_window_gate_access.py::test_controller_and_close_handler_hold_no_backend_protocol_directly`, `test_result_widget_boundaries.py`, `test_resume_benchmark_boundaries.py`, …) |
| Never `--no-verify` on commit, never `--force`/`-f` on push; never weaken a ruff/mypy rule or delete/skip a failing test just to make the gate green                                                                                      | `hookify:block-no-verify` (first half) — rest advisory                                                                                                                                                                                                                                                                                                                                 |
| `docs/v3_specification/` is never deleted/modified by an automated session                                                                                                                                                                | `hookify:protect-spec-folder`                                                                                                                                                                                                                                                                                                                                                          |
| Gate green + `just trace-check` passing + agent-memory mirrors in sync before a story is done                                                                                                                                             | pre-commit `pre-push` stage + `pr-gate.yml` lint job (`validate_traceability.py`, `sync-agent-files.py --check`)                                                                                                                                                                                                                                                                       |

Everything else the spec demands (Protocol-vs-ABC, icontract placement, provider_id/UUID
handling, judge binary-verdict shape, DB single-writer/no-migrations discipline, no telemetry or
auto-update, secrets/redaction) is real but has no tool-level enforcer today — it lives in the
relevant `.claude/rules/*.md`, loaded automatically when you touch a matching file. Don't
restate it here; go read the rule.

## End every turn with Next step

**Every turn that advances the work ends with this block.** Not after a research answer, not
after a partial run, not after a failure.

```markdown
## Next step

**State:** <where the work actually is, one line, citing evidence>
**Command:** `<exact command>`  — or "none — decision needed from you"
**Prompt:**
> <complete, copy-pasteable: names the unit of work, the artifacts to read first, and the
>  constraint most likely to be violated at this step>
```

- **Be honest.** "All ACs written" is not "all ACs verified." If the gate hasn't run, the state
  is *unverified*, whatever the checkboxes say.
- **Self-contained.** `"continue"` is not a prompt — it must work in a fresh session.
- **A decision is a valid next step.** State the options, recommend one. Never invent a command
  just to look productive.

## What will bite you

- **A six-line change that adds a blocking modal passes its own module's tests and hangs the
  whole integration suite.** It happened for real: the change passed its module's 41 tests, was
  independently reviewed and approved, then hung every integration test — each one builds the
  real app offline, reaches that state, and waits forever for a click that never comes. No
  `pytest-timeout` is configured, so the run produces no output at all; it just never ends.
  Anything that can open a dialog, block a thread, or touch startup ordering needs the full gate.
- **Two agents running the full suite at once manufacture failures that look real.**
  Timing-sensitive Qt tests fail under contention in a way indistinguishable from a real
  regression — this has already produced two independent agents reporting the same non-existent
  failure and agreeing with each other. Never run two full-suite verifications concurrently,
  including two subagents that each run one.

## Where things live

- Spec (authority, never edited without explicit approval): `docs/v3_specification/`
- Decisions: `docs/adr/`
- Work tracking: `docs/stories/` (one file per story, strict front-matter format)
- Traceability record: `traceability.yaml` (repo root) — regenerate with `just trace`
- Rules are `paths:`-scoped under `.claude/rules/`; skills and subagents load themselves.
- `.claude/` is canonical for Claude-specific mechanics. `.codex/agents/*.toml` is generated —
  never hand-edit; run `python3 scripts/sync-agent-files.py --apply`.

## Communication

Write for the reader, not for the spec. Plain language, no unexplained requirement/AC/phase/
ticket IDs without restating what they mean, enough context to answer without opening another
document, concrete examples over abstractions. Say what's happening, why it matters, and what's
needed — recommend a default rather than asking an open-ended question. If understanding your
message would require the reader to go read project docs, rewrite it.
