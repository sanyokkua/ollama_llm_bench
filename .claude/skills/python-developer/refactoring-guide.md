# Python Developer — Refactoring Guide

Use this guide when the user asks to **refactor backend code** to the target architecture: extract use-cases, split repositories from data-API god-classes, demote utilities to feature folders, decouple backend from PySide6.

See [pyside6-ui/references/refactoring-playbook.md](../pyside6-ui/references/refactoring-playbook.md) for the UI half (god-widget → MVP component).

> **Trigger phrases that should activate this guide:**
> - "refactor `<service>` to the new architecture"
> - "split `<DataApi>` into repositories"
> - "extract use-cases from `<controller>`"
> - "move PySide6 imports out of `backend/`"
> - "clean up `backend/utils/`"

---

## 1. Before you touch code

1. **Add tests for current behavior first.** A refactor that produces no behavior change must be provably equivalent. If the code is untested, write characterization tests against the public surface before changing anything.
2. **Confirm the target shape.** Open [architecture.md](architecture.md) and [repository-and-services.md](repository-and-services.md). Identify which roles the legacy code should split into.
3. **Establish the smallest reversible unit.** Refactor in increments that each pass `./scripts/ai-check.sh` (ruff → ruff format → mypy → pytest). Never bundle "rename + extract + reshape" into one commit.
4. **Don't rename existing classes mid-refactor** unless renaming is the refactor. Leave `*Controller`, `SqLiteDataApi`, `BenchmarkExecutionTask` as-is; introduce new presenters/repositories alongside, migrate consumers feature by feature.

---

## 2. The Refactor Order (do these in sequence)

### Step 1 — Lock behavior with tests

For the legacy class you're about to refactor, write integration-level tests against its **public** methods. These tests must continue to pass after each step. If the legacy class is too coupled to test, see Step 2 — extract one method first.

```bash
uv run pytest tests/integration/test_sq_lite_data_api.py -v
```

### Step 2 — Extract domain dataclasses (if not already)

If the legacy class returns tuples or dicts, introduce frozen dataclasses in `backend/core/models.py` and have the legacy class return those instead. Run tests.

```python
# WAS
def get_run(self, run_id: int) -> tuple[int, str, datetime]: ...

# IS
@dataclass(frozen=True)
class BenchmarkRun:
    run_id: int
    name: str
    created_at: datetime

def get_run(self, run_id: int) -> BenchmarkRun: ...
```

### Step 3 — Split god-DataApi into Repositories (one aggregate at a time)

`SqLiteDataApi` (or any multi-aggregate DataApi) is a god-class — it owns persistence for runs, results, settings, and tasks. Split it.

**Order:**

1. Define the per-aggregate ABC in `backend/core/interfaces.py`:
   ```python
   class RunsRepository(ABC):
       @abstractmethod
       def save(self, run: BenchmarkRun) -> None: ...
       @abstractmethod
       def get(self, run_id: int) -> Optional[BenchmarkRun]: ...
   ```

2. Create the per-aggregate concrete in a new feature folder:
   ```
   backend/services/benchmark/
       repository.py     ← SqliteRunsRepository(RunsRepository)
   ```
   The concrete class can initially **delegate** to the legacy `SqLiteDataApi`. This is a strangler-fig pattern:
   ```python
   class SqliteRunsRepository(RunsRepository):
       def __init__(self, *, legacy_data_api: DataApi) -> None:
           self._legacy = legacy_data_api

       @override
       def save(self, run: BenchmarkRun) -> None:
           self._legacy.create_run(run)  # delegates until extraction is complete
   ```

3. Wire it in `app_context.py`. Inject `RunsRepository` into consumers; have them stop calling `SqLiteDataApi.create_run` directly.

4. **Once every consumer goes through `RunsRepository`,** inline the SQL into `SqliteRunsRepository` and remove `create_run` from `SqLiteDataApi`.

5. Repeat for the next aggregate (`ResultsRepository`, `SettingsRepository`, …).

The legacy `SqLiteDataApi` shrinks with each iteration. Delete it when empty.

### Step 4 — Extract Use-Cases from Controllers

Inspect `ui/controllers/<name>_controller.py`. If a method:

- calls multiple services / repositories in sequence,
- enforces a domain rule before/between those calls,
- or returns a domain object that the UI then reflects,

…it's a use-case wearing controller's clothing. Extract it.

**Order:**

1. Identify the operation. Name it: `StartBenchmarkRunUseCase`, `ExportResultsUseCase`.
2. Create `backend/services/<feature>/use_cases.py`.
3. Define the class with constructor-injected ABCs (NOT the controller, NOT the event bus — those are UI concerns).
4. Move the orchestration logic from the controller's method into `execute()`. The controller's method now becomes a one-liner:
   ```python
   # ui/controllers/new_run_controller.py — before
   def on_start_clicked(self, models: list[str]) -> None:
       if not models:
           self._event_bus.emit_warning("No models selected")
           return
       tasks = self._task_loader.load(self._dataset_path)
       run = BenchmarkRun.new(...)
       self._runs_repo.save(run)
       self._event_bus.emit_run_started(run)

   # ui/controllers/new_run_controller.py — after
   def on_start_clicked(self, models: list[str]) -> None:
       try:
           run = self._start_run_uc.execute(models=models, dataset_path=self._dataset_path)
           self._event_bus.emit_run_started(run)
       except NoModelsSelected:
           self._event_bus.emit_warning("No models selected")
   ```

5. Wire the use-case in `app_context.py`.
6. Run tests. The controller's tests should mostly still pass; add a new unit test for the use-case (no Qt needed).

### Step 5 — Move PySide6 imports out of `backend/`

Search for any `from PySide6` in `backend/`:

```bash
grep -rn "from PySide6" src/ollama_llm_bench/backend/ || true
```

If a backend class needs to emit events:

1. Today: change it to return events (use a `dataclass` for the event, return a list or `Iterator`), and have the **caller** in `ui/qt_classes/` emit Qt signals.
2. Target: replace with `psygnal.Signal` declared in `backend/core/events.py`. See [repository-and-services.md §"Domain events"](repository-and-services.md).

Backend code MUST import `psygnal` (when adopted), NOT `PySide6`.

If a backend class subclasses `QObject` purely for `Signal` support, that's a leak. Move the `QObject` half to `ui/qt_classes/` as an adapter; keep the logic in the backend.

### Step 6 — Demote utilities to feature folders

For each function in `backend/utils/`:

1. Find every caller: `grep -rn "from ollama_llm_bench.backend.utils.<file> import <fn>" src/`.
2. Apply the "3 + pure + generic" test ([repository-and-services.md §"Utility test"](repository-and-services.md#the-3--pure--generic-test-must-pass-all-three)):
   - Used by ≥ 3 unrelated features? Stays in `backend/utils/`.
   - Used by 1–2 features? Move into the feature folder as `_utils.py` (or split between the consumers).
   - Takes a domain dataclass? Move it to that domain (might belong as a method on the dataclass).
3. Rename any `utils.py` / `helpers.py` / `common.py` / `misc.py` at the top of a feature folder to a precise name.

### Step 7 — Introduce psygnal for cross-call domain events (when ready)

Adopt incrementally. Pick ONE use-case that emits multiple events (typically the benchmark iteration). See [repository-and-services.md §"Domain events"](repository-and-services.md). Steps:

1. Add `psygnal>=0.10` to `pyproject.toml` dev deps first; promote to runtime when first feature ships.
2. Declare events in `backend/core/events.py`.
3. Have the use-case emit them.
4. Add a `BackendEventBridge` adapter in `ui/qt_classes/` that subscribes to psygnal and re-emits via `QtEventBus`.
5. Existing controllers continue to subscribe to `QtEventBus` — they don't know psygnal exists.

### Step 8 — Add `import-linter` contracts

Once a refactor passes, lock the boundary with CI. See [architecture.md §"import-linter Contracts"](architecture.md#5-import-linter-contracts) for the full snippet. Add to `pyproject.toml` and to `./scripts/ai-check.sh`.

If a contract fails on existing code, that's a real architectural debt — file a TODO with the specific violation, but **do not loosen the contract**.

### Step 9 — Run the full check

```bash
./scripts/ai-check.sh
# = uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest -q
```

ALL of ruff / format / mypy / pytest must pass before considering the refactor step "done."

---

## 3. Refactor Smells Checklist

When opening a class to refactor, scan for these:

| Smell | Signal | Fix |
|---|---|---|
| 12+ arg `__init__` | Constructor 20+ lines, alphabet-soup deps | Split into multiple classes — likely a god-service |
| `def method_for_<feature_a>(...)` and `def method_for_<feature_b>(...)` on same class | Class collects unrelated operations | Split into per-feature use-cases |
| Method body > 50 lines | Mixed concerns | Extract helpers; if helpers reach across layers, extract use-case |
| `if isinstance(provider, OpenAIClient): ... elif isinstance(provider, AnthropicClient):` | Type-dispatch in caller | Move method onto the abstraction; use polymorphism |
| `from PySide6.QtCore import Signal` in `backend/` | Layer leak | Use callback Protocol or psygnal |
| `from ollama_llm_bench.ui` in `backend/` | Reverse import | Refactor immediately — backend must not know UI exists |
| Direct `sqlite3.connect(...)` in `ui/` | Bypassing repository | Inject the repository ABC, route through it |
| `import_linter` failure | Boundary violation | Don't `# noqa` it — restructure |
| `# TODO: refactor` older than 30 days | Rot | File ticket and either fix or remove |

---

## 4. Anti-Patterns to Refuse to Implement

If during refactoring you find pressure to do any of these — push back:

1. **"Just add `# type: ignore` to make mypy pass."** No. Type errors are real. Either the type is wrong or the design is wrong.
2. **"Bypass the ABC for this one case."** No. The ABC is the architectural rule. Either widen it cleanly (adding a method) or refactor the calling code.
3. **"Use `ContextProvider.get_context()` in this widget."** No. Constructor-inject the controller/presenter the widget needs.
4. **"It's faster to just put the SQL in the controller."** No. The controller doesn't know SQLite exists. Route through a repository.
5. **"Make this backend class a `QObject` so it can emit signals."** No. Either return the events from the method or use psygnal (when adopted).
6. **"It's only one method, no need for an ABC."** Acceptable IF the concrete class is used in exactly one place. The moment a second consumer appears (especially a test), introduce the ABC.

---

## 5. Communication During Refactor

When working on a refactor:

1. **State the smell** you're fixing in plain English ("`SqLiteDataApi` is a god-class — splitting into `RunsRepository` and `ResultsRepository`").
2. **State the smallest step.** Don't promise the full refactor in one message — promise this step.
3. **Show the diff before applying** when the change is non-trivial (>30 lines).
4. **Run `./scripts/ai-check.sh` after every step.** If it fails, the step isn't done.
5. **Don't delete old code until every consumer has migrated.** Use the strangler-fig delegate pattern (Step 3.2 above).

---

## 6. Worked Example: Splitting `SqLiteDataApi`

Concrete refactor walk-through for the largest god-class in the project.

### Inventory

`SqLiteDataApi` currently provides:
- runs: `create_run`, `update_run_status`, `get_run`, `list_runs`
- results: `create_result`, `update_result`, `get_results_for_run`
- settings: `get_setting`, `set_setting`
- tasks: `get_tasks_for_run`

### Target

```
backend/core/interfaces.py
    RunsRepository
    ResultsRepository
    SettingsRepository
    TasksRepository

backend/services/benchmark/repository.py
    SqliteRunsRepository
    SqliteResultsRepository
    SqliteTasksRepository

backend/services/settings/repository.py
    SqliteSettingsRepository
```

### Increment-by-increment plan

**Increment 1: Extract `RunsRepository`**
- Define ABC in `core/interfaces.py`.
- Create `SqliteRunsRepository` that delegates to `SqLiteDataApi`.
- Wire in `app_context.py`. Inject `RunsRepository` into every consumer that calls `data_api.create_run` / `get_run` / `update_run_status` / `list_runs`.
- Each consumer: replace `data_api.create_run(...)` with `runs_repo.save(...)` etc.
- Run `./scripts/ai-check.sh`. Commit.

**Increment 2: Inline SQL into `SqliteRunsRepository`**
- Move the actual SQL from `SqLiteDataApi.create_run` into `SqliteRunsRepository.save`.
- Delete the run-related methods from `SqLiteDataApi`.
- Run `./scripts/ai-check.sh`. Commit.

**Increment 3: Repeat for Results.** Same shape, smaller scope.

**Increment 4: Repeat for Settings.** Same shape.

**Increment 5: Repeat for Tasks.** Same shape.

**Increment 6: Delete `SqLiteDataApi` and `DataApi` ABC.** Should be empty by now; if not, find the missed consumer and migrate it.

Each increment is independently reversible — if Increment 3 fails, Increment 1 and 2 still hold.

---

## 7. After the Refactor

- Update [architecture.md](architecture.md) only if a rule changed. Refactors that produce the target shape need no doc update — they ratify what's there.
- Update [examples.md](examples.md) if the new patterns benefit future authors.
- Remove the TODO that tracked the refactor.
- Add `import-linter` contracts to prevent regression.
