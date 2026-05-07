# Technical Design: JudgePromptService (Phase 2 — Task 5)

## Status
DRAFT — Awaiting human review

## Context

V1 uses `SimplePromptBuilderApi` with two hard-coded templates from `prompt_constants.py`
(`SYSTEM_PROMPT`, `USER_PROMPT`) that reference V1 fields (`most_expected`, `good_answer`,
`pass_option`, `incorrect_direction`, `category`, `sub_category`). The V2 data model replaces
those with `golden_answer`, `pass_criteria`, `fail_criteria`, and a discriminating `task_type`
enum — making V1 templates structurally incompatible with V2 `BenchmarkTask`.

`JudgePromptService` is consumed exclusively by `LLMJudgeEvaluator` (Layer 4). It has no
constructor dependencies, produces no side effects, and is deterministic — making it one of the
simplest services in the pipeline.

The `JudgePromptServiceApi` Protocol is already defined and committed in
`src/ollama_llm_bench/backend/core/interfaces.py` (lines 1033–1039). The V2 domain models
(`TaskType`, `BenchmarkTask`, `BenchmarkResult`) are already present in `models.py`. Nothing else
needs to change before this task can be implemented.

## Problem Statement

Implement `JudgePromptService` as a stateless, task-type-aware prompt builder that:

1. Satisfies the existing `JudgePromptServiceApi` Protocol — verified via `isinstance()` check.
2. Returns `(task.question, "")` for `build_inference_prompt` (empty system prompt, plain question
   as user prompt).
3. Returns `(user_prompt, system_prompt)` for `build_judge_prompt` where:
   - `system_prompt` is selected from a `dict[TaskType, str]` dispatch table keyed on
     `task.task_type`, falling back to a default rubric for unmapped types.
   - Every system prompt variant enforces the V2 output schema:
     `{"verdict":"pass"|"fail","score":<float 0.00–1.00>,"reasoning":"<one sentence>"}`.
     No markdown, no extra keys.
   - `user_prompt` is the same template for all task types, with placeholders substituted:
     `{task_type}`, `{question}`, `{golden_answer}`, `{pass_criteria}`, `{fail_criteria}`,
     `{submitted_answer}`.
   - `submitted_answer` = `result.sanitized_response` if non-empty, else `result.raw_response`,
     else `""`.

**Success criteria:**
- `uv run mypy src/ollama_llm_bench/backend/services/judge_prompt_service.py` — zero errors.
- `uv run pytest tests/unit/services/test_judge_prompt_service.py -v` — all tests pass.
- No Qt imports anywhere in the service file.
- All 8 `TaskType` values produce a distinct system prompt (7 specific + 1 default).
- `isinstance(JudgePromptService(), JudgePromptServiceApi)` returns `True`.

## Alternatives Considered

### Option A: Single universal system prompt + per-type rubric injected as a placeholder

**Approach:** One system prompt template with a `{rubric}` placeholder; a `dict[TaskType, str]`
maps each type to a rubric snippet injected at call time.

**Pros:** DRY — shared boilerplate defined once; easy to add new task types.
**Cons:** Rubric text is tightly constrained by surrounding prose; tuning one type risks breaking
others; a single broken placeholder would silently produce a malformed prompt.
**Effort:** Low

### Option B: Separate module-level constant per task type + dispatch dict (Selected)

**Approach:** Each task type group gets its own complete system prompt constant
(`_CODE_JUDGE_SYSTEM_PROMPT`, `_REASONING_JUDGE_SYSTEM_PROMPT`, etc.). A
`dict[TaskType, str]` dispatch table maps each `TaskType` to the correct constant. A
`_DEFAULT_JUDGE_SYSTEM_PROMPT` catches unmapped types. The user prompt template is a single
module-level constant shared across all types.

**Pros:** Each constant is fully self-contained — safe to tune one type without touching others.
No runtime string-building beyond placeholder substitution. Easy to read and test. Matches the
`TaskFileLoader` and `AppSettingsService` patterns already in the codebase.
**Cons:** More constants; slight duplication of the JSON schema enforcement clause across
constants (acceptable — copy-paste risk is low since the schema is stable).
**Effort:** Low

### Option C: External YAML/JSON template files loaded at construction time

**Approach:** Store prompt templates in files under `dataset/` or `config/`; load at
`__init__` time.

**Pros:** Templates editable without code changes.
**Cons:** Introduces a file I/O dependency into a service that the plan explicitly states has no
constructor dependencies; adds failure modes (file not found); violates the "no-constructor-deps"
requirement from `PLAN_DOCUMENT_PHASE_2.md` Task 5; runtime loading has no clear benefit over
constants for a closed, known set of task types.
**Effort:** Medium

## Decision

Selected **Option B** because it directly matches the existing codebase patterns
(`app_settings_service.py` module-level constants, `task_file_loader.py`'s `_YAML_EXTENSIONS`
frozenset dispatch), keeps the service purely stateless, and lets each rubric vary independently
without risk of cross-contamination. The "duplication" of the output-schema enforcement line is
deliberate: each system prompt must be independently parseable by the judge LLM.

## Architecture

The service fits cleanly into the existing layer structure. No new files outside the two
specified targets are required.

```
build_judge_prompt(task, result)
        │
        ▼
_JUDGE_SYSTEM_PROMPTS.get(task.task_type, _DEFAULT_JUDGE_SYSTEM_PROMPT)
        │                                         │
        │                                         ▼
        │                               _DEFAULT_JUDGE_SYSTEM_PROMPT
        │
  ┌─────┴────────────────────────────────────────────────┐
  │ TaskType.CODE_GENERATION / CODE_REVIEW               │ → _CODE_JUDGE_SYSTEM_PROMPT
  │ TaskType.REASONING                                   │ → _REASONING_JUDGE_SYSTEM_PROMPT
  │ TaskType.TRANSLATION                                 │ → _TRANSLATION_JUDGE_SYSTEM_PROMPT
  │ TaskType.FACTUAL_QA                                  │ → _FACTUAL_QA_JUDGE_SYSTEM_PROMPT
  │ TaskType.TEXT_REWRITE / SUMMARIZATION                │ → _REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT
  │ TaskType.DATA_EXTRACTION                             │ → _DATA_EXTRACTION_JUDGE_SYSTEM_PROMPT
  └──────────────────────────────────────────────────────┘
        │
        ▼
_USER_PROMPT_TEMPLATE.format(
    task_type, question, golden_answer,
    pass_criteria, fail_criteria, submitted_answer
)
        │
        ▼
  return (user_prompt, system_prompt)
```

## Data Structures

No new dataclasses or ABCs. The service uses only existing models.

### Module-level constants in `judge_prompt_service.py`

**`_USER_PROMPT_TEMPLATE: str`** — Single template, all types:

```
task_type: {task_type}
question: {question}
golden_answer: {golden_answer}
pass_criteria: {pass_criteria}
fail_criteria: {fail_criteria}
submitted_answer: {submitted_answer}
```

**System prompt constants** — one per rubric group. Each constant MUST contain:
1. A role declaration: "You are an objective evaluator."
2. The rubric emphasis for that task type.
3. The exact V2 output schema enforcement clause:
   `{"verdict":"pass"|"fail","score":<float 0.00-1.00>,"reasoning":"<one sentence>"}`
   No markdown, no extra keys.

| Constant name | Covers `TaskType` values | Rubric emphasis |
|---|---|---|
| `_CODE_JUDGE_SYSTEM_PROMPT` | `CODE_GENERATION`, `CODE_REVIEW` | Correctness, required API usage, plausibility to compile |
| `_REASONING_JUDGE_SYSTEM_PROMPT` | `REASONING` | Logical soundness, chain of thought validity |
| `_TRANSLATION_JUDGE_SYSTEM_PROMPT` | `TRANSLATION` | Fidelity to meaning, entity/number preservation, register |
| `_FACTUAL_QA_JUDGE_SYSTEM_PROMPT` | `FACTUAL_QA` | Accuracy of claimed facts against golden answer |
| `_REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT` | `TEXT_REWRITE`, `SUMMARIZATION` | Correctness and format adherence |
| `_DATA_EXTRACTION_JUDGE_SYSTEM_PROMPT` | `DATA_EXTRACTION` | Correctness and strict format adherence |
| `_DEFAULT_JUDGE_SYSTEM_PROMPT` | All unhandled types | Balanced correctness and completeness |

**`_JUDGE_SYSTEM_PROMPTS: dict[TaskType, str]`** — dispatch table mapping each `TaskType` to its
constant. `TEXT_REWRITE` and `SUMMARIZATION` both map to
`_REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT`. `CODE_GENERATION` and `CODE_REVIEW` both map to
`_CODE_JUDGE_SYSTEM_PROMPT`.

### Class structure

```python
class JudgePromptService:
    """Stateless, task-type-aware prompt builder for V2 benchmark evaluation."""

    def __init__(self) -> None: ...

    def build_inference_prompt(self, task: BenchmarkTask) -> tuple[str, str]:
        """Return (task.question, "") — plain question, no system prompt."""
        ...

    def build_judge_prompt(
        self, task: BenchmarkTask, result: BenchmarkResult
    ) -> tuple[str, str]:
        """Return (user_prompt, system_prompt) using task-type-specific rubric."""
        ...
```

Note: This class implements the `JudgePromptServiceApi` Protocol structurally (duck typing).
No `@override` annotation is used because Protocol implementation is structural, not
inheritance-based. The `@runtime_checkable` decorator on the Protocol enables
`isinstance(JudgePromptService(), JudgePromptServiceApi)`.

## Implementation Steps

### Step 1: Create `judge_prompt_service.py`

- **File:** `src/ollama_llm_bench/backend/services/judge_prompt_service.py`
- **Action:** Create
- **Description:**
  The file is organized as follows (per `coding-style.md` file organization rule):
  1. Module docstring
  2. Imports: `import logging` (stdlib), then `from ollama_llm_bench.backend.core.models import ...`
  3. Module-level `_logger = logging.getLogger(__name__)`
  4. Seven system prompt string constants (`_CODE_JUDGE_SYSTEM_PROMPT`, etc.) as `str` literals
  5. `_DEFAULT_JUDGE_SYSTEM_PROMPT: str`
  6. `_USER_PROMPT_TEMPLATE: str`
  7. `_JUDGE_SYSTEM_PROMPTS: dict[TaskType, str]` dispatch table
  8. `JudgePromptService` class

  **Imports required:**
  ```
  import logging
  from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkTask, TaskType
  ```

  **`build_inference_prompt` logic:**
  - No validation required — return `(task.question, "")` directly.

  **`build_judge_prompt` logic:**
  - Resolve `submitted_answer`: `result.sanitized_response or result.raw_response or ""`
  - Look up system prompt: `_JUDGE_SYSTEM_PROMPTS.get(task.task_type, _DEFAULT_JUDGE_SYSTEM_PROMPT)`
  - Fill user prompt:
    ```python
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        task_type=task.task_type.value,
        question=task.question,
        golden_answer=task.golden_answer,
        pass_criteria=task.pass_criteria,
        fail_criteria=task.fail_criteria,
        submitted_answer=submitted_answer,
    )
    ```
  - Return `(user_prompt, system_prompt)`

  **System prompt content — exact schema enforcement line** (identical across all constants):
  ```
  Return ONLY a JSON object with this exact schema:
  {"verdict":"pass"|"fail","score":<float 0.00-1.00>,"reasoning":"<one sentence>"}
  No markdown, no code fences, no extra keys, no explanation outside the JSON object.
  ```

  **Per-constant rubric focus (coder must write the full natural-language rubric):**

  `_CODE_JUDGE_SYSTEM_PROMPT`:
  > You are an objective evaluator of code quality.
  > Evaluate based on: (1) correctness — does the submitted code solve the problem?
  > (2) API usage — does it use the required language/API/library?
  > (3) plausibility to compile or run without modification given the stated language version?
  > Use the golden_answer as the reference implementation. Apply pass_criteria to grant PASS;
  > apply fail_criteria to grant FAIL.
  > [schema enforcement line]

  `_REASONING_JUDGE_SYSTEM_PROMPT`:
  > You are an objective evaluator of reasoning quality.
  > Evaluate based on: (1) logical soundness — are the reasoning steps valid?
  > (2) correct chain of thought — does each step follow from the previous?
  > (3) correct final answer — does the conclusion match the golden_answer?
  > Apply pass_criteria to grant PASS; apply fail_criteria to grant FAIL.
  > [schema enforcement line]

  `_TRANSLATION_JUDGE_SYSTEM_PROMPT`:
  > You are an objective evaluator of translation quality.
  > Evaluate based on: (1) fidelity to meaning of the source text,
  > (2) preservation of all named entities, numbers, and proper nouns,
  > (3) appropriate register and style matching the golden_answer.
  > Apply pass_criteria to grant PASS; apply fail_criteria to grant FAIL.
  > [schema enforcement line]

  `_FACTUAL_QA_JUDGE_SYSTEM_PROMPT`:
  > You are an objective evaluator of factual accuracy.
  > Evaluate based on: (1) accuracy of all claimed facts against the golden_answer,
  > (2) absence of fabricated or contradictory information.
  > Apply pass_criteria to grant PASS; apply fail_criteria to grant FAIL.
  > [schema enforcement line]

  `_REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT`:
  > You are an objective evaluator of text rewriting and summarization quality.
  > Evaluate based on: (1) correctness — does the response fulfill the requested transformation?
  > (2) format adherence — does the output format match the golden_answer structure?
  > (3) completeness — are all required points covered?
  > Apply pass_criteria to grant PASS; apply fail_criteria to grant FAIL.
  > [schema enforcement line]

  `_DATA_EXTRACTION_JUDGE_SYSTEM_PROMPT`:
  > You are an objective evaluator of data extraction quality.
  > Evaluate based on: (1) correctness — are all extracted values accurate?
  > (2) strict format adherence — does the output exactly match the required format in
  > golden_answer (field names, separators, order)?
  > (3) completeness — are all required fields present?
  > Apply pass_criteria to grant PASS; apply fail_criteria to grant FAIL.
  > [schema enforcement line]

  `_DEFAULT_JUDGE_SYSTEM_PROMPT`:
  > You are an objective evaluator.
  > Evaluate based on a balanced rubric: (1) correctness — does the response answer the question?
  > (2) completeness — does it cover all required points from the golden_answer?
  > (3) format adherence — does it match any explicit format requirements?
  > Apply pass_criteria to grant PASS; apply fail_criteria to grant FAIL.
  > [schema enforcement line]

  `_JUDGE_SYSTEM_PROMPTS` dispatch table:
  ```python
  _JUDGE_SYSTEM_PROMPTS: dict[TaskType, str] = {
      TaskType.CODE_GENERATION: _CODE_JUDGE_SYSTEM_PROMPT,
      TaskType.CODE_REVIEW: _CODE_JUDGE_SYSTEM_PROMPT,
      TaskType.REASONING: _REASONING_JUDGE_SYSTEM_PROMPT,
      TaskType.TRANSLATION: _TRANSLATION_JUDGE_SYSTEM_PROMPT,
      TaskType.FACTUAL_QA: _FACTUAL_QA_JUDGE_SYSTEM_PROMPT,
      TaskType.TEXT_REWRITE: _REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT,
      TaskType.SUMMARIZATION: _REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT,
      TaskType.DATA_EXTRACTION: _DATA_EXTRACTION_JUDGE_SYSTEM_PROMPT,
  }
  ```

  Note: All 8 `TaskType` values are covered in this table. The default is not dead code — it
  protects against future `TaskType` additions that predate a service update.

- **Validation:**
  ```bash
  uv run ruff check src/ollama_llm_bench/backend/services/judge_prompt_service.py
  uv run mypy src/ollama_llm_bench/backend/services/judge_prompt_service.py
  ```

### Step 2: Create `test_judge_prompt_service.py`

- **File:** `tests/unit/services/test_judge_prompt_service.py`
- **Action:** Create
- **Description:**
  No mocks are needed — `JudgePromptService` has no dependencies. Tests construct
  `BenchmarkTask` and `BenchmarkResult` instances directly (per testing standards: do NOT mock
  dataclasses). The file follows the class-grouped test structure seen in
  `test_app_settings_service.py`.

  **Fixtures:**

  ```python
  @pytest.fixture
  def service() -> JudgePromptService:
      return JudgePromptService()

  def _make_task(task_type: TaskType, **overrides: object) -> BenchmarkTask:
      """Build a minimal valid BenchmarkTask for the given task type."""
      defaults: dict[str, object] = {
          "task_id": "test_task_001",
          "category": "test",
          "sub_category": "unit",
          "task_type": task_type,
          "question": "What is 2 + 2?",
          "golden_answer": "4",
          "pass_criteria": "Answer is 4",
          "fail_criteria": "Answer is not 4",
      }
      defaults.update(overrides)
      return BenchmarkTask(**defaults)  # type: ignore[arg-type]

  def _make_result(
      sanitized_response: str | None = "The answer is 4.",
      raw_response: str | None = None,
  ) -> BenchmarkResult:
      """Build a minimal BenchmarkResult."""
      return BenchmarkResult(
          sanitized_response=sanitized_response,
          raw_response=raw_response,
      )
  ```

  **Test classes and cases:**

  ---

  **`class TestBuildInferencePrompt`**

  `test_returns_question_as_user_prompt`:
  - Arrange: task with `question="What is 2 + 2?"`
  - Act: `user, system = service.build_inference_prompt(task)`
  - Assert: `user == "What is 2 + 2?"` and `system == ""`

  `test_returns_empty_string_as_system_prompt`:
  - Same fixture; just `assert system == ""`

  `test_returns_question_unchanged_for_multiline_question`:
  - Arrange: task with multi-line question `"Line one.\nLine two."`
  - Assert: `user == "Line one.\nLine two."` (no transformation)

  ---

  **`class TestBuildJudgePromptUserPromptContent`**

  `test_user_prompt_contains_task_type_value`:
  - Arrange: task with `task_type=TaskType.FACTUAL_QA`
  - Act: `user, _ = service.build_judge_prompt(task, result)`
  - Assert: `"factual_qa" in user`

  `test_user_prompt_contains_question`:
  - Assert: `task.question in user`

  `test_user_prompt_contains_golden_answer`:
  - Assert: `task.golden_answer in user`

  `test_user_prompt_contains_pass_criteria`:
  - Assert: `task.pass_criteria in user`

  `test_user_prompt_contains_fail_criteria`:
  - Assert: `task.fail_criteria in user`

  `test_user_prompt_contains_sanitized_response_when_present`:
  - Arrange: result with `sanitized_response="sanitized text"`, `raw_response="raw text"`
  - Assert: `"sanitized text" in user` and `"raw text" not in user`

  `test_user_prompt_falls_back_to_raw_response_when_sanitized_is_none`:
  - Arrange: result with `sanitized_response=None`, `raw_response="raw text"`
  - Assert: `"raw text" in user`

  `test_user_prompt_falls_back_to_raw_response_when_sanitized_is_empty_string`:
  - Arrange: result with `sanitized_response=""`, `raw_response="raw text"`
  - Assert: `"raw text" in user`

  `test_user_prompt_uses_empty_string_when_both_responses_are_none`:
  - Arrange: result with `sanitized_response=None`, `raw_response=None`
  - Act: `user, _ = service.build_judge_prompt(task, result)`
  - Assert: does not raise; `"submitted_answer:" in user`

  ---

  **`class TestBuildJudgePromptSystemPromptPerTaskType`**

  This class uses `@pytest.mark.parametrize` to iterate over all 8 `TaskType` values and
  confirm each returns a non-empty system prompt containing the V2 schema enforcement string.

  `test_all_task_types_return_non_empty_system_prompt` (parametrized over all 8 TaskType values):
  - Assert: `len(system) > 0`
  - Assert: `'{"verdict"' in system` (schema enforcement present)
  - Assert: `'"score"' in system`
  - Assert: `'"reasoning"' in system`

  `test_code_generation_returns_code_specific_system_prompt`:
  - Arrange: task with `task_type=TaskType.CODE_GENERATION`
  - Assert: specific keyword unique to code rubric is present (e.g., `"compile"` or
    `"API usage"`)

  `test_code_review_returns_same_system_prompt_as_code_generation`:
  - Assert: system prompts for `CODE_GENERATION` and `CODE_REVIEW` are identical

  `test_text_rewrite_returns_same_system_prompt_as_summarization`:
  - Assert: system prompts for `TEXT_REWRITE` and `SUMMARIZATION` are identical

  `test_reasoning_returns_reasoning_specific_system_prompt`:
  - Assert: `"chain of thought"` or `"logical"` present in system prompt

  `test_translation_returns_translation_specific_system_prompt`:
  - Assert: `"fidelity"` or `"entities"` present in system prompt

  `test_factual_qa_returns_factual_specific_system_prompt`:
  - Assert: `"factual"` or `"accuracy"` present in system prompt

  `test_data_extraction_returns_extraction_specific_system_prompt`:
  - Assert: `"extraction"` or `"format"` present in system prompt

  `test_all_8_task_types_return_distinct_system_prompts_except_known_shared_pairs`:
  - Collect all 8 system prompts.
  - Assert that `CODE_GENERATION == CODE_REVIEW` (expected shared).
  - Assert that `TEXT_REWRITE == SUMMARIZATION` (expected shared).
  - Assert that `REASONING`, `TRANSLATION`, `FACTUAL_QA`, `DATA_EXTRACTION`, and the code
    group are all mutually distinct.
  - Assert that the default is distinct from all 8 (use a hypothetical unknown task type —
    but since `TaskType` is a closed enum, test the default constant directly via import).

  ---

  **`class TestBuildJudgePromptSystemPromptDefault`**

  `test_default_prompt_is_distinct_from_all_specific_prompts`:
  - Import `_DEFAULT_JUDGE_SYSTEM_PROMPT` and all specific constants from the service module.
  - Assert `_DEFAULT_JUDGE_SYSTEM_PROMPT` differs from each specific constant.

  Note: importing private constants in tests is acceptable for completeness verification;
  the `isinstance` Protocol check is the authoritative structural conformance test.

  ---

  **`class TestProtocolConformance`**

  `test_isinstance_check_passes_against_judge_prompt_service_api`:
  - `from ollama_llm_bench.backend.core.interfaces import JudgePromptServiceApi`
  - Assert: `isinstance(JudgePromptService(), JudgePromptServiceApi)` is `True`

  `test_build_inference_prompt_return_type_is_tuple_of_two_strings`:
  - Assert: return value is `tuple` and `len(result) == 2`
  - Assert: both elements are `str`

  `test_build_judge_prompt_return_type_is_tuple_of_two_strings`:
  - Assert: same shape check for `build_judge_prompt`

- **Validation:**
  ```bash
  uv run pytest tests/unit/services/test_judge_prompt_service.py -v
  ```

### Step 3: Full pipeline validation

- **File(s):** No changes — validation only
- **Action:** Verify
- **Description:**
  Run the complete quality pipeline to confirm no regressions in existing tests, no new Mypy
  errors, and no ruff violations.
- **Validation:**
  ```bash
  uv run ruff check --output-format=concise src/ tests/
  uv run ruff format --check src/ tests/
  uv run mypy src/ollama_llm_bench/backend/services/judge_prompt_service.py
  uv run pytest tests/unit/services/test_judge_prompt_service.py -v
  uv run pytest tests/unit/ -q
  ```

  Spot-check: confirm no Qt imports leaked into the new file:
  ```bash
  grep -n "PySide6\|PyQt6\|QObject\|Signal" \
    src/ollama_llm_bench/backend/services/judge_prompt_service.py
  # Expected: no output (zero matches)
  ```

  Confirm all 8 `TaskType` values covered in dispatch table:
  ```bash
  grep -c "TaskType\." \
    src/ollama_llm_bench/backend/services/judge_prompt_service.py
  # Expected: >= 8
  ```

## Security Considerations

- System prompts are hardcoded constants — no user input reaches them.
- `user_prompt` is built via `str.format()` with `task` and `result` fields. These fields
  originate from trusted internal sources (YAML files and SQLite). No sanitization is required
  here; injection via prompt content is a model-level concern, not an application security issue.
- No file I/O, no network calls, no secrets.

## Performance Considerations

- `_JUDGE_SYSTEM_PROMPTS` is a module-level dict initialized once at import time — `O(1)` lookup.
- `str.format()` on short prompts is effectively free relative to any LLM call overhead.
- No caching is needed.

## Rollback Plan

The service is a new file with no modifications to existing files. Rollback is:
```bash
rm src/ollama_llm_bench/backend/services/judge_prompt_service.py
rm tests/unit/services/test_judge_prompt_service.py
```

No existing functionality is affected. `LLMJudgeEvaluator` (Task 9) and `app_context.py`
(Task 12) do not yet reference `JudgePromptService`, so nothing breaks if this task is reverted.

## Open Questions

None. All design inputs are resolved:
- Protocol signature: confirmed in `interfaces.py` lines 1033–1039.
- `BenchmarkTask` fields: confirmed in `models.py` lines 133–150.
- `BenchmarkResult` fields: confirmed in `models.py` lines 171–256.
- `TaskType` values: all 8 confirmed in `models.py` lines 15–25.
- Test patterns: confirmed from `test_app_settings_service.py` and `test_task_file_loader.py`.
- Log level for `caplog`: confirmed `log_level = "WARNING"` in `pyproject.toml` — no `caplog`
  usage needed in this service since it logs nothing (no warning/error paths exist).
