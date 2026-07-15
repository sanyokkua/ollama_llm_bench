"""Architecture tests: ``adapters/qt_benchmark_flow/`` imports no ``asyncio``, and the
``QtBenchmarkFlow`` facade class contains only forwarding calls to the backend pipeline
(STORY-042).

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§4a (the dispatcher thread, DD-38); ``docs/v3_specification/08_Cross_Cutting/
08-E_interfaces_contracts.md`` §11 (the ``BenchmarkFlowApi`` method surface this facade
forwards unchanged). Mirrors ``tests/architecture/test_qt_runnables_module.py`` (STORY-041).
"""

import ast
import inspect
from pathlib import Path

import pytest

import ollama_llm_bench

_PACKAGE_ROOT = Path(inspect.getfile(ollama_llm_bench)).parent
_QT_BENCHMARK_FLOW_ROOT = _PACKAGE_ROOT / "adapters" / "qt_benchmark_flow"
_FORBIDDEN_IMPORT_ROOTS = ("asyncio", "anyio", "qasync")
_FACADE_FILE_NAME = "facade.py"
_FACADE_CLASS_NAME = "QtBenchmarkFlow"


def _iter_source_files() -> list[Path]:
    files = []
    for path in _QT_BENCHMARK_FLOW_ROOT.rglob("*.py"):
        if "tests" in path.relative_to(_QT_BENCHMARK_FLOW_ROOT).parts:
            continue
        files.append(path)
    return sorted(files)


def _iter_source_files_and_ids() -> tuple[list[Path], list[str]]:
    files = _iter_source_files()
    ids = [str(path.relative_to(_QT_BENCHMARK_FLOW_ROOT)) for path in files]
    return files, ids


def _imports_forbidden_root(tree: ast.AST) -> bool:
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
    return not imported_roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


_SOURCE_FILES, _SOURCE_FILE_IDS = _iter_source_files_and_ids()


def test_at_least_one_source_file_discovered() -> None:
    """Sanity guard for the AST walker itself: ``adapters/qt_benchmark_flow/`` has at
    least one discoverable ``.py`` source file, so the parametrized checks below are not
    vacuously true."""
    # Assert
    assert len(_SOURCE_FILES) > 0


@pytest.mark.parametrize("source_file", _SOURCE_FILES, ids=_SOURCE_FILE_IDS)
def test_qt_benchmark_flow_module_imports_no_asyncio(source_file: Path) -> None:
    """Proves: STORY-042-AC-1

    Every source file under ``adapters/qt_benchmark_flow/`` imports no
    ``asyncio``, no ``anyio``, and no ``qasync`` — the facade and its real
    dispatcher thread use only ``threading``/``queue`` plus the backend's
    ``RunDispatcher``/``BenchmarkFlowApi`` Protocols (D-R-01).
    """
    # Arrange
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    # Assert
    assert not _imports_forbidden_root(tree)


def _facade_class_node(tree: ast.Module) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == _FACADE_CLASS_NAME:
            return node
    raise AssertionError(f"{_FACADE_CLASS_NAME} class not found in {_FACADE_FILE_NAME}")


def _method_body_is_a_single_forwarding_call(method: ast.FunctionDef) -> bool:
    """A method's body carries no business logic iff, once its docstring `Expr` (if
    any) is stripped, it consists of exactly one statement — either a bare
    `self._pipeline.<method>(...)` call or a `return` of one."""
    body = [
        stmt
        for stmt in method.body
        if not (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
    ]
    if len(body) != 1:
        return False
    (statement,) = body
    if isinstance(statement, ast.Return | ast.Expr):
        call = statement.value
    else:
        return False
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Attribute)
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "self"
        and func.value.attr == "_pipeline"
    )


def test_qt_benchmark_flow_facade_holds_only_forwarding_methods() -> None:
    """Proves: STORY-042-AC-2

    Every public method on ``QtBenchmarkFlow`` (excluding ``__init__``) is a
    single-line forward to the identically-named method on
    ``self._pipeline`` — the facade carries no business logic of its own,
    per this story's Definition of Done.
    """
    # Arrange
    facade_file = _QT_BENCHMARK_FLOW_ROOT / "_internal" / _FACADE_FILE_NAME
    tree = ast.parse(facade_file.read_text(encoding="utf-8"), filename=str(facade_file))
    facade_class = _facade_class_node(tree)
    public_methods = [
        node
        for node in facade_class.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]

    # Assert
    assert len(public_methods) > 0
    assert all(_method_body_is_a_single_forwarding_call(method) for method in public_methods)
