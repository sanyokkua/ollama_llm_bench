# Glossary

Domain vocabulary used throughout the Ollama LLM Bench codebase and documentation.
When two terms sound similar, this glossary clarifies the distinction and points to the code that defines them.

## Core Concepts

### Benchmark Task

A single, self-contained question with tiered reference answers used to evaluate a model.
Defined as the frozen dataclass `BenchmarkTask` in `src/ollama_llm_bench/core/models.py`.
Loaded from a YAML file under `src/ollama_llm_bench/dataset/` by `YamlBenchmarkTaskApi`.
Contains a question, three tiers of expected answers (`most_expected`, `good_answer`, `pass_option`), and a negative anchor (`incorrect_direction`).
See [dataset-format.md](dataset-format.md) for the schema.

### Benchmark Run

One execution of the benchmark pipeline against a chosen set of models.
Represented as `BenchmarkRun` in `core/models.py` and persisted as a row in the `benchmark_runs` SQLite table.
A run has exactly one judge model and a status of `NOT_COMPLETED`, `COMPLETED`, or `FAILED`.
A run is created when the user clicks **Start** in the New Run widget; it lives in the database until explicitly deleted.

### Benchmark Result

The outcome of running **one task** against **one model** within a single run.
Represented as `BenchmarkResult` in `core/models.py` and stored as a row in the `results` SQLite table.
Each result owns inference timing, token counts, the raw LLM response, and — after judging — an `evaluation_score` and `evaluation_reason`.
A run with `m` test models and `n` tasks produces `m × n` results.

### Three Conceptually Similar Terms

| Term | Entity | Identifier | Count per run |
|---|---|---|---|
| **Task** | `BenchmarkTask` (the question definition) | `task_id` string | Fixed by the dataset (~50 currently) |
| **Run** | `BenchmarkRun` (one end-to-end execution) | `run_id` int | One per invocation |
| **Result** | `BenchmarkResult` (one task × one model within a run) | `result_id` int | `models × tasks` per run |

## Pipeline Vocabulary

### Stage

A discrete phase of the benchmark pipeline.
Five string constants in `src/ollama_llm_bench/core/stages_constants.py`:

- `STAGE_INITIALIZING` — task records are being created in SQLite.
- `STAGE_BENCHMARKING` — inference loop: each task is sent to each test model.
- `STAGE_JUDGING` — the judge model evaluates each completed inference.
- `STAGE_FINISHED` — run completed successfully.
- `STAGE_FAILED` — run was aborted due to an unhandled exception.

Stages are reported to the UI via `ReporterStatusMsg.current_stage`.

### Warm-up

A preparatory call issued to Ollama before real inference starts, forcing the model to load into memory.
Implemented in `OllamaApi.warm_up` (`services/ollama_llm_api.py`): sends the prompt `"Say Hello"` and retries up to **5 times** with **30 s** between attempts.
Warm-up runs once per model at the start of the benchmarking stage, and once for the judge model at the start of the judging stage.
Without warm-up, the first task's `time_taken_ms` would include the model load time and skew averages.

### Judge Model

An LLM chosen by the user to evaluate the outputs of the test models.
The judge receives the `SYSTEM_PROMPT` and `USER_PROMPT` from `core/prompt_constants.py` and returns a JSON object `{"reason": str, "grade": float}`.
The judge model is stored per-run in `benchmark_runs.judge_model`.
It is **also** included in the `benchmark_runs` row for that run but is typically not one of the test models being scored.

### Test Model

Any model selected in the New Run widget's multi-select list to be benchmarked.
For each test model, every task is executed in the benchmarking stage.
Test models are not stored explicitly on the run; they are implied by the distinct `model_name` values in the `results` rows belonging to that run.

### Three-Tier Answer / Scoring

Every task defines three reference answers that map to scoring tiers:

| Field | Tier | Target score range |
|---|---|---|
| `most_expected` | Tier 1 — ideal | 0.85 – 1.00 |
| `good_answer` | Tier 2 — acceptable | 0.65 – 0.84 |
| `pass_option` | Tier 3 — minimum to pass | 0.30 – 0.64 |
| `incorrect_direction` | Negative anchor | ≤ 0.29 |

The ranges are specified in the judge prompt (`core/prompt_constants.py`) and are interpreted by the judge model, not enforced by code.
See [benchmark-pipeline.md](benchmark-pipeline.md#scoring-system) for the full rubric.

### Resumability

The ability to stop a benchmark mid-run and resume it later without losing progress.
Implemented through the three-valued `BenchmarkResultStatus` enum:

- `NOT_COMPLETED` — inference has not yet run; work to do in the benchmarking stage.
- `WAITING_FOR_JUDGE` — inference completed; work to do in the judging stage.
- `COMPLETED` — fully evaluated; no more work.

On resume, `BenchmarkExecutionTask` queries `results` for rows in each intermediate state and picks up where the previous run left off.
A run with status `NOT_COMPLETED` remains resumable via the **Previous Runs** tab.

## Infrastructure Vocabulary

### EventBus

The application-wide publish/subscribe channel that decouples background work from the UI thread.
Interface: `EventBus` ABC in `core/interfaces.py`.
Implementation: `QtEventBus` in `qt_classes/qt_event_bus.py`, which uses `pyqtSignal` under the hood.
See [architecture.md](architecture.md#eventbus) for the signal catalogue.

### ContextProvider

A thread-safe singleton that holds the `ApplicationContext` for the lifetime of the process.
Defined in `src/ollama_llm_bench/app_context.py`.
Uses `QMutex` for initialization safety; any component can retrieve the context via `ContextProvider.get_context()`.

### ApplicationContext

The dependency injection container.
An immutable `__slots__`-bound object holding references to every service and controller.
Constructed once in `_create_app_context()` during application startup.

### QRunnable / QThreadPool

Qt's worker-abstraction primitives used to run the benchmark pipeline off the UI thread.
The project creates **one** `QThreadPool` with `maxThreadCount = 1`, so benchmarks execute **serially** — there is never more than one active `BenchmarkExecutionTask`.

### MetaQObjectABC

A metaclass combining `type(QObject)` and `ABCMeta` so a class can inherit from both `QObject` and an ABC.
Defined in `qt_classes/meta_class.py`.
Required for `QtEventBus` and `QtBenchmarkFlowApi` because Python does not allow a class to have two incompatible metaclasses otherwise.

### Inference

A single call to an LLM (Ollama `generate`) with a given prompt.
The result is wrapped in `InferenceResponse` (`core/models.py`) with timing, token count, and error fields.
A single task = one inference during the benchmarking stage + one inference during the judging stage.

## Data-Shape Vocabulary

### AvgSummaryTableItem

One row in the **Summary** table shown in the Results tab.
Holds averages across all tasks for a single model in a single run: `avg_time_ms`, `avg_tokens_per_second`, `avg_score`.
Produced by `AppResultApi.retrieve_avg_benchmark_results_for_run`.

### SummaryTableItem

One row in the **Detailed** table shown in the Results tab.
Holds per-task metrics for a single model: `time_ms`, `tokens`, `tokens_per_second`, `score`, `score_reason`.
Produced by `AppResultApi.retrieve_detailed_benchmark_results_for_run`.

### ReporterStatusMsg

The progress payload broadcast during execution.
Contains the current run ID, stage, model, task, counters (`tasks_completed` / `tasks_total`), and start/end timestamps.
Emitted by `BenchmarkExecutionTask._update_progress()` on every state change.

### InferenceResponse

The typed return of a single Ollama `generate` call, wrapping the raw text, timing, token count, and any error state.
See `core/models.py`.

## Acronyms

| Abbreviation | Expansion |
|---|---|
| ABC | Abstract Base Class (`abc.ABC`) |
| DI | Dependency Injection |
| DTO | Data Transfer Object (all of this project's DTOs are `@dataclass(frozen=True)`) |
| LLM | Large Language Model |
| MRO | Method Resolution Order (relevant to `MetaQObjectABC`) |
| MVC | Model-View-Controller (loose analogy — this project uses widget + controller + services) |
| YAML | YAML Ain't Markup Language — the dataset serialization format |
