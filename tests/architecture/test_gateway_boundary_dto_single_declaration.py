"""Architecture guard: each of the eleven gateway-boundary record types a
``ResultGateway``/``SettingsGateway`` signature mentions is declared exactly once, in
``adapters/ui_gateways/``, and the widget module that consumes it imports the identical
object rather than declaring its own nominally-distinct copy (STORY-113-AC-1, ADR-0017).

Source of truth: ``docs/stories/story-113-canonical-gateway-boundary-dtos.md``
Acceptance criteria (STORY-113-AC-1's table). Before STORY-113, ``JudgeAnalysisGenerationOutcome``/
``JudgeAnalysisGenerationResult`` were declared once in ``adapters/ui_gateways/protocols.py``
and once again in ``ui/results/protocols.py``, and ``Severity``/``ValidationFinding``/
``PreviewGroup``/``SettingsImportPreviewRow``/``SettingsImportPreview``/``SettingsImportResult``/
``ProviderImportPreviewRow``/``ProviderImportPreview``/``ProviderImportResult`` were declared
once in ``adapters/ui_gateways/protocols.py`` and once again in
``ui/settings_dialog/models.py``. Because a ``msgspec.Struct``/``StrEnum`` is a *nominal*
type (unlike a structurally-typed ``Protocol``), two field-identical declarations are two
distinct, incompatible runtime types -- field-equality alone (``==``) cannot detect this,
which is why this test asserts object identity (``is``), not equality. STORY-113 fixed the
duplication by making ``adapters/ui_gateways/`` the sole declaration point and having each
widget module import the same object.

This file lives under ``tests/architecture/`` -- not colocated under either module's own
``tests/`` directory -- because it is inherently a cross-module (``adapters`` + ``ui``)
check, following ``tests/architecture/test_result_gateway_protocol_mirrors.py``'s stated
precedent for the same reason: this module's own name (``tests.architecture.*``) falls
outside the ``ollama_llm_bench.adapters``/``ollama_llm_bench.ui`` namespaces the
import-linter "Module internals are private" contract matches, so importing both the
adapters-layer package root and the two widget modules together here is legal, unlike doing
so from production code or either module's own colocated test.
"""

import types

import pytest

from ollama_llm_bench.adapters import ui_gateways
from ollama_llm_bench.ui.results import protocols as results_protocols
from ollama_llm_bench.ui.settings_dialog import models as settings_models

_CASES: tuple[tuple[str, types.ModuleType], ...] = (
    ("JudgeAnalysisGenerationOutcome", results_protocols),
    ("JudgeAnalysisGenerationResult", results_protocols),
    ("Severity", settings_models),
    ("ValidationFinding", settings_models),
    ("PreviewGroup", settings_models),
    ("SettingsImportPreviewRow", settings_models),
    ("SettingsImportPreview", settings_models),
    ("SettingsImportResult", settings_models),
    ("ProviderImportPreviewRow", settings_models),
    ("ProviderImportPreview", settings_models),
    ("ProviderImportResult", settings_models),
)
_CASE_IDS = [name for name, _ in _CASES]


@pytest.mark.parametrize(("name", "widget_module"), _CASES, ids=_CASE_IDS)
def test_gateway_boundary_dto_is_declared_once(name: str, widget_module: types.ModuleType) -> None:
    """Proves: STORY-113-AC-1

    For each of the eleven gateway-boundary record types STORY-113-AC-1's table names,
    the symbol the widget module exposes (``ui.results.protocols`` for the two
    ``JudgeAnalysisGeneration*`` names, ``ui.settings_dialog.models`` for the other nine)
    and the symbol ``ollama_llm_bench.adapters.ui_gateways`` exposes are the identical
    object -- proven with ``is``, not ``==``, because field equality on a
    ``msgspec.Struct``/``StrEnum`` cannot distinguish "the same declaration, imported
    twice" from "two field-identical but nominally distinct declarations", and it is
    exactly the latter defect ADR-0017 eliminates. Table-driven (one row per record
    type, eleven rows total), because the case space is the fixed, enumerable set
    STORY-113-AC-1's own table specifies and totality over that set is the point of the
    criterion.
    """
    widget_symbol = getattr(widget_module, name)
    adapter_symbol = getattr(ui_gateways, name)

    assert widget_symbol is adapter_symbol
