"""Shared fixtures for ``ui/resume_benchmark/`` colocated tests."""

import re
from typing import Final

import pytest

from ollama_llm_bench.backend.domain import BenchmarkRun

_SANITIZE_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]")
_MAX_BASE_LENGTH: Final[int] = 80


class FakeExportFilenameHelper:
    """An ``ExportFilenameHelper`` fake: real sanitisation plus the
    ``Run_<run_id>`` fallback (``05_EXPORT_FORMATS.md`` §2).

    STORY-088-AC-3 consolidated the three byte-identical copies that previously
    lived one apiece in ``test_actions.py``, ``test_controller.py`` and
    ``test_controller_menu_actions.py``.
    """

    def compose_filename(self, *, run: BenchmarkRun, kind: str, ext: str) -> str:
        sanitized = _SANITIZE_RE.sub("_", run.run_name or "")
        collapsed = re.sub(r"_+", "_", sanitized)
        stripped = collapsed.strip("_").lstrip(".")[:_MAX_BASE_LENGTH]
        base = stripped or f"Run_{run.run_id}"
        return f"{base}_{kind}.{ext}"


@pytest.fixture
def export_filename_helper() -> FakeExportFilenameHelper:
    """The shared ``ExportFilenameHelper`` fake — one fresh instance per test."""
    return FakeExportFilenameHelper()
