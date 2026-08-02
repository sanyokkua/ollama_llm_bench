"""Qt-backed ``TaskRunner`` adapter — schedules backend work on a ``QThreadPool``."""

from ollama_llm_bench.adapters.qt_runnables.api import QtTaskRunner, make_qt_task_runner

__all__: list[str] = ["QtTaskRunner", "make_qt_task_runner"]
