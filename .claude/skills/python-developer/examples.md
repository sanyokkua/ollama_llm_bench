# Python Developer — Code Examples

Reference examples for patterns used in Ollama LLM Bench. See [SKILL.md](SKILL.md) for rules.

---

## ABC Interface Definition

Full template — use this when defining a new service interface in `core/interfaces.py`:

```python
from abc import ABC, abstractmethod
from typing import Optional

class MyServiceApi(ABC):
    """Abstract interface for the my-service concern."""

    def __init__(self, *, data_api: DataApi):
        self._data_api = data_api

    @abstractmethod
    def process(self, item_id: str) -> ProcessResult:
        """Process a single item by its identifier.

        Args:
            item_id: Unique identifier of the item; must not be empty.

        Returns:
            Result containing processed data and status.
        """

    @abstractmethod
    def retrieve_all(self) -> list[ProcessResult]:
        """Retrieve all processed items.

        Returns:
            List of results; empty if none found.
        """
```

---

## Protocol Interface (Preferred for New Code)

```python
from typing import Protocol

class Serializable(Protocol):
    """Structural interface for objects that serialize to dictionary."""

    def to_dict(self) -> dict[str, str]: ...

class Configurable(Protocol):
    """Structural interface for objects with configuration."""

    @property
    def config_key(self) -> str: ...
    def validate(self) -> bool: ...
```

---

## Frozen Dataclass

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

class TaskStatus(StrEnum):
    """Status of a processing task."""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

@dataclass(frozen=True)
class ProcessResult:
    """Immutable result of a processing operation."""
    result_id: int
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    output: Optional[str] = None
    error_message: Optional[str] = None
```

---

## Service Implementation

```python
import logging
from typing import override

from ollama_llm_bench.core.interfaces import DataApi, MyServiceApi
from ollama_llm_bench.core.models import ProcessResult

logger = logging.getLogger(__name__)

class ConcreteMyService(MyServiceApi):
    """Concrete implementation of MyServiceApi using SQLite storage."""

    def __init__(self, *, data_api: DataApi) -> None:
        super().__init__(data_api=data_api)

    @override
    def process(self, item_id: str) -> ProcessResult:
        logger.debug("Processing item: %s", item_id)
        try:
            result = self._data_api.retrieve(item_id)
            return ProcessResult(
                result_id=result.id,
                task_id=item_id,
                status=TaskStatus.COMPLETED,
                output=result.data,
            )
        except Exception as e:
            logger.error("Failed to process item %s: %s", item_id, e)
            return ProcessResult(
                result_id=-1,
                task_id=item_id,
                status=TaskStatus.FAILED,
                error_message=str(e),
            )

    @override
    def retrieve_all(self) -> list[ProcessResult]:
        return self._data_api.retrieve_all_results()
```

---

## DI Wiring in app_context.py

```python
def _create_app_context(app_root: Path, dataset_path: Path) -> ApplicationContext:
    event_bus = QtEventBus()
    data_api = SqLiteDataApi(app_root / "db.sqlite")

    # Services depend on ABCs, not concrete classes
    my_service = ConcreteMyService(data_api=data_api)

    # Controllers depend on services and event bus
    my_controller = MyController(
        my_service=my_service,
        event_bus=event_bus,
    )

    return ApplicationContext(
        my_service=my_service,
        my_controller=my_controller,
        event_bus=event_bus,
        # ... other services
    )
```

---

## QRunnable Background Task

Use this pattern for long-running operations (see `BenchmarkExecutionTask`):

```python
from PySide6.QtCore import QObject, QRunnable, Signal

class MyTask(QRunnable):
    """Background task for long-running operation."""

    class Signals(QObject):
        """Signals emitted by the task for progress updates."""
        status_changed = Signal(bool)
        progress = Signal(str)

    def __init__(self, *, data_api: DataApi) -> None:
        super().__init__()
        self._data_api = data_api
        self.signals = self.Signals()
        self._stop_requested = False
        self.setAutoDelete(True)

    def stop(self) -> None:
        """Request cancellation of the task."""
        self._stop_requested = True

    def run(self) -> None:
        """Execute the task in a background thread."""
        try:
            self.signals.status_changed.emit(True)
            self._do_work()
        except Exception as e:
            logger.error("Task failed: %s", e)
        finally:
            self.signals.status_changed.emit(False)

    def _do_work(self) -> None:
        for item in self._data_api.retrieve_all():
            if self._stop_requested:
                return
            self.signals.progress.emit(f"Processing {item.id}")
            # ... process item
```

---

## MetaQObjectABC Usage

When combining `QObject` with an ABC (see `QtEventBus`):

```python
from PySide6.QtCore import QObject, Signal
from ollama_llm_bench.qt_classes.meta_class import MetaQObjectABC

class QtEventBus(QObject, EventBus, metaclass=MetaQObjectABC):
    """Qt-based event bus using Signal for cross-component communication."""

    _run_id_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()

    @override
    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None:
        self._run_id_changed.connect(callback)

    @override
    def emit_run_id_changed(self, value: Optional[int]) -> None:
        self._run_id_changed.emit(value or -1)
```

---

## Error Handling in Pipeline Methods

Capture errors in model fields — never throw from `run()`:

```python
def _execute_task(self, task: BenchmarkResult) -> None:
    try:
        response = self._llm_api.inference(
            model_name=task.model_name,
            user_prompt=prompt,
        )
        updated = BenchmarkResult(
            result_id=task.result_id,
            run_id=task.run_id,
            task_id=task.task_id,
            model_name=task.model_name,
            status=BenchmarkResultStatus.COMPLETED,
            llm_response=response.llm_response,
            time_taken_ms=response.time_taken_ms,
        )
        self._data_api.update_benchmark_result(updated)
    except Exception as e:
        logger.error("Failed to execute task %s: %s", task.task_id, e)
        failed = BenchmarkResult(
            result_id=task.result_id,
            run_id=task.run_id,
            task_id=task.task_id,
            model_name=task.model_name,
            status=BenchmarkResultStatus.FAILED,
            error_message=str(e),
        )
        self._data_api.update_benchmark_result(failed)
```
