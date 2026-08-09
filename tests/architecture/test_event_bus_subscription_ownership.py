"""STORY-118 -- no owner-less event-bus subscription may exist under ``src/``."""

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "ollama_llm_bench"


def _owner_less_subscribe_call_sites() -> list[str]:
    """Return every ``....subscribe(...)`` call under ``src/`` that omits ``owner=``.

    Walks ``ast.Call`` only, so the 28 ``def subscribe`` declarations (the ``EventBus``
    Protocol, the deliverer, the activity bridge, and 25 colocated test doubles) are
    never visited and need no exclusion list.
    """
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            if name == "subscribe" and not any(kw.arg == "owner" for kw in node.keywords):
                offenders.append(f"{path.relative_to(_SRC_ROOT)}:{node.lineno}")
    return offenders


def test_every_subscribe_call_site_passes_owner() -> None:
    """Proves: STORY-118-AC-4

    08-J §2: a subscription with no owner is a programming error rejected at subscribe
    time by ``QtEventBusDeliverer``'s icontract precondition, so an owner-less call site
    is a live crash on whatever surface constructs it -- not a style nit.
    """
    # Arrange / Act
    offenders = _owner_less_subscribe_call_sites()

    # Assert
    assert offenders == [], (
        "subscribe() called without owner= (08-J §2 rejects this at subscribe time, "
        f"crashing the app): {offenders}"
    )
