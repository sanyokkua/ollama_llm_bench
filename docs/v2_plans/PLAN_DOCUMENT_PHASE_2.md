# Phase 2 — Execution Engine V2 — Implementation Plan

**Generated**: 2026-04-16
**Source**: `docs/v2/v2-implementation-plan.md` sections 2.1, 2.2, 2.3, 2.4
**Scope**: Build the V2 execution engine — multi-stage pipeline (init → benchmark → judge → finish), dual-mode inference with 20 Hz streaming buffer, 4-layer evaluation pipeline (rule → keyword → cosine → LLM judge), structured event system with configurable pause/resume, and structured UI progress/log widgets.

---

## Prerequisites

- Phase 1 complete and verified: `OpenAICompatibleProvider`, `AnthropicProvider`, `GeminiProvider`, `OpenAIEmbeddingProvider`, `ProviderRegistry`, `ProviderConfigLoader`, `EmbeddingService`, `ModelNameParser` are all implemented and tested.
- Python 3.13+, UV, PySide6, `openai`, `anthropic`, `google-genai` packages installed.
- SQLite schema V2 (5 tables: `schema_version`, `benchmark_runs`, `benchmark_results`, `prompt_variants`, `app_settings`) is in place — see `src/ollama_llm_bench/backend/core/sql_constants.py`.
- `BenchmarkResult` has all 57 fields including evaluation layer fields (`layer1_*` through `layer4_*`, `final_verdict`, `resolution_layer`).

---

## Architecture Decisions

These are non-negotiable constraints every task must follow:

1. **No `ollama` SDK** — inference goes through `LLMProviderApi` (OpenAI-compatible or Anthropic/Gemini SDK) only.
2. **Dual-mode inference** — `inference_sync()` for judge calls; `inference_stream()` for benchmark inference. Both modes co-exist; neither replaces the other.
3. **20 Hz streaming buffer** — `BenchmarkExecutionTask` buffers stream chunks and emits `StreamingChunkEvent` to EventBus at maximum 20 Hz (every 50 ms). Never one event per token.
4. **4-layer evaluation in order** — Layer 1 (rule) → 2 (keyword) → 3 (cosine) → 4 (LLM judge). First layer to produce a terminal verdict stops the pipeline.
5. **Pause/resume via `threading.Event`** — the task blocks on `_pause_event.wait()` at every stage boundary. Stop uses a separate `_stop_flag` boolean. No polling loops.
6. **All new events are frozen dataclasses** in `core/models.py`. Zero Qt imports in `core/` or `services/`.
7. **All threading in `qt_classes/` only** — evaluators, task loader, settings service are pure Python services.
8. **Constructor DI with keyword-only args** — `def __init__(self, *, dep: DepType)` on every new service.
9. **Absolute imports only** — `from ollama_llm_bench.backend.core.models import BenchmarkStartedEvent`.
10. **`core/` is pure Python** — no Qt, no `openai`, no `yaml`, no `anthropic` imports allowed in `core/`.

---

## Task 1: Core Models — New Enums and Event Dataclasses

**Files to modify**: `src/ollama_llm_bench/backend/core/models.py`
**Files to create**: `tests/unit/core/test_event_models.py`
**Depends on**: None

### Context

Phase 2 introduces 15 new frozen dataclasses (events) and 6 new StrEnums. All event types, verdicts, and pipeline stages are domain models — they live in `core/models.py` alongside existing models like `BenchmarkRun` and `BenchmarkResult`. The existing `ReporterStatusMsg` dataclass is superseded by `ProgressUpdateEvent` but should remain for backward compatibility during the transition.

### Requirements

1. Add `PipelineStage(StrEnum)` with values: `INITIALIZING = "Initializing"`, `BENCHMARKING = "Benchmarking"`, `JUDGING = "Judging"`, `FINISHED = "Finished"`, `FAILED = "Failed"`. Note: these mirror the string constants in `stages_constants.py` — after this task, the constants file becomes optional (keep it for backward compat, don't delete).
2. Add `EvalLayer(StrEnum)` with values: `RULE_BASED = "rule_based"`, `KEYWORD = "keyword"`, `COSINE = "cosine"`, `LLM_JUDGE = "llm_judge"`.
3. Add `EvalVerdict(StrEnum)` with values: `PASS = "pass"`, `FAIL = "fail"`, `UNKNOWN = "unknown"`.
4. Add `PauseReason(StrEnum)` with values: `USER = "user"`, `EVENT_POLICY = "event_policy"`, `PROVIDER_ERROR = "provider_error"`.
5. Add `StopReason(StrEnum)` with values: `USER = "user"`, `FATAL_ERROR = "fatal_error"`.
6. Add `LogEntryType(StrEnum)` with values: `TASK_START = "task_start"`, `PROMPT = "prompt"`, `STREAM_CHUNK = "stream_chunk"`, `THINKING_BLOCK = "thinking_block"`, `INFERENCE_COMPLETE = "inference_complete"`, `JUDGE_RESULT = "judge_result"`, `ERROR = "error"`, `SYSTEM = "system"`.
7. Add `EvaluationResult` frozen dataclass with fields: `verdict: EvalVerdict`, `score: float` (0.0–1.0), `reasoning: str`, `is_terminal: bool`, `layer: EvalLayer`. Decorator: `@dataclass(frozen=True, slots=True, kw_only=True)`.
8. Add all 15 lifecycle/switch/completion/streaming/progress event dataclasses (see Implementation Guidance below). Each uses `@dataclass(frozen=True, slots=True, kw_only=True)`.
9. All existing models remain unchanged — this task is additive only.
10. New test file verifies: each new dataclass is immutable (`FrozenInstanceError` on assignment), default factories work, tuple fields are tuples not lists.

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/models.py` — follow the existing `@dataclass(frozen=True, slots=True, kw_only=True)` pattern used on `BenchmarkRun`, `ModelDescriptor`, `InferenceResponse`.
- Existing enums in the same file: `RunMode`, `TaskType`, `Difficulty`, `ResponseScope`, `ProviderType`, `BenchmarkRunStatus`, `BenchmarkResultStatus` — use the same `StrEnum` inheritance pattern.
- `src/ollama_llm_bench/backend/core/stages_constants.py` — contains `STAGE_INITIALIZING` etc. as bare strings. The new `PipelineStage` enum replaces these with type-safe values; keep the module for backward compatibility.
- `tests/unit/core/test_models.py` — pattern for testing frozen dataclasses: instantiate, assert field values, assert `pytest.raises(FrozenInstanceError)` on mutation.

### Implementation Guidance

Add the following to `models.py` (after existing dataclasses, before the end of file). Preserve existing import order.

**New enums** (add to the enum section after `BenchmarkResultStatus`):
```python
class PipelineStage(StrEnum):
    INITIALIZING = "Initializing"
    BENCHMARKING = "Benchmarking"
    JUDGING = "Judging"
    FINISHED = "Finished"
    FAILED = "Failed"

class EvalLayer(StrEnum):
    RULE_BASED = "rule_based"
    KEYWORD = "keyword"
    COSINE = "cosine"
    LLM_JUDGE = "llm_judge"

class EvalVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"

class PauseReason(StrEnum):
    USER = "user"
    EVENT_POLICY = "event_policy"
    PROVIDER_ERROR = "provider_error"

class StopReason(StrEnum):
    USER = "user"
    FATAL_ERROR = "fatal_error"

class LogEntryType(StrEnum):
    TASK_START = "task_start"
    PROMPT = "prompt"
    STREAM_CHUNK = "stream_chunk"
    THINKING_BLOCK = "thinking_block"
    INFERENCE_COMPLETE = "inference_complete"
    JUDGE_RESULT = "judge_result"
    ERROR = "error"
    SYSTEM = "system"
```

**EvaluationResult dataclass** (add after enums):
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationResult:
    verdict: EvalVerdict
    score: float           # 0.0 to 1.0
    reasoning: str
    is_terminal: bool      # True = this verdict terminates the eval pipeline
    layer: EvalLayer
```

**Event dataclasses** (add in the order below, after `EvaluationResult`):

```python
# Lifecycle events
@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkStartedEvent:
    run_id: int
    total_tasks: int
    models: tuple[ModelDescriptor, ...]
    run_mode: RunMode

@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkPausedEvent:
    run_id: int
    pause_reason: PauseReason
    paused_at_stage: PipelineStage

@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkResumedEvent:
    run_id: int

@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkStoppedEvent:
    run_id: int
    stop_reason: StopReason

@dataclass(frozen=True, slots=True, kw_only=True)
class BenchmarkFinishedEvent:
    run_id: int
    total_time_ms: float
    completed_count: int
    failed_count: int

# Switch events
@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSwitchEvent:
    run_id: int
    from_provider_id: str | None
    to_provider_id: str
    provider_label: str

@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderHealthCheckEvent:
    run_id: int
    provider_id: str
    is_healthy: bool
    error_message: str | None

@dataclass(frozen=True, slots=True, kw_only=True)
class ModelSwitchEvent:
    run_id: int
    from_model: str | None
    to_model: ModelDescriptor

@dataclass(frozen=True, slots=True, kw_only=True)
class TaskSwitchEvent:
    run_id: int
    model: ModelDescriptor
    task_id: str
    task_category: str
    task_type: TaskType
    task_number: int
    tasks_total: int

@dataclass(frozen=True, slots=True, kw_only=True)
class ModeSwitchEvent:
    run_id: int
    from_stage: PipelineStage
    to_stage: PipelineStage

# Completion events
@dataclass(frozen=True, slots=True, kw_only=True)
class TaskCompletedEvent:
    run_id: int
    result_id: int
    model: ModelDescriptor
    task_id: str
    status: BenchmarkResultStatus
    total_time_ms: float | None
    ttft_ms: float | None
    final_verdict: str | None

@dataclass(frozen=True, slots=True, kw_only=True)
class JudgeStartedEvent:
    run_id: int
    result_id: int
    layer: EvalLayer

@dataclass(frozen=True, slots=True, kw_only=True)
class JudgeCompletedEvent:
    run_id: int
    result_id: int
    layer: EvalLayer
    verdict: EvalVerdict
    resolved: bool  # True = terminal verdict produced

# Streaming event
@dataclass(frozen=True, slots=True, kw_only=True)
class StreamingChunkEvent:
    run_id: int
    result_id: int
    model_name: str
    task_id: str
    chunk_text: str
    is_thinking_block: bool

# Progress event
@dataclass(frozen=True, slots=True, kw_only=True)
class ProgressUpdateEvent:
    run_id: int
    stage: PipelineStage
    current_provider: str
    current_model: str
    current_task: str
    tasks_completed: int
    tasks_total: int
    start_time_ms: float
    current_time_ms: float
    estimated_remaining_ms: float | None
```

**Test expectations** in `tests/unit/core/test_event_models.py`:
- Instantiate each dataclass with valid fields; assert field access.
- `pytest.raises(dataclasses.FrozenInstanceError)` on `event.run_id = 999`.
- `BenchmarkStartedEvent.models` must be a `tuple`, not a `list`.
- `EvaluationResult.score = 0.5` must round-trip correctly.

### Verification

- [ ] `uv run ruff check src/ollama_llm_bench/backend/core/models.py` passes
- [ ] `uv run mypy src/ollama_llm_bench/backend/core/models.py` passes
- [ ] `uv run pytest tests/unit/core/test_event_models.py -v` passes
- [ ] All new classes importable: `from ollama_llm_bench.backend.core.models import BenchmarkStartedEvent, EvaluationResult, PipelineStage`

---

## Task 2: Core Interfaces — New Protocol Definitions

**Files to modify**: `src/ollama_llm_bench/backend/core/interfaces.py`
**Depends on**: Task 1

### Context

Phase 2 introduces five new service protocols (`TaskFileLoaderApi`, `EvaluatorApi`, `LLMJudgeEvaluatorApi`, `JudgePromptServiceApi`, `AppSettingsServiceApi`, `LogFileWriterApi`) and extends the `EventBus` ABC with 15 new subscribe/emit method pairs for all event types defined in Task 1.

### Requirements

1. Add `TaskFileLoaderApi(Protocol)` with methods: `load_tasks(file_paths: list[Path]) -> list[BenchmarkTask]`, `get_task(task_id: str) -> BenchmarkTask`, `scan_directory(directory: Path) -> list[Path]`.
2. Add `EvaluatorApi(Protocol)` for layers 1–3: `evaluate(task: BenchmarkTask, result: BenchmarkResult) -> EvaluationResult`. Add `@property layer(self) -> EvalLayer`.
3. Add `LLMJudgeEvaluatorApi(Protocol)` for layer 4 (different signature because it needs judge context): `evaluate(task: BenchmarkTask, result: BenchmarkResult, *, judge_provider_id: str, judge_model: str) -> EvaluationResult`. Add `@property layer(self) -> EvalLayer`.
4. Add `JudgePromptServiceApi(Protocol)` with: `build_inference_prompt(task: BenchmarkTask) -> tuple[str, str]` (user_prompt, system_prompt) and `build_judge_prompt(task: BenchmarkTask, result: BenchmarkResult) -> tuple[str, str]`.
5. Add `AppSettingsServiceApi(Protocol)` with: `get(key: str, default: str | None = None) -> str | None`, `set(key: str, value: str) -> None`, `get_bool(key: str, default: bool = False) -> bool`, `get_int(key: str, default: int = 0) -> int`.
6. Add `LogFileWriterApi(Protocol)` with: `write_entry(run_id: int, entry_type: LogEntryType, content: str) -> None`, `get_log_path(run_id: int) -> Path`, `close(run_id: int) -> None`.
7. Extend the existing `EventBus` ABC with 15 new subscribe/emit method pair abstract methods covering all new event types from Task 1. Follow the exact naming pattern already used: `subscribe_to_<event_snake_case>(self, callback: Callable[[EventType], None]) -> None` and `emit_<event_snake_case>(self, event: EventType) -> None`.
8. Add `from pathlib import Path` to imports if not already present.
9. Add all new type imports from `models.py` (new enums + event dataclasses).
10. All new protocols must have `@runtime_checkable` decorator.

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/interfaces.py` — read the existing `ProviderConfigLoaderApi(Protocol)`, `LLMProviderApi(Protocol)` for the Protocol pattern. Read `EventBus(ABC)` for the subscribe/emit method pair pattern. The existing pairs are: `subscribe_to_run_id_changed`/`emit_run_id_changed`, `subscribe_to_log_append`/`emit_log_append`, etc.
- `src/ollama_llm_bench/backend/core/models.py` — `BenchmarkTask`, `BenchmarkResult` are the primary domain objects passed between evaluators.

### Implementation Guidance

**New EventBus methods** (add as `@abstractmethod` to the existing `EventBus(ABC)` class):

```python
@abstractmethod
def subscribe_to_benchmark_started(self, callback: Callable[[BenchmarkStartedEvent], None]) -> None: ...
@abstractmethod
def emit_benchmark_started(self, event: BenchmarkStartedEvent) -> None: ...
# Repeat for: benchmark_paused, benchmark_resumed, benchmark_stopped, benchmark_finished,
# provider_switch, provider_health_check, model_switch, task_switch, mode_switch,
# task_completed, judge_started, judge_completed, streaming_chunk, progress_update
```

**IMPORTANT**: Adding abstract methods to `EventBus(ABC)` means `QtEventBus` will fail Mypy until Task 10 implements them. Implement Task 10 immediately after Task 2 to avoid a broken build state, or add temporary `NotImplementedError` stubs in `QtEventBus` with a `# TODO(phase2-task10)` comment.

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/core/interfaces.py` passes
- [ ] All new protocols importable: `from ollama_llm_bench.backend.core.interfaces import TaskFileLoaderApi, EvaluatorApi, AppSettingsServiceApi`
- [ ] `uv run pytest tests/unit/` — existing tests still pass

---

## Task 3: AppSettingsService

**Files to create**: `src/ollama_llm_bench/backend/services/app_settings_service.py`
**Files to create**: `tests/unit/services/test_app_settings_service.py`
**Depends on**: Task 2

### Context

`AppSettingsService` wraps the `app_settings` SQLite table as a typed key-value store. It stores per-installation configuration like pause policies and feature flags. Settings are read by `BenchmarkExecutionTask` at stage boundaries (streaming enabled, pause on provider/model switch, stop on provider error, etc.).

### Requirements

1. Class `AppSettingsService` implements `AppSettingsServiceApi` from Task 2.
2. Constructor: `def __init__(self, *, data_api: DataApi) -> None`.
3. Define the following setting key constants as module-level `UPPER_SNAKE_CASE` strings:
   - `SETTING_PAUSE_ON_PROVIDER_SWITCH = "benchmark.pause_on_provider_switch"` (default `"false"`)
   - `SETTING_PAUSE_ON_MODEL_SWITCH = "benchmark.pause_on_model_switch"` (default `"false"`)
   - `SETTING_PAUSE_ON_STAGE_SWITCH = "benchmark.pause_on_stage_switch"` (default `"false"`)
   - `SETTING_STOP_ON_PROVIDER_ERROR = "benchmark.stop_on_provider_error"` (default `"true"`)
   - `SETTING_STREAMING_ENABLED = "feature.streaming_enabled"` (default `"true"`)
   - `SETTING_LOG_TO_FILE = "feature.log_to_file"` (default `"false"`)
   - `SETTING_LOG_VERBOSITY = "ui.log_verbosity"` (default `"normal"`)
   - `SETTING_LOG_MAX_LINES = "ui.log_max_lines"` (default `"10000"`)
   - `SETTING_WARMUP_ENABLED = "benchmark.warmup_enabled"` (default `"true"`)
4. `get(key, default=None)` → `data_api.get_app_setting(key).value` or `default` if not found.
5. `set(key, value)` → `data_api.set_app_setting(key, value)`.
6. `get_bool(key, default=False)` → `True` only when stored value (case-insensitive) == `"true"`.
7. `get_int(key, default=0)` → parsed int, returns `default` on `ValueError`.
8. Unit tests use `mocker.Mock(spec=DataApi)` — no real SQLite.

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/interfaces.py` — `DataApi.get_app_setting(key: str) -> AppSetting | None` and `DataApi.set_app_setting(key: str, value: str) -> None`.
- `src/ollama_llm_bench/backend/core/models.py` — `AppSetting(key, value, updated_at)` frozen dataclass.
- `tests/unit/services/test_embedding_service.py` — pattern for `mocker.Mock(spec=...)`.

### Implementation Guidance

```python
import logging
from ollama_llm_bench.backend.core.interfaces import DataApi

logger = logging.getLogger(__name__)

SETTING_PAUSE_ON_PROVIDER_SWITCH = "benchmark.pause_on_provider_switch"
# ... (all 9 constants)

class AppSettingsService:
    def __init__(self, *, data_api: DataApi) -> None:
        self._data_api = data_api

    def get(self, key: str, default: str | None = None) -> str | None:
        setting = self._data_api.get_app_setting(key)
        return setting.value if setting is not None else default

    def set(self, key: str, value: str) -> None:
        self._data_api.set_app_setting(key, value)

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.get(key)
        return raw.lower() == "true" if raw is not None else default

    def get_int(self, key: str, default: int = 0) -> int:
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            logger.warning("invalid_int_setting", extra={"key": key, "value": raw})
            return default
```

**Test scenarios**: `get()` returns value when exists / default when not, `get_bool` returns True for `"true"` (case-insensitive), False for all other values, `get_int` parses valid strings and returns default on invalid.

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/services/app_settings_service.py` passes
- [ ] `uv run pytest tests/unit/services/test_app_settings_service.py -v` passes
- [ ] No Qt imports in the file

---

## Task 4: TaskFileLoader

**Files to create**: `src/ollama_llm_bench/backend/services/task_file_loader.py`
**Files to create**: `tests/unit/services/test_task_file_loader.py`
**Depends on**: Task 2

### Context

`TaskFileLoader` replaces `YamlBenchmarkTaskApi` for V2. It loads benchmark tasks from multiple YAML files or a directory, validates against the V2 schema (new fields: `task_type`, `golden_answer`, `pass_criteria`, `fail_criteria`, `required_terms`, `response_scope`, `difficulty`), deduplicates by `task_id`, and caches results for `get_task()`.

### Requirements

1. Class `TaskFileLoader` implements `TaskFileLoaderApi` from Task 2.
2. No constructor dependencies: `def __init__(self) -> None`.
3. `scan_directory(directory: Path) -> list[Path]`: returns all `.yaml` and `.yml` files in `directory` (non-recursive, sorted alphabetically).
4. `load_tasks(file_paths: list[Path]) -> list[BenchmarkTask]`: loads all tasks, deduplicates by `task_id` (first occurrence wins, duplicates logged as WARNING), caches for `get_task()`.
5. `get_task(task_id: str) -> BenchmarkTask`: returns from cache, raises `KeyError` if not found.
6. Required task fields: `task_id`, `task_type` (must be valid `TaskType` value), `question`, `golden_answer`. Missing or invalid → skip task, log WARNING.
7. Optional fields with defaults: `category=""`, `sub_category=""`, `difficulty=Difficulty.MEDIUM`, `pass_criteria=""`, `fail_criteria=""`, `response_scope=ResponseScope.CONTAINS`.
8. `required_terms`: parse `exact`, `semantic`, `forbidden` sub-keys as `list[str]`. Missing sub-keys default to `[]`.
9. Malformed YAML files: catch all exceptions from `yaml.safe_load`, log ERROR, return empty list for that file. Never raise from `load_tasks()`.
10. Unit tests use `tmp_path` fixture to create temporary YAML files.

### Existing Code Reference

- `src/ollama_llm_bench/backend/services/yaml_benchmark_task_api.py` — existing implementation for YAML parsing pattern (`_load_file`, `_parse_task`). V2 version adds new fields.
- `src/ollama_llm_bench/backend/core/models.py` — `BenchmarkTask`, `RequiredTerms`, `TaskType`, `Difficulty`, `ResponseScope`.

### Implementation Guidance

```python
_YAML_EXTENSIONS = frozenset({".yaml", ".yml"})

class TaskFileLoader:
    def __init__(self) -> None:
        self._cache: dict[str, BenchmarkTask] = {}

    def scan_directory(self, directory: Path) -> list[Path]:
        return sorted(p for p in directory.iterdir() if p.suffix in _YAML_EXTENSIONS and p.is_file())

    def load_tasks(self, file_paths: list[Path]) -> list[BenchmarkTask]:
        self._cache = {}
        tasks: list[BenchmarkTask] = []
        for path in file_paths:
            for task in self._load_file(path):
                if task.task_id in self._cache:
                    logger.warning("duplicate_task_id", extra={"task_id": task.task_id, "file": str(path)})
                    continue
                self._cache[task.task_id] = task
                tasks.append(task)
        return tasks

    def get_task(self, task_id: str) -> BenchmarkTask:
        return self._cache[task_id]  # KeyError if not loaded

    def _load_file(self, file_path: Path) -> list[BenchmarkTask]:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            entries = raw if isinstance(raw, list) else [raw]
            return [t for entry in entries if (t := self._parse_task(entry, file_path)) is not None]
        except Exception as e:
            logger.error("yaml_load_failed", extra={"file": str(file_path), "error": str(e)})
            return []

    def _parse_task(self, data: dict[str, Any], file_path: Path) -> BenchmarkTask | None:
        task_id = data.get("task_id", "")
        if not task_id:
            logger.warning("missing_task_id", extra={"file": str(file_path)})
            return None
        raw_type = data.get("task_type", "")
        try:
            task_type = TaskType(raw_type)
        except ValueError:
            logger.warning("invalid_task_type", extra={"task_id": task_id, "value": raw_type})
            return None
        question = data.get("question", "")
        golden_answer = data.get("golden_answer", "")
        if not question or not golden_answer:
            logger.warning("missing_required_field", extra={"task_id": task_id})
            return None
        rt = data.get("required_terms", {}) or {}
        required_terms = RequiredTerms(
            exact=list(rt.get("exact", [])),
            semantic=list(rt.get("semantic", [])),
            forbidden=list(rt.get("forbidden", [])),
        )
        try:
            difficulty = Difficulty(data.get("difficulty", Difficulty.MEDIUM))
        except ValueError:
            difficulty = Difficulty.MEDIUM
        try:
            response_scope = ResponseScope(data.get("response_scope", ResponseScope.CONTAINS))
        except ValueError:
            response_scope = ResponseScope.CONTAINS
        return BenchmarkTask(
            task_id=task_id,
            category=data.get("category", ""),
            sub_category=data.get("sub_category", ""),
            task_type=task_type,
            question=question,
            golden_answer=golden_answer,
            pass_criteria=data.get("pass_criteria", ""),
            fail_criteria=data.get("fail_criteria", ""),
            required_terms=required_terms,
            response_scope=response_scope,
            difficulty=difficulty,
        )
```

**Test scenarios**: single file single task, single file list of tasks, multiple files, duplicate task_id deduplication, missing required fields skipped, invalid task_type skipped, malformed YAML returns empty list, `scan_directory` returns sorted yaml files only, non-yaml files excluded.

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/services/task_file_loader.py` passes
- [ ] `uv run pytest tests/unit/services/test_task_file_loader.py -v` passes (all tests use `tmp_path`)
- [ ] No Qt imports in the file

---

## Task 5: JudgePromptService

**Files to create**: `src/ollama_llm_bench/backend/services/judge_prompt_service.py`
**Files to create**: `tests/unit/services/test_judge_prompt_service.py`
**Depends on**: Task 2

### Context

`JudgePromptService` replaces `SimplePromptBuilderApi` for V2. It provides task-type-specific evaluation prompts using V2 fields (`golden_answer`, `pass_criteria`, `fail_criteria`) instead of V1's multi-tier expected answer fields. The judge must return structured JSON: `{"verdict": "pass"|"fail", "score": 0.00-1.00, "reasoning": "..."}`.

### Requirements

1. Class `JudgePromptService` implements `JudgePromptServiceApi` from Task 2.
2. No constructor dependencies: `def __init__(self) -> None`.
3. `build_inference_prompt(task: BenchmarkTask) -> tuple[str, str]`: returns `(task.question, "")` — plain question as user prompt, empty system prompt.
4. `build_judge_prompt(task: BenchmarkTask, result: BenchmarkResult) -> tuple[str, str]`: builds prompts using task-type-specific system prompt template. User prompt fills in `{task_type}`, `{question}`, `{golden_answer}`, `{pass_criteria}`, `{fail_criteria}`, `{submitted_answer}`.
5. Judge output schema enforced in system prompt: `{"verdict":"pass"|"fail","score":<float 0.00-1.00>,"reasoning":"<one sentence>"}`. No markdown, no extra keys.
6. Task-type-specific system prompt variants with different rubric emphasis:
   - `CODE_GENERATION`, `CODE_REVIEW`: correctness, API usage, plausibility to compile.
   - `REASONING`: logical soundness, correct chain of thought.
   - `TRANSLATION`: fidelity to meaning, entity/number preservation, register.
   - `FACTUAL_QA`: accuracy of claimed facts.
   - `TEXT_REWRITE`, `SUMMARIZATION`, `DATA_EXTRACTION`: correctness + format adherence.
   - Default: balanced correctness + completeness rubric.
7. `build_judge_prompt` uses `result.sanitized_response` if non-empty, else `result.raw_response`.
8. Do NOT use the V1 `SYSTEM_PROMPT`/`USER_PROMPT` from `prompt_constants.py`.

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/prompt_constants.py` — V1 templates for reference (to understand what's being replaced).
- `src/ollama_llm_bench/backend/core/models.py` — `TaskType`, `BenchmarkTask.golden_answer`, `BenchmarkTask.pass_criteria`, `BenchmarkTask.fail_criteria`, `BenchmarkResult.sanitized_response`, `BenchmarkResult.raw_response`.
- `src/ollama_llm_bench/backend/services/simple_prompt_builder_api.py` — V1 `build_judge_prompt` pattern for template string filling.

### Implementation Guidance

Store task-type system prompts as module-level constants. Use a `dict[TaskType, str]` dispatch table keyed by `TaskType`. Fall back to `_DEFAULT_JUDGE_SYSTEM_PROMPT` for unhandled types.

The V2 user prompt template (same for all types):
```python
_USER_PROMPT_TEMPLATE = """task_type: {task_type}
question: {question}
golden_answer: {golden_answer}
pass_criteria: {pass_criteria}
fail_criteria: {fail_criteria}
submitted_answer: {submitted_answer}"""
```

```python
def build_judge_prompt(self, task: BenchmarkTask, result: BenchmarkResult) -> tuple[str, str]:
    system_prompt = _JUDGE_SYSTEM_PROMPTS.get(task.task_type, _DEFAULT_JUDGE_SYSTEM_PROMPT)
    answer = result.sanitized_response or result.raw_response or ""
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        task_type=task.task_type.value,
        question=task.question,
        golden_answer=task.golden_answer,
        pass_criteria=task.pass_criteria,
        fail_criteria=task.fail_criteria,
        submitted_answer=answer,
    )
    return user_prompt, system_prompt
```

**Tests**: verify `build_inference_prompt` returns `(task.question, "")`, verify `build_judge_prompt` substitutes all template fields, verify each task type returns distinct system prompt, verify default fallback for unknown task type.

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/services/judge_prompt_service.py` passes
- [ ] `uv run pytest tests/unit/services/test_judge_prompt_service.py -v` passes
- [ ] No Qt imports in the file

---

## Task 6: RuleBasedEvaluator (Layer 1)

**Files to create**: `src/ollama_llm_bench/backend/services/evaluators/__init__.py` (empty)
**Files to create**: `src/ollama_llm_bench/backend/services/evaluators/rule_based_evaluator.py`
**Files to create**: `tests/unit/services/evaluators/__init__.py` (empty)
**Files to create**: `tests/unit/services/evaluators/test_rule_based_evaluator.py`
**Depends on**: Task 1, Task 2

### Context

Layer 1 applies fast, deterministic rules to detect obviously failing responses. A terminal failure stops the pipeline — no expensive embedding or LLM calls wasted. If all rules pass, returns `EvalVerdict.UNKNOWN` with `is_terminal=False` to let the pipeline continue.

### Requirements

1. Class `RuleBasedEvaluator` implements `EvaluatorApi` from Task 2.
2. No constructor dependencies: `def __init__(self) -> None`.
3. `layer` property returns `EvalLayer.RULE_BASED`.
4. `evaluate(task, result) -> EvaluationResult`: run checks in order: inference error → empty → echo → too short → error marker. First failing check returns terminal FAIL.
5. **Inference error check**: if `result.has_inference_error is True` → FAIL, reasoning `"Inference error: {result.inference_error_message}"`.
6. **Empty check**: `(result.sanitized_response or result.raw_response or "").strip() == ""` → FAIL, reasoning `"Response is empty"`.
7. **Echo check**: response (lowercased, stripped) starts with the question (lowercased, stripped, first 100 chars) → FAIL, reasoning `"Response echoes the input prompt"`.
8. **Too short check**: len(stripped response) < `_MIN_RESPONSE_CHARS = 10` → FAIL, reasoning `"Response too short ({n} chars)"`.
9. **Error marker check**: response (lowercased) contains any of `_ERROR_MARKERS = frozenset({"error:", "traceback (most recent call last)", "exception:", "syntaxerror", "nameerror", "typeerror", "fatal error"})` → FAIL.
10. All checks pass → return `EvaluationResult(verdict=EvalVerdict.UNKNOWN, score=0.5, reasoning="All rule-based checks passed", is_terminal=False, layer=EvalLayer.RULE_BASED)`.

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/models.py` — `BenchmarkTask`, `BenchmarkResult` (fields: `sanitized_response`, `raw_response`, `has_inference_error`, `inference_error_message`), `EvaluationResult`, `EvalVerdict`, `EvalLayer`.
- `src/ollama_llm_bench/backend/core/interfaces.py` — `EvaluatorApi(Protocol)` from Task 2.

### Implementation Guidance

```python
_MIN_RESPONSE_CHARS = 10
_ERROR_MARKERS = frozenset({
    "error:", "traceback (most recent call last)", "exception:",
    "syntaxerror", "nameerror", "typeerror", "fatal error",
})

class RuleBasedEvaluator:
    @property
    def layer(self) -> EvalLayer:
        return EvalLayer.RULE_BASED

    def evaluate(self, task: BenchmarkTask, result: BenchmarkResult) -> EvaluationResult:
        response = (result.sanitized_response or result.raw_response or "").strip()

        if result.has_inference_error:
            return self._fail(f"Inference error: {result.inference_error_message}")
        if not response:
            return self._fail("Response is empty")
        if response.lower().startswith(task.question.lower().strip()[:100]):
            return self._fail("Response echoes the input prompt")
        if len(response) < _MIN_RESPONSE_CHARS:
            return self._fail(f"Response too short ({len(response)} chars)")
        if any(marker in response.lower() for marker in _ERROR_MARKERS):
            return self._fail("Response contains error marker")
        return EvaluationResult(verdict=EvalVerdict.UNKNOWN, score=0.5,
                                reasoning="All rule-based checks passed",
                                is_terminal=False, layer=self.layer)

    def _fail(self, reasoning: str) -> EvaluationResult:
        return EvaluationResult(verdict=EvalVerdict.FAIL, score=0.0,
                                reasoning=reasoning, is_terminal=True, layer=self.layer)
```

**Tests**: empty response → FAIL, whitespace-only → FAIL, inference_error=True → FAIL, echo → FAIL, too short → FAIL, error marker → FAIL, valid response → UNKNOWN (is_terminal=False).

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/services/evaluators/rule_based_evaluator.py` passes
- [ ] `uv run pytest tests/unit/services/evaluators/test_rule_based_evaluator.py -v` passes
- [ ] No Qt imports

---

## Task 7: KeywordEvaluator (Layer 2)

**Files to create**: `src/ollama_llm_bench/backend/services/evaluators/keyword_evaluator.py`
**Files to create**: `tests/unit/services/evaluators/test_keyword_evaluator.py`
**Depends on**: Task 1, Task 2, Task 6 (for package `__init__.py`)

### Context

Layer 2 checks `BenchmarkTask.required_terms` — exact must-have terms, forbidden terms, and optionally semantic term similarity using embeddings. If `required_terms` is empty, short-circuits to `UNKNOWN`. Forbidden terms and missing exact terms produce terminal failures.

### Requirements

1. Class `KeywordEvaluator` implements `EvaluatorApi`.
2. Constructor: `def __init__(self, *, embedding_service: EmbeddingProviderApi) -> None`.
3. `layer` property returns `EvalLayer.KEYWORD`.
4. `evaluate(task, result) -> EvaluationResult`:
   - Empty `required_terms` (all three lists empty) → UNKNOWN, non-terminal.
   - Forbidden check first: any forbidden term present (case-insensitive) → FAIL terminal.
   - Exact check: all required exact terms must be in response (case-insensitive). Any missing → FAIL terminal.
   - Semantic check (if `task.required_terms.semantic` non-empty): compute average cosine similarity between each semantic term embedding and the response embedding.
     - `avg_sim >= _SEMANTIC_PASS_THRESHOLD (0.70)` → PASS terminal.
     - `avg_sim < _SEMANTIC_FAIL_THRESHOLD (0.40)` → FAIL terminal.
     - Otherwise → UNKNOWN non-terminal.
   - Exact check passes, no semantic terms → UNKNOWN non-terminal.
5. Cosine similarity: pure Python (no numpy). `dot(a, b) / (norm(a) * norm(b))`. Return `0.0` if either norm is zero.
6. If `embedding_service.encode()` raises → log WARNING, return UNKNOWN non-terminal (don't crash pipeline).
7. Use `result.sanitized_response or result.raw_response or ""` as the response text.

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/models.py` — `RequiredTerms(exact, semantic, forbidden)`, `EvaluationResult`, `EvalVerdict`, `EvalLayer`.
- `src/ollama_llm_bench/backend/core/interfaces.py` — `EmbeddingProviderApi.encode(texts: list[str]) -> list[list[float]]`.

### Implementation Guidance

```python
import math

_SEMANTIC_PASS_THRESHOLD = 0.70
_SEMANTIC_FAIL_THRESHOLD = 0.40

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
```

**Tests**: mock `embedding_service` with `spec=EmbeddingProviderApi`; test each branch.

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/services/evaluators/keyword_evaluator.py` passes
- [ ] `uv run pytest tests/unit/services/evaluators/test_keyword_evaluator.py -v` passes

---

## Task 8: CosineSimilarityEvaluator (Layer 3)

**Files to create**: `src/ollama_llm_bench/backend/services/evaluators/cosine_evaluator.py`
**Files to create**: `tests/unit/services/evaluators/test_cosine_evaluator.py`
**Depends on**: Task 1, Task 2, Task 6

### Context

Layer 3 computes cosine similarity between the response embedding and `golden_answer` embedding. Skipped for task types where semantic similarity is a poor proxy (`CODE_GENERATION`, `CODE_REVIEW`, `REASONING`). The `response_scope` field on the task controls pass/fail thresholds.

### Requirements

1. Class `CosineSimilarityEvaluator` implements `EvaluatorApi`.
2. Constructor: `def __init__(self, *, embedding_service: EmbeddingProviderApi) -> None`.
3. `layer` property returns `EvalLayer.COSINE`.
4. `evaluate(task, result) -> EvaluationResult`:
   - If `task.task_type in _SKIP_TASK_TYPES` → return UNKNOWN non-terminal, reasoning `"Cosine skipped for {task_type}"`.
   - Encode `[task.golden_answer, response]` via `embedding_service.encode()`.
   - Compute cosine similarity (same pure-Python function from Task 7).
   - Look up thresholds from `_SCOPE_THRESHOLDS[task.response_scope]`.
   - `similarity >= pass_threshold` → PASS terminal.
   - `similarity < fail_threshold` → FAIL terminal.
   - Otherwise → UNKNOWN non-terminal.
   - If embedding call fails → log WARNING, return UNKNOWN non-terminal.
5. `_SKIP_TASK_TYPES = frozenset({TaskType.CODE_GENERATION, TaskType.CODE_REVIEW, TaskType.REASONING})`.
6. `_SCOPE_THRESHOLDS: dict[ResponseScope, tuple[float, float]]`:
   - `ResponseScope.EXACT: (0.90, 0.70)`
   - `ResponseScope.CONTAINS: (0.75, 0.50)`
   - `ResponseScope.COVERS: (0.65, 0.40)`

### Existing Code Reference

- `src/ollama_llm_bench/backend/core/models.py` — `ResponseScope`, `TaskType` enums.
- Task 7 `keyword_evaluator.py` — `_cosine_similarity()` function (replicate, don't import).

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/services/evaluators/cosine_evaluator.py` passes
- [ ] `uv run pytest tests/unit/services/evaluators/test_cosine_evaluator.py -v` passes
- [ ] Tests cover: skipped task types, all three `ResponseScope` outcomes, embedding error fallback

---

## Task 9: LLMJudgeEvaluator (Layer 4) + V2 Response Parser

**Files to create**: `src/ollama_llm_bench/backend/services/evaluators/llm_judge_evaluator.py`
**Files to create**: `tests/unit/services/evaluators/test_llm_judge_evaluator.py`
**Files to modify**: `src/ollama_llm_bench/backend/utils/text_utils.py`
**Depends on**: Task 1, Task 2, Task 5

### Context

Layer 4 calls the judge LLM via `ProviderRegistry`. It builds task-type-specific prompts via `JudgePromptService` and parses the judge's structured JSON response. A new `parse_v2_judge_response()` function in `text_utils.py` handles the V2 format (`verdict`, `score`, `reasoning`) — distinct from the existing V1 `parse_judge_response()` which parses `grade` float.

### Requirements

1. Add `parse_v2_judge_response(text: str) -> tuple[bool, EvalVerdict, float, str]` to `text_utils.py`. Returns `(has_error, verdict, score, reasoning)`. Try `json.loads()` first; fall back to regex extraction. Returns `(True, EvalVerdict.UNKNOWN, 0.0, "error reason")` on complete failure. Clamp score to `[0.0, 1.0]`.
2. Class `LLMJudgeEvaluator` implements `LLMJudgeEvaluatorApi` from Task 2.
3. Constructor: `def __init__(self, *, provider_registry: ProviderRegistryApi, judge_prompt_service: JudgePromptServiceApi) -> None`.
4. `layer` property returns `EvalLayer.LLM_JUDGE`.
5. `evaluate(task, result, *, judge_provider_id: str, judge_model: str) -> EvaluationResult`: Build prompts → get provider → call `provider.inference_sync(model, messages, temperature=0.0, max_tokens=256)` → parse response → return `EvaluationResult`.
6. Use `supports_structured_output()` to optionally pass `response_format={"type": "json_object"}` (only if True).
7. Parse error → log WARNING, return non-terminal UNKNOWN (don't lose the result).
8. Provider call exception → log WARNING, return non-terminal UNKNOWN.
9. Successful parse → return terminal `EvaluationResult`.
10. The existing `parse_judge_response()` in `text_utils.py` must NOT be modified — it's still used by V1 code.

### Existing Code Reference

- `src/ollama_llm_bench/backend/utils/text_utils.py` — existing `parse_judge_response()` (V1, returns `(has_error, grade, reason)`). New function follows same tuple signature but handles V2 format.
- `src/ollama_llm_bench/backend/core/interfaces.py` — `ProviderRegistryApi.get_provider(provider_id)`, `LLMProviderApi.inference_sync()`, `LLMProviderApi.supports_structured_output()`.
- Task 5 `judge_prompt_service.py` — `build_judge_prompt()` return type.

### Implementation Guidance

```python
# In text_utils.py — add (do not modify existing parse_judge_response):
import json, re

def parse_v2_judge_response(text: str) -> tuple[bool, EvalVerdict, float, str]:
    from ollama_llm_bench.backend.core.models import EvalVerdict
    cleaned = text.strip()
    try:
        data = json.loads(cleaned)
        verdict_raw = str(data.get("verdict", "")).lower()
        verdict = EvalVerdict.PASS if verdict_raw == "pass" else EvalVerdict.FAIL if verdict_raw == "fail" else EvalVerdict.UNKNOWN
        score = max(0.0, min(1.0, float(data.get("score", 0.0))))
        reasoning = str(data.get("reasoning", ""))
        return False, verdict, score, reasoning
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    # Regex fallback
    v = re.search(r'"verdict"\s*:\s*"(pass|fail)"', cleaned, re.IGNORECASE)
    s = re.search(r'"score"\s*:\s*([0-9.]+)', cleaned)
    r = re.search(r'"reasoning"\s*:\s*"([^"]+)"', cleaned)
    if v and s:
        verdict = EvalVerdict.PASS if v.group(1).lower() == "pass" else EvalVerdict.FAIL
        return False, verdict, max(0.0, min(1.0, float(s.group(1)))), r.group(1) if r else ""
    return True, EvalVerdict.UNKNOWN, 0.0, f"Could not parse: {cleaned[:100]}"
```

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/utils/text_utils.py` passes
- [ ] `uv run mypy src/ollama_llm_bench/backend/services/evaluators/llm_judge_evaluator.py` passes
- [ ] `uv run pytest tests/unit/services/evaluators/test_llm_judge_evaluator.py -v` passes
- [ ] `parse_v2_judge_response` tests: valid JSON, regex fallback, total failure, score clamping

---

## Task 10: QtEventBus — New Signals

**Files to modify**: `src/ollama_llm_bench/ui/qt_classes/qt_event_bus.py`
**Depends on**: Task 1, Task 2

### Context

`QtEventBus` must implement all 15 new subscribe/emit method pairs added to the `EventBus` ABC in Task 2. Each pair follows the exact existing pattern: a private `Signal` in the inner `Signals(QObject)` class and corresponding `subscribe_*`/`emit_*` methods.

### Requirements

1. Add 15 new `Signal(EventType)` attributes to the inner `QtEventBus.Signals(QObject)` class — one per new event type from Task 1.
2. Add 15 new `subscribe_to_*/emit_*` method pairs to `QtEventBus`, following the existing pattern exactly.
3. All `subscribe_to_*` methods: `self._signals.<signal>.connect(callback)`.
4. All `emit_*` methods: `self._signals.<signal>.emit(event)`.
5. After this task, `uv run mypy src/ollama_llm_bench/ui/qt_classes/qt_event_bus.py` must pass with no "abstract method not implemented" errors.
6. Remove any `NotImplementedError` stubs added temporarily in Task 2.
7. Keep ALL existing signals and methods unchanged — purely additive.

### Existing Code Reference

- `src/ollama_llm_bench/ui/qt_classes/qt_event_bus.py` — read the FULL file. The existing pattern e.g.: `_run_id_changed = Signal(int)` in `Signals` class + `subscribe_to_run_id_changed(callback)`/`emit_run_id_changed(value)` methods in outer class.

### Implementation Guidance

```python
# In Signals(QObject) inner class — add 15 signals:
benchmark_started = Signal(BenchmarkStartedEvent)
benchmark_paused = Signal(BenchmarkPausedEvent)
benchmark_resumed = Signal(BenchmarkResumedEvent)
benchmark_stopped = Signal(BenchmarkStoppedEvent)
benchmark_finished = Signal(BenchmarkFinishedEvent)
provider_switch = Signal(ProviderSwitchEvent)
provider_health_check = Signal(ProviderHealthCheckEvent)
model_switch = Signal(ModelSwitchEvent)
task_switch = Signal(TaskSwitchEvent)
mode_switch = Signal(ModeSwitchEvent)
task_completed = Signal(TaskCompletedEvent)
judge_started = Signal(JudgeStartedEvent)
judge_completed = Signal(JudgeCompletedEvent)
streaming_chunk = Signal(StreamingChunkEvent)
progress_update = Signal(ProgressUpdateEvent)

# In QtEventBus outer class — add 30 methods (15 subscribe + 15 emit pairs):
def subscribe_to_benchmark_started(self, callback: Callable[[BenchmarkStartedEvent], None]) -> None:
    self._signals.benchmark_started.connect(callback)

def emit_benchmark_started(self, event: BenchmarkStartedEvent) -> None:
    self._signals.benchmark_started.emit(event)
# ... repeat for all 14 remaining pairs
```

Add all new event type imports to the import block at the top of the file.

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/ui/qt_classes/qt_event_bus.py` passes (no abstract method errors)
- [ ] `uv run pytest tests/unit/` — all existing tests still pass

---

## Task 11: BenchmarkExecutionTask V2 Rewrite

**Files to modify**: `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py`
**Depends on**: Tasks 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

### Context

Complete rewrite of `BenchmarkExecutionTask`. The V1 version uses `LLMApi` (Ollama-only) and has a simple two-stage pipeline. V2 uses `ProviderRegistry`, runs a four-stage pipeline (INITIALIZING → BENCHMARKING → JUDGING → FINISHED/FAILED), streams with a 20 Hz buffer, implements pause/resume via `threading.Event`, runs the 4-layer evaluator pipeline, and emits all new events via `EventBus`.

### Requirements

1. New constructor signature (positional — QRunnable requires it):
   ```python
   def __init__(
       self,
       run_id: int,
       data_api: DataApi,
       task_loader: TaskFileLoaderApi,
       judge_prompt_service: JudgePromptServiceApi,
       provider_registry: ProviderRegistryApi,
       event_bus: EventBus,
       app_settings: AppSettingsServiceApi,
       rule_evaluator: EvaluatorApi,
       keyword_evaluator: EvaluatorApi,
       cosine_evaluator: EvaluatorApi,
       llm_judge_evaluator: LLMJudgeEvaluatorApi,
   ) -> None
   ```

2. **Pause/resume**: Add `_pause_event: threading.Event` initialized as `threading.Event(); _pause_event.set()` (set = not paused). Add:
   - `pause()` — clears `_pause_event`, emits `BenchmarkPausedEvent(run_id, PauseReason.USER, current_stage)`.
   - `resume()` — sets `_pause_event`, emits `BenchmarkResumedEvent(run_id)`.
   - `_check_pause_or_stop() -> bool` — if `_stop_requested` return False; if `not _pause_event.is_set()` then `_pause_event.wait()` (blocks); return `not _stop_requested`.

3. **STAGE_INITIALIZING**:
   - Load `run = data_api.retrieve_benchmark_run(run_id)`.
   - Load tasks: `task_loader.load_tasks([Path(p) for p in run.task_file_paths])`.
   - For each selected model in `run.models_json` × each task: insert `BenchmarkResult` rows with status `NOT_COMPLETED` if not already in DB (resumability: skip existing rows).
   - Emit `BenchmarkStartedEvent(run_id, total_tasks, models=tuple(descriptors), run_mode)`.

4. **STAGE_BENCHMARKING**: Group results by `provider_id`. For each provider group:
   - Check `app_settings.get_bool(SETTING_PAUSE_ON_PROVIDER_SWITCH)` → emit `ProviderSwitchEvent`, call `_check_pause_or_stop()`.
   - Health check: call `provider.get_available_models()`. Emit `ProviderHealthCheckEvent`. If unhealthy and `SETTING_STOP_ON_PROVIDER_ERROR` → return.
   - For each model: emit `ModelSwitchEvent`, optionally warm up (if `SETTING_WARMUP_ENABLED`), check `SETTING_PAUSE_ON_MODEL_SWITCH`.
   - For each task result: emit `TaskSwitchEvent`, run inference (streaming or sync per `SETTING_STREAMING_ENABLED`), emit `TaskCompletedEvent`.
   - Resumability: skip results with status != `NOT_COMPLETED`.

5. **Dual-mode inference** (streaming):
   - Buffer stream chunks in `list[str]`, emit batched `StreamingChunkEvent` via `event_bus.emit_streaming_chunk()` at 20 Hz max (50 ms interval). Flush on completion.
   - Track `last_emit_time = time.monotonic()`.

6. **STAGE_JUDGING** (skipped when `run.run_mode == RunMode.SPEED`):
   - For each result with status `WAITING_FOR_JUDGE`:
   - Layer 1: `rule_evaluator.evaluate(task, result)`. Emit `JudgeStartedEvent`/`JudgeCompletedEvent`. If terminal → write result, next record.
   - Layer 2–4: same pattern. Layer 4: `llm_judge_evaluator.evaluate(task, result, judge_provider_id=run.judge_provider_id, judge_model=run.judge_model)`.
   - Write final verdict fields to DB result: `final_verdict`, `resolution_layer`, `judge_score`, `judge_reasoning`, per-layer fields.
   - Update result status to `COMPLETED` or `FAILED`.

7. **ProgressUpdateEvent**: Emit after each task completion. Compute `estimated_remaining_ms` using rolling average of last 10 task durations.

8. **Speed mode**: After inference, set status directly to `COMPLETED` (skip `WAITING_FOR_JUDGE`). Skip STAGE_JUDGING entirely.

9. **Error isolation**: Wrap each task's inference and each evaluator layer call in `try/except`. Log + update to FAILED on exception. Never let a single task failure crash the run.

10. Keep inner `Signals(QObject)` class with existing `status_changed`, `log_message`, `progress` signals — they are still used by `QtBenchmarkFlowApi`.

11. Emit `BenchmarkFinishedEvent` or `BenchmarkStoppedEvent` in the `finally` block.

### Existing Code Reference

- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` — read the FULL existing file. Preserve: inner `Signals` class, `setAutoDelete(True)`, `_notify`/`_notify_warn` pattern, error recovery in `_update_failed_task`.
- `src/ollama_llm_bench/backend/core/interfaces.py` — `ProviderRegistryApi.get_provider(provider_id)`, `DataApi.retrieve_benchmark_run()`, `DataApi.retrieve_benchmark_results_for_run_with_status()`.
- `src/ollama_llm_bench/backend/core/models.py` — `BenchmarkRun.task_file_paths: list[str]`, `BenchmarkRun.judge_provider_id`, `BenchmarkRun.judge_model`, `BenchmarkRun.run_mode`, `BenchmarkResult.provider_id`, `BenchmarkResult.model_name`.
- `src/ollama_llm_bench/backend/services/app_settings_service.py` (Task 3) — setting key constants (`SETTING_STREAMING_ENABLED`, `SETTING_WARMUP_ENABLED`, etc.).

### Implementation Guidance

20 Hz streaming buffer pattern:
```python
_STREAM_EMIT_INTERVAL_S = 0.05  # 20 Hz

def _run_streaming_inference(self, ...) -> InferenceResponse:
    buffer: list[str] = []
    last_emit = time.monotonic()
    final_response: InferenceResponse | None = None

    for item in provider.inference_stream(model=model, messages=messages, ...):
        if isinstance(item, StreamChunk) and item.delta_content:
            buffer.append(item.delta_content)
            now = time.monotonic()
            if now - last_emit >= _STREAM_EMIT_INTERVAL_S:
                self._flush_chunk_buffer(buffer, result_id, model_name, task_id)
                buffer.clear()
                last_emit = now
        elif isinstance(item, InferenceResponse):
            final_response = item
    if buffer:
        self._flush_chunk_buffer(buffer, result_id, model_name, task_id)
    return final_response or InferenceResponse(has_error=True, error_message="No response received", ...)
```

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/ui/qt_classes/qt_benchmark_execution_task.py` passes
- [ ] `uv run pytest tests/unit/` — no regressions
- [ ] `uv run ollama_llm_bench` — starts without errors
- [ ] With a live Ollama instance: start a run → INITIALIZING → BENCHMARKING (streaming visible) → JUDGING (4-layer logs) → FINISHED
- [ ] Pause mid-run: task halts at stage boundary; resume continues correctly

---

## Task 12: ApplicationContext Wiring

**Files to modify**: `src/ollama_llm_bench/app_context.py`
**Files to modify**: `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_flow.py`
**Files to modify**: `src/ollama_llm_bench/backend/core/interfaces.py` (add getters to `AppContext` ABC)
**Depends on**: Tasks 3, 4, 5, 6, 7, 8, 9, 11

### Context

`_create_app_context()` must wire all new Phase 2 services into the dependency graph. `ApplicationContext` exposes new getter methods. `QtBenchmarkFlowApi` receives new services via its constructor and passes them to `BenchmarkExecutionTask` on `start_execution()`.

### Requirements

1. In `_create_app_context()`, instantiate in order:
   - `task_loader = TaskFileLoader()`
   - `app_settings = AppSettingsService(data_api=data_api)`
   - `judge_prompt_svc = JudgePromptService()`
   - `embedding_provider = provider_registry.get_embedding_provider()`
   - `rule_evaluator = RuleBasedEvaluator()`
   - `keyword_evaluator = KeywordEvaluator(embedding_service=embedding_provider)`
   - `cosine_evaluator = CosineSimilarityEvaluator(embedding_service=embedding_provider)`
   - `llm_judge_evaluator = LLMJudgeEvaluator(provider_registry=provider_registry, judge_prompt_service=judge_prompt_svc)`
2. Pass all new services to `QtBenchmarkFlowApi` constructor.
3. Add to `ApplicationContext`: `get_app_settings_service() -> AppSettingsServiceApi`, `get_task_file_loader() -> TaskFileLoaderApi`, `get_judge_prompt_service() -> JudgePromptServiceApi`.
4. Update `AppContext` ABC in `interfaces.py` with the three new `@abstractmethod` getters.
5. Update `QtBenchmarkFlowApi.__init__()` to accept all new services; update `start_execution()` to pass them all to `BenchmarkExecutionTask(...)`.
6. Check all usages of `OllamaApi` before removing it — keep it if any controller or widget still references it directly.
7. All new imports added to top of `app_context.py`.

### Existing Code Reference

- `src/ollama_llm_bench/app_context.py` — read the FULL file. Note `ApplicationContext` slot-based constructor, `_create_app_context()` wiring sequence, how `QtBenchmarkFlowApi` is currently instantiated.
- `src/ollama_llm_bench/ui/qt_classes/qt_benchmark_flow.py` — read the FULL file. The `start_execution()` method instantiates `BenchmarkExecutionTask`.

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/app_context.py` passes
- [ ] `uv run mypy src/ollama_llm_bench/ui/qt_classes/qt_benchmark_flow.py` passes
- [ ] `uv run pytest tests/unit/` — all tests pass
- [ ] `uv run ollama_llm_bench` — app starts without errors

---

## Task 13: UI Progress Widget (Structured)

**Files to modify**: identify exact file(s) by reading `src/ollama_llm_bench/ui/widgets/` before starting
**Depends on**: Task 10, Task 12

### Context

The progress area replaces flat text output with a structured widget of named, independently-updating fields. Each field is driven by new EventBus events. **Before starting this task**: read the `pyside6-ui` skill and `docs/v2/v2-ui-design-guide.html` for the exact widget mockup and design token colors.

### Requirements

1. Create `ProgressPanelWidget(QWidget)` with these named child widgets:
   - `_stage_badge: QLabel` — stage name with colored background.
   - `_progress_bar: QProgressBar` — `tasks_completed / tasks_total * 100`.
   - `_progress_label: QLabel` — `"341 / 539 (63%)"`.
   - `_eta_label: QLabel` — `"ETA: 14 min"` or `"ETA: –"` when `estimated_remaining_ms` is None.
   - `_provider_label: QLabel` — current provider.
   - `_model_label: QLabel` — current model.
   - `_task_label: QLabel` — current task ID (truncated; full text as tooltip via `setToolTip()`).
   - `_elapsed_label: QLabel` — `"2h 48m 33s"` format using `time_utils.format_elapsed_time()`.
2. Subscribe to `event_bus.subscribe_to_progress_update()` — update all fields.
3. Stage badge background colors (via `setStyleSheet` or QSS):
   - INITIALIZING → blue (`#2196F3`)
   - BENCHMARKING → orange (`#FF9800`)
   - JUDGING → purple (`#9C27B0`)
   - FINISHED → green (`#4CAF50`)
   - FAILED → red (`#F44336`)
4. Subscribe to `subscribe_to_benchmark_finished()` → update `_eta_label` with `"Finished"`.
5. Subscribe to `subscribe_to_benchmark_stopped()` → set `_stage_badge` text to `"Stopped"` with grey background.
6. Layout: `QVBoxLayout` with `QHBoxLayout` rows.
7. Constructor: `def __init__(self, *, event_bus: EventBus, parent: QWidget | None = None) -> None`.
8. Widget file location: place in the same package as existing panel widgets (follow codebase convention).

### Existing Code Reference

- Read ALL files in `src/ollama_llm_bench/ui/widgets/` to understand existing structure and where the current progress display is.
- `src/ollama_llm_bench/backend/utils/time_utils.py` — `format_elapsed_time()` for elapsed display.
- `docs/v2/v2-ui-design-guide.html` — **must read** for design token values and layout mockup.

### Verification

- [ ] `uv run mypy` on the modified widget file passes
- [ ] App starts without errors
- [ ] Start a benchmark run → progress panel updates live with stage badge, model, task, ETA

---

## Task 14: UI Log Panel (Structured) + LogFileWriter Service

**Files to create**: `src/ollama_llm_bench/backend/services/log_file_writer.py`
**Files to create**: `tests/unit/services/test_log_file_writer.py`
**Files to modify**: log widget file(s) in `src/ollama_llm_bench/ui/widgets/` (identify by reading directory)
**Depends on**: Task 10, Task 12, Task 13

### Context

The log panel becomes a structured widget rendering different entry types with distinct visual treatment. Log entries are delivered via 20 Hz buffered `StreamingChunkEvent`. A scrollback limit prevents unbounded memory growth. `LogFileWriter` writes entries to disk when `feature.log_to_file` is enabled. **Before starting this task**: read the `pyside6-ui` skill and `docs/v2/v2-ui-design-guide.html`.

### Requirements

**LogFileWriter service**:
1. Class `LogFileWriter` implements `LogFileWriterApi` from Task 2.
2. Constructor: `def __init__(self, *, app_root: Path) -> None`. Log files: `app_root / "logs" / "benchmark_{run_id}_{timestamp}.log"`.
3. `write_entry(run_id, entry_type, content)` — appends `"[HH:MM:SS] [{entry_type}] {content}\n"`.
4. `get_log_path(run_id) -> Path`.
5. `close(run_id)` — flushes and closes file handle. Removes from internal dict.
6. `dict[int, IO[str]]` to track open handles. Files opened with `encoding="utf-8"`, `buffering=1`.
7. Unit tests use `tmp_path` fixture.

**Log widget**:
8. Subscribe to `event_bus.subscribe_to_streaming_chunk()` — buffer to a `list[str]`, drain via a `QTimer` with 50 ms interval (20 Hz). Append drained text to the display.
9. Subscribe to `event_bus.subscribe_to_task_completed()` — append formatted inference summary line.
10. Subscribe to `event_bus.subscribe_to_judge_completed()` — append verdict line.
11. Enforce line cap: when line count exceeds `app_settings.get_int(SETTING_LOG_MAX_LINES, 10000)`, remove oldest lines from top.
12. Auto-scroll: track `QScrollBar` position. If user scrolled up manually, disable auto-scroll and show a `"↓ Jump to bottom"` button. Re-enable when user returns to bottom or clicks the button.
13. `QTimer` started on `subscribe_to_benchmark_started`, stopped on `subscribe_to_benchmark_finished`/`subscribe_to_benchmark_stopped`.

### Existing Code Reference

- Read log widget file(s) in `src/ollama_llm_bench/ui/widgets/` to understand current log display implementation.
- `src/ollama_llm_bench/backend/services/app_settings_service.py` (Task 3) — `SETTING_LOG_MAX_LINES`, `SETTING_LOG_TO_FILE`.
- `docs/v2/v2-ui-design-guide.html` — log entry type visual rendering spec.

### Verification

- [ ] `uv run mypy src/ollama_llm_bench/backend/services/log_file_writer.py` passes
- [ ] `uv run pytest tests/unit/services/test_log_file_writer.py -v` passes
- [ ] `uv run ollama_llm_bench` — streaming output appears in log panel without UI freezing
- [ ] Setting `feature.log_to_file = true` (via `AppSettingsService`) → log file appears in `logs/`

---

## Final Verification Checklist

When ALL tasks are complete, verify end-to-end:

- [ ] `uv run ruff check --output-format=concise src/ tests/` — zero violations
- [ ] `uv run ruff format --check src/ tests/` — zero formatting issues
- [ ] `uv run mypy src/` — zero errors
- [ ] `uv run pytest tests/ -v` — all tests pass, no regressions
- [ ] `uv run ollama_llm_bench` — app starts without import errors or crashes
- [ ] Create a `RunMode.FULL_GRADING` run: verify INITIALIZING → BENCHMARKING (streaming chunks visible) → JUDGING (4-layer eval logs visible) → FINISHED
- [ ] Create a `RunMode.SPEED` run: verify inference only, no judging stage
- [ ] Pause mid-run via Pause button: task halts at stage boundary without crash
- [ ] Resume paused run: execution continues, `BenchmarkResumedEvent` emitted
- [ ] Restart partially-completed run: `NOT_COMPLETED` re-run, `WAITING_FOR_JUDGE` go straight to judging, `COMPLETED` skipped
- [ ] No Qt imports in `core/` or `services/` — `uv run ruff check` reports no architecture violations
- [ ] All new classes use dependency injection with keyword-only constructor args
- [ ] All public methods have type annotations
- [ ] CLAUDE.md V2 New Services table updated — Phase 2 services marked as IMPLEMENTED
