---
name: Phase 2 Task 5 — JudgePromptService design decision
description: Architectural decision for JudgePromptService implementation approach and testing patterns confirmed during planning on 2026-04-16
type: project
---

Chose **Option B** (separate module-level constants + dispatch dict) for JudgePromptService. Rejected a single-template-with-rubric-placeholder (Option A) and external YAML templates (Option C).

**Why:** Matches existing codebase patterns (`app_settings_service.py`, `task_file_loader.py`). Keeps each rubric independently tunable. No file I/O dependency for a zero-dependency service.

**How to apply:** When designing other stateless, multi-variant services (evaluators, parsers), default to module-level constant dispatch tables rather than parameterized templates. Use `dict[SomeEnum, str]` keyed on domain enum for variant selection.

---

Key facts confirmed as of 2026-04-16 (Phase 1 complete, Phase 2 in progress):

- `JudgePromptServiceApi` Protocol: already in `interfaces.py` lines 1033–1039 with `@runtime_checkable`.
- `TaskType` has exactly 8 values; all 8 are covered in the dispatch table (`CODE_GENERATION` and `CODE_REVIEW` share a constant; `TEXT_REWRITE` and `SUMMARIZATION` share a constant).
- `BenchmarkTask` uses `golden_answer`, `pass_criteria`, `fail_criteria` (V2 fields) — NOT V1 fields `most_expected`, `pass_option`, `incorrect_direction`.
- `BenchmarkResult.sanitized_response` takes priority over `raw_response`; empty string is treated as absent (fallback to raw).
- `pyproject.toml` sets `log_level = "WARNING"` globally — `caplog` works without overrides for WARNING-level messages. JudgePromptService itself logs nothing (no error paths).
- Tests do NOT mock dataclasses — construct `BenchmarkTask` and `BenchmarkResult` directly.
- Private module constants (e.g., `_DEFAULT_JUDGE_SYSTEM_PROMPT`) are imported in tests for completeness verification. This is accepted pattern in this project.
- `JudgePromptService` has no ABC inheritance — Protocol conformance is structural only. No `@override` annotation needed.
- The default prompt constant is intentionally kept even though all 8 TaskType values are mapped — guards against future TaskType additions.
