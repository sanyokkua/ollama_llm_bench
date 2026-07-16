"""Architecture tests: adapters/notification_service/ imports PySide6 only --
no backend module and no asyncio (STORY-047, 01_MODULE_INVENTORY.md §5).
"""

import ast
import inspect
from pathlib import Path

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_NOTIFICATION_SERVICE_ROOT = _PACKAGE_ROOT / "adapters" / "notification_service"


def _iter_source_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*.py"):
        if "tests" in path.relative_to(root).parts:
            continue
        files.append(path)
    return sorted(files)


def _imports_backend(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.startswith("ollama_llm_bench.backend") for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (
            node.module is not None and node.module.startswith("ollama_llm_bench.backend")
        ):
            return True
    return False


def _imports_asyncio(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "asyncio" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            return True
    return False


def test_notification_service_imports_no_backend_module() -> None:
    """adapters/notification_service/ holds no backend Protocol -- it imports
    PySide6 only (01_MODULE_INVENTORY.md §5, STORY-047 design constraints)."""
    # Arrange
    offending_files: list[str] = []
    for source_file in _iter_source_files(_NOTIFICATION_SERVICE_ROOT):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if _imports_backend(tree):
            offending_files.append(str(source_file.relative_to(_PACKAGE_ROOT)))

    # Assert
    assert offending_files == []


def test_notification_service_never_imports_asyncio() -> None:
    """adapters/notification_service/ never imports asyncio, per the
    concurrency standard's synchronous-backend-plus-Qt model (STORY-047)."""
    # Arrange
    offending_files: list[str] = []
    for source_file in _iter_source_files(_NOTIFICATION_SERVICE_ROOT):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        if _imports_asyncio(tree):
            offending_files.append(str(source_file.relative_to(_PACKAGE_ROOT)))

    # Assert
    assert offending_files == []
