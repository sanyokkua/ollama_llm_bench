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

### 1. Application Flow (Abstracted)

1. **Model Selection**

   * UI uses `LLMManagerApi.list_models()` to display available LLMs.
   * User selects one or more generation models and a single judge model via `BenchmarkApi.select_models(...)` and `BenchmarkApi.select_judge_model(...)`.

2. **Benchmark Initialization**

   * UI calls `BenchmarkApi.start_benchmark()`.
   * `BenchmarkApi`:

     * Persists run metadata: calls `DataManagerApi.create_run(selected_models)` → `run_id`.
     * Loads raw tasks from disk: calls `DataSetLoaderApi.load_tasks(dataset_path)` → list of `BenchmarkTask`.
     * Persists tasks: calls `DataManagerApi.save_tasks(run_id, tasks)` (status = `NEW`).
     * Emits `BenchmarkEvent.STARTED`.

3. **Task Execution (via TaskManagerApi)**

   * For each combination of `model_name` × `BenchmarkTask`:

     * `BenchmarkApi` submits a job: `TaskManagerApi.submit_task(run_id, task, model_name)` → returns `submission_id`.
     * `BenchmarkApi` registers callbacks:

       * `TaskManagerApi.subscribe(submission_id, BenchmarkEvent.PROGRESS_CHANGED, on_progress)`
       * `TaskManagerApi.subscribe(submission_id, BenchmarkEvent.STREAMING_RESULT, on_stream)`
       * `TaskManagerApi.subscribe(submission_id, BenchmarkEvent.ERROR, on_error)`
       * `TaskManagerApi.subscribe(submission_id, BenchmarkEvent.COMPLETED, on_complete)`
     * Internally, `TaskManagerApi` uses:

       * `PromptApi.build_generation_prompt()`
       * `LLMManagerApi.prepare_model()`
       * `LLMManagerApi.stream_generate()`
       * Collects full `llm_response`, timing, tokens
       * Creates `Result(status=PENDING_JUDGEMENT)` and calls `DataManagerApi.save_result()`
       * Emits `COMPLETED` event for this submission
     * UI (via `BenchmarkApi`) aggregates task-level events into run-level progress events.

4. **Judgment Phase**

   * After all generation submissions complete, `BenchmarkApi`:

     * Loads all `Result` with status = `PENDING_JUDGEMENT`: `DataManagerApi.load_results(run_id, TaskStatus.PENDING_JUDGEMENT)`.
     * For each `Result`:

       * Build judge prompt: `PromptApi.build_judge_prompt(task, result.llm_response)`
       * Synchronous judge call: `LLMManagerApi.generate(judge_model, prompt)`
       * Parse JSON → update `result.evaluation_score`, `result.evaluation_reason`
       * Update status = `JUDGEMENT_COMPLETED`; call `DataManagerApi.update_result(result)`
       * Emit `BenchmarkEvent.PROGRESS_CHANGED` for UI update

5. **Reporting**

   * Once all judged, UI calls `BenchmarkApi.generate_report(run_id)`.
   * `BenchmarkApi` assembles run summary (aggregates, charts, export formats) and returns report path or content.
   * Emits `BenchmarkEvent.COMPLETED`.

---

### 2. Enums (`enums.py`)

```python
from enum import Enum

class TaskStatus(Enum):
    NEW = "NEW"
    PENDING_JUDGEMENT = "PENDING_JUDGEMENT"
    JUDGEMENT_COMPLETED = "JUDGEMENT_COMPLETED"
    FAILED = "FAILED"

class BenchmarkEvent(Enum):
    STARTED = "started"
    PROGRESS_CHANGED = "progress_changed"
    STREAMING_RESULT = "streaming_result"
    ERROR = "error"
    COMPLETED = "completed"
```

---

### 3. Data Types (`types.py`)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ExpectedAnswer:
    most_expected: str
    good_answer: str
    pass_option: str

@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    question: str
    expected_answer: ExpectedAnswer
    incorrect_direction: str

@dataclass
class Result:
    result_id: int | None = None
    run_id: int | None = None
    model_name: str = ""
    task_id: str = ""
    llm_response: str = ""
    time_taken_ms: int = 0
    tokens_generated: int = 0
    status: TaskStatus = TaskStatus.NEW
    evaluation_score: float = -1.0
    evaluation_reason: str = ""
    error_message: str | None = None

@dataclass(frozen=True)
class BenchmarkConfig:
    run_id: int
    model_names: list[str]
    judge_model_name: str
    concurrency: int
    timeout_sec: int
    dataset_path: str

@dataclass(frozen=True)
class BenchmarkProgress:
    total_tasks: int
    completed_tasks: int
    percent_complete: float
```

---

### 4. Interfaces

#### 4.1 `BenchmarkApi` (`benchmark_api.py`)

```python
from typing import Protocol, Callable
from .types import BenchmarkConfig, BenchmarkProgress
from .enums import BenchmarkEvent

class BenchmarkApi(Protocol):
    def list_models(self) -> list[str]: ...
    def select_models(self, model_names: list[str]) -> None: ...
    def select_judge_model(self, judge_model_name: str) -> None: ...
    def start_benchmark(self) -> int: ...
    def get_progress(self) -> dict[str, float]: ...
    def generate_report(self, run_id: int) -> str: ...
    def subscribe(self, event: BenchmarkEvent, callback: Callable[[any], None]) -> int: ...
    def unsubscribe(self, token: int) -> None: ...
```

#### 4.2 `DataManagerApi` (`data_manager_api.py`)

```python
from typing import Protocol
from .types import BenchmarkTask, Result
from .enums import TaskStatus

class DataManagerApi(Protocol):
    def create_run(self, model_names: list[str]) -> int: ...
    def save_tasks(self, run_id: int, tasks: list[BenchmarkTask]) -> None: ...
    def save_result(self, result: Result) -> None: ...
    def load_results(self, run_id: int, status: TaskStatus) -> list[Result]: ...
    def update_result(self, result: Result) -> None: ...
```

#### 4.3 `DataSetLoaderApi` (`dataset_loader_api.py`)

```python
from typing import Protocol
from .types import BenchmarkTask

class DataSetLoaderApi(Protocol):
    def load_tasks(self, folder_path: str) -> list[BenchmarkTask]: ...
```

#### 4.4 `LLMManagerApi` (`llm_manager_api.py`)

```python
from typing import Protocol, Callable

class LLMManagerApi(Protocol):
    def list_models(self) -> list[str]: ...
    def prepare_model(self, name: str) -> None: ...
    def stream_generate(self,
                        model_name: str,
                        prompt: str,
                        on_token: Callable[[str], None]
                       ) -> None: ...
    def generate(self, model_name: str, prompt: str) -> str: ...
```

#### 4.5 `PromptApi` (`prompt_api.py`)

```python
from typing import Protocol
from .types import BenchmarkTask

class PromptApi(Protocol):
    def build_generation_prompt(self, task: BenchmarkTask) -> str: ...
    def build_judge_prompt(self, task: BenchmarkTask, llm_response: str) -> str: ...
```

#### 4.6 `TaskManagerApi` (`task_manager_api.py`)

```python
from typing import Protocol, Callable
from .types import BenchmarkTask, Result
from .enums import BenchmarkEvent

class TaskManagerApi(Protocol):
    def submit_task(
        self,
        run_id: int,
        task: BenchmarkTask,
        model_name: str
    ) -> int:
        """Submit a single task for background execution; returns submission_id."""

    def subscribe(
        self,
        submission_id: int,
        event: BenchmarkEvent,
        callback: Callable[[any], None]
    ) -> int:
        """Register a callback for task-level events; returns token."""

    def unsubscribe(self, token: int) -> None:
        """Remove a previously registered callback."""
```

---

### 5. Implementation Checkpoints & User Stories

1. **File Setup**

   * [ ] Create new `task_manager_api.py` alongside existing interfaces.

2. **Interface Definitions**

   * [ ] Ensure `TaskManagerApi` is importable and its methods match signatures above.

3. **Flow Integration**

   * [ ] Update `BenchmarkApi` implementation (when coding) to depend on `TaskManagerApi`.

4. **Testing**

   * [ ] Write a stub `TaskManagerApi` that simulates event emissions to verify UI subscription logic.

5. **Documentation**

   * [ ] Expand README to describe `TaskManagerApi` role: batching, concurrency, callbacks.
