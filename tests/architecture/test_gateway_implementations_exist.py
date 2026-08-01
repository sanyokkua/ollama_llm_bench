"""Architecture guard: every UI-declared gateway Protocol has exactly one production
implementation, reachable through exactly one ``make_*_gateway`` factory, in
``adapters/ui_gateways/`` (STORY-104-AC-1).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b (the seven gateway Protocols);
``docs/stories/story-104-ui-adapter-gateway-implementations.md`` Design constraints (why
this test resolves each widget module's own Protocol copy, never
``adapters/ui_gateways/protocols.py``'s deliberate mirror, and why "reachable through the
public surface" means reached via a ``make_*_gateway`` factory rather than an importable
class name -- the seven concrete classes are ``_``-prefixed and unexported).

This file lives under ``tests/architecture/`` rather than ``adapters/ui_gateways/tests/``
because it is a cross-module (``adapters`` + seven ``ui`` widget modules) structural check
-- the ``testing.md`` "colocated tests test only their own module" rule places a check
like this at the top level, mirroring ``test_result_gateway_protocol_mirrors.py``'s own
precedent for the same reason. This module's own name (``tests.architecture.*``) falls
outside the ``ollama_llm_bench.adapters``/``ollama_llm_bench.ui`` namespaces
import-linter's "Module internals are private" contract matches
(``root_packages = ["ollama_llm_bench"]``), so importing
``adapters.ui_gateways._internal`` here to enumerate its classes is legal, unlike doing so
from production code or a colocated module test.
"""

import importlib
import inspect
import pkgutil

import pytest

from ollama_llm_bench.adapters import ui_gateways
from ollama_llm_bench.adapters.ui_gateways import _internal as _ui_gateways_internal
from ollama_llm_bench.ui.main_window.protocols import MainWindowGateway
from ollama_llm_bench.ui.new_benchmark.protocols import NewBenchmarkGateway
from ollama_llm_bench.ui.progress.protocols import ProgressGateway
from ollama_llm_bench.ui.results.protocols import ResultGateway
from ollama_llm_bench.ui.resume_benchmark.protocols import ResumeGateway
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway
from ollama_llm_bench.ui.task_editor.protocols import TaskEditorGateway

_GATEWAY_PROTOCOLS: tuple[tuple[str, type], ...] = (
    ("MainWindowGateway", MainWindowGateway),
    ("NewBenchmarkGateway", NewBenchmarkGateway),
    ("ProgressGateway", ProgressGateway),
    ("ResultGateway", ResultGateway),
    ("ResumeGateway", ResumeGateway),
    ("SettingsGateway", SettingsGateway),
    ("TaskEditorGateway", TaskEditorGateway),
)
_GATEWAY_PROTOCOL_IDS = [name for name, _ in _GATEWAY_PROTOCOLS]


def _protocol_method_names(protocol: type) -> frozenset[str]:
    """Return the public method names a ``Protocol`` class declares directly."""
    return frozenset(
        name
        for name, member in vars(protocol).items()
        if not name.startswith("_") and callable(member)
    )


def _discover_internal_classes() -> dict[str, type]:
    """Import every non-``testing`` module under ``adapters/ui_gateways/_internal`` and
    return every class defined directly in one of those modules, keyed by its
    fully-qualified name."""
    discovered: dict[str, type] = {}
    prefix = f"{_ui_gateways_internal.__name__}."
    for module_info in pkgutil.walk_packages(_ui_gateways_internal.__path__, prefix=prefix):
        if module_info.name.rsplit(".", 1)[-1] == "testing":
            continue
        module = importlib.import_module(module_info.name)
        for _, member in inspect.getmembers(module, inspect.isclass):
            if member.__module__ == module.__name__:
                discovered[f"{module.__name__}.{member.__qualname__}"] = member
    return discovered


def _classes_satisfying(protocol: type, candidates: dict[str, type]) -> list[str]:
    """Return the qualified names of every candidate class structurally satisfying
    ``protocol`` -- every one of the Protocol's declared methods is a callable attribute
    of the candidate."""
    method_names = _protocol_method_names(protocol)
    return [
        qualname
        for qualname, candidate in candidates.items()
        if all(callable(getattr(candidate, name, None)) for name in method_names)
    ]


def _factories_returning(protocol_name: str) -> list[str]:
    """Return the names of every ``make_*_gateway`` factory in ``adapters.ui_gateways``'s
    public surface whose return-type annotation is named ``protocol_name`` -- proving the
    satisfying class is reachable through the module's public factory, not merely present
    somewhere under ``_internal``."""
    matches: list[str] = []
    for name in ui_gateways.__all__:
        if not (name.startswith("make_") and name.endswith("_gateway")):
            continue
        factory = getattr(ui_gateways, name)
        return_annotation = inspect.signature(factory).return_annotation
        if getattr(return_annotation, "__name__", None) == protocol_name:
            matches.append(name)
    return matches


@pytest.mark.parametrize(
    ("protocol_name", "protocol"), _GATEWAY_PROTOCOLS, ids=_GATEWAY_PROTOCOL_IDS
)
def test_every_ui_gateway_protocol_has_one_production_implementation(
    protocol_name: str, protocol: type
) -> None:
    """Proves: STORY-104-AC-1

    For every gateway Protocol declared in a ``ui/*`` widget module's own
    ``protocols.py`` (never ``adapters/ui_gateways/protocols.py``'s deliberate mirror --
    see this file's module docstring and STORY-104's Design constraints), exactly one
    production class defined under ``adapters/ui_gateways/_internal`` -- outside any
    ``testing.py`` module -- structurally satisfies it, and that class is reachable
    through exactly one ``make_*_gateway`` factory in the module's public surface.
    """
    candidates = _discover_internal_classes()

    satisfying = _classes_satisfying(protocol, candidates)
    assert satisfying, (
        f"{protocol_name}: no production class under adapters/ui_gateways/_internal satisfies it"
    )
    assert len(satisfying) == 1, (
        f"{protocol_name}: expected exactly one production implementation, found {satisfying}"
    )

    factories = _factories_returning(protocol_name)
    assert factories, f"{protocol_name}: no make_*_gateway factory returns it"
    assert len(factories) == 1, (
        f"{protocol_name}: expected exactly one make_*_gateway factory returning it, "
        f"found {factories}"
    )
