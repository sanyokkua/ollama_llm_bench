"""Architecture test for the accessibility floor's objectName requirement (§7.1, §10)."""

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"
_SCAN_ROOTS = (_SRC_ROOT / "ui", _SRC_ROOT / "adapters")

_QT_INTERACTIVE_BASE_NAMES = frozenset(
    {
        "QPushButton",
        "QToolButton",
        "QCheckBox",
        "QRadioButton",
        "QAbstractButton",
        "QComboBox",
        "QLineEdit",
        "QTextEdit",
        "QPlainTextEdit",
        "QSpinBox",
        "QDoubleSpinBox",
        "QAbstractSpinBox",
        "QTableView",
        "QTableWidget",
        "QListView",
        "QListWidget",
        "QTreeView",
        "QTreeWidget",
        "QAbstractItemView",
    }
)


def _iter_python_files(roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(
            path
            for path in root.rglob("*.py")
            if "tests" not in path.parts and path.name != "conftest.py"
        )
    return sorted(files)


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _collect_class_bases(files: list[Path]) -> dict[str, set[str]]:
    class_bases: dict[str, set[str]] = {}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = {name for base in node.bases if (name := _base_name(base)) is not None}
                class_bases.setdefault(node.name, set()).update(bases)
    return class_bases


def _interactive_class_names(files: list[Path]) -> frozenset[str]:
    class_bases = _collect_class_bases(files)
    interactive = set(_QT_INTERACTIVE_BASE_NAMES)
    changed = True
    while changed:
        changed = False
        for name, bases in class_bases.items():
            if name not in interactive and bases & interactive:
                interactive.add(name)
                changed = True
    return frozenset(interactive)


def _target_repr(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _target_repr(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _ctor_name(call: ast.Call) -> str | None:
    if isinstance(call.func, (ast.Name, ast.Attribute)):
        return _base_name(call.func) if isinstance(call.func, ast.Attribute) else call.func.id
    return None


class _ScopeCollector(ast.NodeVisitor):
    """Collects (construction, setObjectName) pairs per lexical function scope.

    A push/pop scope stack keyed on each ``FunctionDef`` means a construction in an outer
    method is never matched against a ``setObjectName`` call made inside a nested inner
    function, and vice versa -- each function's own statements are checked against only
    that same function's own ``setObjectName`` calls.
    """

    def __init__(self, interactive_names: frozenset[str]) -> None:
        self._interactive_names = interactive_names
        self.offenders: list[tuple[int, str, str]] = []
        self._scope_stack: list[tuple[dict[str, int], dict[str, ast.expr | None]]] = [({}, {})]

    def _pop_scope(self) -> None:
        constructions, named = self._scope_stack.pop()
        for repr_, lineno in constructions.items():
            if repr_ not in named:
                self.offenders.append((lineno, repr_, "no setObjectName call"))
            elif isinstance(named[repr_], ast.Constant) and named[repr_].value == "":  # type: ignore[union-attr]
                self.offenders.append((lineno, repr_, "empty objectName"))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope_stack.append(({}, {}))
        self.generic_visit(node)
        self._pop_scope()

    def visit_Assign(self, node: ast.Assign) -> None:
        value = node.value
        if isinstance(value, ast.Call) and _ctor_name(value) in self._interactive_names:
            constructions, _ = self._scope_stack[-1]
            for target in node.targets:
                repr_ = _target_repr(target)
                if repr_ is not None:
                    constructions[repr_] = node.lineno
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "setObjectName":
            constructions, named = self._scope_stack[-1]
            obj_repr = _target_repr(node.func.value)
            arg = node.args[0] if node.args else None
            if obj_repr is not None:
                named[obj_repr] = arg
            elif (
                isinstance(node.func.value, ast.Call)
                and _ctor_name(node.func.value) in self._interactive_names
            ):
                key = f"<chained:{node.lineno}>"
                constructions[key] = node.lineno
                named[key] = arg
        self.generic_visit(node)

    def finalize(self) -> None:
        while self._scope_stack:
            self._pop_scope()


def test_scope_collector_flags_missing_and_empty_objectname_on_synthetic_source() -> None:
    """Proves: STORY-091-AC-1 (self-check)

    _ScopeCollector flags a QPushButton with no setObjectName call and one with an empty
    string, and does not flag one that sets a non-empty objectName -- proving the walker
    catches a real regression before it is trusted against the real source tree.
    """
    source = """
class _View:
    def _build(self):
        good = QPushButton("Save")
        good.setObjectName("save_button")
        missing = QPushButton("Cancel")
        empty = QPushButton("Close")
        empty.setObjectName("")
"""
    tree = ast.parse(source)
    collector = _ScopeCollector(frozenset({"QPushButton"}))
    collector.visit(tree)
    collector.finalize()

    flagged_vars = {repr_ for _, repr_, _ in collector.offenders}
    assert flagged_vars == {"missing", "empty"}


def test_every_interactive_control_sets_a_nonempty_objectname() -> None:
    """Proves: STORY-091-AC-1

    Every interactive control constructed in ui/ or adapters/ -- a Qt built-in interactive
    widget type or a local subclass of one -- calls setObjectName with a non-empty value in
    its own construction scope (08_ACCESSIBILITY_FLOOR.md §7.1, §10).
    """
    files = _iter_python_files(_SCAN_ROOTS)
    interactive_names = _interactive_class_names(files)
    offenders: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        collector = _ScopeCollector(interactive_names)
        collector.visit(tree)
        collector.finalize()
        offenders.extend(
            f"{path.relative_to(_SRC_ROOT)}:{lineno} {repr_} -- {reason}"
            for lineno, repr_, reason in collector.offenders
        )
    assert offenders == [], "controls with no author-assigned objectName:\n" + "\n".join(offenders)
