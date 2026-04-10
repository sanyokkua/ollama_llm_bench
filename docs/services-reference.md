# Services API Reference

This document lists every service interface (ABC) in `src/ollama_llm_bench/core/interfaces.py` alongside its concrete implementation under `src/ollama_llm_bench/services/` or `src/ollama_llm_bench/qt_classes/`.
Docstrings are in the source and the coding rules require Google-style summaries; this document provides the cross-reference and usage notes you cannot derive by reading a single file.

## Interface → Implementation Map

```mermaid
classDiagram
    class LLMApi {
        <<ABC>>
        +get_models_list() list~str~
        +warm_up(model_name) bool
        +inference(...) InferenceResponse
    }
    class OllamaApi {
        -_ollama_client: ollama.Client
    }
    LLMApi <|.. OllamaApi

    class DataApi {
        <<ABC>>
        +create_benchmark_run(run) int
        +retrieve_benchmark_runs() list
        +update_benchmark_run(run)
        +delete_benchmark_run(run_id)
        +create_benchmark_result(r) int
        +retrieve_benchmark_results_for_run(id) list
        +update_benchmark_result(r)
    }
    class SqLiteDataApi {
        -db_path: Path
    }
    DataApi <|.. SqLiteDataApi

    class ResultApi {
        <<ABC>>
        +retrieve_avg_benchmark_results_for_run(id) list
        +retrieve_detailed_benchmark_results_for_run(id) list
    }
    class AppResultApi
    ResultApi <|.. AppResultApi

    class BenchmarkTaskApi {
        <<ABC>>
        +load_tasks() list
        +get_task(task_id) BenchmarkTask
    }
    class YamlBenchmarkTaskApi
    BenchmarkTaskApi <|.. YamlBenchmarkTaskApi

    class PromptBuilderApi {
        <<ABC>>
        +build_prompt(task_id) str
        +build_judge_prompt(result) tuple
    }
    class SimplePromptBuilderApi
    PromptBuilderApi <|.. SimplePromptBuilderApi

    class BenchmarkFlowApi {
        <<ABC>>
        +start_execution(run_id)
        +stop_execution()
        +is_running() bool
        +get_current_run_id() int
    }
    class QtBenchmarkFlowApi
    BenchmarkFlowApi <|.. QtBenchmarkFlowApi

    class EventBus {
        <<ABC>>
        +subscribe_to_*(callback)
        +emit_*(value)
    }
    class QtEventBus
    EventBus <|.. QtEventBus

    class ITableSerializer {
        <<ABC>>
        +save_summary_as_csv(items)
        +save_summary_as_md(items)
        +save_details_as_csv(items)
        +save_details_as_md(items)
    }
    class TableSerializer
    ITableSerializer <|.. TableSerializer
```

## `LLMApi` → `OllamaApi`

- **ABC**: `src/ollama_llm_bench/core/interfaces.py` (`class LLMApi`).
- **Implementation**: `src/ollama_llm_bench/services/ollama_llm_api.py` (`class OllamaApi`).
- **Dependencies**: an `ollama.Client` instance (created in `_create_app_context` with `timeout=300`).

### Methods

| Method | Signature | Notes |
|---|---|---|
| `get_models_list` | `() -> list[str]` | Sorted, deduplicated list of Ollama model names. Returns `[]` on error (logged). **Annotation bug**: the source annotation says `List[dict]` but the body returns `list[str]` — see [technical-debt.md](technical-debt.md). |
| `warm_up` | `(model_name: str) -> bool` | Calls `generate(model=..., prompt="Say Hello")` with up to **5** attempts; sleeps **30 s** between failures. Returns `True` on first success, `False` if all retries fail. |
| `inference` | `(*, model_name, user_prompt, system_prompt=None, on_llm_response=None, on_is_stop_signal=None, is_judge_mode=False) -> InferenceResponse` | Calls `client.generate(..., stream=False)`, measures wall clock, counts `response.eval_count` tokens, sanitises the response with `sanitize_text` (strips `<think>...</think>`). On exception, returns `InferenceResponse(has_error=True, error_message=...)`. |

### Usage Pattern

```python
# Warm up once before looping
if not llm_api.warm_up(model_name):
    return  # bail — Ollama is unresponsive

# Per task
response = llm_api.inference(
    model_name=model_name,
    user_prompt=prompt,
    system_prompt="",          # benchmarking stage: no system prompt
    on_llm_response=callback,  # live log stream
    on_is_stop_signal=self.is_stopped,  # cooperative cancellation
)
```

The cancellation callback `on_is_stop_signal` is plumbed through the Ollama client but `OllamaApi.inference` does not currently check it during the blocking `generate` call — the user's stop request is honoured *between* inferences, not mid-inference.

### Callers

- `BenchmarkExecutionTask._execute_benchmark_task` — benchmarking inference
- `BenchmarkExecutionTask._judge_task` — judging inference (with `is_judge_mode=True`)
- `BenchmarkExecutionTask._warmup_model` — pre-flight warm-up
- `NewRunWidgetController._get_available_models` — populate the test models list
- `ApplicationContext.send_initialization_events` — populate the judge dropdown on app start

## `DataApi` → `SqLiteDataApi`

- **ABC**: `core/interfaces.py` (`class DataApi`).
- **Implementation**: `src/ollama_llm_bench/services/sq_lite_data_api.py`.
- **Dependency**: a `Path` to the SQLite file.

### Connection Semantics

Every method opens a fresh connection via `with sqlite3.connect(self.db_path) as conn`.
No pooling, no persistent cursor.
This makes the service trivially thread-safe *for this project's access patterns*: the worker thread writes status updates while the main thread reads rows, and SQLite handles the coordination at the file level.

### Method Reference

#### Benchmark Runs

| Method | Purpose |
|---|---|
| `create_benchmark_run(run) -> int` | Insert a `BenchmarkRun`; returns `cursor.lastrowid` |
| `retrieve_benchmark_run(run_id) -> BenchmarkRun` | Fetch one; raises `ValueError` if not found |
| `retrieve_benchmark_runs() -> list[BenchmarkRun]` | Fetch all |
| `retrieve_benchmark_runs_with_status(status) -> list[BenchmarkRun]` | Filter by `BenchmarkRunStatus` |
| `update_benchmark_run(run)` | Update every field by `run_id` |
| `delete_benchmark_run(run_id)` | Delete by id; logs a warning if zero rows affected |

#### Benchmark Results

| Method | Purpose |
|---|---|
| `create_benchmark_result(result) -> int` | Insert one result |
| `create_benchmark_results(list)` | Bulk insert (used on run initialization to create `models × tasks` rows) |
| `retrieve_benchmark_result(result_id) -> BenchmarkResult` | Fetch one; raises `ValueError` if not found |
| `retrieve_benchmark_results_for_run(run_id) -> list[BenchmarkResult]` | All results for one run |
| `retrieve_benchmark_results_for_run_with_status(*, run_id, status) -> list[BenchmarkResult]` | Drives resumability — the benchmarking stage filters on `NOT_COMPLETED`, the judging stage filters on `WAITING_FOR_JUDGE` |
| `update_benchmark_result(result)` | Update every field by `result_id`; because `BenchmarkResult` is frozen, this is the only mutation path |
| `delete_benchmark_result(result_id)` | Delete by id |

### Callers

- Controllers call `create_*`, `retrieve_*`, `delete_*` synchronously on the main thread.
- `BenchmarkExecutionTask` calls `retrieve_*_for_run*` and `update_benchmark_result` from the worker thread.

## `ResultApi` → `AppResultApi`

- **ABC**: `core/interfaces.py` (`class ResultApi`).
- **Implementation**: `src/ollama_llm_bench/services/app_result_api.py`.
- **Dependencies**: `DataApi` (passed via `__init__(*, data_api)`).

### Methods

| Method | Returns | Notes |
|---|---|---|
| `retrieve_avg_benchmark_results_for_run(run_id)` | `list[AvgSummaryTableItem]` | One row per model. Groups with `defaultdict(list)`, computes `avg_time`, `avg_score`, and `avg_tokens_per_second = (sum_tokens / sum_time_ms) * 1000` with a guard for `sum_time_ms == 0`. |
| `retrieve_detailed_benchmark_results_for_run(run_id)` | `list[SummaryTableItem]` | One row per stored result. Computes per-row `tokens_per_second`. Handles `None` values via `or 0`. |

Both methods guard on `run_id <= 0` and return `[]`.
Both return `[]` on any exception (logged).

### Callers

- `StatusListener._get_summary_data` and `StatusListener._get_detailed_data` — called whenever the selected run changes or a benchmark stage transitions to `FINISHED` / `FAILED`.

## `BenchmarkTaskApi` → `YamlBenchmarkTaskApi`

- **ABC**: `core/interfaces.py` (`class BenchmarkTaskApi`).
- **Implementation**: `src/ollama_llm_bench/services/yaml_benchmark_task_api.py`.
- **Dependency**: `task_folder_path: Path` (keyword-only).

### Methods

| Method | Returns | Notes |
|---|---|---|
| `load_tasks()` | `list[BenchmarkTask]` | Iterates `*.yaml` / `*.yml` in the folder, parses with `yaml.safe_load`, accepts either single-object or list-of-objects shape, skips malformed entries with a warning. **Cached** — subsequent calls return `self._tasks_cache`. |
| `get_task(task_id)` | `BenchmarkTask` | Lazy-loads the cache if empty, then returns from an internal `dict`. Raises `ValueError` if `task_id` is missing. |

### Error Handling

- Missing required field (e.g. `task_id`) → logged as warning, task skipped.
- YAML parse error → logged as error, file skipped.
- Empty YAML → logged as debug, file skipped.

See [dataset-format.md](dataset-format.md) for the required field set.

### Callers

- `NewRunWidgetController.handle_start_click` — calls `load_tasks()` to produce per-model `BenchmarkResult` rows.
- `SimplePromptBuilderApi.build_prompt` / `build_judge_prompt` — calls `get_task(task_id)`.

## `PromptBuilderApi` → `SimplePromptBuilderApi`

- **ABC**: `core/interfaces.py` (`class PromptBuilderApi`).
- **Implementation**: `src/ollama_llm_bench/services/simple_prompt_builder_api.py`.
- **Dependency**: `task_api: BenchmarkTaskApi`.

### Methods

| Method | Returns | Notes |
|---|---|---|
| `build_prompt(task_id)` | `str` | Returns `task.question` verbatim. No templating. The test model sees the raw question. |
| `build_judge_prompt(benchmark_result)` | `tuple[str, str]` — `(user_prompt, system_prompt)` | Looks up the task by `benchmark_result.task_id`, fills the `USER_PROMPT` template via `str.replace` over 8 placeholders (`{question}`, `{most_expected}`, `{good_answer}`, `{pass_option}`, `{incorrect_direction}`, `{answer}`, `{category}`, `{sub_category}`), returns it alongside the static `SYSTEM_PROMPT`. |

The system prompt is the large rubric in `core/prompt_constants.py` and is always the same string.
The user prompt differs per task and per test model (because `{answer}` is the test model's response).

### Callers

- `BenchmarkExecutionTask._execute_benchmark_task` — builds the benchmark prompt.
- `BenchmarkExecutionTask._judge_task` — builds the judge prompt.

## `BenchmarkFlowApi` → `QtBenchmarkFlowApi`

- **ABC**: `core/interfaces.py` (`class BenchmarkFlowApi`).
- **Implementation**: `src/ollama_llm_bench/qt_classes/qt_benchmark_flow.py` (`class QtBenchmarkFlowApi(QObject, BenchmarkFlowApi, metaclass=MetaQObjectABC)`).
- **Dependencies**: `data_api`, `task_api`, `prompt_builder_api`, `llm_api`, `thread_pool: QThreadPool`.

### Methods

| Method | Signature | Notes |
|---|---|---|
| `start_execution` | `(run_id: int) -> None` | Guards against re-entry (`is_running()`), validates that `benchmark_runs.status == NOT_COMPLETED` (raises `ValueError` otherwise), creates a new `BenchmarkExecutionTask`, wires its nested `Signals` to the three public signals, and submits it to the thread pool. |
| `stop_execution` | `() -> None` | No-op if nothing is running; otherwise calls `task.stop()` on the current task — which sets `_stop_requested = True` and is observed at the next task boundary. |
| `is_running` | `() -> bool` | `self._current_task is not None and not self._current_task.is_stopped()` |
| `get_current_run_id` | `() -> Optional[int]` | Returns the currently-executing run id or `None`. |

### Signals (public, forwarded onto the EventBus via lambdas in `_create_app_context`)

| Signal | Payload | Forwarded to EventBus signal |
|---|---|---|
| `benchmark_status_events` | `bool` | `_background_thread_is_running` |
| `benchmark_output_events` | `str` | `_log_append` |
| `benchmark_progress_events` | `ReporterStatusMsg` | `_background_thread_progress_changed` |

`subscribe_to_benchmark_status_events` fires an **immediate** callback with the current status at subscription time — so components added later in construction still learn the current state.

### Task Lifecycle

```mermaid
flowchart LR
    start["start_execution(run_id)"] --> validate["validate run<br/>status == NOT_COMPLETED"]
    validate --> mkTask["new BenchmarkExecutionTask"]
    mkTask --> connect["connect task.signals → self signals"]
    connect --> submit["thread_pool.start(task)"]
    submit --> emit["benchmark_status_events.emit(True)"]
    emit -.-> run["task.run() on worker thread"]
    run -.-> done["task finishes"]
    done -.-> emitStop["benchmark_status_events.emit(False)"]
```

## `EventBus` → `QtEventBus`

- **ABC**: `core/interfaces.py` (`class EventBus`).
- **Implementation**: `src/ollama_llm_bench/qt_classes/qt_event_bus.py` (`class QtEventBus(QObject, EventBus, metaclass=MetaQObjectABC)`).
- **Dependencies**: none (just `QObject.__init__`).

Eleven `pyqtSignal` attributes plus 22 public methods (11 subscribe, 11 emit).
See [architecture.md](architecture.md#eventbus) for the full signal catalogue and publisher/subscriber map.

**Usage convention**: components that need to *listen* receive the `EventBus` in their constructor and immediately call `subscribe_to_*` methods.
Components that need to *publish* hold the same reference and call `emit_*` methods.

## `ITableSerializer` → `TableSerializer`

- **ABC**: `core/interfaces.py` (`class ITableSerializer`).
- **Implementation**: `src/ollama_llm_bench/services/table_serializer.py`.
- **Dependency**: `root_dir: Path` (created if missing).

### Methods and Output Files

| Method | Output file | Unit conversions |
|---|---|---|
| `save_summary_as_csv(items)` | `<root>/summary.csv` | `avg_time_ms / 1000` → seconds, `avg_score * 100` → percentage, 3-decimal rounding |
| `save_summary_as_md(items)` | `<root>/summary.md` | same |
| `save_details_as_csv(items)` | `<root>/details.csv` | 3-decimal rounding on `tokens_per_second` and `score` |
| `save_details_as_md(items)` | `<root>/details.md` | same |

### Headers

```python
TABLE_SUMMARY_HEADER = ["MODEL", "AVG. TIME (s)", "AVG. TOKENS/s", "AVG. SCORE (%)"]
TABLE_DETAILED_HEADER = ["MODEL", "TASK", "STATUS", "TIME (ms)", "Tokens", "TOKENS/s", "SCORE", "REASON"]
```

### Callers

- `ResultWidgetController.handle_summary_export_csv_click` and the three sibling export handlers.

## Dependency Injection Summary

Every service has its dependencies fixed at construction time in `app_context._create_app_context()`:

| Service | Constructor arguments |
|---|---|
| `OllamaApi` | `client: ollama.Client` |
| `SqLiteDataApi` | `db_path: Path` |
| `AppResultApi` | `*, data_api: DataApi` |
| `YamlBenchmarkTaskApi` | `*, task_folder_path: Path` |
| `SimplePromptBuilderApi` | `*, task_api: BenchmarkTaskApi` |
| `TableSerializer` | `root_dir: Path` |
| `QtBenchmarkFlowApi` | `*, data_api, task_api, prompt_builder_api, llm_api, thread_pool` |
| `QtEventBus` | *(none)* |

Controllers follow the same keyword-only-argument convention — see [developer-guide.md](developer-guide.md).

## Related Documents

- [architecture.md](architecture.md) — layer rules and package responsibilities
- [data-model.md](data-model.md) — the dataclasses these methods return
- [benchmark-pipeline.md](benchmark-pipeline.md) — how these services compose
- [developer-guide.md](developer-guide.md) — how to add a new service
