"""Architecture test for the accessibility floor's mouse-only requirement (§4, §10)."""

import ast
from pathlib import Path
import re

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"
_MNEMONIC_RE = re.compile(r"(?<!&)&(?!&)")
_TEXT_SETTING_ATTRS = frozenset({"setText", "setWindowTitle", "setTitle"})
_TEXT_CONSTRUCTOR_NAMES = frozenset({"QAction", "QMenu"})


def _iter_python_files() -> list[Path]:
    return sorted(
        path
        for path in _SRC_ROOT.rglob("*.py")
        if "tests" not in path.parts and path.name != "conftest.py"
    )


def _offenders_in_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    relative = path.relative_to(_SRC_ROOT)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "QShortcut":
            offenders.append(f"{relative}:{node.lineno} QShortcut(...) constructed")
        if isinstance(func, ast.Attribute) and func.attr in {"setShortcut", "setShortcuts"}:
            offenders.append(f"{relative}:{node.lineno} .{func.attr}(...) called")
        if isinstance(func, ast.Attribute) and func.attr in _TEXT_SETTING_ATTRS:
            offenders.extend(
                f"{relative}:{node.lineno} .{func.attr}({arg.value!r}) has an unescaped '&' mnemonic"
                for arg in node.args
                if isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and _MNEMONIC_RE.search(arg.value)
            )
        if isinstance(func, ast.Name) and func.id in _TEXT_CONSTRUCTOR_NAMES:
            offenders.extend(
                f"{relative}:{node.lineno} {func.id}({arg.value!r}) has an unescaped '&' mnemonic"
                for arg in node.args
                if isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and _MNEMONIC_RE.search(arg.value)
            )
    return offenders


def test_mnemonic_regex_flags_unescaped_ampersand_and_spares_escaped_one() -> None:
    """Proves: STORY-091-AC-5 (self-check)

    The mnemonic regex matches a single '&' (a Qt accelerator marker) and does not match
    an escaped '&&' (Qt's literal-ampersand form) -- proving the check catches a real
    mnemonic before it is trusted against the real source tree.
    """
    assert _MNEMONIC_RE.search("&Save") is not None
    assert _MNEMONIC_RE.search("Save && Close") is None


def test_no_custom_shortcut_accelerator_or_mnemonic_is_registered() -> None:
    """Proves: STORY-091-AC-5

    No module registers a QShortcut, a QAction/button shortcut, or an unescaped '&'
    mnemonic in a button/action/window/group-box label. The toolkit's built-in modal
    Enter/Esc defaults register nothing and so never appear here (D-R-07).
    """
    offenders = [offender for path in _iter_python_files() for offender in _offenders_in_file(path)]
    assert offenders == [], "custom keyboard affordances found:\n" + "\n".join(offenders)
