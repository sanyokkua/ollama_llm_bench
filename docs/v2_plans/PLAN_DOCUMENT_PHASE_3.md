# Phase 3 — Evaluation Pipeline V2 — Implementation Plan

**Generated**: 2026-04-16
**Source**: docs/v2/v2-implementation-plan.md §3.1, §3.2, §3.3
**Scope**: Fix field-initialization bugs in the execution engine, implement Prompt Eval Mode (3.3), align cosine thresholds, and write unit tests for `BenchmarkExecutionTask`.

---

## Context

Phase 3 covers the three run modes: Speed Mode (3.1), Full Grading Mode (3.2), and Prompt Eval Mode (3.3).

**Speed Mode and Full Grading Mode are already implemented** in `BenchmarkExecutionTask` (Phase 2 output). The execution task correctly skips the judging stage for `RunMode.SPEED` and runs the 4-layer eval pipeline for `RunMode.FULL_GRADING`. All 4 evaluator classes are complete and tested. EventBus signals, pause/resume/stop, and streaming inference with 20 Hz buffering are all working.

**What Phase 3 must fix/add:**

1. Several `BenchmarkResult` fields are never set by the execution task: `run_type`, `source_language`, `target_language`, `has_thinking_block`, `prompt_hash`, and `cosine_embedding_model`.
2. Cosine similarity thresholds in `CosineSimilarityEvaluator` diverge from the V2 spec.
3. `RunMode.PROMPT_EVAL` (3.3) is completely unimplemented — no variant-based row creation, no variant prompt rendering.
4. `BenchmarkExecutionTask` has zero unit test coverage.

---

## Prerequisites

- Phase 0 complete: DB schema v2 exists, all 5 tables present in `SqLiteDataApi`.
- Phase 1 complete: `ProviderRegistry`, `EmbeddingService`, all provider clients implemented.
- Phase 2 complete: `BenchmarkExecutionTask`, `QtBenchmarkFlowApi`, `QtEventBus` fully implemented.
- All 4 evaluators implemented and tested: `RuleBasedEvaluator`, `KeywordEvaluator`, `CosineSimilarityEvaluator`, `LLMJudgeEvaluator`.
- `JudgePromptService`, `AppSettingsService`, `TaskFileLoader`, `LogFileWriter` implemented.

---

## Architecture Decisions (hard constraints)

1. `core/` — pure Python only. No Qt, no `openai`, no `yaml`.
2. `services/` — no Qt. All eval logic lives here.
3. All threading lives in `qt_classes/` only. `BenchmarkExecutionTask` is the only background worker.
4. UI updates only via `QtEventBus` signals — no widget mutation from background threads.
5. All dependencies injected via constructor with keyword-only args.
6. Absolute imports only.
7. `BenchmarkResult` is a frozen dataclass — use `dataclasses.replace(result, ...)` to produce updated copies.

---

## Task 1: Fix Missing Fields in `_build_initial_result`

**Files to modify**: `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py`
**Depends on**: None (standalone bug fix)

### Context

`_build_initial_result` creates the skeleton `BenchmarkResult` rows at pipeline initialization. Three fields that the DB schema requires populated from task/run context are never set, leaving them at their dataclass defaults (`""` or `None`):

- `run_type` defaults to `""` but must equal `str(run.run_mode)` (e.g., `"full_grading"`, `"speed"`)
- `source_language` defaults to `None` but should come from `task.source_language`
- `target_language` defaults to `None` but should come from `task.target_language`

These fields are used by the Results tab for column visibility and by the judge prompt service for translation tasks.

### Requirements

1. `_build_initial_result` MUST set `run_type=str(run.run_mode)` on every created row.
2. `_build_initial_result` MUST set `source_language=task.source_language` (may be `None`).
3. `_build_initial_result` MUST set `target_language=task.target_language` (may be `None`).
4. The method signature does NOT change — it remains `@staticmethod`.

### Existing Code Reference

- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` lines 908–930 — `_build_initial_result` body to be extended
- `src/ollama_llm_bench/backend/core/models.py` lines 152–167 — `BenchmarkRun` fields including `run_mode: RunMode`
- `src/ollama_llm_bench/backend/core/models.py` lines 132–150 — `BenchmarkTask` fields including `source_language: str | None` and `target_language: str | None`
- `src/ollama_llm_bench/backend/core/models.py` lines 170–256 — `BenchmarkResult` fields

### Implementation Guidance

In `_build_initial_result`, add three fields to the `BenchmarkResult(...)` constructor call:

```python
run_type=str(run.run_mode),            # "speed" | "full_grading" | "prompt_eval"
source_language=task.source_language,  # str | None
target_language=task.target_language,  # str | None
```

### Verification

- [ ] `uv run pytest tests/unit/services/ -q` still passes (no regressions)
- [ ] Grep `_build_initial_result` in `qt_benchmark_execution_task.py` — confirm `run_type`, `source_language`, `target_language` are set in the `BenchmarkResult(...)` call

---

## Task 2: Fix Inference Metadata — `has_thinking_block` and `prompt_hash`

**Files to modify**: `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py`
**Depends on**: None (standalone bug fix)

### Context

`_run_inference` stores the raw and sanitized response but never sets:
- `has_thinking_block`: `True` if the raw response contains `<think>` tags. The `sanitize_text` function in `text_utils.py` strips `<think>...</think>` blocks, but `_run_inference` doesn't detect their presence before stripping.
- `prompt_hash`: SHA-256 of the rendered user prompt, stored as `"sha256:<hex>"`. Required by the schema for deduplication and change detection.

Both fields are in `BenchmarkResult` Group 4 (Prompt Snapshot) and Group 5 (Raw Inference Output).

### Requirements

1. After computing `raw = inference_resp.llm_response or ""`, set `has_thinking_block = "<think>" in raw`.
2. Compute `prompt_hash = "sha256:" + hashlib.sha256(user_prompt.encode()).hexdigest()`.
3. Both values MUST be set in the `dataclasses.replace(result, ...)` call at the end of `_run_inference`.
4. `import hashlib` must be added at the top of the file (stdlib — no dependency change needed).

### Existing Code Reference

- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` lines 519–561 — `_run_inference` method
- `src/ollama_llm_bench/backend/utils/text_utils.py` lines 16, 157–184 — `REASONING_TAG_PATTERN` and `sanitize_text` (strips `<think>` tags; check `"<think>" in raw` BEFORE sanitizing)
- `src/ollama_llm_bench/backend/core/models.py` lines 199–210 — `BenchmarkResult` fields `has_thinking_block`, `prompt_hash`

### Implementation Guidance

At the top of the file, add `import hashlib` to the stdlib import block (alphabetically after `import dataclasses`).

In `_run_inference`, after `raw = inference_resp.llm_response or ""`:

```python
has_thinking = "<think>" in raw
prompt_hash = "sha256:" + hashlib.sha256(user_prompt.encode()).hexdigest()
sanitized = sanitize_text(raw)
```

In `dataclasses.replace(result, ...)`, add:

```python
has_thinking_block=has_thinking,
prompt_hash=prompt_hash,
```

`user_prompt` is already defined earlier in `_run_inference` as the first return value from `self._judge_prompt_service.build_inference_prompt(task)`.

### Verification

- [ ] `uv run pytest tests/unit/ -q` passes
- [ ] `import hashlib` is present in `qt_benchmark_execution_task.py`
- [ ] `has_thinking_block` and `prompt_hash` appear in the `dataclasses.replace(...)` call in `_run_inference`

---

## Task 3: Set `cosine_embedding_model` on Cosine Layer Results

**Files to modify**: `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py`
**Depends on**: None (standalone bug fix)

### Context

The DB schema has `benchmark_results.cosine_embedding_model TEXT nullable` — the name of the embedding model used for cosine similarity (e.g., `"bge-m3"`). This value comes from `BenchmarkRun.embedding_model`. Currently `_accumulate_layer_result` (a `@staticmethod`) never sets this field.

### Requirements

1. After `_accumulate_layer_result` is called for the COSINE layer, if the eval result is non-UNKNOWN (i.e., a similarity was computed), `cosine_embedding_model` MUST be set to `run.embedding_model` in the `accumulated` dict.
2. `_accumulate_layer_result` remains a `@staticmethod` — the setting happens in the calling method `_run_eval_pipeline`.
3. If `run.embedding_model` is `None`, set `cosine_embedding_model = None` (do not skip).

### Existing Code Reference

- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` lines 626–683 — `_run_eval_pipeline`
- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` lines 685–720 — `_accumulate_layer_result`
- `src/ollama_llm_bench/backend/core/models.py` lines 232–236 — `BenchmarkResult.cosine_embedding_model`, `cosine_similarity`
- `src/ollama_llm_bench/backend/core/models.py` lines 163–164 — `BenchmarkRun.embedding_model: str | None`
- `src/ollama_llm_bench/backend/core/models.py` lines 78–84 — `EvalLayer` enum

### Implementation Guidance

In `_run_eval_pipeline`, after `self._accumulate_layer_result(accumulated, layer, eval_result)`, add:

```python
if layer == EvalLayer.COSINE and eval_result.verdict != EvalVerdict.UNKNOWN:
    accumulated["cosine_embedding_model"] = run.embedding_model
```

`EvalVerdict` is already imported. `run: BenchmarkRun` is a parameter of `_run_eval_pipeline`. `EvalLayer` is already imported.

### Verification

- [ ] `uv run pytest tests/unit/services/evaluators/ -q` passes
- [ ] `"cosine_embedding_model"` appears in `_run_eval_pipeline` in `qt_benchmark_execution_task.py`

---

## Task 4: Align Cosine Similarity Thresholds with V2 Spec

**Files to modify**: `src/ollama_llm_bench/backend/services/evaluators/cosine_evaluator.py`
**Depends on**: None (standalone threshold fix)

### Context

The V2 plan (§3.2, Layer 3) specifies these auto-pass / auto-fail thresholds by `response_scope`:

| scope | auto-PASS (≥) | auto-FAIL (<) |
|---|---|---|
| `exact` | 0.92 | 0.30 |
| `contains` | 0.85 | 0.25 |
| `covers` | 0.75 | 0.20 |

The current implementation (`_SCOPE_THRESHOLDS`) uses:
- `EXACT: (0.90, 0.70)`, `CONTAINS: (0.75, 0.50)`, `COVERS: (0.65, 0.40)`

The fail thresholds are significantly higher than spec (e.g., 0.70 vs 0.30 for EXACT), causing responses with moderate cosine similarity to auto-fail rather than proceeding to the LLM judge. This reduces the role of Layer 4 and makes evaluation more conservative than intended.

### Requirements

1. Update `_SCOPE_THRESHOLDS` to exactly match the V2 spec values:
   - `ResponseScope.EXACT: (0.92, 0.30)`
   - `ResponseScope.CONTAINS: (0.85, 0.25)`
   - `ResponseScope.COVERS: (0.75, 0.20)`
2. Update the class docstring to reflect the new thresholds.
3. No other logic changes.

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/evaluators/cosine_evaluator.py` lines 27–31 — `_SCOPE_THRESHOLDS` dict
- `src/ollama_llm_bench/backend/services/evaluators/cosine_evaluator.py` lines 46–58 — class docstring listing thresholds
- `tests/unit/services/evaluators/test_cosine_evaluator.py` — existing tests that may assert specific threshold behavior and will need updating

### Implementation Guidance

Replace:

```python
_SCOPE_THRESHOLDS: dict[ResponseScope, tuple[float, float]] = {
    ResponseScope.EXACT: (0.90, 0.70),
    ResponseScope.CONTAINS: (0.75, 0.50),
    ResponseScope.COVERS: (0.65, 0.40),
}
```

With:

```python
_SCOPE_THRESHOLDS: dict[ResponseScope, tuple[float, float]] = {
    ResponseScope.EXACT: (0.92, 0.30),
    ResponseScope.CONTAINS: (0.85, 0.25),
    ResponseScope.COVERS: (0.75, 0.20),
}
```

Also update the class docstring lines to reflect the new values.

Then run existing tests — some will fail because they test with values in the old threshold range (e.g., a similarity of 0.85 for EXACT was previously UNKNOWN, now it's FAIL). Update those test cases to use values that exercise the new thresholds correctly. Do NOT change test intent, only the numeric input values.

### Verification

- [ ] `uv run pytest tests/unit/services/evaluators/test_cosine_evaluator.py -v` passes
- [ ] `_SCOPE_THRESHOLDS` in `cosine_evaluator.py` shows `(0.92, 0.30)`, `(0.85, 0.25)`, `(0.75, 0.20)`

---

## Task 5: Implement Prompt Eval Mode Execution (3.3)

**Files to modify**: `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py`
**Depends on**: Task 1 (correct initial result fields), Task 2 (prompt hash logic)

### Context

`RunMode.PROMPT_EVAL` lets users compare N prompt variants against a single model on the same task set. Currently `BenchmarkExecutionTask` never checks for `RunMode.PROMPT_EVAL` — the `run()` method only branches on `RunMode.SPEED` for skipping judging.

**Prompt Eval execution model:**
- One model (from `run.models_json`, first entry used)
- N prompt variants (from `DataApi.retrieve_prompt_variants_for_run(run_id)`)
- Creates N × T result rows (N variants × T tasks), each with `prompt_version = variant.variant_id`
- Each result row has `user_prompt_sent` pre-rendered as `variant.user_prompt_template.replace("{question}", task.question)`
- Inference uses the pre-rendered prompt from `result.user_prompt_sent` instead of calling `JudgePromptService`
- Judging runs the same 4-layer eval pipeline as `RunMode.FULL_GRADING`

The `prompt_variants` table is populated **before** `start_execution()` is called — the UI controller creates variants via `DataApi.create_prompt_variant()` during run setup. `BenchmarkExecutionTask` only reads them.

### Requirements

1. In `_stage_initializing`, when `run.run_mode == RunMode.PROMPT_EVAL`:
   - Load variants: `self._data_api.retrieve_prompt_variants_for_run(run_id)`
   - If no variants found, log a warning and return an empty dict (run will produce zero result rows)
   - Parse the first model descriptor from `run.models_json` (only one model expected in prompt_eval)
   - For each variant × task: create a `BenchmarkResult` row with `prompt_version = variant.variant_id`, `user_prompt_sent = variant.user_prompt_template.replace("{question}", task.question)`, `system_prompt_sent = variant.system_prompt` (may be None)
   - Skip row creation if `(provider_id, model_name, task_id, prompt_version)` already exists (resumability)
   - Fall through to the existing path (total task count update, `BenchmarkStartedEvent`, return tasks_map)

2. In `_run_inference`, use `result.user_prompt_sent` when it is already set (non-empty string):
   ```python
   if result.user_prompt_sent:
       user_prompt = result.user_prompt_sent
       system_prompt = result.system_prompt_sent
   else:
       user_prompt, system_prompt = self._judge_prompt_service.build_inference_prompt(task)
   ```
   This is the only change to `_run_inference` for prompt_eval support — the rest of the method is identical.

3. In `run()`, `RunMode.PROMPT_EVAL` MUST run the judging stage (same as `FULL_GRADING`). The existing condition `if run.run_mode != RunMode.SPEED:` already covers this correctly — no change needed to `run()`.

4. Add a helper `@staticmethod _build_prompt_eval_result(run, desc, task, variant)` that creates the prompt_eval variant result row. This keeps `_build_initial_result` unchanged.

5. Resumability: use the existing-keys check with key `(provider_id, model_name, task_id, prompt_version)`.

### Existing Code Reference

- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` lines 265–308 — `_stage_initializing` (to be extended with a branch)
- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` lines 519–561 — `_run_inference` (2-line change at top)
- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` lines 908–930 — `_build_initial_result` (reference pattern for the new static helper)
- `src/ollama_llm_bench/backend/core/interfaces.py` lines 279–296 — `DataApi.retrieve_prompt_variants_for_run`
- `src/ollama_llm_bench/backend/core/models.py` lines 258–267 — `PromptVariant` dataclass fields: `variant_id`, `run_id`, `variant_label`, `user_prompt_template`, `created_at`, `system_prompt: str | None`
- `src/ollama_llm_bench/backend/core/models.py` lines 6–11 — `RunMode` enum

### Implementation Guidance

**In `_stage_initializing`**, after computing `task_list` and `descriptors`, add a branch:

```python
if run.run_mode == RunMode.PROMPT_EVAL:
    return self._stage_initializing_prompt_eval(run, task_list, descriptors)
```

Place this branch BEFORE the existing resumability block so that prompt_eval rows are created via the new method.

**New private method `_stage_initializing_prompt_eval`**:

```python
def _stage_initializing_prompt_eval(
    self,
    run: BenchmarkRun,
    task_list: list[BenchmarkTask],
    descriptors: list[ModelDescriptor],
) -> dict[str, BenchmarkTask]:
    variants = self._data_api.retrieve_prompt_variants_for_run(self._run_id)
    if not variants:
        self._notify_warn("Prompt eval mode: no variants found for this run.")
        return {t.task_id: t for t in task_list}

    desc = descriptors[0] if descriptors else None
    if desc is None:
        self._notify_warn("Prompt eval mode: no model descriptor found.")
        return {t.task_id: t for t in task_list}

    existing = self._data_api.retrieve_benchmark_results_for_run(self._run_id)
    existing_keys = {(r.provider_id, r.model_name, r.task_id, r.prompt_version) for r in existing}

    new_rows = [
        self._build_prompt_eval_result(run, desc, task, variant)
        for variant in variants
        for task in task_list
        if (desc.provider_id, desc.model_name, task.task_id, variant.variant_id) not in existing_keys
    ]
    if new_rows:
        self._data_api.create_benchmark_results(new_rows)
        self._notify(f"Created {len(new_rows)} prompt-eval result rows.")

    return {t.task_id: t for t in task_list}
```

**New static helper `_build_prompt_eval_result`**:

```python
@staticmethod
def _build_prompt_eval_result(
    run: BenchmarkRun,
    desc: ModelDescriptor,
    task: BenchmarkTask,
    variant: PromptVariant,
) -> BenchmarkResult:
    rendered_prompt = variant.user_prompt_template.replace("{question}", task.question)
    return BenchmarkResult(
        run_id=run.run_id,
        run_type=str(run.run_mode),
        provider_id=desc.provider_id,
        provider_type=desc.provider_type,
        model_name=desc.model_name,
        model_family=desc.model_family,
        model_size_b=desc.model_size_b,
        quantization_label=desc.quantization_label,
        task_id=task.task_id,
        task_category=task.category,
        task_type=str(task.task_type),
        task_difficulty=str(task.difficulty) if task.difficulty else None,
        response_scope=str(task.response_scope) if task.response_scope else None,
        source_language=task.source_language,
        target_language=task.target_language,
        golden_answer=task.golden_answer,
        prompt_version=variant.variant_id,
        user_prompt_sent=rendered_prompt,
        system_prompt_sent=variant.system_prompt,
        status=BenchmarkResultStatus.NOT_COMPLETED,
    )
```

Add `PromptVariant` to the imports from `ollama_llm_bench.backend.core.models`.

**In `_run_inference`**, replace the two lines at the top that call `build_inference_prompt`:

```python
# Before:
user_prompt, system_prompt = self._judge_prompt_service.build_inference_prompt(task)
messages = self._build_messages(user_prompt, system_prompt)
```

With:

```python
if result.user_prompt_sent:
    user_prompt = result.user_prompt_sent
    system_prompt = result.system_prompt_sent
else:
    user_prompt, system_prompt = self._judge_prompt_service.build_inference_prompt(task)
messages = self._build_messages(user_prompt, system_prompt or "")
```

Note: `system_prompt` from `result.system_prompt_sent` is `str | None`. `_build_messages` checks truthiness, so `None` behaves the same as empty string — but `or ""` makes the type explicit for mypy.

### Verification

- [ ] `PromptVariant` is in the imports at the top of `qt_benchmark_execution_task.py`
- [ ] `_stage_initializing_prompt_eval` method exists and is called when `run.run_mode == RunMode.PROMPT_EVAL`
- [ ] `_build_prompt_eval_result` static method exists
- [ ] `_run_inference` checks `result.user_prompt_sent` before calling `build_inference_prompt`
- [ ] `uv run pytest tests/unit/ -q` passes

---

## Task 6: Unit Tests for `BenchmarkExecutionTask`

**Files to create**:
- `tests/unit/qt_classes/__init__.py` (empty)
- `tests/unit/qt_classes/test_benchmark_execution_task.py`

**Depends on**: Tasks 1–5 (tests the corrected implementation)

### Context

`BenchmarkExecutionTask` is the central orchestration class for V2. It has zero test coverage. Tests must mock all external dependencies (providers, data_api, evaluators) and run the task synchronously by calling `task.run()` directly instead of via `QThreadPool`.

**Qt isolation**: `BenchmarkExecutionTask` extends `QRunnable` and has an inner `Signals(QObject)` class. `QRunnable.run()` can be called directly in tests without a `QApplication` event loop. Mock `task.signals` after construction to bypass QObject signal requirements.

**Key patterns** (from `tests/unit/services/evaluators/test_cosine_evaluator.py`):
- Use `mocker.Mock(spec=<Interface>)` for all injected dependencies
- Use factory helpers (`_make_task`, `_make_result`, `_make_run`) to build frozen dataclasses
- One logical concept per test; Arrange → Act → Assert structure

### Requirements

1. Create `tests/unit/qt_classes/__init__.py` (empty file).
2. Create `tests/unit/qt_classes/test_benchmark_execution_task.py` with all tests listed below.
3. All tests use `mocker` fixture from `pytest-mock` with `spec=` on every mock.
4. Tests call `task.run()` directly (not via `QThreadPool`).
5. Mock `task.signals` after construction: `task.signals = mocker.Mock()`.

### Test Functions to Implement

```
test_speed_mode_skips_judging_stage
    - run.run_mode = RunMode.SPEED
    - data_api.retrieve_benchmark_results_for_run_with_status returns 1 NOT_COMPLETED result
    - Verify result is saved with status COMPLETED (not WAITING_FOR_JUDGE)
    - Verify retrieve_benchmark_results_for_run_with_status is never called with WAITING_FOR_JUDGE

test_full_grading_mode_runs_eval_pipeline
    - run.run_mode = RunMode.FULL_GRADING
    - benchmarking sets results to WAITING_FOR_JUDGE
    - rule/keyword/cosine evaluators return non-terminal UNKNOWN
    - llm_judge_evaluator returns terminal PASS
    - Verify data_api.update_benchmark_result called with status=COMPLETED

test_stop_cancels_before_benchmarking
    - task.stop() called before run()
    - Verify data_api never queried for NOT_COMPLETED results
    - Verify event_bus.emit_benchmark_stopped called

test_build_initial_result_sets_run_type
    - Call BenchmarkExecutionTask._build_initial_result(run, desc, task) directly
    - Assert result.run_type == str(run.run_mode)

test_build_initial_result_copies_language_fields
    - task has source_language="en", target_language="fr"
    - Assert result.source_language == "en", result.target_language == "fr"

test_run_inference_detects_thinking_block
    - provider.inference_sync returns InferenceResponse with
      llm_response="<think>reasoning</think>answer"
    - Call _run_inference directly
    - Assert updated.has_thinking_block is True
    - Assert updated.sanitized_response == "answer"

test_run_inference_no_thinking_block_when_absent
    - provider.inference_sync returns InferenceResponse with llm_response="plain answer"
    - Assert updated.has_thinking_block is False

test_run_inference_sets_prompt_hash
    - Call _run_inference
    - Assert updated.prompt_hash.startswith("sha256:")
    - Assert len(updated.prompt_hash) == 71  # "sha256:" (7) + hex digest (64)

test_prompt_eval_mode_creates_rows_per_variant
    - run.run_mode = RunMode.PROMPT_EVAL
    - data_api.retrieve_prompt_variants_for_run returns 2 PromptVariant objects
    - task_list has 3 tasks
    - Assert data_api.create_benchmark_results called once with a list of 6 rows

test_mark_failed_persists_error
    - Call _mark_failed(result, RuntimeError("boom")) directly
    - Assert data_api.update_benchmark_result called with has_inference_error=True
    - Assert the updated result's inference_error_message contains "boom"
```

### Existing Code Reference

- `tests/unit/services/evaluators/test_rule_based_evaluator.py` — fixture + mock patterns
- `tests/unit/services/evaluators/test_cosine_evaluator.py` — `_make_task`, `_make_result` factory pattern
- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` — class under test
- `src/ollama_llm_bench/backend/core/interfaces.py` — `DataApi`, `EvaluatorApi`, `LLMJudgeEvaluatorApi`, `EventBus`, `AppSettingsServiceApi`, `TaskFileLoaderApi`, `JudgePromptServiceApi`, `LogFileWriterApi`, `ProviderRegistryApi` — all need `spec=` mocks

### Implementation Guidance

**Shared fixture pattern:**

```python
from pytest_mock import MockerFixture
from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi, DataApi, EvaluatorApi, EventBus,
    JudgePromptServiceApi, LLMJudgeEvaluatorApi, LogFileWriterApi,
    ProviderRegistryApi, TaskFileLoaderApi,
)
from ollama_llm_bench.ui.qt_classes.qt_benchmark_execution_task import BenchmarkExecutionTask

def _make_exec_task(mocker: MockerFixture) -> BenchmarkExecutionTask:
    task = BenchmarkExecutionTask(
        run_id=1,
        data_api=mocker.Mock(spec=DataApi),
        task_loader=mocker.Mock(spec=TaskFileLoaderApi),
        judge_prompt_service=mocker.Mock(spec=JudgePromptServiceApi),
        provider_registry=mocker.Mock(spec=ProviderRegistryApi),
        event_bus=mocker.Mock(spec=EventBus),
        app_settings=mocker.Mock(spec=AppSettingsServiceApi),
        rule_evaluator=mocker.Mock(spec=EvaluatorApi),
        keyword_evaluator=mocker.Mock(spec=EvaluatorApi),
        cosine_evaluator=mocker.Mock(spec=EvaluatorApi),
        llm_judge_evaluator=mocker.Mock(spec=LLMJudgeEvaluatorApi),
        log_file_writer=mocker.Mock(spec=LogFileWriterApi),
    )
    task.signals = mocker.Mock()
    # Default: all feature flags off (no streaming, no warmup, no log-to-file)
    task._app_settings.get_bool.side_effect = lambda key, default=False: default
    return task
```

**Configuring evaluator mocks:**

```python
from ollama_llm_bench.backend.core.models import EvalLayer, EvalVerdict, EvaluationResult

task._rule_evaluator.layer = EvalLayer.RULE_BASED
task._rule_evaluator.evaluate.return_value = EvaluationResult(
    verdict=EvalVerdict.UNKNOWN, score=0.5, reasoning="", is_terminal=False,
    layer=EvalLayer.RULE_BASED,
)
# same pattern for _keyword_evaluator (EvalLayer.KEYWORD) and _cosine_evaluator (EvalLayer.COSINE)

task._llm_judge_evaluator.layer = EvalLayer.LLM_JUDGE
task._llm_judge_evaluator.evaluate.return_value = EvaluationResult(
    verdict=EvalVerdict.PASS, score=0.9, reasoning="Good answer", is_terminal=True,
    layer=EvalLayer.LLM_JUDGE,
)
```

**Configuring data_api for full grading end-to-end test:**

```python
run = BenchmarkRun(
    run_id=1, timestamp="2026-01-01T00:00:00", judge_model="qwen3:8b",
    judge_provider_id="ollama", status=BenchmarkRunStatus.NOT_COMPLETED,
    run_mode=RunMode.FULL_GRADING, models_json='[{"provider_id":"p","provider_type":"openai_compatible","model_name":"m","display_label":"m"}]',
    task_file_paths=("tasks/test.yaml",),
)
result_not_completed = BenchmarkResult(result_id=1, run_id=1, task_id="t1", ...)
result_waiting = dataclasses.replace(result_not_completed, status=BenchmarkResultStatus.WAITING_FOR_JUDGE)

task._data_api.retrieve_benchmark_run.return_value = run
task._data_api.retrieve_benchmark_results_for_run.return_value = [result_not_completed]
task._task_loader.load_tasks.return_value = [<BenchmarkTask>]
# NOT_COMPLETED query → returns pending inference rows
task._data_api.retrieve_benchmark_results_for_run_with_status.side_effect = lambda *, run_id, status: (
    [result_not_completed] if status == BenchmarkResultStatus.NOT_COMPLETED else [result_waiting]
)
```

### Verification

- [ ] `uv run pytest tests/unit/qt_classes/ -v` — all new tests pass
- [ ] `uv run pytest tests/unit/ -q` — no regressions
- [ ] `tests/unit/qt_classes/__init__.py` exists (empty)
- [ ] At least 10 test functions present in the test file

---

## Final Verification Checklist

When all tasks are complete, verify end-to-end:

- [ ] All tests pass: `uv run pytest tests/ -q --tb=short`
- [ ] Ruff clean: `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`
- [ ] Type check: `uv run mypy src/` — no new errors
- [ ] `_build_initial_result` sets `run_type`, `source_language`, `target_language`
- [ ] `_run_inference` sets `has_thinking_block` and `prompt_hash`
- [ ] `_run_eval_pipeline` sets `cosine_embedding_model` when cosine layer produces a score
- [ ] `cosine_evaluator.py` thresholds match spec: EXACT (0.92/0.30), CONTAINS (0.85/0.25), COVERS (0.75/0.20)
- [ ] `RunMode.PROMPT_EVAL` triggers `_stage_initializing_prompt_eval` with variant-based row creation
- [ ] Pre-rendered `user_prompt_sent` is used in `_run_inference` for prompt_eval results
- [ ] `PromptVariant` imported in `qt_benchmark_execution_task.py`
- [ ] All new code uses absolute imports, keyword-only constructor args, frozen dataclass patterns
- [ ] No Qt imports in `core/` or `services/`
- [ ] `BenchmarkExecutionTask` test file created with ≥10 test functions
- [ ] CLAUDE.md Phase 3 section updated: mark pipeline modes as IMPLEMENTED
