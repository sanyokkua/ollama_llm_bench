"""Architecture tests: ``ui/main_window/`` reaches settings/readiness/pipeline concerns only
through its own ``MainWindowGateway`` Protocol (D-R-06, STORY-053), and its public surface is
exactly one symbol.

Modelled on ``tests/architecture/test_ui_gate_access.py`` (STORY-043).
"""

import ast
import inspect
from pathlib import Path

import ollama_llm_bench
from ollama_llm_bench.ui import main_window

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_MAIN_WINDOW_INTERNAL_ROOT = _PACKAGE_ROOT / "ui" / "main_window" / "_internal"
_FORBIDDEN_BACKEND_MODULES = (
    "ollama_llm_bench.backend.settings",
    "ollama_llm_bench.backend.readiness",
    "ollama_llm_bench.backend.benchmark_pipeline",
)
_CHECKED_FILES = ("controller.py", "close_handler.py")


def _iter_checked_files() -> list[Path]:
    return sorted(
        path for path in _MAIN_WINDOW_INTERNAL_ROOT.rglob("*.py") if path.name in _CHECKED_FILES
    )


def _imports_forbidden_backend_module(tree: ast.AST) -> str | None:
    """Return the first forbidden backend module ``tree`` imports, or ``None``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in _FORBIDDEN_BACKEND_MODULES:
                    if alias.name == forbidden or alias.name.startswith(forbidden + "."):
                        return forbidden
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for forbidden in _FORBIDDEN_BACKEND_MODULES:
                if node.module == forbidden or node.module.startswith(forbidden + "."):
                    return forbidden
    return None


def _find_forbidden_backend_importers() -> dict[str, str]:
    offenders: dict[str, str] = {}
    for source_file in _iter_checked_files():
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        forbidden = _imports_forbidden_backend_module(tree)
        if forbidden is not None:
            offenders[str(source_file.relative_to(_PACKAGE_ROOT))] = forbidden
    return offenders


def test_at_least_two_checked_files_discovered() -> None:
    """Sanity guard for the AST walker itself: both ``controller.py`` and
    ``close_handler.py`` exist under ``ui/main_window/_internal/``, so the check below is not
    vacuously true."""
    # Assert
    assert len(_iter_checked_files()) == len(_CHECKED_FILES)


def test_controller_and_close_handler_hold_no_backend_protocol_directly() -> None:
    """Proves: STORY-053 Definition of Done

    ``ui/main_window/_internal/controller.py`` and ``_internal/close_handler.py`` import no
    ``backend.settings``, ``backend.readiness``, or ``backend.benchmark_pipeline`` symbol --
    they depend only on their own ``MainWindowGateway`` Protocol (D-R-06).
    """
    # Arrange / Act
    offenders = _find_forbidden_backend_importers()

    # Assert
    assert offenders == {}


def test_main_window_public_surface_is_exactly_make_main_window_and_make_status_bar() -> None:
    """Proves: STORY-053 Definition of Done

    The public surface of ``ui/main_window/`` is exactly two symbols, ``make_main_window``
    and ``make_status_bar`` (STORY-077 Fix 2 -- the status bar must be built before
    ``make_main_window`` so ``compose.py`` can share one instance with
    ``adapters.notification_service``).
    """
    # Assert
    assert main_window.__all__ == ["make_main_window", "make_status_bar"]
