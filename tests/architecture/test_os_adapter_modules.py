"""Architecture tests: the three sibling OS-adapter packages
(adapters/native_pickers/, adapters/clipboard/, adapters/file_system_actions/)
import no asyncio, and any per-OS branching logic lives only in each module's
_internal/ package (STORY-048, 01_MODULE_INVENTORY.md §5).
"""

import ast
import inspect
from pathlib import Path

import pytest

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_OS_ADAPTER_ROOTS = [
    _PACKAGE_ROOT / "adapters" / "native_pickers",
    _PACKAGE_ROOT / "adapters" / "clipboard",
    _PACKAGE_ROOT / "adapters" / "file_system_actions",
]


def _iter_source_files(root: Path, *, exclude_internal: bool) -> list[Path]:
    files = []
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if "tests" in parts:
            continue
        if exclude_internal and "_internal" in parts:
            continue
        files.append(path)
    return sorted(files)


def _imports_asyncio(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "asyncio" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            return True
    return False


def _has_platform_branch(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "platform"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "system"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "platform"
        ):
            return True
    return False


@pytest.mark.parametrize("module_root", _OS_ADAPTER_ROOTS, ids=lambda p: p.name)
def test_os_adapter_module_never_imports_asyncio(module_root: Path) -> None:
    """adapters/{native_pickers,clipboard,file_system_actions}/ never import
    asyncio, per the synchronous, Qt-plus-blocking-worker concurrency model
    (STORY-048 design constraints)."""
    # Arrange
    offending_files = [
        str(source_file.relative_to(_PACKAGE_ROOT))
        for source_file in _iter_source_files(module_root, exclude_internal=False)
        if _imports_asyncio(ast.parse(source_file.read_text(encoding="utf-8")))
    ]
    # Assert
    assert offending_files == []


@pytest.mark.parametrize("module_root", _OS_ADAPTER_ROOTS, ids=lambda p: p.name)
def test_os_adapter_module_isolates_platform_branches_in_internal(module_root: Path) -> None:
    """Any sys.platform/platform.system() branching in an OS-adapter module
    lives only inside its _internal/ package -- __init__.py, api.py, and
    protocols.py stay platform-agnostic (STORY-048 design constraints)."""
    # Arrange
    offending_files = [
        str(source_file.relative_to(_PACKAGE_ROOT))
        for source_file in _iter_source_files(module_root, exclude_internal=True)
        if _has_platform_branch(ast.parse(source_file.read_text(encoding="utf-8")))
    ]
    # Assert
    assert offending_files == []
