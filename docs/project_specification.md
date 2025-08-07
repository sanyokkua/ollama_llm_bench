### **Project Specification: Ollama LLM Benchmarker**

## 1\. Vision & Objectives

The **Ollama LLM Benchmarker** is a cross-platform desktop application tailored for developers, researchers, and AI enthusiasts. It enables systematic, repeatable evaluation of local LLMs hosted via Ollama. Unlike simple latency tests, it integrates an automated qualitative judging phase in which a user-selected model evaluates peer responses. Users receive comprehensive, comparative reports—empowering data‑driven model selection for varied use cases.

**Key Objectives:**

1.  **Automate** the full benchmarking cycle (execution + judging).
2.  **Quantify** both performance (speed, throughput) and quality (semantic accuracy).
3.  **Persist** results for historical analysis and reproducibility.
4.  **Visualize** and **export** findings in clear, actionable formats.

-----

## 2\. Feature Overview

### 2.1 Dynamic Model Management

* **Auto-Discovery:** Polls the local Ollama instance for available models on launch and on user request.
* **Refresh Control:** Manual refresh button to update the model list at any time.

### 2.2 Benchmark Lifecycle Controls

* **Start New Benchmark:** Launch a fresh run with selected models, judge, and dataset.
* **Pause / Resume:** Safely pause execution and resume without losing progress.
* **Stop:** Halt a run entirely, marking incomplete tasks accordingly.
* **Continue Unfinished:** Select and resume any run in a `PAUSED` or `STOPPED` state from the application's history.

### 2.3 Execution Metrics

For each model-task pair, the application captures:

1.  **Response Time** (in milliseconds)
2.  **Tokens Generated**
3.  **Throughput** (calculated as Tokens per Second)

### 2.4 Automated Qualitative Judging

* **Judge Model Selection:** Any discovered model can be nominated as the judge for a benchmark run.
* **Scoring & Rationale:** The judge produces a 0–100% quality score and, crucially, a **textual rationale** explaining the score, which is displayed directly in the results.

### 2.5 Data Persistence & History

* **Local Database:** A local SQLite database stores all run data, including individual task results and judge evaluations.
* **Run History:** Provides a filterable list of all past runs with their metadata (timestamp, judge model, status).

### 2.6 Reporting & Export

* **Interactive Results:** The UI features sortable tables that summarize per-model averages and show detailed task-by-task breakdowns.
* **CSV Export:** Allows the user to download the complete, detailed data for any run for external analysis.

-----

## 3\. User Interface & Experience

The application uses a clean, two-panel layout to separate user controls from information display, ensuring an intuitive workflow.

### 3.1 UI Mockup: Benchmark in Progress

This view shows the application during an active run. The left panel's controls are locked to prevent disruption, while the right `Log` tab provides a real-time stream of events.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ OLLAMA LLM BENCHMARKER v1.0                                                                         │
├──────────────────────────────────────────┬──────────────────────────────────────────────────────────┤
│ LEFT CONTROL PANEL                       │ RIGHT PANEL                                              │
│ ▼ Continue Unfinished Run...              │ [   LOG   ] [  RESULTS  ]                                │
│   [ Run #4 (Paused) ]                    │ -------------------------------------------------------- │
│                                          │ [2025-08-07 18:16:10] Resuming benchmark run #4.         │
│ ▼ Judge Model                            │ [2025-08-07 18:16:10] Judge model: 'mistral:instruct'.   │
│   [ mistral:instruct      (locked) ]     │ [2025-08-07 18:16:11] 45 of 80 tasks remaining.          │
│                                          │ ...                                                      │
│ MODELS TO BENCHMARK (locked)             │ [2025-08-07 18:17:22] --- Starting model: gemma:7b ---   │
│   [X] llama3:8b                          │ [2025-08-07 18:17:25] Running task 'logic_puzzle_3'...   │
│   [X] gemma:7b                           │ [2025-08-07 18:17:26] Model Stream: The answer is...     │
│                                          │ [2025-08-07 18:17:31] Task 'logic_puzzle_3' completed.   │
│ [ REFRESH MODELS ] (disabled)            │   Time: 6,102 ms, Tokens: 155, TPS: 25.4                 │
│                                          │                                                          │
│ [START NEW BENCHMARK] (disabled)         │                                                          │
│ [■ STOP] [❚❚ PAUSE]                      │                                                          │
│                                          │                                                          │
│ OVERALL PROGRESS: [███████████░░░░░░] 55%│                                                          │
│ STATUS: Running task 36/80 on 'gemma:7b' │                                                          │
└──────────────────────────────────────────┴──────────────────────────────────────────────────────────┘
```

### 3.2 UI Mockup: Reviewing Results

The `Results` tab is the primary analysis hub. It features a dropdown to select any run from history and presents two tables: a high-level summary and a detailed breakdown. **The judge's reasoning is displayed directly in the last column of the detailed table.**

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ OLLAMA LLM BENCHMARKER v1.0                                                                                           │
├──────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────┤
│ LEFT CONTROL PANEL                       │ RIGHT PANEL                                                                │
│                                          │ [  LOG  ] [  RESULTS  ]                                                    │
│ ▼ Judge Model                            │ -------------------------------------------------------------------------- │
│   [ mistral:instruct      ]              │ Select Benchmark Run to View:                                              │
│                                          │ ▼ [ Run #5: 2025-08-07 15:35:10 (Completed) ]                              │
│ MODELS TO BENCHMARK                      │                                                                            │
│   [ ] llama3:8b                          │                                         [EXPORT RUN TO CSV] [DELETE RUN]   │
│   [ ] gemma:7b                           │                                                                            │
│                                          │ == Summary: Average Performance per Model ==                               │
│ [ REFRESH MODELS ]                       │ MODEL      | AVG. TIME (s) | AVG. TOKENS/s | AVG. SCORE (%)                 │
│                                          │ -------------------------------------------------------------------------- │
│ [START NEW BENCHMARK]                    │ llama3:8b  |          8.9s |          28.1 |        88%                     │
│                                          │ gemma:7b   |         12.4s |          21.5 |        92%                     │
│                                          │                                                                            │
│ PROGRESS: [-------------------------]    │ == Detailed Results for Run #5 ==                                          │
│ STATUS: Idle. Ready for new benchmark.   │ ▼ MODEL    | ▼ TASK ID              | TIME(ms)| SCORE | SCORE REASON       │
│                                          │ -------------------------------------------------------------------------- │
│                                          │ gemma:7b   | python_fibonacci       |    7015 |   95% | Correctly handles base cases. │
│                                          │ gemma:7b   | french_translation     |   11050 |   90% | Accurate but overly formal.   │
│                                          │ ... (38 more rows for gemma:7b) ...                                        │
│                                          │ llama3:8b  | python_fibonacci       |    6102 |   90% | Function is correct.          │
│                                          │ llama3:8b  | french_translation     |    9890 |   85% | Minor grammatical error.      │
│                                          │ ... (38 more rows for llama3:8b) ...                                       │
│                                          │ (Table is sortable. Click headers to sort.)                                │
└──────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────┘
```

-----

## 4\. Backend Architecture & Workflow

### 4.1 Layered Structure & Principles

The application is built on modern software design principles to ensure it is robust, maintainable, and responsive.

1.  **Layered Design:** Code is strictly separated into a **UI Layer** (`ui/`), a **Core Layer** (`core/` for interfaces and data models), and a **Services Layer** (`services/` for concrete implementations).
2.  **Dependency Injection (DI):** A `ServiceProvider` container instantiates all services at startup and injects them where needed. This decouples components and simplifies testing.
3.  **Asynchronous Execution:** All heavy lifting (benchmarking, judging) is performed on a background `QThread`, communicating with the UI via Qt's signals and slots to prevent freezing.

### 4.2 Benchmark Flow

1.  **Initialization:** `Start New Benchmark` creates a `benchmark_runs` record (`status='RUNNING'`). It then loads all tasks from `dataset/*.yml` and populates the `results` table with a row for each model-task combination, setting their status to `AWAITING_EXECUTION`.
2.  **Execution Phase (Optimized by Model):** The `BenchmarkController` fetches all `AWAITING_EXECUTION` tasks and groups them by model to minimize expensive model loading operations. For each group, it loads the model once, executes all its tasks, and updates the database after each task.
3.  **Judging Phase:** After all tasks are executed, the run `status` switches to `JUDGING`. The `BenchmarkController` then iterates through each task that is `AWAITING_JUDGEMENT`, using the judge model to get a score and reason.
4.  **Resumption & State:** On `PAUSE` or `STOP`, the run status is updated. Resuming a run simply involves fetching tasks that are still `AWAITING_EXECUTION` and continuing the execution loop.
5.  **Error Handling:** If a model is missing on resume or a task fails, its status is marked `FAILED` with an error message, and the benchmark continues with the remaining tasks.

-----

## 5\. Data Models & Schema

A local SQLite database (`benchmark_data.db`) persists all application data. The schema is defined as follows:

```sql
CREATE TABLE IF NOT EXISTS benchmark_runs (
  run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp    TEXT NOT NULL,
  judge_model  TEXT NOT NULL,
  status       TEXT NOT NULL    -- e.g., 'RUNNING', 'PAUSED', 'COMPLETED', 'FAILED'
);

CREATE TABLE IF NOT EXISTS results (
  result_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id            INTEGER NOT NULL REFERENCES benchmark_runs(run_id),
  task_id           TEXT    NOT NULL,
  model_name        TEXT    NOT NULL,
  status            TEXT    NOT NULL,  -- e.g., 'AWAITING_EXECUTION', 'COMPLETED'
  llm_response      TEXT,
  time_taken_ms     INTEGER,
  tokens_generated  INTEGER,
  evaluation_score  REAL,         -- Score from 0.0 to 1.0
  evaluation_reason TEXT,         -- The judge's textual rationale for the score
  error_message     TEXT
);
```

The application code uses `dataclasses` and `StrEnum`s defined in `core/models.py` to represent this data.

-----

## 6\. Technology Stack

* **Core Language:** Python 3.13
* **UI Framework:** PyQt6
* **LLM Client:** `ollama-python`
* **Database:** SQLite (via the standard `sqlite3` library)
* **Task Definitions:** YAML (loaded with PyYAML)
* **Dependency Management:** Poetry
* **Threading:** Qt `QThread` with a signals/slots communication model.

# 7. Implementation Details

## 7.1 Project Structure

The project follows a clean, standard Python layout with strict adherence to the layered architecture principles outlined in section 4.1. The `src/ollama_llm_bench` directory is organized to maintain separation of concerns and facilitate testability.

```
.
└── src
    └── ollama_llm_bench
        ├── __init__.py
        ├── main.py                 # Application entry point, DI container setup
        │
        ├── core                    # Core application logic and definitions
        │   ├── __init__.py
        │   ├── models.py           # Dataclasses and Enums (e.g., BenchmarkRun, TaskStatus)
        │   ├── interfaces.py       # Abstract interfaces (Protocols) for all services
        │   └── benchmark_controller.py # The main QObject orchestrator for the background thread
        │
        ├── services                # Concrete implementations of core interfaces
        │   ├── __init__.py
        │   ├── data_service.py     # SQLiteDataService implementation
        │   ├── ollama_service.py   # OllamaManager implementation
        │   └── task_loader.py      # YAMLTaskLoader implementation
        │
        ├── ui                      # PyQt6 UI components
        │   ├── __init__.py
        │   ├── main_window.py      # The main application window (QMainWindow)
        │   └── widgets/            # Folder for custom widgets (e.g., ControlPanel, ResultsTab)
        │
        └── utils                   # Utility functions, helpers, constants
            ├── __init__.py
            └── service_provider.py # The simple DI/IoC container class
```

**Key Structural Principles:**
- **Strict Layer Boundaries:** Code in the `core` directory must not import from `services` or `ui`, ensuring business logic remains independent of implementation details.
- **Interface-Driven Development:** All concrete services implement interfaces defined in `core/interfaces.py`, enabling easy mocking for testing.
- **Thread Safety:** The `benchmark_controller.py` handles all background operations using Qt's threading model, with proper signal/slot communication to the UI layer.

## 7.2 Development Toolchain

The project leverages modern Python development tools to ensure quality, maintainability, and consistent environments.

### Primary Stack
- **Python Version:** 3.13 (Required for specific typing features and performance improvements)
- **Package Management:** Poetry (v2.0+)
    - Handles dependencies, virtual environments, and packaging
    - Ensures reproducible builds across platforms
- **UI Framework:** PyQt6 (v6.9.1+)
    - Provides cross-platform desktop application capabilities
    - Offers robust signal/slot system for thread-safe UI updates

### Development Dependencies
- **Static Analysis:** Pyright (v1.1.403+)
    - Type checking to catch errors early
    - Enforces type hints throughout the codebase
- **Testing:** pytest (v8.4.1+)
    - Comprehensive unit and integration testing
    - Mocking capabilities for service interfaces

### Project Configuration
The `pyproject.toml` file defines all dependencies with strict version constraints to ensure compatibility:

```toml
[project]
name = "ollama-llm-bench"
version = "0.1.0"
description = "Ollama benchmark"
requires-python = ">=3.13"
dependencies = [
    "pyqt6 (>=6.9.1,<7.0.0)",
    "ollama (>=0.5.1,<0.6.0)",
    "pyyaml (>=6.0.2,<7.0.0)",
    "platformdirs (>=4.3.8,<5.0.0)"
]

[tool.poetry.group.dev.dependencies]
pytest = "^8.4.1"
pyright = "^1.1.403"
```

## 7.3 Dataset Format Specification

Benchmark tasks are defined in YAML format within the `dataset/` directory. Each task file contains a list of task definitions with standardized structure to support consistent evaluation.

### Task Schema
```yaml
- task_id: "unique_task_identifier"
  category: "Broad category (e.g., Coding, Translation)"
  sub_category: "Specific area (e.g., Java, French)"
  question: "The prompt/question to present to the LLM"
  expected_answer:
    most_expected: "Perfect answer that meets all requirements"
    good_answer: "Acceptable answer with minor imperfections"
    pass_option: "Minimal answer that still qualifies as correct"
  incorrect_direction: "Description of incorrect answers that should be penalized"
```

### Example Task
```yaml
- task_id: "java_hello_world"
  category: "Coding"
  sub_category: "Java"
  question: "Write a standard 'Hello, World!' program in Java. The class should be named 'HelloWorld'."
  expected_answer:
    most_expected: "public class HelloWorld { public static void main(String[] args) { System.out.println(\"Hello, World!\"); } }"
    good_answer: "Contains 'public class', 'public static void main', and 'System.out.println'. Code is compilable."
    pass_option: "A code snippet that prints 'Hello, World!' to the console, even if not in a full class structure."
  incorrect_direction: "The code uses Python syntax, is not valid Java, or prints the wrong text."
```

### Dataset Organization
- Tasks are grouped by category in separate YAML files (e.g., `coding.yml`, `translation.yml`)
- Each task must have a unique `task_id` across the entire dataset
- The `expected_answer` field provides the judge model with clear criteria for scoring
- New tasks can be added by creating additional YAML files in the `dataset/` directory

## 7.4 Service Implementation Details

### Dependency Injection Container
The `utils/service_provider.py` implements a simple but effective DI container that:
- Registers all service implementations at application startup
- Resolves dependencies based on interface types
- Ensures single instance services where appropriate (e.g., database connection)
- Provides clean separation between object creation and usage

### Critical Service Implementations
- **SQLiteDataService:** Implements database operations with transaction safety
    - Uses parameterized queries to prevent SQL injection
    - Handles database schema migrations automatically
    - Implements connection pooling for performance

- **OllamaManager:** Provides safe interaction with Ollama API
    - Includes robust error handling for network issues
    - Implements model availability checks before execution
    - Manages resource cleanup after model usage

- **YAMLTaskLoader:** Processes dataset files with validation
    - Validates task structure against schema
    - Caches loaded tasks for performance
    - Provides category-based filtering capabilities

## 7.5 Quality Assurance Practices

To maintain high code quality and reliability, the project implements:

- **Comprehensive Type Hints:** Full type annotation coverage enforced by Pyright
- **Unit Testing:** >80% test coverage for core logic and service implementations
- **Integration Testing:** End-to-end tests for critical user workflows
- **Thread Safety Checks:** Rigorous testing of background operations
- **Database Transaction Testing:** Verification of atomic operations and error recovery

# Rules and Restrictions

---

## 1. Project Configuration

1.  This is a pure Python project.
2.  Target Python version must be 3.13 or newer.
3.  Manage all dependencies with Poetry (`pyproject.toml`).

---

## 2. Architecture & Dependency Management

1.  Define every service or component as an abstract base class (ABC) describing its public API.
    - Concrete implementations must subclass the ABC.
2.  Enforce absolute imports from the root package.
    - Example:
      ```python
      from myapp.module.submodule.my_class import MyClass
      ```  
    - Do not use relative imports like `from .my_module import Item`.
3.  Prevent cyclic dependencies.
    - If a cycle arises, insert an abstraction (ABC) to break it.
4.  All external dependencies must be injected via constructor.
    - Classes should never instantiate collaborators internally.
    - Exception: factories or builder classes that explicitly create and return new instances.

---

## 3. Code Style & Quality

1.  Use strict typing and type hints for every function, method, and variable.
2.  Only interact with other objects through their public APIs.
    - Never call private methods or access private fields from outsiders.
3.  Eliminate magic numbers—replace with named constants and add a descriptive docstring or comment.
4.  Avoid repeating string literals—define them once as constants with clear names.
5.  Use `Enum` for grouped constants and `StrEnum` for string-based enums.
6.  Treat all class attributes and methods as private by default, unless they belong to your public API.
7.  Expose public-facing attributes via `@property` decorators.
8.  Annotate overridden methods with `@override`.
9.  Define abstract base classes using `ABC` (from the `abc` module).
10. Remove any unused imports, variables, or methods before committing.
11. Use `@dataclass` for data-holder classes, and set `frozen=True` for immutable (read-only) instances.

---

## 4. PyQt6-Specific Guidelines

1.  Use PyQt6 exclusively.
2.  When combining ABCs with PyQt QObject subclasses, define a proper metaclass to resolve MRO conflicts:
    ```python
    from abc import ABCMeta
    from PyQt6.QtCore import QObject

    class _MetaQObjectABC(type(QObject), ABCMeta):
        pass

    class MyInterface(QObject, metaclass=_MetaQObjectABC):
        ...
    ```  

---

## 5. Multithreading & UI Safety

1.  Handle concurrency using Qt’s thread-pool mechanisms (e.g., `QThreadPool`).
2.  Synchronize shared data appropriately (locks, signals).
3.  UI updates must occur **only** on the main (GUI) thread.
4.  Background callbacks must not manipulate widgets directly—emit signals and connect them to slots on the main thread.

---