"""Architecture test: the accessibility-floor e2e checks may never be silenced per platform.

`just check` runs `tests/e2e/` on the host's **native** Qt platform; CI (`pr-gate.yml`) and
`just test-e2e` pin `QT_QPA_PLATFORM=offscreen` (16_Engineering_Standards/07_TESTING_STANDARD.md
§12). STORY-091's click-target and focus-ring checks passed offscreen and failed natively for
two months without CI noticing, and the cheapest way to make that red go away would have been a
`skipif` -- which would have left the product defect shipped. This test makes the honest fix the
only fix: neither module may carry a skip, an xfail, or a branch on the platform name.
"""

import ast
from pathlib import Path

import pytest

_E2E_ROOT = Path(__file__).resolve().parents[1] / "e2e"
_GUARDED_MODULES = (
    _E2E_ROOT / "test_click_target_size.py",
    _E2E_ROOT / "test_focus_ring_visibility.py",
)
_BANNED_ATTRIBUTES = frozenset({"skipif", "xfail", "skip"})
_BANNED_NAMES = frozenset({"QT_QPA_PLATFORM", "platformName"})


def _dotted_name(node: ast.expr) -> str:
    """Render an attribute/name expression as its dotted source spelling."""
    if isinstance(node, ast.Attribute):
        return f"{_dotted_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _platform_guards(module_path: Path) -> list[str]:
    """Report every skip/xfail marker or platform-name reference found in ``module_path``."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _BANNED_ATTRIBUTES:
            findings.append(f"{module_path.name}:{node.lineno} {_dotted_name(node)}")
        if isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            findings.append(f"{module_path.name}:{node.lineno} {node.id}")
        if isinstance(node, ast.Constant) and node.value in _BANNED_NAMES:
            findings.append(f"{module_path.name}:{node.lineno} {node.value!r}")
    return findings


@pytest.mark.parametrize("module_path", _GUARDED_MODULES, ids=lambda path: path.name)
def test_accessibility_e2e_checks_carry_no_platform_skip(module_path: Path) -> None:
    """Proves: STORY-119-AC-3

    Neither accessibility-floor e2e module carries a `pytest.mark.skipif`, a
    `pytest.mark.xfail`, a `pytest.skip(...)` call, or any reference to `QT_QPA_PLATFORM` /
    `QGuiApplication.platformName()`, so the identical assertions execute under `just check`
    natively and under `just test-e2e` offscreen.
    """
    assert module_path.exists(), f"{module_path} is missing; the check cannot be silenced away"

    guards = _platform_guards(module_path)

    assert guards == [], (
        "accessibility-floor e2e checks must run identically on every platform; found:\n"
        + "\n".join(guards)
    )
