## Abstraction Module Specification

**Location**: `src/core/abstraction/`

* `benchmark_api.py`       — `BenchmarkApi` interface
* `data_manager_api.py`    — `DataManagerApi` interface
* `dataset_loader_api.py`  — `DataSetLoaderApi` interface
* `llm_manager_api.py`     — `LLMManagerApi` interface
* `prompt_api.py`          — `PromptApi` interface
* `task_manager_api.py`    — `TaskManagerApi` interface
* `types.py`               — dataclasses: `BenchmarkTask`, `ExpectedAnswer`, `Result`, `BenchmarkConfig`, `BenchmarkProgress`
* `enums.py`               — enums: `TaskStatus`, `BenchmarkEvent`

---

### 1. Abstract Flow Overview

1. **Model Selection**

   * UI calls `LLMManagerApi.list_models()`
   * Calls `BenchmarkApi.select_models(...)` & `select_judge_model(...)`
2. **Benchmark Initialization**

   * `BenchmarkApi.start_benchmark()`
   * Persists run via `DataManagerApi.create_run`
   * Loads tasks via `DataSetLoaderApi.load_tasks`
   * Saves tasks via `DataManagerApi.save_tasks`
   * Emits `BenchmarkEvent.STARTED`
3. **Task Execution**

   * Loop models × tasks:

     * `BaselineApi` submits each using `TaskManagerApi.submit_task`
     * Subscribes to `PROGRESS_CHANGED`, `STREAMING_RESULT`, `ERROR`, `COMPLETED`
     * `TaskManagerApi` uses `PromptApi` & `LLMManagerApi.stream_generate`, then `DataManagerApi.save_result` (status→PENDING\_JUDGEMENT)
     * Emits `COMPLETED` per task
4. **Judgment Phase**

   * Load results status=PENDING\_JUDGEMENT
   * For each, build judge prompt, call `LLMManagerApi.generate`, parse, `DataManagerApi.update_result` (status→JUDGEMENT\_COMPLETED)
   * Emit progress updates
5. **Reporting**

   * `BenchmarkApi.generate_report(run_id)` → aggregates, returns report
   * Emit `BenchmarkEvent.COMPLETED`

---

## Implementation Module Plan

**Location**: `src/core/implementation/`
This module contains concrete implementations of the abstract interfaces defined in `src/core/abstraction/`. Implementations must:

* Follow exact method signatures from the abstract `Protocol`s.
* Receive all external dependencies via constructor (DI); no internal creation of database connections, file paths, or thread pools.
* Use constants/enums for SQL statements, prompt templates, table names—no hardcoded literals.
* Isolate SQL queries in `src/core/constants/sql_queries.py` and prompt patterns in `src/core/constants/prompt_templates.py`.
* Wrap lower‑level errors into domain exceptions from `src/core/errors.py`.
* Depend only on the Python standard library (e.g., `sqlite3`, `yaml`) and minimal required external libraries (e.g., PyQt6 for TaskManager).

---

### 2. DataManager Implementation (SQLite)

**File**: `data_manager_impl.py`
**Class**: `SqliteDataManager` implements `DataManagerApi`

**Dependencies** (constructor):

* `connection: sqlite3.Connection`
* `queries: SqlQueries` (from `src/core/constants/sql_queries.py`)

**Responsibilities & Steps**:

1. **create\_run(model\_names: list\[str]) -> int**

   * Execute `queries.CREATE_RUN` with parameterized placeholder for models (e.g., comma‑joined).
   * Use `cursor.lastrowid` to retrieve `run_id`.
2. **save\_tasks(run\_id: int, tasks: list\[BenchmarkTask]) -> None**

   * For each task, execute `queries.INSERT_TASK` with fields and initial status `TaskStatus.NEW.value`.
   * Use a transaction (`connection.execute('BEGIN')` … `connection.commit()`).
3. **save\_result(result: Result) -> None**

   * Execute `queries.INSERT_RESULT` mapping all `Result` attributes.
4. **load\_results(run\_id: int, status: TaskStatus) -> list\[Result]**

   * Execute `queries.SELECT_RESULTS_BY_STATUS`, fetch rows, map to `Result` instances.
5. **update\_result(result: Result) -> None**

   * Execute `queries.UPDATE_RESULT_BY_ID`, passing `result.result_id`, `status`, `evaluation_score`, `evaluation_reason`, `error_message`.

**Error Handling**:

* Catch `sqlite3.Error` and wrap as `DataError` (from `src/core/errors.py`).

---

### 3. DataSetLoader Implementation (YAML)

**File**: `dataset_loader_impl.py`
**Class**: `YamlDataSetLoader` implements `DataSetLoaderApi`

**Dependencies**:

* `dataset_folder: pathlib.Path`
* `yaml_loader: Callable[[str], Any]` (e.g., `yaml.safe_load`)

**Responsibilities & Steps**:

1. **load\_tasks(folder\_path: str) -> list\[BenchmarkTask]**

   * Iterate over all `*.yml` files in `dataset_folder`.
   * Load each file, expect a list of dicts; for each dict:

     * Validate presence of `task_id`, `question`, `expected_answer`, `incorrect_direction`.
     * Instantiate `ExpectedAnswer` and `BenchmarkTask`.
   * Return combined list.

**Error Handling**:

* On missing keys or parse errors, raise `DataError`.

---

### 4. PromptApi Implementation (Simple Replacement)

**File**: `prompt_api_impl.py`
**Class**: `SimplePromptApi` implements `PromptApi`

**Dependencies**:

* `templates: PromptTemplates` (constants mapping template names to raw string with placeholders like `{{question}}`, `{{most_expected}}`)

**Responsibilities & Steps**:

1. **build\_generation\_prompt(task: BenchmarkTask) -> str**

   * **Return** `task.question` directly; no additional context is added.

2. **build\_judge\_prompt(task: BenchmarkTask, llm\_response: str) -> str**

   * Fetch `templates.JUDGE` (contains placeholders: `{{question}}`, `{{most_expected}}`, `{{good_answer}}`, `{{pass_option}}`, `{{incorrect}}`, `{{llm_response}}`).
   * Prepare parameters dict:

     ```python
     params = {
         'question': task.question,
         'most_expected': task.expected_answer.most_expected,
         'good_answer': task.expected_answer.good_answer,
         'pass_option': task.expected_answer.pass_option,
         'incorrect': task.incorrect_direction,
         'llm_response': llm_response
     }
     ```
   * Perform placeholder replacement:

     ```python
     result = template
     for key, val in params.items():
         placeholder = f"{{{{{key}}}}}"
         result = result.replace(placeholder, val)
     return result
     ```

**Error Handling**:

* If any placeholder remains unreplaced or a key is missing in the template, raise `PromptError` with details.

---

### 5. LLMManager Implementation (Ollama)

**File**: `llm_manager_impl.py`
**Class**: `OllamaLLMManager` implements `LLMManagerApi`

**Dependencies**:

* `client: OllamaClient`
* `config: BenchmarkConfig` (for timeouts)
* `logger: logging.Logger`

**Responsibilities & Steps**:

1. **list\_models() -> list\[str]**: delegate to `client.list_models()`.
2. **prepare\_model(name: str) -> None**:

   * Call `client.ping(name)`; if `False`, raise `LLMError`.
   * Optionally `client.load(name)` if required.
3. **stream\_generate(model\_name: str, prompt: str, on\_token: Callable\[\[str], None]) -> None**:

   * Call `client.stream_chat(model_name, prompt, timeout=config.timeout_sec)`
   * For each token chunk, call `on_token(token)`.
4. **generate(model\_name: str, prompt: str) -> str**:

   * Call `client.chat(model_name, prompt, timeout=config.timeout_sec)` and return full text.

**Error Handling**:

* Catch client exceptions, wrap as `LLMError`.

---

### 6. TaskManager Implementation (Qt-based)

**Location**: `src/task_manager/`
**File**: `qt_task_manager.py`
**Class**: `QtTaskManager` implements `TaskManagerApi`

**Purpose**: Run the **inference** step (LLM streaming or batch) in a background thread, and notify the main thread of tokens, completion, or errors. It must be agnostic of application logic like prompt building or database updates.

**Dependencies**:

* `thread_pool: PyQt6.QtCore.QThreadPool`
* `llm_manager: LLMManagerApi`
* `callback_router: CallbackRouter` (maps submission\_id & event → callbacks)

**Responsibilities & Steps**:

1. **submit\_task(run\_id: int, task: BenchmarkTask, model\_name: str) -> int**:

   * **Generate** a unique `submission_id` (atomic counter).
   * **Pre-build**: Obtain prompt by calling upstream service (outside TaskManager).
   * **Create** a `QRunnable` that in its `run()` method:

     * Call `llm_manager.stream_generate(model_name, prompt, on_token)`.

       * On each token: invoke `callback_router.emit(submission_id, BenchmarkEvent.STREAMING_RESULT, token)`.
     * On full stream completion: emit `callback_router.emit(submission_id, BenchmarkEvent.COMPLETED, None)`.
     * On any exception: emit `callback_router.emit(submission_id, BenchmarkEvent.ERROR, error)`.
   * **Submit** the runnable: `thread_pool.start(runnable)`.
   * **Return** `submission_id` immediately.

2. **subscribe(submission\_id: int, event: BenchmarkEvent, callback: Callable) -> int**:

   * **Forward** to `callback_router.register(submission_id, event, callback)`.
   * **Return** the registration token.

3. **unsubscribe(token: int) -> None**:

   * **Forward** to `callback_router.unregister(token)`.

**Contracts**:

* **No database** or prompt-building logic here. TaskManager only orchestrates the background LLM call.
* **Callbacks** must be delivered on the Qt main thread via `pyqtSignal` mechanisms.
* **Injected** dependencies only; do not create `thread_pool` or `llm_manager` internally.

---

### 7. BenchmarkApi Implementation

**File**: `benchmark_service.py`
**Class**: `BenchmarkService` implements `BenchmarkApi`

**Dependencies**:

* `data_manager: DataManagerApi`
* `dataset_loader: DataSetLoaderApi`
* `prompt_api: PromptApi`
* `llm_manager: LLMManagerApi`
* `task_manager: TaskManagerApi`
* `event_router: CallbackRouter`
* `config: BenchmarkConfig`
* `report_generator: ReportGenerator`

**Responsibilities & Steps**:

1. **list\_models()**: return `llm_manager.list_models()`.
2. **select\_models(model\_names: list\[str]) / select\_judge\_model(name: str)**: assign to internal state.
3. **start\_benchmark() -> int**:

   * `run_id = data_manager.create_run(selected_models)`.
   * `tasks = dataset_loader.load_tasks(config.dataset_path)`.
   * `data_manager.save_tasks(run_id, tasks)`.
   * Emit `STARTED`.
   * For each `model` in selected\_models and for each `task` in tasks:

     * `submission_id = task_manager.submit_task(run_id, task, model)`.
     * Subscribe to that submission’s events to aggregate progress and re-emit via `event_router.emit(BenchmarkEvent.PROGRESS_CHANGED, progress)`.
   * After all generation submissions complete, load `PENDING_JUDGEMENT` results and perform synchronous judgment:

     * Build judge prompt, call `llm_manager.generate()`, update each `Result` via `data_manager.update_result` and emit progress.
4. **get\_progress() -> dict\[str, float]**: calculate percentages by querying `data_manager.load_results` for each status.
5. **generate\_report(run\_id: int) -> str**: call `report_generator.generate(run_id)`.
6. **subscribe/unsubscribe**: proxy to `event_router`.

**Contracts**:

* Do not instantiate any dependency; use only what was injected via constructor.
* Delegate SQL and prompt logic to the respective implementations.

---

### 8. Constants & Errors

* **SQL Queries**: `src/core/constants/sql_queries.py` — simple SQLite statements with `?` placeholders.
* **Prompt Templates**: `src/core/constants/prompt_templates.py` — Python-formatted templates (e.g., `"Your task: {question}
  ..."`).
* **Errors**: `src/core/errors.py` defining `DataError`, `PromptError`, `LLMError`, `TaskError`, `ServiceError`.

---

### 9. Agent Guidelines

* **Match signatures**: verify each implementation method matches its abstract `Protocol` exactly.
* **Constructor DI**: all external resources passed in; no new imports for engines or thread pools inside.
* **Constants/enums**: use named constants for SQL, templates, event names.
* **Minimal dependencies**: rely on Python stdlib (`sqlite3`, `yaml`), PyQt6 for threading; avoid heavy frameworks.
* **Error wrapping**: catch low‑level exceptions and raise domain errors.
* **Testing**: write unit tests mocking dependencies; add integration test using an in‑memory SQLite DB and a small YAML dataset.

