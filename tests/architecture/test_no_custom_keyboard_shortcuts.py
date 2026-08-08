"""Architecture test for the accessibility floor's mouse-only requirement (§4, §10)."""

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"
_TEXT_SETTING_ATTRS = frozenset({"setText", "setWindowTitle", "setTitle"})
_TEXT_CONSTRUCTOR_NAMES = frozenset(
    {
        "QAction",
        "QMenu",
        "QPushButton",
        "QToolButton",
        "QCheckBox",
        "QRadioButton",
        "QGroupBox",
        "QLabel",
    }
)
_TEXT_ADDING_ATTRS = frozenset({"addTab", "insertTab", "setTabText", "addItem", "addAction"})


def _has_unescaped_mnemonic(text: str) -> bool:
    """Whether `text` contains a Qt accelerator marker: a '&' not part of an escaped '&&' pair.

    Qt consumes ampersands left-to-right, pairing consecutive ones as escaped literals; an odd
    run of 3+ consecutive '&' still leaves one live mnemonic marker, which a lookaround regex
    checking only immediate neighbours misses (e.g. "&&&Save" renders as "&Save" with S as a
    live accelerator).
    """
    i = 0
    length = len(text)
    while i < length:
        if text[i] == "&":
            if i + 1 < length and text[i + 1] == "&":
                i += 2
                continue
            return True
        i += 1
    return False


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
                and _has_unescaped_mnemonic(arg.value)
            )
        if isinstance(func, ast.Attribute) and func.attr in _TEXT_ADDING_ATTRS:
            offenders.extend(
                f"{relative}:{node.lineno} .{func.attr}({arg.value!r}) has an unescaped '&' mnemonic"
                for arg in node.args
                if isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and _has_unescaped_mnemonic(arg.value)
            )
        if isinstance(func, ast.Name) and func.id in _TEXT_CONSTRUCTOR_NAMES:
            offenders.extend(
                f"{relative}:{node.lineno} {func.id}({arg.value!r}) has an unescaped '&' mnemonic"
                for arg in node.args
                if isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and _has_unescaped_mnemonic(arg.value)
            )
    return offenders


def test_mnemonic_scan_flags_unescaped_ampersand_and_spares_escaped_one() -> None:
    """Proves: STORY-091-AC-5 (self-check)

    _has_unescaped_mnemonic flags a single '&' (a Qt accelerator marker) and an odd run of
    3+ consecutive '&' (still one live marker after pairing), and does not flag an escaped
    '&&' or an even-length run of '&' -- proving the check catches a real mnemonic, including
    the lookaround-regex blind spot the prior implementation missed, before it is trusted
    against the real source tree.
    """
    assert _has_unescaped_mnemonic("&Save") is True
    assert _has_unescaped_mnemonic("Save && Close") is False
    assert _has_unescaped_mnemonic("&&&Save") is True
    assert _has_unescaped_mnemonic("&&&&Save") is False


def test_no_custom_shortcut_accelerator_or_mnemonic_is_registered() -> None:
    """Proves: STORY-091-AC-5

    No module registers a QShortcut, a QAction/button shortcut, or an unescaped '&'
    mnemonic in a button/action/window/group-box label. The toolkit's built-in modal
    Enter/Esc defaults register nothing and so never appear here (D-R-07).
    """
    offenders = [offender for path in _iter_python_files() for offender in _offenders_in_file(path)]
    assert offenders == [], "custom keyboard affordances found:\n" + "\n".join(offenders)
