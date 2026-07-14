"""Comment-preserving YAML formatter — the single writer of task files.

Source of truth: `docs/v3_specification/11_Services_and_Algorithms/12_YAML_FORMATTER.md`.

``YamlFormatter`` round-trip loads a task file into a comment-carrying
``TaskFileDocument`` handle and writes it back with canonical field ordering,
style normalization, and an atomic write-temp-then-rename save so an
interrupted save never leaves a truncated file on disk. The loader-tolerant
reader and the editor-strict validator live in ``backend/task_files/``.
"""

from ollama_llm_bench.backend.yaml_formatter.api import make_yaml_formatter
from ollama_llm_bench.backend.yaml_formatter.models import (
    SaveFailureReason,
    SaveResult,
    TaskFileDocument,
)
from ollama_llm_bench.backend.yaml_formatter.protocols import YamlFormatter

__all__: list[str] = [
    "SaveFailureReason",
    "SaveResult",
    "TaskFileDocument",
    "YamlFormatter",
    "make_yaml_formatter",
]
